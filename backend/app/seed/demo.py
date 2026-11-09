"""Synthetic demo data. Realistic shape (tenure curve, hiring waves, TL variance, attrition, People/Process mix),
zero real people. Safe to commit, safe to demo to prospects."""

from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import Agent, Classification, CoachingTemplate, Organization, Role, Survey, User
from app.services.taxonomy import is_vulnerable

KB_PATH = Path(__file__).with_name("coaching_kb.json")
DEMO_PASSWORD = "BuddyBud2026!"

FIRST = ["Anele", "Thabo", "Lerato", "Sipho", "Zanele", "Kyle", "Aisha", "Nomsa", "Ruan", "Kagiso", "Megan", "Lwazi",
         "Tasneem", "Bongani", "Chantel", "Musa", "Naledi", "Jason", "Palesa", "Yusuf", "Ayanda", "Michelle", "Tumi",
         "Zaid", "Lindiwe", "Ethan", "Refilwe", "Shaun", "Nandi", "Imran", "Precious", "Dylan", "Busisiwe", "Keegan",
         "Thandeka", "Riaan", "Mpho", "Fatima", "Sibusiso", "Jade", "Kamogelo", "Ashwin", "Nokuthula", "Brandon",
         "Asanda", "Nadia", "Vusi", "Courtney", "Siyabonga", "Leila"]
LAST = ["Mokoena", "Daniels", "Ndlovu", "Petersen", "Khumalo", "Adams", "Dlamini", "Jacobs", "Naidoo", "Botha",
        "Mthembu", "Abrahams", "Nkosi", "Hendricks", "Zulu", "Van Wyk", "Sithole", "Isaacs", "Mahlangu", "Pillay",
        "Cele", "Williams", "Molefe", "Davids", "Maseko", "February", "Ntuli", "Solomons", "Radebe", "Arendse"]

PRAISE = [
    "The agent was so patient and explained everything clearly, sorted in one call.",
    "Brilliant service, really friendly and went above and beyond to fix my bill.",
    "Very helpful and polite, didn't rush me at all. Thank you!",
    "Quick, professional and actually listened to what I needed.",
    "Lovely person, kept me updated and did exactly what they said they would.",
    "Excellent — fixed my porting issue that had been dragging on for weeks.",
    "Really kind and calm while I was stressed about my account. Great job.",
    "Sorted my upgrade in minutes and explained the costs honestly.",
]
DETRACTOR_TEXT = {
    "Unaccommodating": ["The agent was rude and didn't listen to what I was saying.", "Felt dismissive, like I was a nuisance.",
                        "Kept cutting me off and had an attitude the whole call.", "Didn't care about my problem at all, just wanted me off the phone."],
    "Incorrect Information": ["I was told the wrong information about my contract end date.", "Agent gave me incorrect info and now I've been charged.",
                              "Got told one thing, next person said the opposite. Misinformed again."],
    "Language Barrier/Comprehension": ["Couldn't understand the agent, had to repeat myself many times.", "Hard to understand the accent and they didn't understand me either."],
    "Limited in assistance": ["They said they couldn't help and had to transfer me again.", "Agent was nice but unable to help, no authority to do anything."],
    "Promise Not Kept": ["I was promised a refund that never happened.", "Said it would be fixed in 48 hours, still waiting two weeks later."],
    "Failed Callback": ["Promised a call back that never came.", "Was told someone would ring me back, nobody did."],
    "Network": ["No signal at home for a week, network is useless.", "Constant outage in my area and no fix date."],
    "App/Digital": ["The app keeps logging me out and the website is broken.", "Can't log in online to see my bill."],
    "Porting/SIM": ["My PAC code didn't work and porting took ages.", "SIM swap failed twice, no service for days."],
    "Faulty Hardware": ["Handset is faulty, screen stopped working after a month.", "Phone keeps restarting, need a repair."],
    "Fraud": ["Someone made unauthorised changes to my account, fraud.", "Scam texts and an unauthorised charge."],
    "IVR/Wait": ["Waited on hold for 45 minutes before anyone answered.", "The automated menu goes round in circles, long queue."],
    "Resolution/FCR (Process)": ["Still not resolved after calling 4 times.", "Issue not fixed, have called multiple times now."],
    "Billing": ["Overcharged on my bill again this month.", "Direct debit taken twice, billing is a mess."],
    "Policy": ["Policy says they can't do anything, ridiculous rules.", "Not allowed to change my plan because of the terms."],
    "Pricing Policy": ["Price rise in the middle of my contract, too expensive now.", "Tariff costs more than advertised."],
    "Account/Data Mgmt": ["They still have my old address on the account.", "Account details wrong even after I updated them."],
    "Sales Process": ["Upgrade process was confusing and pushy.", "Sales call promised a deal that doesn't exist in my contract."],
    "Delivery/DPD": ["Courier never delivered my phone, DPD lost it.", "Parcel delivery delayed by a week."],
}
PEOPLE_W = {"Unaccommodating": 37, "Incorrect Information": 21, "Language Barrier/Comprehension": 17,
            "Limited in assistance": 11, "Promise Not Kept": 8, "Failed Callback": 6}
