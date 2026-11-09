"""File imports: agent masterfile and survey exports (CSV or Excel). Column names are matched loosely."""

from __future__ import annotations

import io
import re
import secrets
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import Agent, Classification, IngestRun, Role, Survey, User
from app.services.email import send_email
from app.services.taxonomy import PEOPLE_CATEGORIES, PROCESS_CATEGORIES, is_vulnerable

ALIASES = {
    "employee_ref": ["employee_ref", "employee_id", "emp_id", "staff_id", "agent_id", "employee_number", "personnel_number", "pno"],
    "full_name": ["full_name", "agent_name", "name", "agent"],
    "email": ["email", "work_email", "agent_email", "email_address"],
    "tl_name": ["tl_name", "tl", "team_leader", "team_lead", "teamleader"],
    "om_name": ["om_name", "om", "operations_manager", "ops_manager", "manager"],
    "start_date": ["start_date", "capita_start_date", "hire_date", "employment_start"],
    "go_live_date": ["go_live_date", "gb_go_live_date", "live_date", "golive_date", "go_live"],
    "status": ["status", "employment_status"],
    "leave_date": ["leave_date", "termination_date", "exit_date", "leaving_date"],
    "leave_type": ["leave_type", "voluntary_involuntary", "exit_type"],
    "leave_reason": ["leave_reason", "exit_reason", "termination_reason", "reason"],
    "sid": ["sid", "survey_id", "response_id", "id"],
    "date": ["date", "survey_date", "response_date", "call_date"],
    "nps": ["nps", "nps_score", "likelihood_to_recommend", "ltr"],
    "osat": ["osat", "osat_score", "satisfaction", "csat"],
    "comment": ["comment", "verbatim", "customer_comment", "feedback", "comments"],
    "bucket": ["bucket", "people_process", "driver_type"],
    "category": ["category", "sub_category", "subcategory", "driver"],
}


def _norm(c: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")


def read_table(content: bytes, filename: str) -> pd.DataFrame:
    if filename.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content), dtype=str)
    else:
        df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
    df.columns = [_norm(c) for c in df.columns]
    rename = {}
    for canon, alts in ALIASES.items():
        for a in alts:
            if a in df.columns and canon not in rename.values():
                rename[a] = canon
                break
    df = df.rename(columns=rename)
    return df.fillna("")


def _date(v) -> date | None:
    v = str(v or "").strip()
    if not v:
        return None
    try:
        return pd.to_datetime(v, dayfirst=not re.match(r"^\d{4}-", v)).date()
    except (ValueError, TypeError):
        raise ValueError(f"bad date '{v}'") from None


def _int(v, lo: int, hi: int, field: str) -> int | None:
    v = str(v or "").strip()
    if v == "":
        return None
    try:
        n = int(float(v))
    except ValueError:
        raise ValueError(f"{field} '{v}' is not a number") from None
    if not lo <= n <= hi:
        raise ValueError(f"{field} {n} outside {lo}-{hi}")
    return n


def _require(df: pd.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}. Found: {', '.join(df.columns)}")


def import_agents(db: Session, org_id: int, df: pd.DataFrame, filename: str, user_id: int | None,
                  create_logins: bool = False) -> dict:
    _require(df, ["employee_ref", "full_name", "tl_name", "om_name"])
    existing = {a.employee_ref: a for a in db.scalars(select(Agent).where(Agent.org_id == org_id))}
    ok, errors, created_logins = 0, [], []
    for i, r in enumerate(df.to_dict("records"), start=2):
        try:
            ref = str(r["employee_ref"]).strip()
            if not ref or not str(r["full_name"]).strip():
                raise ValueError("employee_ref and full_name are required")
            a = existing.get(ref) or Agent(org_id=org_id, employee_ref=ref)
            a.full_name = str(r["full_name"]).strip()
            a.email = (str(r.get("email", "")).strip().lower() or None)
            a.tl_name, a.om_name = str(r["tl_name"]).strip(), str(r["om_name"]).strip()
            a.start_date, a.go_live_date = _date(r.get("start_date")), _date(r.get("go_live_date"))
            a.leave_date = _date(r.get("leave_date"))
            status = str(r.get("status", "")).strip().lower()
            a.status = "left" if (status in ("left", "leaver", "inactive", "terminated") or a.leave_date) else "active"
            lt = str(r.get("leave_type", "")).strip().lower()
            a.leave_type = "involuntary" if lt.startswith("inv") else "voluntary" if lt.startswith("vol") else None
            a.leave_reason = str(r.get("leave_reason", "")).strip() or None
            if a.id is None:
                db.add(a)
                existing[ref] = a
            ok += 1
        except ValueError as e:
            errors.append({"row": i, "error": str(e)})
    db.flush()
    if create_logins:
        created_logins = ensure_agent_logins(db, org_id)
    db.add(IngestRun(org_id=org_id, kind="agents", filename=filename, rows_ok=ok, rows_bad=len(errors),
                     errors=errors[:200], created_by=user_id))
    db.commit()
    return {"rows_ok": ok, "rows_bad": len(errors), "errors": errors[:50], "logins_created": created_logins}


