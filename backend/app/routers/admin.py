"""Admin endpoints: API-key management and quota usage.

Creating a key requires an existing valid key (the first key is bootstrapped on
startup and logged once).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import ApiKey, create_api_key, require_api_key
from app.schemas import CreateKeyRequest, CreateKeyResponse
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
