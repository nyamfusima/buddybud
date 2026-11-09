"""Deterministic offline model so the whole system (and the test suite) runs with no API key.
It follows the same tool-calling protocol as a real model, so the LangGraph coach is exercised end to end."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterator, Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

PERF = re.compile(r"nps|osat|number|score|doing|perform|improv|detractor|categor|why|target|stats|month|week|feedback|customer", re.I)
FEEL = re.compile(r"stress|tired|burn|overwhelm|frustrat|angry|sad|upset|anxious|pressure|hate|can'?t cope|difficult", re.I)


class FakeCoachModel(BaseChatModel):
    tool_names: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "fake-coach"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any):  # type: ignore[override]
        names = [getattr(t, "name", None) or t.get("name") for t in tools]
        return FakeCoachModel(tool_names=[n for n in names if n])

    # ------------------------------------------------------------------ core
    def _reply(self, messages: list[BaseMessage]) -> AIMessage:
        last = messages[-1]
        if isinstance(last, ToolMessage):
            return AIMessage(content=self._answer_from_tools(messages))
        human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
        text = str(human.content) if human else ""
        if "REWRITE" in text and "numbers" in text:
            return AIMessage(content="Let's keep this to what's actually on your record — ask me about a specific date range and I'll pull it up.")
        if FEEL.search(text):
            return AIMessage(content=(
                "That sounds genuinely tough, and I'm glad you said it. Do you want to talk through what's been "
                "hardest this week? If it's weighing on you a lot, your TL's manager, HR or your EAP line can help in "
                "ways I can't — I'm an AI inside a work tool, so this isn't a private channel."))
        if PERF.search(text) and "get_my_metrics" in self.tool_names:
            return AIMessage(content="", tool_calls=[{"name": "get_my_metrics", "args": {}, "id": f"call_{uuid.uuid4().hex[:8]}"}])
        return AIMessage(content=("I'm your coach — ask me how you're tracking against target, what's driving your "
                                  "detractors, or just tell me how things are going."))

    def _answer_from_tools(self, messages: list[BaseMessage]) -> str:
        results = []
        for m in reversed(messages):
            if not isinstance(m, ToolMessage):
                break
            try:
                results.append(json.loads(m.content))
            except (TypeError, json.JSONDecodeError):
                pass
        data = next((r for r in results if isinstance(r, dict) and "nps" in r), None)
        if not data:
            return "I couldn't find anything on your record for that — try a wider date range."
        parts = [f"From {data['from']} to {data['to']} you're on NPS {data['nps']} across {data['surveys']} surveys"]
        if data.get("osat") is not None:
            parts[0] += f", with OSAT at {data['osat']}%"
        parts[0] += "."
        if data.get("categories"):
            top = data["categories"][0]
            parts.append(f"Your biggest driver is {top['category']} ({top['count']} cases).")
        parts.append("Want a quick win to work on for your next few calls?")
        return " ".join(parts)

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager: CallbackManagerForLLMRun | None = None,
                  **kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._reply(messages))])

    def _stream(self, messages: list[BaseMessage], stop=None, run_manager: CallbackManagerForLLMRun | None = None,
                **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        msg = self._reply(messages)
        if msg.tool_calls:
            tc = msg.tool_calls[0]
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=[
                {"name": tc["name"], "args": json.dumps(tc["args"]), "id": tc["id"], "index": 0}]))
            return
        words = re.findall(r"\S+\s*", str(msg.content))
        for w in words:
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=w))
            if run_manager:
                run_manager.on_llm_new_token(w, chunk=chunk)
            yield chunk
