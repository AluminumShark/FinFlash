"""Admin endpoints: API-key management and quota usage.

Creating a key requires an existing valid key (the first key is bootstrapped on
startup and logged once).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import ApiKey, create_api_key, require_api_key
from app.schemas import CreateKeyRequest, CreateKeyResponse
from core.config import get_settings
from core.maintenance import purge_old_data
from services.rate_limiter import get_quota_manager

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/keys", response_model=CreateKeyResponse)
async def create_key(body: CreateKeyRequest, _: ApiKey = Depends(require_api_key)):
    plaintext = await create_api_key(body.name)
    return CreateKeyResponse(name=body.name, api_key=plaintext)


@router.get("/usage")
async def my_usage(api_key: ApiKey = Depends(require_api_key)):
    usage = await get_quota_manager().usage(api_key.id)
    return {"api_key": api_key.name, "today": usage}


@router.post("/cleanup")
async def cleanup(days: int | None = None, _: ApiKey = Depends(require_api_key)):
    """Purge news + analyses older than `days` (defaults to DATA_RETENTION_DAYS).

    `days` is clamped up to CLEANUP_MIN_AGE_DAYS so this endpoint can never delete
    recent data, even on an auth-disabled instance.
    """
    settings = get_settings()
    requested = days if days is not None else settings.data_retention_days
    if requested <= 0:
        return {
            "retention_days": 0,
            "deleted": {"news": 0, "analyses": 0},
            "note": "Nothing purged. Pass ?days=N or set DATA_RETENTION_DAYS.",
        }
    effective = max(requested, settings.cleanup_min_age_days)
    deleted = await purge_old_data(effective)
    return {"retention_days": effective, "deleted": deleted}
