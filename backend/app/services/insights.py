"""Manager-side analytics from the annual diagnostic: tenure curve, TL outliers (tenure-adjusted),
new-team watchlist, hiring-wave forecaster and the client-escalation view."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

import pandas as pd

from app.db.models import Agent
from app.services.metrics import nps_df, nps_of, osat_df
from app.services.taxonomy import TENURE_BANDS, process_owner, tenure_band


def _add_tenure(df: pd.DataFrame, agents: dict[int, Agent]) -> pd.DataFrame:
    def band(row):
        a = agents.get(row.agent_id)
        anchor = a and (a.go_live_date or a.start_date)
        return tenure_band((row.date - anchor).days) if anchor else "unknown"

    df = df.copy()
    df["band"] = [band(r) for r in df.itertuples(index=False)] if len(df) else []
    return df


def tenure_curve(df: pd.DataFrame, agents: dict[int, Agent]) -> list[dict]:
    if df.empty:
        return []
    d = _add_tenure(df, agents)
    out = []
    for b in TENURE_BANDS:
        g = d[d["band"] == b]
        if len(g):
            det_rate = round(float((g["nps"].fillna(99) <= 6).mean()) * 100, 1)
            out.append({"band": b, "n": int(len(g)), "nps": nps_df(g), "osat": osat_df(g), "detractor_rate": det_rate})
    return out


def _band_nps(curve: list[dict]) -> dict[str, float]:
    return {c["band"]: c["nps"] for c in curve if c["nps"] is not None}


def tl_outliers(df: pd.DataFrame, agents: dict[int, Agent], org_curve: list[dict], dmax: date) -> list[dict]:
    """Actual NPS vs what the team's tenure mix alone would predict. The residual is the management signal."""
    if df.empty:
        return []
    band_nps = _band_nps(org_curve)
    d = _add_tenure(df, agents)
    d["tl"] = [agents[a].tl_name if a in agents else "" for a in d["agent_id"]]
    rows = []
    for tl, g in d.groupby("tl"):
        if not tl:
            continue
        mix = g["band"].value_counts(normalize=True)
        expected = sum(share * band_nps.get(b, 0) for b, share in mix.items() if b in band_nps)
        actual = nps_df(g)
        new_share = float(g["band"].isin(TENURE_BANDS[:2]).mean())
        team_agents = [a for a in agents.values() if a.tl_name == tl and a.status == "active"]
        dets = g[g["nps"].fillna(99) <= 6]
        people_share = round(float((dets["bucket"] == "People").mean()) * 100, 1) if len(dets) else None
        top = dets["category"].value_counts().index[0] if dets["category"].notna().any() else None
        rows.append({
            "tl": tl, "om": team_agents[0].om_name if team_agents else "", "agents": len(team_agents), "n": int(len(g)),
            "nps": actual, "osat": osat_df(g), "expected_nps": round(expected, 1),
            "residual": None if actual is None else round(actual - expected, 1),
            "new_starter_share": round(new_share * 100, 1), "people_share": people_share, "top_category": top,
        })
    res = [r["residual"] for r in rows if r["residual"] is not None]
    med = float(pd.Series(res).median()) if res else 0.0
    for r in rows:
        r["flag"] = (
            "below" if r["residual"] is not None and r["residual"] <= med - 5
            else "above" if r["residual"] is not None and r["residual"] >= med + 5 else "in_line"
        )
    rows.sort(key=lambda r: (r["residual"] is None, r["residual"] if r["residual"] is not None else 0))
    return rows


