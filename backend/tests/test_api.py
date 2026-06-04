"""End-to-end API tests (auth, analysis, news) with a mocked LLM."""
from __future__ import annotations

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
async def test_create_key_via_admin(client, api_key):
    resp = await client.post(
        "/api/admin/keys", json={"name": "ci"}, headers={"X-API-Key": api_key}
    )
    assert resp.status_code == 200
    assert resp.json()["api_key"].startswith("ff_")
