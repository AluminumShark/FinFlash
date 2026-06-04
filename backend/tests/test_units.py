"""Unit tests for quota enforcement, output schemas, and LLM config resolution."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from agents.outputs import SentimentOutput
from app.deps import resolve_llm
from core.config import Settings
from services.llm import PROVIDER_DEFAULT_MODEL, LLMConfig
from services.rate_limiter import QuotaExceeded, QuotaManager


def test_auth_required_defaults_by_env():
    # Unset -> on only in production.
    assert Settings(FINFLASH_ENV="development", REQUIRE_API_KEY=None).auth_required is False
    assert Settings(FINFLASH_ENV="production", REQUIRE_API_KEY=None).auth_required is True
    # Explicit override wins.
    assert Settings(FINFLASH_ENV="production", REQUIRE_API_KEY=False).auth_required is False
    assert Settings(FINFLASH_ENV="development", REQUIRE_API_KEY=True).auth_required is True


@pytest.mark.asyncio
async def test_quota_blocks_after_limit(monkeypatch):
    qm = QuotaManager()
    monkeypatch.setattr(qm.settings, "quota_daily_requests", 2, raising=False)
    await qm.check_request("k1")
    await qm.check_request("k1")
    with pytest.raises(QuotaExceeded):
        await qm.check_request("k1")


@pytest.mark.asyncio
async def test_spend_quota(monkeypatch):
    qm = QuotaManager()
    monkeypatch.setattr(qm.settings, "quota_daily_usd", 0.05, raising=False)
    await qm.add_cost("k2", 0.04)
    with pytest.raises(QuotaExceeded):
        await qm.add_cost("k2", 0.02)


@pytest.mark.asyncio
async def test_search_news_dedupes_by_id(monkeypatch):
    from services import news_search

    async def fake_rss(query, num_results):
        return [
            {"id": "x", "title": "a", "content": "c1"},
            {"id": "x", "title": "b", "content": "c2"},  # duplicate id
            {"id": "y", "title": "c", "content": "c3"},
        ]

    monkeypatch.setattr(news_search, "using_exa", lambda: False)
    monkeypatch.setattr(news_search, "_google_news_rss", fake_rss)
    articles = await news_search.search_news("q", num_results=5)
    assert [a["id"] for a in articles] == ["x", "y"]


def test_resolve_llm_defaults():
    resolved = resolve_llm(x_llm_provider=None, x_llm_model=None, x_llm_key=None)
    assert isinstance(resolved.cfg, LLMConfig)
    assert resolved.cfg.model  # falls back to default


def test_resolve_llm_provider_to_model():
    resolved = resolve_llm(x_llm_provider="gemini", x_llm_model=None, x_llm_key="k")
    assert resolved.cfg.model == PROVIDER_DEFAULT_MODEL["gemini"]
    assert resolved.key == "k"


def test_resolve_llm_bare_model_gets_prefix():
    resolved = resolve_llm(x_llm_provider="openai", x_llm_model="gpt-5", x_llm_key=None)
    assert resolved.cfg.model == "openai/gpt-5"


def test_sentiment_score_percentage_is_normalized():
    """A model returning 0-100 percentages is coerced to 0-1."""
    out = SentimentOutput.model_validate(
        {
            "overall_sentiment": "positive",
            "sentiment_score": 80,  # percentage -> 0.8
            "confidence": 95,  # -> 0.95
            "fear_greed_index": 70,
            "market_impact": {"immediate": "high", "short_term": "x", "long_term": "y"},
            "sentiment_breakdown": {},
            "investor_sentiment": "neutral",
            "recommendation": "n/a",
        }
    )
    assert out.sentiment_score == 0.8
    assert out.confidence == 0.95


def test_sentiment_schema_rejects_truly_out_of_range():
    with pytest.raises(ValidationError):
        SentimentOutput.model_validate(
            {
                "overall_sentiment": "positive",
                "sentiment_score": 150,  # >100, not a percentage -> invalid
                "confidence": 0.5,
                "fear_greed_index": 50,
                "market_impact": {"immediate": "low", "short_term": "x", "long_term": "y"},
                "sentiment_breakdown": {},
                "investor_sentiment": "neutral",
                "recommendation": "n/a",
            }
        )
