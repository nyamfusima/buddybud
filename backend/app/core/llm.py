"""One place to build chat models. Switch providers with LLM_PROVIDER=anthropic|ollama|fake."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import get_settings


def get_chat_model(purpose: str = "coach") -> BaseChatModel:
    s = get_settings()
    provider = s.llm_provider.lower()
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if not s.anthropic_api_key:
            raise RuntimeError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty.")
        model = s.llm_classifier_model if purpose == "classifier" else s.llm_model
        return ChatAnthropic(
            model=model,
            api_key=s.anthropic_api_key,
            temperature=0 if purpose in ("classifier", "safety") else s.llm_temperature,
            max_tokens=s.llm_max_tokens if purpose == "coach" else 1500,
            max_retries=2,
            timeout=60,
        )
    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("Install the ollama extra: uv sync --extra ollama") from e
        return ChatOllama(model=s.ollama_model, base_url=s.ollama_base_url,
                          temperature=0 if purpose != "coach" else s.llm_temperature)
    from app.core.fake_llm import FakeCoachModel

    return FakeCoachModel()


def provider_info() -> dict:
    s = get_settings()
    model = {"anthropic": s.llm_model, "ollama": s.ollama_model}.get(s.llm_provider, "fake-offline")
    return {"provider": s.llm_provider, "model": model}
