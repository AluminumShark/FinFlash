"""Persisting news embeddings and similarity search.

Uses pgvector's ``<=>`` cosine distance on Postgres; on SQLite it falls back to
loading candidate rows and computing cosine similarity in Python.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.database import News
from services.embeddings import embed_text

logger = logging.getLogger(__name__)


async def store_embedding(session: AsyncSession, news_id: str, text: str) -> None:
    """Compute and persist the embedding for a news row (best-effort)."""
    try:
        vector = await embed_text(text[:8000])
    except Exception as exc:  # embeddings are optional; never fail the pipeline
        logger.warning("Skipping embedding for %s: %s", news_id, exc)
        return
    news = await session.get(News, news_id)
    if news is not None:
        news.embedding = vector
        await session.flush()


async def search_similar(
    session: AsyncSession,
    text: str,
    *,
    limit: int = 3,
    exclude_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return the most similar previously-stored news items."""
    try:
        query_vec = await embed_text(text[:8000])
    except Exception as exc:
        logger.warning("Similarity search unavailable: %s", exc)
        return []

    settings = get_settings()
    if settings.is_postgres:
        return await _search_pg(session, query_vec, limit, exclude_id)
    return await _search_python(session, query_vec, limit, exclude_id)


async def _search_pg(
    session: AsyncSession, query_vec: list[float], limit: int, exclude_id: str | None
) -> list[dict[str, Any]]:
    stmt = (
        select(News, News.embedding.cosine_distance(query_vec).label("distance"))
        .where(News.embedding.is_not(None))
        .order_by("distance")
        .limit(limit + 1)
    )
    rows = (await session.execute(stmt)).all()
    out = []
    for news, distance in rows:
        if exclude_id and news.id == exclude_id:
            continue
        out.append({"news": news, "similarity": 1 - float(distance)})
    return out[:limit]


async def _search_python(
    session: AsyncSession, query_vec: list[float], limit: int, exclude_id: str | None
) -> list[dict[str, Any]]:
    rows = (await session.execute(select(News).where(News.embedding.is_not(None)))).scalars().all()
    scored = []
    for news in rows:
        if exclude_id and news.id == exclude_id:
            continue
        emb = news.embedding
        if not emb:
            continue
        scored.append({"news": news, "similarity": _cosine(query_vec, emb)})
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:limit]


def _cosine(a: list[float], b: list[float]) -> float:
    import math

    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