PROCESS_W = {"Network": 12, "App/Digital": 9, "Porting/SIM": 8, "Faulty Hardware": 6, "Fraud": 3, "IVR/Wait": 9,
             "Resolution/FCR (Process)": 10, "Sales Process": 5, "Billing": 18, "Policy": 7, "Pricing Policy": 6,
             "Account/Data Mgmt": 5, "Delivery/DPD": 2}
VULN_TAILS = [" My elderly mother is the account holder and she was very confused.", " I'm disabled and struggled with the menu.",
              " I'm struggling to pay after a bereavement."]


def seed_coaching(db: Session, org_id: int) -> None:
    kb = json.loads(KB_PATH.read_text(encoding="utf-8"))
    rows = []
    for bucket, key in (("People", "people"), ("Process", "process")):
        for cat, variants in kb[key].items():
            rows += [CoachingTemplate(org_id=org_id, bucket=bucket, category=cat, variant=i, payload=v) for i, v in enumerate(variants)]
    rows += [CoachingTemplate(org_id=org_id, bucket="DefaultProcess", category="*", variant=i, payload=v)
             for i, v in enumerate(kb["default_process"])]
    rows.append(CoachingTemplate(org_id=org_id, bucket="Closer", category="*", payload={"text": kb["general_process_closer"]}))
    db.add_all(rows)


def create_org(db: Session, name: str, slug: str, client_label: str = "Customer Care") -> Organization:
    org = Organization(name=name, slug=slug, client_label=client_label)
    db.add(org)
    db.flush()
    seed_coaching(db, org.id)
    return org


