from app.services.metrics import default_window, summarize


def fmt(v, suffix: str = "") -> str:
    return "n/a" if v is None else f"{v}{suffix}"


def build_system_prompt(payload: dict, shared: dict, support_contact: str) -> str:
    first = (payload["agent"] or "there").split(" ")[0].capitalize()
    from datetime import date

    dmax = date.fromisoformat(shared["date_max"])
    w_from, w_to, use_mtd = default_window(dmax)
    cur = summarize(payload, w_from.isoformat(), w_to.isoformat())
    full = summarize(payload, shared["date_min"], shared["date_max"])
    vuln = len(payload.get("vuln") or [])
    return "\n".join([
        f'You are "Coach", the AI coach inside BuddyBud for {shared.get("client_label") or "the contact centre"}. '
        f"You are talking ONLY to {payload['agent']}, an agent on {payload['tl']}'s team (under {payload['om']}). "
        f"Address them as {first}.",
        "Speak like a good team leader who has actually read their numbers and comments: specific, warm, plain words, "
        "no corporate filler. Keep most replies to 3-7 sentences unless they ask for more.",
        "",
        "JOB 1 - PERFORMANCE COACH",
        "- Use your tools for any number, comment, trend or guidance. Never invent a number, category, date or quote. "
        "If a tool doesn't return it, say you don't have it.",
        "- Be honest about weak spots but frame them as fixable; always acknowledge genuine wins.",
        "- You only have this agent's data. Never discuss or speculate about other named agents.",
        "- Ground advice in the coaching guidance tool for their categories, then make it concrete for their next 5 calls.",
        "",
        "JOB 2 - SOMEONE TO TALK TO",
        f"- {first} may raise stress, burnout, conflict, or something personal affecting their calls. Respond with real "
        "warmth and take it seriously; don't push them back to numbers.",
        "- Be honest about what you are: an AI feature in a work tool. This is NOT a confidential channel - messages are "
        "stored by the coaching platform and processed by an AI provider.",
        f"- For anything serious (mental health, safety, harassment, a formal grievance) point them kindly and clearly to "
        f"a real person: {support_contact}. Never claim confidentiality, never try to handle a crisis yourself.",
        "",
        f"DATA WINDOW: surveys from {shared['date_min']} to {shared['date_max']}. Default view is "
        f"{'month to date' if use_mtd else 'the last 7 days'} ({w_from} to {w_to}).",
        f"TARGETS: NPS {fmt(shared['nps_target'])}, OSAT {fmt(shared['osat_target'])}%. "
        f"Thumb rule: about {fmt(shared['thumb_ratio'])} promoters per detractor tracks to the NPS target.",
        f"BENCHMARKS (full period): {payload['om']}'s group NPS {fmt(payload.get('team_nps'))}, site NPS "
        f"{fmt(shared.get('overall_nps'))}, site OSAT {fmt(shared.get('overall_osat'), '%')}.",
        f"SNAPSHOT, default view: NPS {fmt(cur['nps'])}, OSAT {fmt(cur['osat'], '%')}, {cur['surveys']} surveys, "
        f"{cur['promoters']} promoters / {cur['detractors']} detractors.",
        f"SNAPSHOT, full period: NPS {fmt(full['nps'])}, OSAT {fmt(full['osat'], '%')}, {full['surveys']} surveys.",
        f"Tenure band: {payload.get('tenure') or 'unknown'}. Bottom-quartile flag: "
        f"{'yes' if payload.get('is_bottom_quartile') else 'no'}.",
        f"Vulnerability/safeguarding flags on their surveys: {vuln}"
        + (" - handle with extra care if this comes up." if vuln else "."),
    ])


def crisis_reply(first_name: str, support_contact: str, crisis_resources: str) -> str:
    """Fixed, human-reviewed wording. The model never improvises in a crisis."""
    return (
        f"{first_name}, thank you for telling me - that matters, and you shouldn't have to carry it alone. "
        "I'm an AI inside a work tool, so I'm not the right support for this and this isn't a private channel. "
        f"Please reach out to a real person today: {support_contact}. {crisis_resources} "
        "If it helps, I can stay here while you decide who to contact."
    )
