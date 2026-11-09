"""Attrition early-warning model.

Training data = monthly snapshots of every agent's recent performance; label = left within the next 60 days.
Logistic regression keeps it explainable: each score comes with the features pushing it up.
Use the output as a prompt for a supportive TL conversation, never as grounds for action against someone.

CLI:  python -m app.ml.attrition train   |   python -m app.ml.attrition score
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Agent, AttritionScore, Organization
from app.services.metrics import data_range, nps_of, surveys_df

FEATURES = [
    "tenure_days", "nps_30d", "nps_90d", "nps_trend", "det_rate_90d", "surveys_30d",
    "people_share_90d", "unaccommodating_90d", "team_new_share",
]
LABELS = {
    "tenure_days": "short tenure", "nps_30d": "low recent NPS", "nps_90d": "low 90-day NPS",
    "nps_trend": "NPS falling", "det_rate_90d": "high detractor rate", "surveys_30d": "low call volume",
    "people_share_90d": "mostly People-side detractors", "unaccommodating_90d": "Unaccommodating feedback",
    "team_new_share": "team mostly new starters",
}
HORIZON_DAYS = 60


def _nps(series) -> float:
    v = nps_of([None if pd.isna(x) else int(x) for x in series])
    return float(v) if v is not None else np.nan


def features_for(agent: Agent, agent_df: pd.DataFrame, as_of: date, team_new_share: float) -> dict:
    """agent_df = this agent's surveys only."""
    g = agent_df[agent_df["date"] <= as_of] if len(agent_df) else agent_df
    g90 = g[g["date"] > as_of - timedelta(days=90)]
    g30 = g[g["date"] > as_of - timedelta(days=30)]
    g_prev = g[(g["date"] > as_of - timedelta(days=60)) & (g["date"] <= as_of - timedelta(days=30))]
    dets = g90[g90["nps"].fillna(99) <= 6]
    anchor = agent.go_live_date or agent.start_date
    return {
        "tenure_days": (as_of - anchor).days if anchor else np.nan,
        "nps_30d": _nps(g30["nps"]),
        "nps_90d": _nps(g90["nps"]),
        "nps_trend": _nps(g30["nps"]) - _nps(g_prev["nps"]),
        "det_rate_90d": float((g90["nps"].fillna(99) <= 6).mean()) if len(g90) else np.nan,
        "surveys_30d": float(len(g30)),
        "people_share_90d": float((dets["bucket"] == "People").mean()) if len(dets) else 0.0,
        "unaccommodating_90d": float((dets["category"] == "Unaccommodating").sum()),
        "team_new_share": team_new_share,
    }


def _team_new_share(agents: list[Agent], as_of: date) -> dict[str, float]:
    out: dict[str, list[bool]] = {}
    for a in agents:
        anchor = a.go_live_date or a.start_date
        employed = anchor and anchor <= as_of and (not a.leave_date or a.leave_date > as_of)
        if employed:
            out.setdefault(a.tl_name, []).append((as_of - anchor).days <= 90)
    return {k: sum(v) / len(v) for k, v in out.items()}


def build_training_set(db: Session, org_id: int) -> pd.DataFrame:
    agents = list(db.scalars(select(Agent).where(Agent.org_id == org_id)))
    df = surveys_df(db, org_id)
    if df.empty:
        return pd.DataFrame()
    dmin, dmax = data_range(db, org_id)
    groups = dict(tuple(df.groupby("agent_id")))
    empty = df.iloc[0:0]
    rows = []
    snap = dmin + timedelta(days=60)
    while snap <= dmax - timedelta(days=HORIZON_DAYS):
        tns = _team_new_share(agents, snap)
        for a in agents:
            anchor = a.go_live_date or a.start_date
            if not anchor or anchor > snap or (a.leave_date and a.leave_date <= snap):
                continue
            f = features_for(a, groups.get(a.id, empty), snap, tns.get(a.tl_name, 0.0))
            f["label"] = int(bool(a.leave_date and snap < a.leave_date <= snap + timedelta(days=HORIZON_DAYS)))
            rows.append(f)
        snap += timedelta(days=30)
    return pd.DataFrame(rows)


def _model_path(db: Session, org_id: int) -> Path:
    p = Path(get_settings().model_dir)
    p.mkdir(parents=True, exist_ok=True)
    slug = db.get(Organization, org_id).slug
    return p / f"attrition_{slug}.joblib"


