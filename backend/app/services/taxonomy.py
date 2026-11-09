"""People/Process taxonomy from the annual diagnostic, plus ownership groups and keyword fallbacks."""

import re

PEOPLE_CATEGORIES = [
    "Unaccommodating",
    "Incorrect Information",
    "Language Barrier/Comprehension",
    "Limited in assistance",
    "Promise Not Kept",
    "Failed Callback",
]

PROCESS_CATEGORIES = [
    "Network",
    "App/Digital",
    "Porting/SIM",
    "Faulty Hardware",
    "Fraud",
    "IVR/Wait",
    "Resolution/FCR (Process)",
    "Sales Fulfilment",
    "Sales Process",
    "Billing",
    "Policy",
    "Pricing Policy",
    "Account/Data Mgmt",
    "Top-Up/Bundle",
    "Payment/Top-Up",
    "Delivery/DPD",
    "Voicemail/Technical",
]

# Who owns the fix (deck slide 11). Anything unlisted counts as agent-influenceable.
CLIENT_OWNED = {"Network", "App/Digital", "Porting/SIM", "Faulty Hardware", "Fraud", "Voicemail/Technical", "Delivery/DPD"}
MGMT_OWNED = {"IVR/Wait", "Resolution/FCR (Process)", "Sales Fulfilment", "Sales Process"}
AGENT_INFLUENCEABLE = {"Billing", "Policy", "Pricing Policy", "Account/Data Mgmt", "Top-Up/Bundle", "Payment/Top-Up"}


def process_owner(category: str | None) -> str:
    if category in CLIENT_OWNED:
        return "client"
    if category in MGMT_OWNED:
        return "management"
    return "agent"


TENURE_BANDS = ["0-30 days", "31-90 days", "91-180 days", "181-365 days", "365+ days"]


def tenure_band(days: int | None) -> str:
    if days is None:
        return "unknown"
    if days <= 30:
        return TENURE_BANDS[0]
    if days <= 90:
        return TENURE_BANDS[1]
    if days <= 180:
        return TENURE_BANDS[2]
    if days <= 365:
        return TENURE_BANDS[3]
    return TENURE_BANDS[4]


# ---- keyword fallback classifier (used when no LLM is configured, and as a cheap first pass) ----
KEYWORDS: list[tuple[str, str, str]] = [
    # (bucket, category, regex)
    ("People", "Promise Not Kept", r"promis|said (?:it|they) would|never (?:happened|came|arrived)|still waiting for (?:the )?refund"),
    ("People", "Failed Callback", r"call(?:ed)? ?back|callback|ring me back|never rang|didn'?t ring"),
    ("People", "Incorrect Information", r"wrong info|incorrect|misinform|told (?:me )?the wrong|lied|contradict"),
    ("People", "Language Barrier/Comprehension", r"accent|understand (?:him|her|them|the agent)|couldn'?t understand|language|english"),
    ("People", "Unaccommodating", r"rude|dismissive|didn'?t care|nuisance|didn'?t listen|not listening|unhelpful attitude|couldn'?t care|attitude|patroni[sz]|hung up|cut me off"),
    ("People", "Limited in assistance", r"couldn'?t help|unable to help|not able to help|no authority|had to transfer|passed around"),
    ("Process", "Network", r"signal|coverage|mast|outage|no service|network"),
    ("Process", "Porting/SIM", r"\bpac\b|port(?:ing)?|sim (?:card|swap)|esim|number transfer"),
    ("Process", "App/Digital", r"\bapp\b|website|online account|log ?in|password reset"),
    ("Process", "Faulty Hardware", r"faulty|broken (?:phone|handset)|screen|repair|handset"),
    ("Process", "Fraud", r"fraud|scam|unauthori[sz]ed"),
    ("Process", "IVR/Wait", r"wait(?:ed|ing)? (?:for|on)|hold for|on hold|queue|menu|automated"),
    ("Process", "Billing", r"bill|overcharg|charged|direct debit|invoice"),
    ("Process", "Pricing Policy", r"price (?:rise|increase)|too expensive|cost more|tariff"),
    ("Process", "Policy", r"policy|terms|not allowed|rules"),
    ("Process", "Account/Data Mgmt", r"account (?:details|holder)|update my details|data (?:wrong|error)|address"),
    ("Process", "Delivery/DPD", r"deliver|dpd|courier|parcel"),
    ("Process", "Sales Process", r"upgrade|contract|sales"),
    ("Process", "Top-Up/Bundle", r"top ?up|bundle|data allowance"),
    ("Process", "Resolution/FCR (Process)", r"not (?:resolved|fixed|sorted)|still not|multiple times|called (?:\d+|several|many) times"),
]
_COMPILED = [(b, c, re.compile(rx, re.I)) for b, c, rx in KEYWORDS]


def keyword_classify(comment: str) -> tuple[str, str | None, float]:
    text = comment or ""
    if len(text.strip()) < 4:
        return "None", None, 0.9
    for bucket, cat, rx in _COMPILED:
        if rx.search(text):
            return bucket, cat, 0.55
    return "None", None, 0.3


VULN_RX = re.compile(
    r"elderly|pensioner|disab|dementia|alzheimer|carer|vulnerab|bereave|passed away|died|hospital|"
    r"blind|deaf|wheelchair|mental health|anxiety|safeguard|domestic|abuse|struggling to pay|debt",
    re.I,
)


def is_vulnerable(comment: str) -> bool:
    return bool(VULN_RX.search(comment or ""))
