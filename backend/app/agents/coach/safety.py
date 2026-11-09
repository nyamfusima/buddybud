"""Safety routing. A high-recall keyword screen runs first (no model can talk its way past it); an optional
model check catches indirect phrasing. Anything labelled crisis gets the fixed reply, never a generated one."""

from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import get_settings

log = logging.getLogger("buddybud.safety")

CRISIS_RX = re.compile(
    r"\b(kill(ing)? myself|suicid\w*|end (it all|my life)|take my (own )?life|want to die|wanna die|"
    r"better off dead|no reason to live|self[- ]?harm\w*|hurt(ing)? myself|cut(ting)? myself|overdose|"
    r"(he|she|they|someone|my (tl|manager|boss|colleague)) (is |has been )?(hitting|assault\w*|touch\w* me|threaten\w*)|"
    r"sexual(ly)? harass\w*|being abused|domestic (abuse|violence)|not safe at home)\b",
    re.I,
)


class SafetyLabel(BaseModel):
    label: Literal["performance", "wellbeing", "crisis", "off_topic"] = Field(
        description="crisis = risk of self-harm or suicide, abuse, violence, harassment, or someone unsafe right now"
    )


def keyword_screen(text: str) -> bool:
    return bool(CRISIS_RX.search(text or ""))


def classify(text: str, model_factory) -> str:
    if keyword_screen(text):
        return "crisis"
    s = get_settings()
    if s.llm_provider == "fake" or not s.safety_llm_check:
        return "unchecked"
    try:
        model = model_factory("safety").with_structured_output(SafetyLabel)
        res = model.invoke(
            "Label this message from a call-centre agent to their workplace AI coach. Use 'crisis' only for risk of "
            f"self-harm/suicide, abuse, violence, harassment or immediate danger.\n\nMessage: {text[:2000]}"
        )
        return res.label
    except Exception:  # never block the chat on the safety model; the keyword screen already ran
        log.exception("safety model failed")
        return "unchecked"
