"""Data retention: purge old news + analyses, optionally on a background loop."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from core.config import get_settings
from core.database import AnalysisResult, News, session_scope

logger = logging.getLogger(__name__)


async def purge_old_data(days: int) -> dict[str, int]:
    """Delete news + analysis rows older than ``days`` (no-op if days <= 0)."""
    if days <= 0:
        return {"news": 0, "analyses": 0}
    cutoff = datetime.now(UTC) - timedelta(days=days)
    async with session_scope() as session:
        analyses = await session.execute(
            delete(AnalysisResult).where(AnalysisResult.analysis_date < cutoff)
        )
        news = await session.execute(delete(News).where(News.collected_date < cutoff))
        await session.commit()
    # rowcount exists on the runtime CursorResult (ty's stub doesn't model it).
    result = {
        "news": news.rowcount or 0,  # ty: ignore[unresolved-attribute]
        "analyses": analyses.rowcount or 0,  # ty: ignore[unresolved-attribute]
    }
    if result["news"] or result["analyses"]:
        logger.info("Retention purge (>%dd): %s", days, result)
    return result


async def cleanup_loop() -> None:
    """Background task: purge on the configured interval while retention is on."""
    settings = get_settings()
    interval = max(1, settings.cleanup_interval_hours) * 3600
    while True:
        try:
            await purge_old_data(settings.data_retention_days)
        except Exception as exc:  # never let cleanup crash the app
            logger.warning("Cleanup loop error: %s", exc)
        await asyncio.sleep(interval)
