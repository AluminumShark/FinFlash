"""Summary report endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_api_key
from core.database import AnalysisResult, get_session

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("")
async def list_reports(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _=Depends(require_api_key),
):
    rows = (
        await session.execute(
            select(AnalysisResult)
            .where(AnalysisResult.agent_type == "summary")
            .order_by(AnalysisResult.analysis_date.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {"items": [r.to_dict() for r in rows]}
