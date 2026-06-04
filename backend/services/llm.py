"""Multi-provider LLM client built on LiteLLM.

Features
--------
* One interface for OpenAI / Anthropic / Gemini / DeepSeek (and any LiteLLM model).
* Bring-your-own-key (BYO): each request may carry its own provider + API key.
* Structured outputs via Pydantic schema + constrained decoding (with a retry that
  feeds validation errors back to the model) — replaces the legacy ``json_object`` mode.
* Per-call token + USD cost accounting (LiteLLM's live pricing, not a 2024 table).
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, TypeVar

import litellm
from pydantic import BaseModel, ValidationError

from core.config import get_settings

logger = logging.getLogger(__name__)

# LiteLLM is verbose by default and raises for unmapped params on some providers.
litellm.drop_params = True
litellm.suppress_debug_info = True  # ty: ignore[invalid-assignment]

T = TypeVar("T", bound=BaseModel)

# Friendly provider name -> a sensible default LiteLLM model id.
# Use model ids that actually exist on each provider's API today.
PROVIDER_DEFAULT_MODEL = {
    "openai": "openai/gpt-5",
    "anthropic": "anthropic/claude-opus-4-6",
    "gemini": "gemini/gemini-2.5-flash",
    "deepseek": "deepseek/deepseek-chat",
}


class LLMError(RuntimeError):
    """Raised when the LLM call fails after retries."""


@dataclass
class LLMConfig:
    """Resolved per-request model configuration."""

    model: str
    api_key: str | None = None
    temperature: float = 0.4
    api_base: str | None = None  # for self-hosted backends (Ollama)

    @property
    def provider(self) -> str:
        return self.model.split("/", 1)[0] if "/" in self.model else "openai"

    @property
    def is_ollama(self) -> bool:
        return self.provider.startswith("ollama")


@dataclass
class Usage:
    """Accumulated usage for a single graph run (or any scope)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0
    per_model: dict[str, int] = field(default_factory=dict)

    def add(self, model: str, prompt: int, completion: int, cost: float) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += prompt + completion
        self.cost_usd += cost
        self.calls += 1
        self.per_model[model] = self.per_model.get(model, 0) + prompt + completion

    def as_dict(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "calls": self.calls,
            "per_model": self.per_model,
        }


class LLMClient:
    """Thin async wrapper around ``litellm.acompletion``.

    A single client is shared across the app; the model + key vary per call so
    that BYO-key requests never leak between callers.
    """

    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries
        self.settings = get_settings()
        n = self.settings.llm_max_concurrency
        # A semaphore caps concurrent provider calls; 0 means unlimited.
        self._sem: asyncio.Semaphore | None = asyncio.Semaphore(n) if n > 0 else None

    def _key_for(self, cfg: LLMConfig) -> str | None:
        if cfg.is_ollama:
            return None  # self-hosted Ollama needs no API key
        if cfg.api_key:
            return cfg.api_key
        key = self.settings.default_key_for(cfg.provider)
        if not key:
            raise LLMError(
                f"No API key for provider '{cfg.provider}'. Supply X-LLM-Key or "
                f"configure a server-side key."
            )
        return key

    def _api_base_for(self, cfg: LLMConfig) -> str | None:
        if cfg.api_base:
            return cfg.api_base
        if cfg.is_ollama:
            return self.settings.ollama_api_base or None
        return None

    async def complete(
        self,
        messages: list[dict[str, str]],
        cfg: LLMConfig,
        usage: Usage | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Plain text completion."""
        resp = await self._call(messages, cfg, usage=usage, max_tokens=max_tokens)
        return resp.choices[0].message.content or ""

    async def structured(
        self,
        messages: list[dict[str, str]],
        schema: type[T],
        cfg: LLMConfig,
        usage: Usage | None = None,
        max_tokens: int = 3000,
    ) -> T:
        """Return a validated instance of ``schema`` using constrained decoding.

        Retries on validation errors by appending the error text to the prompt.
        ``max_tokens`` bounds runaway generation (small local models can loop under
        strict schema constraints and emit tens of KB of garbage otherwise).
        """
        convo = list(messages)
        last_err: Exception | None = None

        for attempt in range(self.max_retries):
            resp = await self._call(
                convo, cfg, usage=usage, response_format=schema, max_tokens=max_tokens
            )
            content = resp.choices[0].message.content or "{}"
            try:
                return schema.model_validate_json(content)
            except ValidationError as exc:
                last_err = exc
                logger.warning(
                    "Structured output validation failed (attempt %d): %s",
                    attempt + 1,
                    exc,
                )
                convo = [
                    *messages,
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            "Your previous response did not match the required schema. "
                            f"Fix these errors and return ONLY valid JSON:\n{exc}"
                        ),
                    },
                ]
        raise LLMError(f"Structured output failed after {self.max_retries} attempts: {last_err}")

    async def _call(
        self,
        messages: list[dict[str, str]],
        cfg: LLMConfig,
        *,
        usage: Usage | None = None,
        response_format: Any = None,
        max_tokens: int | None = None,
    ) -> Any:
        api_key = self._key_for(cfg)
        api_base = self._api_base_for(cfg)
        last_err: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                resp = await self._acompletion(
                    model=cfg.model,
                    messages=messages,
                    api_key=api_key,
                    api_base=api_base,
                    temperature=cfg.temperature,
                    response_format=response_format,
                    max_tokens=max_tokens,
                    num_retries=0,  # we manage retries here
                )
                self._record(resp, cfg, usage)
                return resp
            except (litellm.RateLimitError, litellm.APIConnectionError) as exc:
                last_err = exc
                wait = min(2**attempt, 30)
                logger.warning("LLM transient error, retrying in %ss: %s", wait, exc)
                await asyncio.sleep(wait)
            except litellm.APIError as exc:
                last_err = exc
                logger.error("LLM API error: %s", exc)
                break

        raise LLMError(f"LLM call failed: {last_err}")

    async def _acompletion(self, **kwargs: Any) -> Any:
        """litellm.acompletion gated by the optional concurrency semaphore."""
        if self._sem is None:
            return await litellm.acompletion(**kwargs)
        async with self._sem:
            return await litellm.acompletion(**kwargs)

    def _record(self, resp: Any, cfg: LLMConfig, usage: Usage | None) -> None:
        if usage is None:
            return
        u = getattr(resp, "usage", None)
        prompt = getattr(u, "prompt_tokens", 0) or 0
        completion = getattr(u, "completion_tokens", 0) or 0
        try:
            cost = litellm.completion_cost(completion_response=resp) or 0.0
        except Exception:  # pricing not known for the model
            cost = 0.0
        usage.add(cfg.model, prompt, completion, cost)


def parse_json_block(text: str) -> dict[str, Any]:
    """Best-effort JSON extraction (used where a raw string is unavoidable)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].lstrip("json").strip()
    return json.loads(text)


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
