from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore")

    # --- core ---
    env: str = "dev"  # dev | test | prod
    app_name: str = "BuddyBud AI Coach"
    database_url: str = f"sqlite:///{BACKEND_DIR / 'buddybud.db'}"
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    access_token_minutes: int = 60 * 12
    cors_origins: str = "http://localhost:5173"
    frontend_url: str = "http://localhost:5173"
    serve_frontend_dir: str = ""  # path to frontend/dist to serve the SPA from the API (single-service deploy)

    # --- LLM ---
    llm_provider: str = "fake"  # anthropic | ollama | fake
    llm_model: str = "claude-haiku-5-5"
    llm_classifier_model: str = "claude-haiku-5-5"
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    llm_temperature: float = 0.4
    llm_max_tokens: int = 700
    coach_history_turns: int = 10
    coach_rate_limit_per_10min: int = 30
    safety_llm_check: bool = True

    # --- email (password reset / invites). Empty host = links are logged to the console. ---
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "BuddyBud <no-reply@example.com>"

    # --- ML ---
    model_dir: str = str(BACKEND_DIR / "models")

    # --- LangSmith (optional; set LANGSMITH_TRACING=true + LANGSMITH_API_KEY in env to trace) ---

    @field_validator("database_url")
    @classmethod
    def _psycopg3(cls, v: str) -> str:
        """Hosting providers hand out postgres:// URLs; we use the psycopg (v3) driver."""
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
