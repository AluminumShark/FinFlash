"""Application settings loaded from environment (pydantic-settings)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration.

    Values are read from environment variables / a local ``.env`` file.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    env: str = Field(default="development", alias="FINFLASH_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    # Require an X-API-Key on /api routes. If unset, defaults to ON only in
    # production — so local dev/testing needs no key, public deploys are gated.
    require_api_key: bool | None = Field(default=None, alias="REQUIRE_API_KEY")

    @property
    def auth_required(self) -> bool:
        if self.require_api_key is not None:
            return self.require_api_key
        return self.env == "production"

    # Infra
    database_url: str = Field(
        default="sqlite+aiosqlite:///./financial_news.db", alias="DATABASE_URL"
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # Default (fallback) provider keys — used only when a request omits its own key.
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")

    default_llm_model: str = Field(default="openai/gpt-5", alias="DEFAULT_LLM_MODEL")
    default_embedding_model: str = Field(
        default="openai/text-embedding-3-small", alias="DEFAULT_EMBEDDING_MODEL"
    )
    # Vector dimension of the embedding model (pgvector column width).
    # openai text-embedding-3-small = 1536; gemini text-embedding-004 = 768.
    embedding_dim: int = Field(default=1536, alias="EMBEDDING_DIM")

    # RAG retrieval only considers news collected within this many days (0 = no
    # limit), so stale articles aren't injected as "historical context".
    rag_max_age_days: int = Field(default=90, alias="RAG_MAX_AGE_DAYS")

    # Auto-purge news + analyses older than this many days (0 = keep forever).
    # When > 0, a background task runs every `cleanup_interval_hours`.
    data_retention_days: int = Field(default=0, alias="DATA_RETENTION_DAYS")
    cleanup_interval_hours: int = Field(default=24, alias="CLEANUP_INTERVAL_HOURS")
    # Safety floor for the manual cleanup endpoint: it can never delete anything
    # newer than this many days, so an open (auth-off) instance can't be used to
    # wipe recent data.
    cleanup_min_age_days: int = Field(default=7, alias="CLEANUP_MIN_AGE_DAYS")
    transcription_model: str = Field(
        default="openai/gpt-4o-transcribe", alias="TRANSCRIPTION_MODEL"
    )

    exa_api_key: str = Field(default="", alias="EXA_API_KEY")

    # Ollama (self-hosted, no key). Set to e.g. http://192.168.0.11:11434 to use
    # local models like ollama_chat/qwen3.6 and ollama/embeddinggemma.
    ollama_api_base: str = Field(default="", alias="OLLAMA_API_BASE")

    # Max concurrent LLM calls (0 = unlimited). Set to 1 for a resource-constrained
    # self-hosted backend so the parallel analysts don't overload it.
    llm_max_concurrency: int = Field(default=0, alias="LLM_MAX_CONCURRENCY")

    # Per-API-key quotas (0 disables the limit)
    quota_daily_requests: int = Field(default=500, alias="QUOTA_DAILY_REQUESTS")
    quota_daily_usd: float = Field(default=10.0, alias="QUOTA_DAILY_USD")

    # Observability
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="finflash", alias="LANGSMITH_PROJECT")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    def default_key_for(self, provider: str) -> str:
        """Return the configured server-side key for a provider, if any."""
        return {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "gemini": self.gemini_api_key,
            "deepseek": self.deepseek_api_key,
        }.get(provider, "")


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
