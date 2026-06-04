"""News browsing endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_api_key
from core.database import AnalysisResult, News, get_session

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("")
async def list_news(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    _=Depends(require_api_key),
):
    rows = (
        await session.execute(
            select(News).order_by(News.collected_date.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return {"items": [n.to_dict() for n in rows], "limit": limit, "offset": offset}


@router.get("/{news_id}")
async def get_news(
    news_id: str,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_api_key),
):
    news = await session.get(News, news_id)
    if news is None:
        raise HTTPException(status_code=404, detail="News not found.")
    analyses = (
        await session.execute(
            select(AnalysisResult).where(AnalysisResult.news_id == news_id)
        )
    ).scalars().all()
    return {
        "news": news.to_dict(),
        "analyses": {a.agent_type: a.result for a in analyses},
    }
