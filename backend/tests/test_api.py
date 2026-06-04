"""End-to-end API tests (auth, analysis, news) with a mocked LLM."""
from __future__ import annotations

from datetime import UTC

import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_text_analysis_requires_key(client):
    resp = await client.post("/api/analysis/text", json={"content": "Apple beats earnings."})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_text_analysis_rejects_bad_key(client):
    resp = await client.post(
        "/api/analysis/text",
        json={"content": "Apple beats earnings."},
        headers={"X-API-Key": "ff_not_a_real_key"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_text_analysis_happy_path(client, api_key):
    resp = await client.post(
        "/api/analysis/text",
        json={
            "content": "Apple reports record Q4 earnings.",
            "title": "Apple",
            "enable_rag": False,
        },
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("completed", "completed_with_errors")
    assert body["analyses"]["sentiment"]["overall_sentiment"] == "positive"
    assert body["analyses"]["risk"]["risk_summary"]["risk_score"] == 45
    assert body["summary"]["executive_summary"]["confidence_level"] == "high"
    assert body["usage"]["total_tokens"] > 0


@pytest.mark.asyncio
async def test_byo_key_header_overrides_model(client, api_key):
    resp = await client.post(
        "/api/analysis/text",
        json={"content": "Tesla deliveries rise.", "enable_rag": False},
        headers={
            "X-API-Key": api_key,
            "X-LLM-Provider": "anthropic",
            "X-LLM-Key": "byo-secret",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["model"] == "anthropic/claude-opus-4-6"


@pytest.mark.asyncio
async def test_news_persisted_and_listed(client, api_key):
    await client.post(
        "/api/analysis/text",
        json={"content": "Nvidia announces new GPU.", "title": "Nvidia", "enable_rag": False},
        headers={"X-API-Key": api_key},
    )
    resp = await client.get("/api/news", headers={"X-API-Key": api_key})
    assert resp.status_code == 200
    assert resp.json()["items"], "expected at least one persisted news item"


@pytest.mark.asyncio
async def test_company_verdict(client, api_key, monkeypatch):
    async def fake_search(company, *, num_results=5, days_back=14):
        return [
            {"id": "a1", "title": "TestCo beats earnings", "source": "Reuters",
             "url": "http://x/1", "content": "TestCo beat earnings.", "published_date": None},
            {"id": "a2", "title": "TestCo faces competition", "source": "CNBC",
             "url": "http://x/2", "content": "Rivals emerge.", "published_date": None},
        ]

    monkeypatch.setattr("app.routers.analysis.search_news", fake_search, raising=True)
    resp = await client.post(
        "/api/analysis/company",
        json={"company": "TestCo", "num_results": 2},
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["articles_analyzed"] == 2
    assert body["verdict"]["recommendation"] == "hold"
    assert len(body["sources"]) == 2


@pytest.mark.asyncio
async def test_persist_dedups_analysis_rows(app):
    """Re-analyzing the same news_id replaces rows instead of piling up duplicates."""
    from agents.graph import run_analysis
    from core.database import AnalysisResult, select, session_scope
    from services.llm import LLMConfig

    cfg = LLMConfig(model="openai/gpt-5")
    for _ in range(2):
        await run_analysis(
            content="Acme posts strong results.", title="Acme",
            news_id="dedup-news-1", llm=cfg, enable_rag=False,
        )

    async with session_scope() as session:
        rows = (
            await session.execute(
                select(AnalysisResult).where(
                    AnalysisResult.news_id == "dedup-news-1",
                    AnalysisResult.agent_type == "sentiment",
                )
            )
        ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_persist_partial_failure_replaces_without_stale_mix(app):
    """A re-run where one node failed leaves no stale row from the prior run."""
    from agents.nodes.analysis import persist_node
    from core.database import AnalysisResult, select, session_scope
    from services.llm import LLMConfig

    base = {
        "news_id": "p1", "title": "t", "content": "c",
        "llm": LLMConfig(model="openai/gpt-5"), "enable_rag": False,
    }
    # First run: all four analysts succeed.
    await persist_node({**base, "sentiment": {"v": 1}, "extraction": {"v": 1},
                        "risk": {"v": 1}, "summary": {"v": 1}})
    # Second run: risk failed.
    await persist_node({**base, "sentiment": {"v": 2}, "extraction": {"v": 2},
                        "risk": {"error": "boom"}, "summary": {"v": 2}})

    async with session_scope() as session:
        types = sorted(
            (await session.execute(
                select(AnalysisResult.agent_type).where(AnalysisResult.news_id == "p1")
            )).scalars().all()
        )
    assert types == ["extraction", "sentiment", "summary"]  # no stale 'risk'


@pytest.mark.asyncio
async def test_retention_purge_removes_old_only(app):
    """purge_old_data deletes rows older than the cutoff and keeps recent ones."""
    from datetime import datetime, timedelta

    from core.database import News, select, session_scope
    from core.maintenance import purge_old_data

    now = datetime.now(UTC)
    async with session_scope() as session:
        session.add(News(id="old-1", title="old", content="x", news_type="text",
                         collected_date=now - timedelta(days=200)))
        session.add(News(id="new-1", title="new", content="x", news_type="text",
                         collected_date=now - timedelta(days=1)))
        await session.commit()

    result = await purge_old_data(90)
    assert result["news"] >= 1

    async with session_scope() as session:
        ids = set((await session.execute(select(News.id))).scalars().all())
    assert "old-1" not in ids
    assert "new-1" in ids


@pytest.mark.asyncio
async def test_cleanup_endpoint_respects_min_age_floor(client, api_key):
    """days below CLEANUP_MIN_AGE_DAYS is clamped up, protecting recent data."""
    from datetime import datetime, timedelta

    from core.database import News, select, session_scope

    now = datetime.now(UTC)
    async with session_scope() as session:
        session.add(News(id="recent", title="r", content="x", news_type="text",
                         collected_date=now - timedelta(days=3)))
        session.add(News(id="ancient", title="a", content="x", news_type="text",
                         collected_date=now - timedelta(days=100)))
        await session.commit()

    resp = await client.post("/api/admin/cleanup?days=1", headers={"X-API-Key": api_key})
    assert resp.status_code == 200
    assert resp.json()["retention_days"] == 7  # clamped up from 1 to the floor

    async with session_scope() as session:
        ids = set((await session.execute(select(News.id))).scalars().all())
    assert "recent" in ids  # 3 days old < 7-day floor → protected
    assert "ancient" not in ids


@pytest.mark.asyncio
async def test_purge_removes_orphan_analyses(app):
    """Purging old news also removes its analyses even if they're recent."""
    from datetime import datetime, timedelta

    from core.database import AnalysisResult, News, select, session_scope
    from core.maintenance import purge_old_data

    now = datetime.now(UTC)
    async with session_scope() as session:
        session.add(News(id="oldnews", title="o", content="x", news_type="text",
                         collected_date=now - timedelta(days=200)))
        session.add(AnalysisResult(news_id="oldnews", agent_type="sentiment",
                                   result={}, analysis_date=now))  # recent analysis
        await session.commit()

    await purge_old_data(90)

    async with session_scope() as session:
        news_ids = set((await session.execute(select(News.id))).scalars().all())
        orphans = (
            await session.execute(
                select(AnalysisResult).where(AnalysisResult.news_id == "oldnews")
            )
        ).scalars().all()
    assert "oldnews" not in news_ids
    assert orphans == []  # orphan removed despite being recent


@pytest.mark.asyncio
async def test_create_key_via_admin(client, api_key):
    resp = await client.post(
        "/api/admin/keys", json={"name": "ci"}, headers={"X-API-Key": api_key}
    )
    assert resp.status_code == 200
    assert resp.json()["api_key"].startswith("ff_")
