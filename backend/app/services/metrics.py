"""Metric definitions. Mirrors the v2 dashboard's JavaScript (npsOf / osatOf / computeView) exactly,
so the numbers an agent sees in the UI and the numbers the AI coach quotes are always the same."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Agent, Classification, CoachingTemplate, Organization, Survey
from app.services.taxonomy import tenure_band


def _r1(x: float) -> float:
    """JS Math.round(x*10)/10 (round half up), not Python banker's rounding."""
    import math

    return math.floor(x * 10 + 0.5) / 10


def nps_of(values: Iterable[int | None]) -> float | None:
    v = [x for x in values if x is not None]
    if not v:
        return None
    p = sum(1 for x in v if x >= 9)
    d = sum(1 for x in v if x <= 6)
    return _r1((p - d) / len(v) * 100)


def osat_of(values: Iterable[int | None]) -> float | None:
    v = [x for x in values if x is not None]
    if not v:
        return None
    return _r1(sum(1 for x in v if x == 5) / len(v) * 100)


# ---------------------------------------------------------------- data access


def surveys_df(
    db: Session,
    org_id: int,
    agent_ids: list[int] | None = None,
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    q = (
        select(
            Survey.id,
            Survey.sid,
            Survey.agent_id,
            Survey.date,
            Survey.nps,
            Survey.osat,
            Survey.comment,
            Survey.vulnerable,
            Classification.bucket,
            Classification.category,
        )
        .outerjoin(Classification, Classification.survey_id == Survey.id)
        .where(Survey.org_id == org_id)
    )
    if agent_ids is not None:
        if not agent_ids:
            return pd.DataFrame(columns=["id", "sid", "agent_id", "date", "nps", "osat", "comment", "vulnerable", "bucket", "category"])
        q = q.where(Survey.agent_id.in_(agent_ids))
    if start:
        q = q.where(Survey.date >= start)
    if end:
        q = q.where(Survey.date <= end)
    rows = db.execute(q).all()
    df = pd.DataFrame(rows, columns=["id", "sid", "agent_id", "date", "nps", "osat", "comment", "vulnerable", "bucket", "category"])
    if not df.empty:
        df["nps"] = df["nps"].astype("Int64")
        df["osat"] = df["osat"].astype("Int64")
    return df


def _vals(series) -> list[int | None]:
    return [None if pd.isna(x) else int(x) for x in series]


def nps_df(df: pd.DataFrame) -> float | None:
    return nps_of(_vals(df["nps"])) if len(df) else None


def osat_df(df: pd.DataFrame) -> float | None:
    return osat_of(_vals(df["osat"])) if len(df) else None


def data_range(db: Session, org_id: int) -> tuple[date, date]:
    lo, hi = db.execute(select(func.min(Survey.date), func.max(Survey.date)).where(Survey.org_id == org_id)).one()
    today = date.today()
    return (lo or today, hi or today)


def tenure_days(agent: Agent, as_of: date) -> int | None:
    anchor = agent.go_live_date or agent.start_date
    if not anchor:
        return None
    end = agent.leave_date if agent.leave_date and agent.leave_date < as_of else as_of
    return max(0, (end - anchor).days)


def default_window(dmax: date) -> tuple[date, date, bool]:
    """Month-to-date once we're past day 7, otherwise a rolling 7 days (same rule as v2)."""
    use_mtd = dmax.day > 7
    start = dmax.replace(day=1) if use_mtd else dmax - timedelta(days=6)
    return start, dmax, use_mtd


# ---------------------------------------------------------------- shared / leaderboard


def display_name(full: str) -> str:
    parts = full.split()
    if not parts:
        return full
    first = parts[0].capitalize()
    return f"{first} {parts[-1][0].upper()}." if len(parts) > 1 else first


def leaderboard(db: Session, org: Organization, dmax: date | None = None) -> dict:
    dmin_all, dmax_all = data_range(db, org.id)
    dmax = dmax or dmax_all
    start, end, use_mtd = default_window(dmax)
    df = surveys_df(db, org.id, start=start, end=end)
    active = {a.id: a for a in db.scalars(select(Agent).where(Agent.org_id == org.id, Agent.status == "active"))}
    entries = []
    if not df.empty:
        for agent_id, g in df.groupby("agent_id"):
            if agent_id not in active or len(g) < org.leaderboard_min_n:
                continue
            entries.append(
                {"name": active[agent_id].full_name, "display": display_name(active[agent_id].full_name),
                 "nps": nps_df(g), "osat": osat_df(g), "n": int(len(g))}
            )
    entries.sort(key=lambda e: (-(e["nps"] or -999), -(e["osat"] or -999), -e["n"]))
    entries = entries[: org.leaderboard_size]
    for i, e in enumerate(entries, 1):
        e["rank"] = i
        e.pop("name")
    return {"window_from": start.isoformat(), "window_to": end.isoformat(), "use_mtd": use_mtd,
            "min_n": org.leaderboard_min_n, "entries": entries}


def shared_block(db: Session, org: Organization) -> dict:
    dmin, dmax = data_range(db, org.id)
    df = surveys_df(db, org.id)
    return {
        "date_min": dmin.isoformat(),
        "date_max": dmax.isoformat(),
        "overall_nps": nps_df(df),
        "overall_osat": osat_df(df),
        "nps_target": org.nps_target,
        "osat_target": org.osat_target,
        "thumb_ratio": org.thumb_ratio,
        "client_label": org.client_label,
        "org_name": org.name,
    }


def coaching_kb(db: Session, org_id: int) -> dict:
    kb: dict = {"people": {}, "process": {}, "default_process": [], "general_process_closer": ""}
    rows = db.scalars(
        select(CoachingTemplate).where(CoachingTemplate.org_id == org_id).order_by(CoachingTemplate.category, CoachingTemplate.variant)
    ).all()
    for t in rows:
        if t.bucket == "People":
            kb["people"].setdefault(t.category, []).append(t.payload)
        elif t.bucket == "Process":
            kb["process"].setdefault(t.category, []).append(t.payload)
        elif t.bucket == "DefaultProcess":
            kb["default_process"].append(t.payload)
        elif t.bucket == "Closer":
            kb["general_process_closer"] = t.payload.get("text", "")
    return kb


# ---------------------------------------------------------------- per-agent payload (the v2 "agent data" object)

_POSITIVE = re.compile(r"brilliant|excellent|amazing|fantastic|helpful|patient|friendly|polite|lovely|great|thank|sorted|quick|professional|kind", re.I)


def win_score(nps: int, comment: str) -> float:
    return (nps - 8) * 2 + min(len(comment), 240) / 80 + len(_POSITIVE.findall(comment)) * 1.5


def agent_payload(db: Session, agent: Agent, org: Organization) -> dict:
    dmin, dmax = data_range(db, org.id)
    df = surveys_df(db, org.id, agent_ids=[agent.id])
    rows, dets, wins, vuln = [], [], [], []
    for r in df.itertuples(index=False):
        nps = None if pd.isna(r.nps) else int(r.nps)
        osat = None if pd.isna(r.osat) else int(r.osat)
        d = r.date.isoformat()
        rows.append({"date": d, "nps": nps, "osat": osat})
        comment = r.comment or ""
        if nps is not None and nps <= 6:
            dets.append({"sid": r.sid, "date": d, "nps": nps, "bucket": r.bucket if isinstance(r.bucket, str) else None,
                         "category": r.category if isinstance(r.category, str) else None, "comment": comment})
        if nps is not None and nps >= 9 and len(comment.strip()) >= 20:
            wins.append({"date": d, "nps": nps, "comment": comment, "score": round(win_score(nps, comment), 2)})
        if r.vulnerable:
            vuln.append({"sid": r.sid, "date": d, "nps": nps, "comment": comment})

    # OM-group average over the full period (v2 labels this "your <OM> team average")
    group_ids = list(db.scalars(select(Agent.id).where(Agent.org_id == org.id, Agent.om_name == agent.om_name)))
    team_nps = nps_df(surveys_df(db, org.id, agent_ids=group_ids))

    # typical complete-month volume
    hist_avg = None
    if not df.empty:
        months = Counter(r.date.strftime("%Y-%m") for r in df.itertuples(index=False))
        current = dmax.strftime("%Y-%m")
        complete = [n for m, n in months.items() if m != current]
        hist_avg = round(sum(complete) / len(complete), 1) if complete else None

    return {
        "agent_id": agent.id,
        "agent": agent.full_name,
        "tl": agent.tl_name,
        "om": agent.om_name,
        "tenure": tenure_band(tenure_days(agent, dmax)),
        "all_rows": rows,
        "detractors": dets,
        "win_candidates": wins,
        "vuln": vuln,
        "team_nps": team_nps,
        "hist_avg_monthly_n": hist_avg,
        "is_bottom_quartile": is_bottom_quartile(db, org, agent.id, dmax),
    }


def is_bottom_quartile(db: Session, org: Organization, agent_id: int, dmax: date) -> bool:
    df = surveys_df(db, org.id, start=dmax - timedelta(days=89), end=dmax)
    if df.empty:
        return False
    scores = {}
    for aid, g in df.groupby("agent_id"):
        if len(g) >= org.leaderboard_min_n:
            scores[aid] = nps_df(g)
    if agent_id not in scores or len(scores) < 4:
        return False
    cutoff = pd.Series(list(scores.values())).quantile(0.25)
    return bool(scores[agent_id] <= cutoff)


# ---------------------------------------------------------------- range summary (Python port of computeView's numbers)


def summarize(payload: dict, start: str, end: str) -> dict:
    rows = [r for r in payload["all_rows"] if start <= r["date"] <= end]
    dets = [d for d in payload["detractors"] if start <= d["date"] <= end]
    nps = nps_of(r["nps"] for r in rows)
    osat = osat_of(r["osat"] for r in rows)
    prom = sum(1 for r in rows if r["nps"] is not None and r["nps"] >= 9)
    detr = sum(1 for r in rows if r["nps"] is not None and r["nps"] <= 6)
    pas = sum(1 for r in rows if r["nps"] is not None and 7 <= r["nps"] <= 8)
    people = Counter(d["category"] for d in dets if d["bucket"] == "People")
    process = Counter(d["category"] for d in dets if d["bucket"] == "Process")
    tot = sum(people.values()) + sum(process.values())
    cats = [
        {"bucket": b, "category": c, "count": n, "pct": _r1(n / tot * 100) if tot else 0}
        for b, counter in (("People", people), ("Process", process))
        for c, n in counter.items()
    ]
    cats.sort(key=lambda c: -c["count"])
    return {
        "from": start, "to": end, "surveys": len(rows), "nps": nps, "osat": osat,
        "promoters": prom, "passives": pas, "detractors": detr,
        "promoter_to_detractor_ratio": _r1(prom / detr) if detr else None,
        "people_cases": sum(people.values()), "process_cases": sum(process.values()),
        "categories": cats,
    }


def monthly_trend(payload: dict) -> list[dict]:
    by: dict[str, list] = {}
    for r in payload["all_rows"]:
        by.setdefault(r["date"][:7], []).append(r)
    return [{"month": m, "surveys": len(v), "nps": nps_of(x["nps"] for x in v), "osat": osat_of(x["osat"] for x in v)}
            for m, v in sorted(by.items())]