def new_team_watchlist(agents: dict[int, Agent], df_recent: pd.DataFrame, as_of: date) -> list[dict]:
    teams: dict[str, list[Agent]] = defaultdict(list)
    for a in agents.values():
        if a.status == "active" and a.tl_name:
            teams[a.tl_name].append(a)
    out = []
    for tl, members in teams.items():
        lives = [a.go_live_date for a in members if a.go_live_date]
        if not lives:
            continue
        new = [d for d in lives if (as_of - d).days <= 90]
        share = len(new) / len(members)
        if share < 0.5:
            continue
        median_live = sorted(lives)[len(lives) // 2]
        g = df_recent[df_recent["agent_id"].isin([m.id for m in members])] if not df_recent.empty else df_recent
        out.append({
            "tl": tl, "om": members[0].om_name, "agents": len(members), "new_share": round(share * 100, 1),
            "median_go_live": median_live.isoformat(),
            "leaves_trough_on": (median_live + timedelta(days=90)).isoformat(),
            "days_left_in_trough": max(0, 90 - (as_of - median_live).days),
            "nps_30d": nps_df(g) if len(g) else None, "n_30d": int(len(g)),
        })
    out.sort(key=lambda r: -r["new_share"])
    return out


# ------------------------------------------------------------------ hiring-wave forecaster


def _month_starts(start: date, months: int) -> list[date]:
    out, y, m = [], start.year, start.month
    for _ in range(months):
        out.append(date(y, m, 1))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def monthly_hazards(agents: list[Agent], as_of: date) -> dict[str, float]:
    """P(leaving in a given month) for each tenure band, from historical exposure."""
    exposure: dict[str, float] = defaultdict(float)
    exits: dict[str, int] = defaultdict(int)
    for a in agents:
        anchor = a.go_live_date or a.start_date
        if not anchor:
            continue
        end = a.leave_date if (a.status == "left" and a.leave_date) else as_of
        days = (end - anchor).days
        if days < 0:
            continue
        # walk the agent's life in 30-day steps
        t = 0
        while t <= days:
            exposure[tenure_band(t)] += min(30, days - t + 1) / 30
            t += 30
        if a.status == "left" and a.leave_date:
            exits[tenure_band(days)] += 1
    return {b: min(0.5, exits[b] / exposure[b]) if exposure[b] else 0.03 for b in TENURE_BANDS}


def hiring_wave_forecast(
    agents: list[Agent], df: pd.DataFrame, agent_map: dict[int, Agent], org_curve: list[dict],
    as_of: date, planned: list[dict], months: int = 6,
) -> dict:
    band_nps = _band_nps(org_curve)
    hazards = monthly_hazards(agents, as_of)
    month_list = _month_starts(as_of.replace(day=1) + timedelta(days=32), months)

    def project(cohorts: list[tuple[date, float]]) -> list[dict]:
        rows = []
        for m in month_list:
            mid = m + timedelta(days=14)
            w_band: dict[str, float] = defaultdict(float)
            for live, weight in cohorts:
                if live > mid:
                    continue
                # survival from as_of (or go-live, if later) to mid-month
                surv, t = weight, max(0, (as_of - live).days)
                end_t = (mid - live).days
                while t < end_t:
                    surv *= 1 - hazards[tenure_band(t)]
                    t += 30
                w_band[tenure_band(end_t)] += surv
            tot = sum(w_band.values())
            exp = sum(w * band_nps.get(b, 0) for b, w in w_band.items()) / tot if tot else None
            new_share = (w_band["0-30 days"] + w_band["31-90 days"]) / tot if tot else 0
            rows.append({"month": m.strftime("%Y-%m"), "expected_nps": None if exp is None else round(exp, 1),
                         "headcount": round(tot, 1), "new_starter_share": round(new_share * 100, 1)})
        return rows

    base = [(a.go_live_date or a.start_date, 1.0) for a in agents if a.status == "active" and (a.go_live_date or a.start_date)]
    plan = base + [(date.fromisoformat(p["go_live"]), float(p["count"])) for p in planned if p.get("count")]

    # back-test: actual monthly NPS vs what tenure mix alone predicted
    history = []
    if not df.empty:
        d = _add_tenure(df, agent_map)
        d["month"] = [x.strftime("%Y-%m") for x in d["date"]]
        for mth, g in d.groupby("month"):
            mix = g["band"].value_counts(normalize=True)
            exp = sum(s * band_nps.get(b, 0) for b, s in mix.items() if b in band_nps)
            history.append({"month": mth, "actual_nps": nps_df(g), "expected_nps": round(exp, 1), "n": int(len(g)),
                            "new_starter_share": round(float(g["band"].isin(TENURE_BANDS[:2]).mean()) * 100, 1)})
    return {
        "tenure_curve": org_curve, "monthly_hazards": {k: round(v, 3) for k, v in hazards.items()},
        "history": history, "baseline": project(base), "with_plan": project(plan), "planned": planned,
    }


# ------------------------------------------------------------------ client escalation tracker


def escalations(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"months": [], "categories": [], "owner_totals": {}}
    total_by_month = df.assign(month=[x.strftime("%Y-%m") for x in df["date"]]).groupby("month").size()
    dets = df[(df["nps"].fillna(99) <= 6) & (df["bucket"] == "Process")].copy()
    dets["owner"] = [process_owner(c) for c in dets["category"]]
    dets["month"] = [x.strftime("%Y-%m") for x in dets["date"]]
    months = []
    for m, n_all in total_by_month.items():
        g = dets[dets["month"] == m]
        months.append({"month": m, "surveys": int(n_all), **{o: int((g["owner"] == o).sum()) for o in ("client", "management", "agent")}})
    total = len(df)
    cats = []
    for (cat, owner), g in dets.groupby(["category", "owner"]):
        cats.append({"category": cat, "owner": owner, "count": int(len(g)),
                     # NPS points recovered if these detractors had been passives instead
                     "nps_impact_pts": round(len(g) / total * 100, 2)})
    cats.sort(key=lambda c: -c["count"])
    owner_totals = dets["owner"].value_counts().to_dict()
    return {"months": months, "categories": cats, "owner_totals": {k: int(v) for k, v in owner_totals.items()},
            "process_total": int(len(dets)), "nps_overall": nps_of([None if pd.isna(x) else int(x) for x in df["nps"]])}
