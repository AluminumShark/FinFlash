"""Provider-agnostic text embeddings via LiteLLM (used by the RAG layer).

Embeddings are a *deployment-level* setting: the model/provider/key come from the
server's configuration (``DEFAULT_EMBEDDING_MODEL`` + the matching provider key, or a
self-hosted Ollama endpoint), not from per-request BYO keys. This keeps the stored
vector dimension consistent across all requests.
"""
from __future__ import annotations

import logging

import litellm

from core.config import get_settings
from services.llm import LLMError

logger = logging.getLogger(__name__)


async def embed_texts(texts: list[str], *, model: str | None = None) -> list[list[float]]:
    """Embed a batch of texts. Returns one vector per input."""
    if not texts:
        return []
    settings = get_settings()
    model = model or settings.default_embedding_model
    provider = model.split("/", 1)[0] if "/" in model else "openai"

    kwargs: dict[str, str] = {}
    if provider.startswith("ollama"):
        if not settings.ollama_api_base:
            raise LLMError("OLLAMA_API_BASE is required for Ollama embeddings.")
        kwargs["api_base"] = settings.ollama_api_base
    else:
        key = settings.default_key_for(provider)
        if not key:
            raise LLMError(f"No server-side API key for embedding provider '{provider}'.")
        kwargs["api_key"] = key

    resp = await litellm.aembedding(model=model, input=texts, **kwargs)
    return [item["embedding"] for item in resp["data"]]


async def embed_text(text: str, *, model: str | None = None) -> list[float]:
    vectors = await embed_texts([text], model=model)
    return vectors[0]
