import secrets

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import audit, require_roles
from app.api.routes.auth import user_out
from app.core.llm import provider_info
from app.core.security import hash_password
from app.db.models import Agent, Classification, IngestRun, Role, Survey, User
from app.db.session import SessionLocal, get_db
from app.ml import attrition
from app.pipelines import classify, ingest
from app.services.email import send_email
from app.services.taxonomy import PEOPLE_CATEGORIES, PROCESS_CATEGORIES

router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = require_roles(Role.admin)
MAX_UPLOAD = 25 * 1024 * 1024


async def _read(file: UploadFile) -> bytes:
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File is larger than 25 MB.")
    return data


@router.get("/status")
def status(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    org = user.org
    count = lambda q: db.scalar(q) or 0  # noqa: E731
    return {
        "org": {"name": org.name, "client_label": org.client_label, "nps_target": org.nps_target, "osat_target": org.osat_target,
                "thumb_ratio": org.thumb_ratio, "leaderboard_min_n": org.leaderboard_min_n, "leaderboard_size": org.leaderboard_size,
                "support_contact": org.support_contact, "crisis_resources": org.crisis_resources},
        "counts": {
            "agents": count(select(func.count()).select_from(Agent).where(Agent.org_id == org.id)),
            "active_agents": count(select(func.count()).select_from(Agent).where(Agent.org_id == org.id, Agent.status == "active")),
            "surveys": count(select(func.count()).select_from(Survey).where(Survey.org_id == org.id)),
            "detractors": count(select(func.count()).select_from(Survey).where(Survey.org_id == org.id, Survey.nps <= 6)),
            "unclassified": count(select(func.count()).select_from(Survey).outerjoin(Classification)
                                  .where(Survey.org_id == org.id, Survey.nps <= 6, Classification.survey_id.is_(None))),
            "needs_review": count(select(func.count()).select_from(Classification).join(Survey)
                                  .where(Survey.org_id == org.id, Classification.needs_review.is_(True))),
            "users": count(select(func.count()).select_from(User).where(User.org_id == org.id)),
        },
        "llm": provider_info(),
        "runs": [{"id": r.id, "kind": r.kind, "filename": r.filename, "rows_ok": r.rows_ok, "rows_bad": r.rows_bad,
                  "errors": r.errors[:10], "at": r.created_at.isoformat() if r.created_at else None}
                 for r in db.scalars(select(IngestRun).where(IngestRun.org_id == org.id).order_by(IngestRun.id.desc()).limit(10))],
    }


class OrgPatch(BaseModel):
    name: str | None = None
    client_label: str | None = None
    nps_target: float | None = Field(None, ge=-100, le=100)
    osat_target: float | None = Field(None, ge=0, le=100)
    thumb_ratio: float | None = Field(None, gt=0, le=20)
    leaderboard_min_n: int | None = Field(None, ge=1, le=100)
    leaderboard_size: int | None = Field(None, ge=1, le=50)
    support_contact: str | None = None
    crisis_resources: str | None = None


@router.patch("/org")
def patch_org(body: OrgPatch, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    org = user.org
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(org, k, v)
    audit(db, user, "org_updated", **body.model_dump(exclude_none=True))
    db.commit()
    return {"ok": True}


@router.post("/import/agents")
async def import_agents(file: UploadFile = File(...), create_logins: bool = Form(False), user: User = Depends(admin_only)):
    data, name, uid, oid = await _read(file), file.filename or "upload", user.id, user.org_id

    def run():
        with SessionLocal() as db:
            df = ingest.read_table(data, name)
            return ingest.import_agents(db, oid, df, name, uid, create_logins)

    try:
        return await run_in_threadpool(run)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/import/surveys")
async def import_surveys(file: UploadFile = File(...), auto_classify: bool = Form(True), user: User = Depends(admin_only)):
    data, name, uid, oid = await _read(file), file.filename or "upload", user.id, user.org_id

    def run():
        with SessionLocal() as db:
            df = ingest.read_table(data, name)
            res = ingest.import_surveys(db, oid, df, name, uid)
            if auto_classify:
                res["classification"] = classify.classify_pending(db, oid)
            return res

    try:
        return await run_in_threadpool(run)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/classify")
async def run_classifier(reclassify_keyword: bool = False, user: User = Depends(admin_only)):
    oid = user.org_id

    def run():
        with SessionLocal() as db:
            return classify.classify_pending(db, oid, reclassify_keyword=reclassify_keyword)

    return await run_in_threadpool(run)


@router.get("/review")
def review_queue(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Survey, Classification).join(Classification).where(Survey.org_id == user.org_id, Classification.needs_review.is_(True))
        .order_by(Classification.confidence).limit(100)
    ).all()
    return {"categories": {"People": PEOPLE_CATEGORIES, "Process": PROCESS_CATEGORIES},
            "items": [{"survey_id": s.id, "sid": s.sid, "date": s.date.isoformat(), "nps": s.nps, "comment": s.comment,
                       "bucket": c.bucket, "category": c.category, "confidence": round(c.confidence, 2), "source": c.source}
                      for s, c in rows]}


class ReviewIn(BaseModel):
    bucket: str
    category: str | None = None


@router.post("/review/{survey_id}")
def resolve_review(survey_id: int, body: ReviewIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    s = db.get(Survey, survey_id)
    if not s or s.org_id != user.org_id or not s.classification:
        raise HTTPException(404, "Not found.")
    if body.bucket not in ("People", "Process", "None"):
        raise HTTPException(400, "Bucket must be People, Process or None.")
    valid = PEOPLE_CATEGORIES if body.bucket == "People" else PROCESS_CATEGORIES if body.bucket == "Process" else [None]
    if body.category not in valid and not (body.bucket == "None"):
        raise HTTPException(400, "Unknown category for that bucket.")
    c = s.classification
    c.bucket, c.category, c.confidence, c.source, c.needs_review = body.bucket, body.category, 1.0, "manual", False
    audit(db, user, "classification_reviewed", survey_id=survey_id, bucket=body.bucket, category=body.category)
    db.commit()
    return {"ok": True}


@router.post("/models/attrition")
async def run_attrition(user: User = Depends(admin_only)):
    oid = user.org_id

    def run():
        with SessionLocal() as db:
            t = attrition.train(db, oid)
            s = attrition.score(db, oid)
            return {"train": t, "score": s}

    return await run_in_threadpool(run)


# ---------------------------------------------------------------- users


@router.get("/users")
def list_users(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    users = db.scalars(select(User).where(User.org_id == user.org_id).order_by(User.role, User.full_name)).all()
    return [{**user_out(u).model_dump(), "is_active": u.is_active,
             "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None} for u in users]


class NewUser(BaseModel):
    email: EmailStr
    full_name: str
    role: Role
    scope_name: str | None = None
    agent_employee_ref: str | None = None


@router.post("/users")
def create_user(body: NewUser, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    if db.scalars(select(User).where(func.lower(User.email) == body.email.lower())).first():
        raise HTTPException(409, "A user with that email already exists.")
    if body.role in (Role.tl, Role.om) and not body.scope_name:
        raise HTTPException(400, "Team leaders and OMs need a scope name (the TL or OM name as it appears in the data).")
    agent_id = None
    if body.role == Role.agent:
        q = select(Agent).where(Agent.org_id == user.org_id)
        q = q.where(Agent.employee_ref == body.agent_employee_ref) if body.agent_employee_ref else q.where(func.lower(Agent.email) == body.email.lower())
        agent = db.scalars(q).first()
        if not agent:
            raise HTTPException(400, "No agent record matches — give the employee ref, or import the masterfile with emails first.")
        agent_id = agent.id
    temp = secrets.token_urlsafe(8) + "A1"
    u = User(org_id=user.org_id, email=body.email.lower(), full_name=body.full_name, role=body.role, scope_name=body.scope_name,
             agent_id=agent_id, password_hash=hash_password(temp), must_change_password=True)
    db.add(u)
    audit(db, user, "user_created", email=u.email, role=body.role.value)
    db.commit()
    send_email(u.email, "Your BuddyBud account", f"Hi {body.full_name.split()[0]},\n\nSign in with {u.email} and the temporary "
               f"password {temp}. You'll choose your own password the first time you sign in.")
    return {"id": u.id, "temp_password": temp}


class UserPatch(BaseModel):
    is_active: bool | None = None
    role: Role | None = None
    scope_name: str | None = None
    reset_password: bool = False


@router.patch("/users/{user_id}")
def patch_user(user_id: int, body: UserPatch, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u or u.org_id != user.org_id:
        raise HTTPException(404, "Not found.")
    if u.id == user.id and body.is_active is False:
        raise HTTPException(400, "You can't deactivate yourself.")
    out = {}
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.role is not None:
        u.role = body.role
    if body.scope_name is not None:
        u.scope_name = body.scope_name or None
    if body.reset_password:
        temp = secrets.token_urlsafe(8) + "A1"
        u.password_hash, u.must_change_password = hash_password(temp), True
        out["temp_password"] = temp
    audit(db, user, "user_updated", target=u.id, **body.model_dump(exclude_none=True))
    db.commit()
    return {"ok": True, **out}


@router.post("/users/agent-logins")
def bulk_agent_logins(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    created = ingest.ensure_agent_logins(db, user.org_id)
    audit(db, user, "agent_logins_created", count=len(created))
    db.commit()
    return {"created": created}
