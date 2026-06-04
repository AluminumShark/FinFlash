"""API-key authentication.

A FinFlash access key gates every ``/api`` route. Only the SHA-256 hash is stored;
the plaintext is returned exactly once at creation. On first startup, if no keys
exist, a bootstrap key is generated and logged so local dev works immediately.
"""
from __future__ import annotations

import hashlib
import logging
import secrets

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.database import ApiKey, get_session, session_scope

logger = logging.getLogger(__name__)

KEY_PREFIX = "ff_"

# Returned when auth is disabled (local dev / self-host) so routes still get an
# ApiKey object for quota bookkeeping without anyone needing a key.
_ANON_KEY = ApiKey(id="anonymous", name="anonymous", key_hash="", active=True)

# Synthetic key returned in dev mode when auth is disabled.
_DEV_KEY = ApiKey(id="dev", name="dev (auth disabled)", key_hash="", active=True)


def generate_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


async def create_api_key(name: str) -> str:
    """Create a key and return its plaintext (shown only once)."""
    plaintext = generate_key()
    async with session_scope() as session:
        session.add(ApiKey(name=name, key_hash=hash_key(plaintext)))
        await session.commit()
    return plaintext


async def ensure_bootstrap_key() -> None:
    """Create a first key if the table is empty (dev convenience)."""
    async with session_scope() as session:
        count = (await session.execute(select(func.count()).select_from(ApiKey))).scalar_one()
        if count:
            return
    plaintext = await create_api_key("bootstrap")
    logger.warning(
        "No API keys found. Created a bootstrap key (store it now, it will not be "
        "shown again): %s",
        plaintext,
    )


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> ApiKey:
    """FastAPI dependency that validates the X-API-Key header.

    No-ops in dev (``auth_required`` False) so local/self-host use needs no key.
    """
    if not get_settings().auth_required:
        return _ANON_KEY
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header.",
        )
    row = (
        await session.execute(
            select(ApiKey).where(
                ApiKey.key_hash == hash_key(x_api_key), ApiKey.active.is_(True)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key."
        )
    return row
