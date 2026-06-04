"""Analysis endpoints: text, streaming, search, audio, and YouTube."""
from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sse_starlette.sse import EventSourceResponse

from agents.graph import run_analysis, stream_analysis
from agents.verdict import synthesize_verdict
from app.auth import ApiKey
from app.deps import ResolvedLLM, enforce_quota, resolve_llm
from app.schemas import (
    AnalysisResponse,
    CompanyAnalysisRequest,
    CompanyAnalysisResponse,
    SearchAnalysisRequest,
    SearchAnalysisResponse,
    TextAnalysisRequest,
    YouTubeAnalysisRequest,
)
from services.llm import Usage
from services.news_search import search_news
from services.rate_limiter import get_quota_manager
from services.transcription import transcribe

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analysis", tags=["analysis"])


async def _charge(api_key: ApiKey, result: dict[str, Any]) -> None:
    cost = (result.get("usage") or {}).get("cost_usd", 0.0)
    if cost:
        try:
            await get_quota_manager().add_cost(api_key.id, cost)
        except Exception as exc:  # quota overflow shouldn't void a finished analysis
            logger.warning("Failed to record cost: %s", exc)


@router.post("/text", response_model=AnalysisResponse)
async def analyze_text(
    body: TextAnalysisRequest,
    llm: ResolvedLLM = Depends(resolve_llm),
    api_key: ApiKey = Depends(enforce_quota),
):
    result = await run_analysis(
        content=body.content,
        title=body.title,
        llm=llm.cfg,
        llm_key=llm.key,
        enable_rag=body.enable_rag,
    )
    await _charge(api_key, result)
    return result


@router.post("/stream")
async def analyze_text_stream(
    body: TextAnalysisRequest,
    llm: ResolvedLLM = Depends(resolve_llm),
    api_key: ApiKey = Depends(enforce_quota),
):
    """Server-Sent Events: emits a `progress` event per node, then `result`."""

    async def event_gen():
        async for evt in stream_analysis(
            content=body.content,
            title=body.title,
            llm=llm.cfg,
            llm_key=llm.key,
            enable_rag=body.enable_rag,
        ):
            if evt["event"] == "result":
                await _charge(api_key, evt["data"])
                yield {"event": "result", "data": json.dumps(evt["data"])}
            else:
                yield {"event": "progress", "data": json.dumps({"node": evt["node"]})}

    return EventSourceResponse(event_gen())


@router.post("/search", response_model=SearchAnalysisResponse)
async def search_and_analyze(
    body: SearchAnalysisRequest,
    llm: ResolvedLLM = Depends(resolve_llm),
    api_key: ApiKey = Depends(enforce_quota),
):
    articles = await search_news(
        body.query, days_back=body.days_back, num_results=body.num_results
    )
    if not articles:
        return SearchAnalysisResponse(
            query=body.query, total_articles=0, analyzed_successfully=0,
            results=[], aggregate={},
        )

    # Analyze all articles concurrently (true parallelism, not the old for-await loop).
    async def analyze_one(article: dict[str, Any]) -> dict[str, Any]:
        return await run_analysis(
            content=article["content"],
            title=article.get("title", ""),
            news_id=article.get("id"),
            llm=llm.cfg,
            llm_key=llm.key,
            enable_rag=body.enable_rag,
        )

    results = await asyncio.gather(
        *(analyze_one(a) for a in articles), return_exceptions=True
    )
    ok = [r for r in results if isinstance(r, dict)]
    for r in ok:
        await _charge(api_key, r)

    return SearchAnalysisResponse(
        query=body.query,
        total_articles=len(articles),
        analyzed_successfully=len(ok),
        results=[AnalysisResponse.model_validate(r) for r in ok],
        aggregate=_aggregate(ok),
    )


