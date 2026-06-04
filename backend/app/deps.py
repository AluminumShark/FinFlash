"""Shared FastAPI dependencies: LLM config resolution and quota enforcement."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from app.auth import ApiKey, require_api_key
from core.config import get_settings
from services.llm import PROVIDER_DEFAULT_MODEL, LLMConfig
from services.rate_limiter import QuotaExceeded, get_quota_manager


class ResolvedLLM:
    """Carries the per-request model config plus the caller's BYO key (if any)."""

    def __init__(self, cfg: LLMConfig, key: str | None) -> None:
        self.cfg = cfg
        self.key = key


def resolve_llm(
    x_llm_provider: str | None = Header(default=None, alias="X-LLM-Provider"),
    x_llm_model: str | None = Header(default=None, alias="X-LLM-Model"),
    x_llm_key: str | None = Header(default=None, alias="X-LLM-Key"),
    x_llm_api_base: str | None = Header(default=None, alias="X-LLM-Api-Base"),
) -> ResolvedLLM:
    """Resolve which model to use from request headers, with sensible fallbacks."""
    settings = get_settings()

    if x_llm_model:
        model = x_llm_model
        if "/" not in model and x_llm_provider:
            model = f"{x_llm_provider}/{model}"
    elif x_llm_provider:
        if x_llm_provider.startswith("ollama"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="For Ollama, pass X-LLM-Model (e.g. ollama_chat/qwen3.6:latest).",
            )
        model = PROVIDER_DEFAULT_MODEL.get(x_llm_provider)
        if not model:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown provider '{x_llm_provider}'.",
            )
    else:
        model = settings.default_llm_model

    is_ollama = model.split("/", 1)[0].startswith("ollama")
    api_base = x_llm_api_base or (settings.ollama_api_base or None if is_ollama else None)
    cfg = LLMConfig(model=model, api_key=x_llm_key, api_base=api_base)
    return ResolvedLLM(cfg=cfg, key=x_llm_key)


async def enforce_quota(api_key: ApiKey = Depends(require_api_key)) -> ApiKey:
    """Increment and enforce the per-key daily request quota."""
    try:
        await get_quota_manager().check_request(api_key.id)
    except QuotaExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    return api_key