def train(db: Session, org_id: int) -> dict:
    data = build_training_set(db, org_id)
    if data.empty or data["label"].sum() < 10 or (data["label"] == 0).sum() < 10:
        _model_path(db, org_id).unlink(missing_ok=True)  # never score with a stale model
        return {"trained": False, "reason": "Not enough leavers in history to train (need 10+). Heuristic scoring will be used."}
    X = data[FEATURES].fillna(data[FEATURES].median()).fillna(0)
    y = data["label"]
    medians = X.median().to_dict()
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500, class_weight="balanced"))
    # time-ordered split: the last 25% of snapshots are the test set
    cut = int(len(X) * 0.75)
    model.fit(X.iloc[:cut], y.iloc[:cut])
    auc = roc_auc_score(y.iloc[cut:], model.predict_proba(X.iloc[cut:])[:, 1]) if y.iloc[cut:].nunique() > 1 else None
    model.fit(X, y)
    joblib.dump({"model": model, "medians": medians, "features": FEATURES, "auc": auc}, _model_path(db, org_id))
    return {"trained": True, "rows": int(len(X)), "positives": int(y.sum()), "holdout_auc": None if auc is None else round(auc, 3)}


def _heuristic(f: dict) -> tuple[float, list[str]]:
    score, drivers = 0.1, []
    rules = [
        (f["tenure_days"] == f["tenure_days"] and f["tenure_days"] <= 90, 0.25, "tenure_days"),
        (f["nps_30d"] == f["nps_30d"] and f["nps_30d"] < 10, 0.2, "nps_30d"),
        (f["nps_trend"] == f["nps_trend"] and f["nps_trend"] < -10, 0.15, "nps_trend"),
        (f["det_rate_90d"] == f["det_rate_90d"] and f["det_rate_90d"] > 0.4, 0.15, "det_rate_90d"),
        (f["unaccommodating_90d"] >= 3, 0.1, "unaccommodating_90d"),
    ]
    for cond, w, name in rules:
        if cond:
            score += w
            drivers.append(LABELS[name])
    return min(score, 0.95), drivers


def score(db: Session, org_id: int) -> dict:
    as_of = data_range(db, org_id)[1]
    agents = list(db.scalars(select(Agent).where(Agent.org_id == org_id)))
    active = [a for a in agents if a.status == "active"]
    df = surveys_df(db, org_id, start=as_of - timedelta(days=120))
    tns = _team_new_share(agents, as_of)
    path = _model_path(db, org_id)
    bundle = joblib.load(path) if path.exists() else None
    db.execute(delete(AttritionScore).where(AttritionScore.org_id == org_id))
    groups = dict(tuple(df.groupby("agent_id"))) if not df.empty else {}
    empty = df.iloc[0:0]
    out = []
    for a in active:
        f = features_for(a, groups.get(a.id, empty), as_of, tns.get(a.tl_name, 0.0))
        if bundle:
            x = pd.DataFrame([f])[bundle["features"]].fillna(bundle["medians"]).fillna(0)
            risk = float(bundle["model"].predict_proba(x)[0, 1])
            lr = bundle["model"][-1]
            scaled = bundle["model"][0].transform(x)[0]
            contrib = sorted(zip(bundle["features"], scaled * lr.coef_[0], strict=True), key=lambda t: -t[1])
            drivers = [LABELS[n] for n, c in contrib[:3] if c > 0.15]
            method = "model"
        else:
            risk, drivers = _heuristic(f)
            method = "heuristic"
        band = "high" if risk >= 0.6 else "medium" if risk >= 0.35 else "low"
        db.add(AttritionScore(org_id=org_id, agent_id=a.id, risk=risk, band=band, drivers=drivers, method=method))
        out.append(band)
    db.commit()
    return {"scored": len(out), "high": out.count("high"), "medium": out.count("medium"), "method": "model" if bundle else "heuristic"}


if __name__ == "__main__":  # pragma: no cover
    from app.db.session import SessionLocal

    cmd = sys.argv[1] if len(sys.argv) > 1 else "score"
    with SessionLocal() as s:
        for org in s.scalars(select(Organization)):
            print(org.slug, train(s, org.id) if cmd == "train" else score(s, org.id))