@router.post("/company", response_model=CompanyAnalysisResponse)
async def analyze_company(
    body: CompanyAnalysisRequest,
    llm: ResolvedLLM = Depends(resolve_llm),
    api_key: ApiKey = Depends(enforce_quota),
):
    """Search recent news for a company and return a buy/hold/sell verdict."""
    articles = await search_news(
        body.company, days_back=body.days_back, num_results=body.num_results
    )
    if not articles:
        raise HTTPException(
            status_code=404, detail=f"No recent news found for '{body.company}'."
        )

    async def analyze_one(article: dict[str, Any]) -> dict[str, Any]:
        return await run_analysis(
            content=article["content"],
            title=article.get("title", ""),
            news_id=article.get("id"),
            llm=llm.cfg,
            llm_key=llm.key,
            enable_rag=True,
        )

    results = await asyncio.gather(
        *(analyze_one(a) for a in articles), return_exceptions=True
    )
    ok = [r for r in results if isinstance(r, dict)]
    for r in ok:
        await _charge(api_key, r)

    verdict = None
    if ok:
        usage = Usage()
        try:
            verdict = await synthesize_verdict(body.company, ok, llm=llm.cfg, usage=usage)
            await get_quota_manager().add_cost(api_key.id, usage.cost_usd)
        except Exception as exc:
            logger.error("Verdict synthesis failed: %s", exc)

    sources = [
        {
            "title": a.get("title"),
            "source": a.get("source"),
            "url": a.get("url"),
            "published_date": a.get("published_date"),
        }
        for a in articles
    ]
    return CompanyAnalysisResponse(
        company=body.company,
        verdict=verdict,
        articles_analyzed=len(ok),
        sources=sources,
        aggregate=_aggregate(ok),
        usage={"note": "per-article usage charged individually"},
        model=llm.cfg.model,
    )


@router.post("/audio", response_model=AnalysisResponse)
async def analyze_audio(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    llm: ResolvedLLM = Depends(resolve_llm),
    api_key: ApiKey = Depends(enforce_quota),
):
    suffix = Path(file.filename or "audio.mp3").suffix or ".mp3"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        transcript = await transcribe(tmp_path, api_key=llm.key)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if not transcript.strip():
        raise HTTPException(status_code=422, detail="Transcription produced no text.")

    result = await run_analysis(
        content=transcript,
        title=title or f"Audio: {file.filename}",
        llm=llm.cfg,
        llm_key=llm.key,
    )
    result["transcript"] = transcript
    await _charge(api_key, result)
    return result


@router.post("/youtube", response_model=AnalysisResponse)
async def analyze_youtube(
    body: YouTubeAnalysisRequest,
    llm: ResolvedLLM = Depends(resolve_llm),
    api_key: ApiKey = Depends(enforce_quota),
):
    transcript = await _transcribe_youtube(body.url, api_key=llm.key)
    if not transcript.strip():
        raise HTTPException(status_code=422, detail="Could not transcribe the video.")
    result = await run_analysis(
        content=transcript, title=f"YouTube: {body.url}",
        llm=llm.cfg, llm_key=llm.key, enable_rag=body.enable_rag,
    )
    result["transcript"] = transcript
    await _charge(api_key, result)
    return result


async def _transcribe_youtube(url: str, *, api_key: str | None) -> str:
    import yt_dlp

    with tempfile.TemporaryDirectory() as tmp:
        out = str(Path(tmp) / f"{uuid.uuid4()}.%(ext)s")
        opts = {
            "format": "bestaudio/best",
            "outtmpl": out,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}
            ],
            "quiet": True,
            "no_warnings": True,
        }

        def _download() -> None:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

        await asyncio.to_thread(_download)
        files = list(Path(tmp).glob("*.mp3"))
        if not files:
            raise HTTPException(status_code=422, detail="Audio download failed.")
        return await transcribe(str(files[0]), api_key=api_key)


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate sentiment / risk across multiple article analyses."""
    sentiments: Counter[str] = Counter()
    risk_scores: list[float] = []
    entities: Counter[str] = Counter()

    for r in results:
        analyses = r.get("analyses") or {}
        sent = analyses.get("sentiment") or {}
        if isinstance(sent, dict) and "overall_sentiment" in sent:
            sentiments[sent["overall_sentiment"]] += 1
        risk = analyses.get("risk") or {}
        if isinstance(risk, dict):
            score = (risk.get("risk_summary") or {}).get("risk_score")
            if isinstance(score, (int, float)):
                risk_scores.append(float(score))
        extraction = analyses.get("extraction") or {}
        companies = (
            (extraction.get("entities") or {}).get("companies", [])
            if isinstance(extraction, dict)
            else []
        )
        for company in companies:
            if isinstance(company, dict) and company.get("name"):
                entities[company["name"]] += 1

    avg_risk = round(sum(risk_scores) / len(risk_scores), 1) if risk_scores else 0
    return {
        "dominant_sentiment": sentiments.most_common(1)[0][0] if sentiments else "unknown",
        "sentiment_distribution": dict(sentiments),
        "average_risk_score": avg_risk,
        "top_entities": [{"name": n, "mentions": c} for n, c in entities.most_common(10)],
    }
