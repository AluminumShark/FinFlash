"""Redis-backed per-API-key daily quotas (requests + USD spend).

Falls back to an in-process counter when Redis is unavailable so local dev and
tests work without a running Redis.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict

from core.config import get_settings

logger = logging.getLogger(__name__)


class QuotaExceeded(Exception):
    """Raised when an API key exceeds its daily request or spend quota."""

    def __init__(self, message: str, retry_after: int = 3600) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class _MemoryBackend:
    """Process-local fallback (not shared across workers)."""

    def __init__(self) -> None:
        self._store: dict[str, float] = defaultdict(float)
        self._expiry: dict[str, float] = {}

    async def incr(self, key: str, amount: float, ttl: int) -> float:
        now = time.time()
        if key in self._expiry and self._expiry[key] < now:
            self._store[key] = 0.0
        self._store[key] += amount
        self._expiry.setdefault(key, now + ttl)
        return self._store[key]


class QuotaManager:
    """Tracks daily usage per API key."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._redis = None
        self._memory = _MemoryBackend()

    async def _backend(self):
        if self._redis is not None:
            return self._redis
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(self.settings.redis_url, decode_responses=True)
            await client.ping()
            self._redis = client
            return client
        except Exception as exc:  # pragma: no cover - infra dependent
            logger.warning("Redis unavailable, using in-memory quota backend: %s", exc)
            return None

    async def _incr(self, key: str, amount: float, ttl: int) -> float:
        backend = await self._backend()
        if backend is None:
            return await self._memory.incr(key, amount, ttl)
        pipe = backend.pipeline()
        pipe.incrbyfloat(key, amount)
        pipe.expire(key, ttl, nx=True)
        result = await pipe.execute()
        return float(result[0])

    async def check_request(self, key_id: str) -> None:
        """Increment the request counter and enforce the daily request quota."""
        limit = self.settings.quota_daily_requests
        if limit <= 0:
            return
        count = await self._incr(f"quota:req:{key_id}", 1, ttl=86400)
        if count > limit:
            raise QuotaExceeded(
                f"Daily request quota ({limit}) exceeded for this API key."
            )

    async def add_cost(self, key_id: str, cost_usd: float) -> None:
        """Record spend and enforce the daily USD quota."""
        limit = self.settings.quota_daily_usd
        if limit <= 0 or cost_usd <= 0:
            return
        spent = await self._incr(f"quota:usd:{key_id}", cost_usd, ttl=86400)
        if spent > limit:
            raise QuotaExceeded(
                f"Daily spend quota (${limit}) exceeded for this API key."
            )

    async def usage(self, key_id: str) -> dict[str, float]:
        backend = await self._backend()
        if backend is None:
            return {"requests": 0, "usd": 0.0}
        req = await backend.get(f"quota:req:{key_id}")
        usd = await backend.get(f"quota:usd:{key_id}")
        return {"requests": float(req or 0), "usd": float(usd or 0)}


_manager: QuotaManager | None = None


def get_quota_manager() -> QuotaManager:
    global _manager
    if _manager is None:
        _manager = QuotaManager()
    return _manager
