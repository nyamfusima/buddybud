from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.coach.graph import build_coach_graph, text_of
from app.agents.coach.prompts import build_system_prompt
from app.agents.coach.tools import make_tools
from app.core.config import get_settings
from app.core.llm import get_chat_model
from app.db.models import Agent, ChatMessage, User
from app.services import metrics

log = logging.getLogger("buddybud.coach")
_rate: dict[int, deque] = defaultdict(deque)

TOOL_STATUS = {
    "get_my_metrics": "Checking your numbers…",
    "get_my_trend": "Looking at your monthly trend…",
    "get_my_detractor_comments": "Reading your recent customer comments…",
    "get_my_wins": "Finding your recent wins…",
    "get_coaching_guidance": "Pulling up the coaching playbook…",
}


def rate_limited(user_id: int) -> bool:
    limit = get_settings().coach_rate_limit_per_10min
    q, now = _rate[user_id], time.time()
    while q and now - q[0] > 600:
        q.popleft()
    if len(q) >= limit:
        return True
    q.append(now)
    return False


def load_history(db: Session, user: User) -> list:
    n = get_settings().coach_history_turns
    rows = list(db.scalars(select(ChatMessage).where(ChatMessage.user_id == user.id)
                           .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(n)))
    rows.reverse()
    while rows and rows[0].role != "user":  # providers expect the conversation to open with a user turn
        rows.pop(0)
    return [HumanMessage(content=r.content) if r.role == "user" else AIMessage(content=r.content) for r in rows]


def prepare(db: Session, user: User, message: str) -> dict:
    agent = db.get(Agent, user.agent_id)
    payload = metrics.agent_payload(db, agent, user.org)
    shared = metrics.shared_block(db, user.org)
    kb = metrics.coaching_kb(db, user.org_id)
    history = load_history(db, user)
    db.add(ChatMessage(org_id=user.org_id, user_id=user.id, role="user", content=message))
    db.commit()
    return {"payload": payload, "shared": shared, "kb": kb, "history": history,
            "support": user.org.support_contact, "crisis": user.org.crisis_resources}


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def stream_reply(ctx: dict, message: str, save) -> AsyncIterator[str]:
    payload, shared = ctx["payload"], ctx["shared"]
    first = (payload["agent"] or "there").split(" ")[0].capitalize()
    graph = build_coach_graph(
        get_chat_model("coach"), make_tools(payload, shared, ctx["kb"]),
        build_system_prompt(payload, shared, ctx["support"]), first, ctx["support"], ctx["crisis"],
        model_factory=get_chat_model,
    )
    final_text, label = "", None
    inputs = {"messages": [*ctx["history"], HumanMessage(content=message)]}
    try:
        async for mode, chunk in graph.astream(inputs, stream_mode=["messages", "updates"]):
            if mode == "messages":
                msg, meta = chunk
                if meta.get("langgraph_node") == "agent" and isinstance(msg, AIMessageChunk):
                    t = text_of(msg)
                    if t:
                        yield sse("token", t)
            else:
                for node, update in (chunk or {}).items():
                    if not update:
                        continue
                    if node == "safety":
                        label = update.get("safety")
                    elif node == "crisis":
                        final_text = text_of(update["messages"][-1])
                        yield sse("token", final_text)
                    elif node == "agent":
                        m = update["messages"][-1]
                        if m.tool_calls:
                            yield sse("status", TOOL_STATUS.get(m.tool_calls[0]["name"], "Thinking…"))
                        else:
                            final_text = text_of(m)
                    elif node == "grounding" and update.get("rewritten"):
                        yield sse("reset", "")
        if not final_text:
            final_text = "Sorry, I didn't catch that — can you rephrase?"
        save(final_text, label)
        yield sse("done", {"text": final_text, "safety": label})
    except Exception as e:  # pragma: no cover - provider/network errors
        log.exception("coach failed")
        yield sse("error", "Sorry, I couldn't reach the coaching service just now. Try again in a moment."
                  if get_settings().env == "prod" else f"Coach error: {e}")