def _wchoice(rng: random.Random, weights: dict[str, float]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def generate_demo(db: Session, end: date | None = None, months: int = 13, seed: int = 7, target_active: int = 200) -> dict:
    rng = random.Random(seed)
    end = end or (date.today() - timedelta(days=1))
    survey_start = (end.replace(day=1) - timedelta(days=30 * (months - 1))).replace(day=1)
    history_start = survey_start - timedelta(days=200)

    if db.scalars(select(Organization).where(Organization.slug == "demo")).first():
        raise RuntimeError("Demo org already exists. Delete the database (or use a fresh one) to reseed.")
    org = create_org(db, "Demo Contact Centre", "demo", client_label="Demo Telco Care")

    oms = ["Nosipho Gumede", "Craig Fortuin", "Shireen Moosa"]
    tls: dict[str, tuple[str, float]] = {}
    tl_names = ["Nosive Gombe", "Sameer Salie", "Tamsin Jordaan", "Lungi Mkhize", "Wesley Booysen", "Priya Govender",
                "Andile Zungu", "Carla Meyer", "Bheki Shabalala", "Fiona Adonis", "Ziyaad Kader", "Ronel Smit"]
    for i, t in enumerate(tl_names):
        effect = 14.0 if i == 0 else rng.gauss(0, 6) - (6 if i in (4, 9) else 0)
        tls[t] = (oms[i % 3], effect)
    new_tls = ["Sonia Padayachee", "Amira Ely", "Carmen Martins"]  # three teams hired in one wave ~75 days ago
    for i, t in enumerate(new_tls):
        tls[t] = (oms[i % 3], rng.gauss(-2, 3))

    used_names: set[str] = set()

    def new_name() -> str:
        while True:
            n = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if n not in used_names:
                used_names.add(n)
                return n

    def hazard(days: int) -> float:  # monthly leaving probability by tenure
        return 0.14 if days <= 90 else 0.06 if days <= 180 else 0.035

    agents: list[Agent] = []
    ref = 1000

    def hire(go_live: date, tl: str):
        nonlocal ref
        ref += 1
        name = new_name()
        a = Agent(org_id=org.id, employee_ref=f"E{ref}", full_name=name,
                  email=f"{name.lower().replace(' ', '.')}@democc.example", tl_name=tl, om_name=tls[tl][0],
                  start_date=go_live - timedelta(days=21), go_live_date=go_live, status="active")
        # simulate their life in 30-day steps
        t = go_live
        while t < end:
            if rng.random() < hazard((t - go_live).days):
                a.status, a.leave_date = "left", min(end, t + timedelta(days=rng.randint(1, 29)))
                invol = rng.random() < 0.45
                a.leave_type = "involuntary" if invol else "voluntary"
                a.leave_reason = rng.choice(["Gross misconduct", "AWOL", "Performance"]) if invol else rng.choice(
                    ["Resigned - better offer", "Resigned - personal", "Resigned - studies", "Did not return after training"])
                break
            t += timedelta(days=30)
        a._skill = rng.gauss(0, 7)  # type: ignore[attr-defined]
        agents.append(a)

    est_tls = tl_names
    # standing population + steady hiring + one big wave early in the survey window
    for _ in range(240):
        hire(history_start - timedelta(days=rng.randint(0, 700)), rng.choice(est_tls))
    d = history_start
    while d < end - timedelta(days=100):
        for _ in range(rng.randint(6, 10)):
            hire(d + timedelta(days=rng.randint(0, 27)), rng.choice(est_tls))
        d += timedelta(days=30)
    wave_start = survey_start + timedelta(days=45)
    for _ in range(110):
        hire(wave_start + timedelta(days=rng.randint(0, 60)), rng.choice(est_tls))
    wave2 = end - timedelta(days=75)
    for t in new_tls:
        for _ in range(rng.randint(9, 13)):
            hire(wave2, t)

    # trim to roughly the target active headcount by marking the oldest extras as leavers
    active = [a for a in agents if a.status == "active" and a.tl_name not in new_tls]
    rng.shuffle(active)
    for a in active[: max(0, len(active) + 34 - target_active)]:
        a.status, a.leave_date, a.leave_type, a.leave_reason = "left", end - timedelta(days=rng.randint(30, 360)), "voluntary", "Resigned - personal"

    db.add_all(agents)
    db.flush()

    # ---------------- surveys
    sid = 500000
    survey_rows, class_rows = [], []
    day = survey_start
    while day <= end:
        if day.weekday() < 6:
            dec_dip = -6 if day.month == 12 else 0
            for a in agents:
                live = a.go_live_date
                if live > day or (a.leave_date and a.leave_date <= day):
                    continue
                if rng.random() > 0.62:
                    continue
                tdays = (day - live).days
                curve = 3 + 17.5 * (1 - math.exp(-tdays / 55))
                target = curve + a._skill + tls[a.tl_name][1] + dec_dip  # type: ignore[attr-defined]
                if a.leave_date and (a.leave_date - day).days < 60:
                    target -= 9  # performance slips before people leave
                p_prom = max(0.05, min(0.9, (0.74 + target / 100) / 2))
                p_det = max(0.03, min(0.8, (0.74 - target / 100) / 2))
                r = rng.random()
                if r < p_prom:
                    nps, osat = rng.choice([9, 10, 10]), (5 if rng.random() < 0.85 else 4)
                elif r < p_prom + p_det:
                    nps, osat = rng.choice([0, 0, 1, 2, 3, 4, 5, 5, 6, 6]), (5 if rng.random() < 0.06 else rng.choice([1, 2, 3, 4]))
                else:
                    nps, osat = rng.choice([7, 8]), (5 if rng.random() < 0.4 else 4)
                comment, bucket, cat = "", None, None
                if nps >= 9 and rng.random() < 0.5:
                    comment = rng.choice(PRAISE)
                elif nps <= 6 and rng.random() < 0.88:
                    people_p = 0.48 + (0.1 if tdays < 90 else 0) - a._skill / 100  # type: ignore[attr-defined]
                    bucket = "People" if rng.random() < people_p else "Process"
                    cat = _wchoice(rng, PEOPLE_W if bucket == "People" else PROCESS_W)
                    comment = rng.choice(DETRACTOR_TEXT[cat])
                elif 7 <= nps <= 8 and rng.random() < 0.2:
                    comment = rng.choice(["Fine, took a while.", "Okay overall.", "Got there in the end."])
                if comment and rng.random() < 0.02:
                    comment += rng.choice(VULN_TAILS)
                sid += 1
                survey_rows.append({"org_id": org.id, "sid": f"S{sid}", "agent_id": a.id, "date": day, "nps": nps,
                                    "osat": osat, "comment": comment, "vulnerable": is_vulnerable(comment)})
                # ~85% of detractors arrive pre-classified (the client's full read); the rest go to the classifier
                if bucket and rng.random() < 0.85:
                    class_rows.append((f"S{sid}", bucket, cat))
        day += timedelta(days=1)

    db.execute(insert(Survey), survey_rows)
    ids = dict(db.execute(select(Survey.sid, Survey.id).where(Survey.org_id == org.id)).all())
    db.execute(insert(Classification), [{"survey_id": ids[s], "bucket": b, "category": c, "confidence": 1.0,
                                         "source": "import", "needs_review": False} for s, b, c in class_rows])

    # ---------------- users (one shared hash: same demo password for everyone)
    pw = hash_password(DEMO_PASSWORD)
    users = [User(org_id=org.id, email="admin@democc.example", full_name="Demo Admin", password_hash=pw, role=Role.admin)]
    for om in oms:
        users.append(User(org_id=org.id, email=f"{om.lower().replace(' ', '.')}@democc.example", full_name=om,
                          password_hash=pw, role=Role.om, scope_name=om))
    for t in tls:
        users.append(User(org_id=org.id, email=f"{t.lower().replace(' ', '.')}@democc.example", full_name=t,
                          password_hash=pw, role=Role.tl, scope_name=t))
    for a in agents:
        if a.status == "active":
            users.append(User(org_id=org.id, email=a.email, full_name=a.full_name, password_hash=pw, role=Role.agent, agent_id=a.id))
    db.add_all(users)
    db.commit()
    sample_agent = next(a for a in agents if a.status == "active" and a.tl_name == tl_names[1])
    return {
        "org": org.slug, "agents": len(agents), "active": sum(a.status == "active" for a in agents),
        "surveys": len(survey_rows), "password": DEMO_PASSWORD,
        "logins": {"admin": "admin@democc.example", "om": users[1].email, "tl": f"{tl_names[1].lower().replace(' ', '.')}@democc.example",
                   "agent": sample_agent.email},
    }
