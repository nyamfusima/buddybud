"""The coach as a LangGraph state machine.

    START -> safety --crisis--> crisis_reply -> END
                    \\--else--> agent <-> tools
                                  \\-> grounding --ok--> END
                                              \\--ungrounded numbers (once)--> agent (rewrite)
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.agents.coach import safety
from app.agents.coach.prompts import crisis_reply


class CoachState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    safety: str
    rewrites: int
    rewritten: bool


NUM_RX = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
SMALL_OK = {str(i) for i in range(0, 13)} | {"24", "30", "60", "90"}


def text_of(msg) -> str:
    c = msg.content
    if isinstance(c, str):
        return c
    return "".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")


def _nums(text: str) -> set[float]:
    out = set()
    for m in NUM_RX.findall(text):
        try:
            out.add(round(abs(float(m)), 1))
        except ValueError:
            pass
    return out


def ungrounded_numbers(reply: str, evidence: list[str]) -> list[str]:
    allowed = set()
    for e in evidence:
        allowed |= _nums(e)
    # allow simple differences/ratios between quoted figures (e.g. "12.4 pts below target")
    base = sorted(allowed)[:400]
    derived = {round(abs(a - b), 1) for i, a in enumerate(base) for b in base[i + 1 :]}
    bad = []
    for raw in NUM_RX.findall(reply):
        if raw.lstrip("-") in SMALL_OK:
            continue
        v = round(abs(float(raw)), 1)
        if v not in allowed and v not in derived:
            bad.append(raw)
    return bad


def build_coach_graph(model, tools, system_prompt: str, first_name: str, support_contact: str, crisis_resources: str,
                      model_factory=None):
    bound = model.bind_tools(tools)

    async def safety_node(state: CoachState):
        last = next((m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), None)
        label = await asyncio.to_thread(safety.classify, text_of(last) if last else "", model_factory) if model_factory else (
            "crisis" if last and safety.keyword_screen(text_of(last)) else "unchecked")
        return {"safety": label, "rewrites": 0, "rewritten": False}

    async def crisis_node(state: CoachState):
        return {"messages": [AIMessage(content=crisis_reply(first_name, support_contact, crisis_resources))]}

    async def agent_node(state: CoachState):
        resp = await bound.ainvoke([SystemMessage(content=system_prompt), *state["messages"]])
        return {"messages": [resp]}

    async def grounding_node(state: CoachState):
        msgs = state["messages"]
        reply = text_of(msgs[-1])
        # evidence = system prompt + everything said in this turn (tool results and the user's own words)
        turn_start = max(i for i, m in enumerate(msgs) if isinstance(m, HumanMessage) and not str(m.content).startswith("REWRITE"))
        evidence = [system_prompt] + [text_of(m) for m in msgs[turn_start:-1] if isinstance(m, ToolMessage | HumanMessage)]
        for m in msgs[turn_start:]:
            if isinstance(m, AIMessage) and m.tool_calls:
                evidence.append(json.dumps([tc.get("args", {}) for tc in m.tool_calls]))
        bad = ungrounded_numbers(reply, evidence)
        if bad and state.get("rewrites", 0) < 1:
            return {"rewrites": state.get("rewrites", 0) + 1, "rewritten": True, "messages": [HumanMessage(content=(
                f"REWRITE: your draft used numbers that aren't in the data ({', '.join(bad[:6])}). Rewrite the reply "
                "for the agent using only numbers returned by your tools or given in your instructions. "
                "Don't mention this check."))]}
        return {}

    def after_safety(state: CoachState):
        return "crisis" if state["safety"] == "crisis" else "agent"

    def after_agent(state: CoachState):
        last = state["messages"][-1]
        return "tools" if isinstance(last, AIMessage) and last.tool_calls else "grounding"

    def after_grounding(state: CoachState):
        last = state["messages"][-1]
        return "agent" if isinstance(last, HumanMessage) and str(last.content).startswith("REWRITE") else END

    g = StateGraph(CoachState)
    g.add_node("safety", safety_node)
    g.add_node("crisis", crisis_node)
    g.add_node("agent", agent_node)
    g.add_node("tools", ToolNode(tools))
    g.add_node("grounding", grounding_node)
    g.add_edge(START, "safety")
    g.add_conditional_edges("safety", after_safety, {"crisis": "crisis", "agent": "agent"})
    g.add_edge("crisis", END)
    g.add_conditional_edges("agent", after_agent, {"tools": "tools", "grounding": "grounding"})
    g.add_edge("tools", "agent")
    g.add_conditional_edges("grounding", after_grounding, {"agent": "agent", END: END})
    return g.compile()
