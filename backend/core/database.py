"""Async database layer: SQLAlchemy 2.0 models + engine/session management.

Supports Postgres (with pgvector for RAG) and SQLite (local dev, embeddings
stored as JSON and compared in Python). The embedding column type is chosen at
import time from the configured ``DATABASE_URL``.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from core.config import get_settings

settings = get_settings()

EMBED_DIM = settings.embedding_dim

# Choose the embedding column type based on the backing database.
if settings.is_postgres:
    from pgvector.sqlalchemy import Vector

    EmbeddingType: object = Vector(EMBED_DIM)
else:
    EmbeddingType = JSON


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class News(Base):
    __tablename__ = "news"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500))
    author: Mapped[str | None] = mapped_column(String(200))
    published_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    language: Mapped[str] = mapped_column(String(10), default="en")
    news_type: Mapped[str | None] = mapped_column(String(50))  # text/audio/video
    original_audio_path: Mapped[str | None] = mapped_column(String(500))
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding = mapped_column(EmbeddingType, nullable=True)  # type: ignore[var-annotated]
    extra_metadata: Mapped[dict | None] = mapped_column(JSON)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "source_url": self.source_url,
            "author": self.author,
            "published_date": self.published_date.isoformat()
            if self.published_date
            else None,
            "collected_date": self.collected_date.isoformat()
            if self.collected_date
            else None,
            "language": self.language,
            "news_type": self.news_type,
            "confidence_score": self.confidence_score,
            "processed": self.processed,
            "metadata": self.extra_metadata,
        }


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    news_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    analysis_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    processing_time: Mapped[float | None] = mapped_column(Float)
    model_used: Mapped[str | None] = mapped_column(String(80))
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "news_id": self.news_id,
            "agent_type": self.agent_type,
            "analysis_date": self.analysis_date.isoformat()
            if self.analysis_date
            else None,
            "result": self.result,
            "confidence": self.confidence,
            "processing_time": self.processing_time,
            "model_used": self.model_used,
            "tokens_used": self.tokens_used,
            "error_message": self.error_message,
        }


class BatchJob(Base):
    __tablename__ = "batch_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    started_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    processed_items: Mapped[int] = mapped_column(Integer, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_type": self.job_type,
            "status": self.status,
            "created_date": self.created_date.isoformat()
            if self.created_date
            else None,
            "started_date": self.started_date.isoformat()
            if self.started_date
            else None,
            "completed_date": self.completed_date.isoformat()
            if self.completed_date
            else None,
            "total_items": self.total_items,
            "processed_items": self.processed_items,
            "failed_items": self.failed_items,
            "error_message": self.error_message,
            "metadata": self.extra_metadata,
        }


class ApiKey(Base):
    """A FinFlash access key. Only the hash is stored; the plaintext is shown once."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON)


# ---- Engine / session management ----

_engine = create_async_engine(settings.database_url, pool_pre_ping=True, future=True)
_SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


async def init_db() -> None:
    """Create the pgvector extension (if Postgres) and all tables."""
    async with _engine.begin() as conn:
        if settings.is_postgres:
            from sqlalchemy import text

            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a transactional async session."""
    async with _SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def session_scope() -> AsyncSession:
    """Create a standalone session (caller manages its lifecycle)."""
    return _SessionLocal()


async def ping() -> bool:
    """Lightweight connectivity check for /health."""
    from sqlalchemy import text

    try:
        async with _SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


__all__ = [
    "EMBED_DIM",
    "AnalysisResult",
    "ApiKey",
    "Base",
    "BatchJob",
    "News",
    "get_session",
    "init_db",
    "ping",
    "select",
    "session_scope",
]
