"""FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import ensure_bootstrap_key
from app.routers import admin, analysis, news, reports
from core.config import get_settings
from core.database import init_db as _init_db
from core.database import ping
from core.maintenance import cleanup_loop
from core.observability import setup_observability

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_observability()
    settings = get_settings()
    logger.info("Starting FinFlash backend (env=%s)", settings.env)
    await _init_db()
    if settings.auth_required:
        await ensure_bootstrap_key()

    cleanup_task: asyncio.Task | None = None
    if settings.data_retention_days > 0:
        cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("Data retention enabled: %d days", settings.data_retention_days)

    yield

    if cleanup_task is not None:
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task
    logger.info("Shutting down FinFlash backend")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="FinFlash API",
        version="1.0.0",
        description="Financial News Multi-Agent Analysis System (FastAPI + LangGraph)",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for module in (analysis, news, reports, admin):
        app.include_router(module.router)

    @app.get("/health", tags=["system"])
    async def health() -> dict:
        return {
            "status": "ok",
            "database": "healthy" if await ping() else "unhealthy",
            "default_model": settings.default_llm_model,
        }

    return app


app = create_app()
