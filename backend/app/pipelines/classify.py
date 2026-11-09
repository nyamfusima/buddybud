"""Classify detractor comments into the People/Process taxonomy.

With an LLM configured this reproduces the diagnostic's "full read" (every comment read, not keyword-matched),
in batches of 25 with structured output. Low-confidence answers go to the admin review queue.
Without an LLM it falls back to the keyword classifier, marking everything for review."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.llm import get_chat_model
from app.db.models import Classification, Survey
from app.services.taxonomy import PEOPLE_CATEGORIES, PROCESS_CATEGORIES, keyword_classify

log = logging.getLogger("buddybud.classify")
BATCH = 25
REVIEW_BELOW = 0.6


class Item(BaseModel):
    id: int
    bucket: Literal["People", "Process", "None"]
    category: str | None = Field(description="Exact category name from the list, or null when bucket is None")
    confidence: float = Field(ge=0, le=1)


class Batch(BaseModel):
    items: list[Item]


INSTRUCTIONS = f"""You classify why a call-centre customer gave a low NPS score (0-6), using their comment.
People = the agent's own behaviour or knowledge caused it. Categories: {", ".join(PEOPLE_CATEGORIES)}.
Process = a system, policy, product or workflow caused it. Categories: {", ".join(PROCESS_CATEGORIES)}.
None = blank, positive, or too vague to tell.
Read the whole comment: "billing" words can hide a People story (e.g. an agent promised a refund that never came =
Promise Not Kept; a rude or dismissive agent = Unaccommodating). Pick the single main cause.
Return one item per input id. confidence = how sure you are (0-1)."""


def _pending(db: Session, org_id: int, limit: int, reclassify_keyword: bool) -> list[Survey]:
    q = (select(Survey).outerjoin(Classification).where(Survey.org_id == org_id, Survey.nps <= 6))
    if reclassify_keyword:
        q = q.where((Classification.survey_id.is_(None)) | (Classification.source == "keyword"))
    else:
        q = q.where(Classification.survey_id.is_(None))
    return list(db.scalars(q.order_by(Survey.date.desc()).limit(limit)))


def _store(db: Session, s: Survey, bucket: str, cat: str | None, conf: float, source: str) -> None:
    valid = (bucket == "People" and cat in PEOPLE_CATEGORIES) or (bucket == "Process" and cat in PROCESS_CATEGORIES)
    if bucket != "None" and not valid:
        conf = min(conf, 0.3)
    c = s.classification or Classification(survey_id=s.id)
    c.bucket, c.category = bucket, (cat if bucket != "None" else None)
    c.confidence, c.source = conf, source
    c.needs_review = conf < REVIEW_BELOW or source == "keyword"
    s.classification = c


def classify_pending(db: Session, org_id: int, limit: int = 20000, reclassify_keyword: bool = False) -> dict:
    surveys = _pending(db, org_id, limit, reclassify_keyword)
    use_llm = get_settings().llm_provider != "fake"
    done = llm_n = kw_n = 0
    model = get_chat_model("classifier").with_structured_output(Batch) if use_llm else None
    for i in range(0, len(surveys), BATCH):
        chunk = surveys[i : i + BATCH]
        results: dict[int, Item] = {}
        if model:
            try:
                lines = "\n".join(f"[{s.id}] {(s.comment or '').strip()[:600] or '(blank)'}" for s in chunk)
                out = model.invoke(f"{INSTRUCTIONS}\n\nComments:\n{lines}")
                results = {it.id: it for it in out.items}
            except Exception:
                log.exception("LLM batch failed; falling back to keywords for this batch")
        for s in chunk:
            it = results.get(s.id)
            if it:
                _store(db, s, it.bucket, it.category, it.confidence, "llm")
                llm_n += 1
            else:
                b, c, conf = keyword_classify(s.comment)
                _store(db, s, b, c, conf, "keyword")
                kw_n += 1
            done += 1
        db.commit()
    return {"classified": done, "by_llm": llm_n, "by_keyword": kw_n}