def ensure_agent_logins(db: Session, org_id: int) -> list[dict]:
    """Create a login for every active agent with an email and no account yet. Sends an invite email."""
    have = {u.email for u in db.scalars(select(User))}
    out = []
    for a in db.scalars(select(Agent).where(Agent.org_id == org_id, Agent.status == "active", Agent.email.is_not(None))):
        if a.email in have:
            continue
        temp = secrets.token_urlsafe(8) + "A1"
        db.add(User(org_id=org_id, email=a.email, full_name=a.full_name, password_hash=hash_password(temp),
                    role=Role.agent, agent_id=a.id, must_change_password=True))
        send_email(a.email, "Your BuddyBud coach is ready",
                   f"Hi {a.full_name.split()[0]},\n\nSign in with this email and the temporary password: {temp}\n"
                   "You'll be asked to choose your own password the first time.")
        out.append({"email": a.email, "temp_password": temp})
        have.add(a.email)
    db.flush()
    return out


def import_surveys(db: Session, org_id: int, df: pd.DataFrame, filename: str, user_id: int | None) -> dict:
    _require(df, ["sid", "date"])
    if "employee_ref" not in df.columns and "email" not in df.columns:
        raise ValueError("Surveys need an employee_ref (or agent email) column to match agents.")
    agents = list(db.scalars(select(Agent).where(Agent.org_id == org_id)))
    by_ref = {a.employee_ref: a for a in agents}
    by_email = {a.email: a for a in agents if a.email}
    existing = {s.sid: s for s in db.scalars(select(Survey).where(Survey.org_id == org_id))}
    valid_cats = {"People": set(PEOPLE_CATEGORIES), "Process": set(PROCESS_CATEGORIES)}
    ok, errors = 0, []
    for i, r in enumerate(df.to_dict("records"), start=2):
        try:
            sid = str(r["sid"]).strip()
            if not sid:
                raise ValueError("sid is required")
            agent = by_ref.get(str(r.get("employee_ref", "")).strip()) or by_email.get(str(r.get("email", "")).strip().lower())
            if not agent:
                raise ValueError(f"no agent matches '{r.get('employee_ref') or r.get('email')}' — import the masterfile first")
            d = _date(r["date"])
            if not d:
                raise ValueError("date is required")
            s = existing.get(sid) or Survey(org_id=org_id, sid=sid)
            s.agent_id, s.date = agent.id, d
            s.nps, s.osat = _int(r.get("nps"), 0, 10, "nps"), _int(r.get("osat"), 1, 5, "osat")
            s.comment = str(r.get("comment", "")).strip()
            s.vulnerable = is_vulnerable(s.comment)
            if s.id is None:
                db.add(s)
                existing[sid] = s
            bucket = str(r.get("bucket", "")).strip().title()
            cat = str(r.get("category", "")).strip()
            if s.nps is not None and s.nps <= 6 and bucket in valid_cats:
                db.flush()
                c = s.classification or Classification(survey_id=s.id)
                c.bucket, c.category = bucket, cat or None
                c.confidence, c.source = 1.0, "import"
                c.needs_review = bool(cat) and cat not in valid_cats[bucket]
                s.classification = c
            ok += 1
        except ValueError as e:
            errors.append({"row": i, "error": str(e)})
    db.add(IngestRun(org_id=org_id, kind="surveys", filename=filename, rows_ok=ok, rows_bad=len(errors),
                     errors=errors[:200], created_by=user_id))
    db.commit()
    return {"rows_ok": ok, "rows_bad": len(errors), "errors": errors[:50]}
