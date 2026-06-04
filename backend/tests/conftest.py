"""Test fixtures: in-memory-ish SQLite DB, ASGI client, and a mocked LLM client.

Environment must be configured BEFORE the app modules import their settings.
"""
from __future__ import annotations

import os
import tempfile

# --- configure environment before importing the app ---
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.environ.update(
    {
        "FINFLASH_ENV": "testing",
        "REQUIRE_API_KEY": "true",  # exercise auth in tests (off by default in dev)
        "DATABASE_URL": f"sqlite+aiosqlite:///{_DB_PATH}",
        "REDIS_URL": "redis://localhost:6399/0",  # unreachable -> memory fallback
        "DEFAULT_LLM_MODEL": "openai/gpt-5",
        "OPENAI_API_KEY": "test-key",
        "QUOTA_DAILY_REQUESTS": "1000",
        "QUOTA_DAILY_USD": "0",
    }
)

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from agents.outputs import (  # noqa: E402
    ExtractionOutput,
    InvestmentVerdict,
    RiskOutput,
    SentimentOutput,
    SummaryOutput,
)
from app.auth import create_api_key  # noqa: E402
from app.main import create_app  # noqa: E402
from core.database import init_db  # noqa: E402


def _fake_structured(schema):
    """Return a minimal valid instance for each output schema."""
    if schema is SentimentOutput:
        return SentimentOutput.model_validate(
            {
                "overall_sentiment": "positive",
                "sentiment_score": 0.8,
                "confidence": 0.9,
                "fear_greed_index": 70,
                "market_impact": {
                    "immediate": "high",
                    "short_term": "positive",
                    "long_term": "neutral",
                },
                "sentiment_breakdown": {"positive_aspects": ["growth"]},
                "investor_sentiment": "risk-on",
                "recommendation": "Consider exposure.",
            }
        )
    if schema is ExtractionOutput:
        return ExtractionOutput.model_validate(
            {
                "entities": {"companies": [{"name": "Apple", "ticker": "AAPL"}]},
                "event_type": "earnings_announcement",
                "event_details": {"description": "Record earnings"},
            }
        )
    if schema is RiskOutput:
        return RiskOutput.model_validate(
            {
                "risk_summary": {
                    "overall_risk_level": "medium",
                    "primary_risks": ["volatility"],
                    "risk_score": 45,
                },
                "impact_analysis": {"scope": "company"},
                "investment_implications": {
                    "recommendation": "hold",
                    "confidence_level": "medium",
                },
            }
        )
    if schema is SummaryOutput:
        return SummaryOutput.model_validate(
            {
                "executive_summary": {
                    "key_findings": ["Strong quarter"],
                    "market_outlook": "Positive",
                    "confidence_level": "high",
                },
                "key_insights": ["Earnings beat"],
            }
        )
    if schema is InvestmentVerdict:
        return InvestmentVerdict.model_validate(
            {
                "company": "TestCo",
                "recommendation": "hold",
                "confidence": 0.7,
                "rationale": "Mixed signals.",
                "key_catalysts": ["AI demand"],
                "key_risks": ["competition"],
            }
        )
    raise AssertionError(f"Unexpected schema {schema}")


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch):
    """Replace network LLM calls with deterministic structured outputs."""

    async def fake_structured(self, messages, schema, cfg, usage=None):
        if usage is not None:
            usage.add(cfg.model, 100, 50, 0.001)
        return _fake_structured(schema)

    monkeypatch.setattr(
        "services.llm.LLMClient.structured", fake_structured, raising=True
    )

    async def fake_embed(text, **kwargs):
        return [0.1] * 8

    monkeypatch.setattr("rag.store.embed_text", fake_embed, raising=True)


@pytest_asyncio.fixture
async def app():
    application = create_app()
    await init_db()
    return application


@pytest_asyncio.fixture
async def api_key() -> str:
    return await create_api_key("test")


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
