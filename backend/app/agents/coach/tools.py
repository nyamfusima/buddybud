"""Coach tools. They close over ONE agent's precomputed payload, so the model can't reach anyone else's data
no matter what it's asked: scoping is enforced by construction, not by the prompt."""

from __future__ import annotations

import json
from datetime import date

from langchain_core.tools import StructuredTool

from app.services.metrics import default_window, monthly_trend, summarize


def _valid(d: str | None) -> str | None:
    if not d:
        return None
    try:
        return date.fromisoformat(d).isoformat()
    except ValueError:
        return None


def make_tools(payload: dict, shared: dict, kb: dict) -> list[StructuredTool]:
    dmax = date.fromisoformat(shared["date_max"])
    w_from, w_to, _ = default_window(dmax)

    def get_my_metrics(from_date: str | None = None, to_date: str | None = None) -> str:
        """Get this agent's NPS, OSAT, survey count, promoters/passives/detractors, promoter:detractor ratio and
        People/Process detractor categories for a date range (YYYY-MM-DD). Omit dates for the default view
        (month to date, or last 7 days early in the month)."""
        f = _valid(from_date) or w_from.isoformat()
        t = _valid(to_date) or w_to.isoformat()
        out = summarize(payload, f, t)
        out.update({"nps_target": shared["nps_target"], "osat_target": shared["osat_target"],
                    "group_average_nps_full_period": payload.get("team_nps"),
                    "site_average_nps_full_period": shared.get("overall_nps")})
        return json.dumps(out)

    def get_my_trend() -> str:
        """Month-by-month NPS, OSAT and survey volume for this agent over the whole data window."""
        return json.dumps(monthly_trend(payload))

    def get_my_detractor_comments(category: str | None = None, limit: int = 5) -> str:
        """Most recent detractor (NPS 0-6) customer comments for this agent, optionally filtered to one category
        such as 'Unaccommodating' or 'Billing'. Max 10."""
        dets = payload["detractors"]
        if category:
            dets = [d for d in dets if (d.get("category") or "").lower() == category.lower()]
        dets = sorted(dets, key=lambda d: d["date"], reverse=True)[: max(1, min(int(limit), 10))]
        return json.dumps([{"date": d["date"], "nps": d["nps"], "bucket": d["bucket"], "category": d["category"],
                            "comment": (d["comment"] or "")[:260]} for d in dets])

    def get_my_wins(limit: int = 3) -> str:
        """Recent customer praise (NPS 9-10 with a comment) for this agent. Use it to balance the conversation."""
        wins = sorted(payload["win_candidates"], key=lambda w: (w["date"], w["score"]), reverse=True)[: max(1, min(int(limit), 6))]
        return json.dumps([{"date": w["date"], "nps": w["nps"], "comment": w["comment"][:260]} for w in wins])

    def get_coaching_guidance(category: str) -> str:
        """The team's own coaching playbook for one People or Process category: headline, guidance and quick win
        (People) or CareHub area, what it means and what to tell the customer (Process)."""
        c = category.strip().lower()
        for bucket in ("people", "process"):
            for name, variants in kb.get(bucket, {}).items():
                if name.lower() == c:
                    return json.dumps({"category": name, "bucket": bucket, "guidance": variants,
                                       "process_rule_of_thumb": kb.get("general_process_closer") if bucket == "process" else None})
        return json.dumps({"category": category, "guidance": kb.get("default_process", []),
                           "note": "No specific playbook entry; general guidance returned.",
                           "known_categories": sorted([*kb.get("people", {}), *kb.get("process", {})])})

    return [
        StructuredTool.from_function(get_my_metrics),
        StructuredTool.from_function(get_my_trend),
        StructuredTool.from_function(get_my_detractor_comments),
        StructuredTool.from_function(get_my_wins),
        StructuredTool.from_function(get_coaching_guidance),
    ]
