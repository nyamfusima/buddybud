from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import MANAGERS, audit, get_visible_agent, require_roles, visible_agents_query
from app.api.routes.me import dashboard_bundle
from app.db.models import AttritionScore, User
from app.db.session import get_db
from app.services import metrics
from app.services.taxonomy import tenure_band

router = APIRouter(prefix="/team", tags=["team"])


def latest_risk(db: Session, org_id: int) -> dict[int, AttritionScore]:
    out: dict[int, AttritionScore] = {}
    for s in db.scalars(
        select(AttritionScore).where(AttritionScore.org_id == org_id).order_by(AttritionScore.scored_at)
    ):
        out[s.agent_id] = s
    return out


@router.get("/overview")
def overview(
    start: date | None = Query(None, alias="from"),
    end: date | None = Query(None, alias="to"),
    include_leavers: bool = False,
    user: User = Depends(require_roles(*MANAGERS)),
    db: Session = Depends(get_db),
):
    dmin, dmax = metrics.data_range(db, user.org_id)
    if not start or not end:
        start, end, _ = metrics.default_window(dmax)
    q = visible_agents_query(user)
    agents = list(db.scalars(q))
    if not include_leavers:
        agents = [a for a in agents if a.status == "active"]
    ids = [a.id for a in agents]
    df = metrics.surveys_df(db, user.org_id, agent_ids=ids, start=start, end=end)
    groups = {aid: g for aid, g in df.groupby("agent_id")} if not df.empty else {}
    risks = latest_risk(db, user.org_id)
    rows = []
    for a in agents:
        g = groups.get(a.id)
        n = 0 if g is None else len(g)
        dets = g[g["nps"].fillna(99) <= 6] if g is not None else None
        people = int((dets["bucket"] == "People").sum()) if dets is not None else 0
        process = int((dets["bucket"] == "Process").sum()) if dets is not None else 0
        top = None
        if dets is not None and dets["category"].notna().any():
            top = dets["category"].value_counts().index[0]
        tdays = metrics.tenure_days(a, dmax)
        r = risks.get(a.id)
        rows.append({
            "agent_id": a.id, "name": a.full_name, "tl": a.tl_name, "om": a.om_name, "status": a.status,
            "tenure": tenure_band(tdays), "tenure_days": tdays, "is_new": tdays is not None and tdays <= 90,
            "n": n, "nps": metrics.nps_df(g) if g is not None else None, "osat": metrics.osat_df(g) if g is not None else None,
            "detractors": 0 if dets is None else len(dets), "people": people, "process": process, "top_category": top,
            "risk": None if not r else {"risk": round(r.risk, 3), "band": r.band, "drivers": r.drivers},
        })
    rows.sort(key=lambda r: (r["nps"] is None, r["nps"] if r["nps"] is not None else 0))
    return {
        "from": start.isoformat(), "to": end.isoformat(), "date_min": dmin.isoformat(), "date_max": dmax.isoformat(),
        "scope": {"role": user.role.value, "name": user.scope_name},
        "totals": {"agents": len(agents), "n": int(len(df)), "nps": metrics.nps_df(df), "osat": metrics.osat_df(df)},
        "targets": {"nps": user.org.nps_target, "osat": user.org.osat_target},
        "agents": rows,
    }


@router.get("/agents/{agent_id}/dashboard")
def agent_dashboard(agent_id: int, user: User = Depends(require_roles(*MANAGERS)), db: Session = Depends(get_db)):
    agent = get_visible_agent(db, user, agent_id)
    audit(db, user, "view_agent_dashboard", agent_id=agent_id)
    db.commit()
    return dashboard_bundle(db, agent, user)
