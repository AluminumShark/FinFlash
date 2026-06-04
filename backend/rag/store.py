"""Persisting news embeddings and similarity search.

Uses pgvector's ``<=>`` cosine distance on Postgres; on SQLite it falls back to
loading candidate rows and computing cosine similarity in Python. Retrieval is
limited to recently-collected news so stale articles aren't used as context.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.database import News
from services.embeddings import embed_text

logger = logging.getLogger(__name__)


async def store_embedding(session: AsyncSession, news_id: str, text: str) -> None:
    """Compute and persist the embedding for a news row (best-effort, idempotent)."""
    news = await session.get(News, news_id)
    if news is None or news.embedding is not None:
        return  # no row, or already embedded — skip (dedup + saves compute)
    try:
        vector = await embed_text(text[:8000])
    except Exception as exc:  # embeddings are optional; never fail the pipeline
        logger.warning("Skipping embedding for %s: %s", news_id, exc)
        return
    news.embedding = vector
    await session.flush()


def _cutoff() -> datetime | None:
    days = get_settings().rag_max_age_days
    if days and days > 0:
        return datetime.now(UTC) - timedelta(days=days)
    return None


async def search_similar(
    session: AsyncSession,
    text: str,
    *,
    limit: int = 3,
    exclude_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return the most similar recent news items."""
    try:
        query_vec = await embed_text(text[:8000])
    except Exception as exc:
        logger.warning("Similarity search unavailable: %s", exc)
        return []

    cutoff = _cutoff()
    if get_settings().is_postgres:
        return await _search_pg(session, query_vec, limit, exclude_id, cutoff)
    return await _search_python(session, query_vec, limit, exclude_id, cutoff)


async def _search_pg(
    session: AsyncSession,
    query_vec: list[float],
    limit: int,
    exclude_id: str | None,
    cutoff: datetime | None,
) -> list[dict[str, Any]]:
    stmt = select(
        News, News.embedding.cosine_distance(query_vec).label("distance")
    ).where(News.embedding.is_not(None))
    if cutoff is not None:
        stmt = stmt.where(News.collected_date >= cutoff)
    stmt = stmt.order_by("distance").limit(limit + 1)

    rows = (await session.execute(stmt)).all()
    out = []
    for news, distance in rows:
        if exclude_id and news.id == exclude_id:
            continue
        out.append({"news": news, "similarity": 1 - float(distance)})
    return out[:limit]


async def _search_python(
    session: AsyncSession,
    query_vec: list[float],
    limit: int,
    exclude_id: str | None,
    cutoff: datetime | None,
) -> list[dict[str, Any]]:
    stmt = select(News).where(News.embedding.is_not(None))
    if cutoff is not None:
        stmt = stmt.where(News.collected_date >= cutoff)
    rows = (await session.execute(stmt)).scalars().all()
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
