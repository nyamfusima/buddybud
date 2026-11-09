from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import MANAGERS, require_roles, visible_agents_query
from app.api.routes.team import latest_risk
from app.db.models import Agent, Role, User
from app.db.session import get_db
from app.services import insights, metrics

router = APIRouter(prefix="/insights", tags=["insights"])


def _scope(db: Session, user: User):
    agents = list(db.scalars(visible_agents_query(user)))
    return agents, {a.id: a for a in agents}


def _org_curve(db: Session, user: User):
    """Tenure curve across the whole organisation: the baseline every team is compared against."""
    all_agents = {a.id: a for a in db.scalars(select(Agent).where(Agent.org_id == user.org_id))}
    return insights.tenure_curve(metrics.surveys_df(db, user.org_id), all_agents)


@router.get("/summary")
def summary(
    start: date | None = Query(None, alias="from"),
    end: date | None = Query(None, alias="to"),
    user: User = Depends(require_roles(*MANAGERS)),
    db: Session = Depends(get_db),
):
    dmin, dmax = metrics.data_range(db, user.org_id)
    start, end = start or dmin, end or dmax
    agents, amap = _scope(db, user)
    df = metrics.surveys_df(db, user.org_id, agent_ids=list(amap), start=start, end=end)
    curve = _org_curve(db, user)
    recent = metrics.surveys_df(db, user.org_id, agent_ids=list(amap), start=dmax - timedelta(days=29), end=dmax)
    risks = latest_risk(db, user.org_id)
    at_risk = sorted(
        [{"agent_id": a.id, "name": a.full_name, "tl": a.tl_name, "risk": round(risks[a.id].risk, 3), "band": risks[a.id].band,
          "drivers": risks[a.id].drivers, "method": risks[a.id].method}
         for a in agents if a.id in risks and a.status == "active"],
        key=lambda r: -r["risk"],
    )
    leavers = [a for a in agents if a.status == "left"]
    return {
        "from": start.isoformat(), "to": end.isoformat(), "date_min": dmin.isoformat(), "date_max": dmax.isoformat(),
        "headline": {"n": int(len(df)), "nps": metrics.nps_df(df), "osat": metrics.osat_df(df),
                     "active_agents": sum(1 for a in agents if a.status == "active"), "leavers": len(leavers),
                     "involuntary_share": round(sum(1 for a in leavers if a.leave_type == "involuntary") / len(leavers) * 100, 1) if leavers else None,
                     "nps_target": user.org.nps_target},
        "tenure_curve": curve,
        "tenure_curve_scope": insights.tenure_curve(df, amap),
        "tl_outliers": insights.tl_outliers(df, amap, curve, dmax),
        "new_teams": insights.new_team_watchlist(amap, recent, dmax),
        "attrition_risk": at_risk[:40],
        "escalations": insights.escalations(df),
    }


class Planned(BaseModel):
    go_live: date
    count: int = Field(ge=0, le=1000)


class ForecastIn(BaseModel):
    planned: list[Planned] = []
    months: int = Field(6, ge=1, le=18)


@router.post("/hiring-forecast")
def hiring_forecast(body: ForecastIn, user: User = Depends(require_roles(Role.om, Role.admin)), db: Session = Depends(get_db)):
    # Forecasting is a site-level question, so it always uses the whole organisation's roster.
    all_agents = list(db.scalars(select(Agent).where(Agent.org_id == user.org_id)))
    amap = {a.id: a for a in all_agents}
    df = metrics.surveys_df(db, user.org_id)
    _, dmax = metrics.data_range(db, user.org_id)
    curve = insights.tenure_curve(df, amap)
    return insights.hiring_wave_forecast(all_agents, df, amap, curve, dmax,
                                         [{"go_live": p.go_live.isoformat(), "count": p.count} for p in body.planned],
                                         body.months)
