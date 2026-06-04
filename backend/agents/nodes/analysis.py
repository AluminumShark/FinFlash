"""Analysis nodes: retrieve context, run the three analysts, summarize, persist."""
from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import delete

from agents import prompts
from agents.outputs import (
    ExtractionOutput,
    RiskOutput,
    SentimentOutput,
    SummaryOutput,
)
from agents.state import AnalysisState
from core.database import AnalysisResult, News, session_scope
from rag.retriever import build_context
from rag.store import store_embedding
from services.llm import LLMConfig, Usage, get_llm_client

logger = logging.getLogger(__name__)


def _full_content(state: AnalysisState) -> str:
    title = state.get("title", "")
    content = state.get("content", "")
    return f"Title: {title}\n\nContent: {content}" if title else content


async def _run_analyst(
    state: AnalysisState,
    *,
    system: str,
    user: str,
    schema,
    temperature: float,
    key: str,
):
    """Shared helper: call the LLM for structured output and shape a partial state."""
    client = get_llm_client()
    cfg: LLMConfig = replace(state["llm"], temperature=temperature)
    usage = Usage()
    try:
        result = await client.structured(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            schema=schema,
            cfg=cfg,
            usage=usage,
        )
        return {key: result.model_dump(mode="json"), "usage_log": [usage.as_dict()]}
    except Exception as exc:
        logger.error("%s node failed: %s", key, exc)
        return {
            key: {"error": str(exc)},
            "errors": [{"node": key, "error": str(exc)}],
            "usage_log": [usage.as_dict()],
        }


# ---- nodes ----

async def retrieve_node(state: AnalysisState) -> dict:
    """Fetch similar historical news as context (RAG)."""
    if not state.get("enable_rag", True):
        return {"context": ""}
    try:
        async with session_scope() as session:
            context = await build_context(
                session,
                _full_content(state),
                exclude_id=state.get("news_id"),
            )
        return {"context": context}
    except Exception as exc:
        logger.warning("RAG retrieval failed: %s", exc)
        return {"context": ""}


async def sentiment_node(state: AnalysisState) -> dict:
    return await _run_analyst(
        state,
        system=prompts.SENTIMENT_SYSTEM,
        user=prompts.sentiment_user(_full_content(state), state.get("context")),
        schema=SentimentOutput,
        temperature=0.3,
        key="sentiment",
    )


async def extraction_node(state: AnalysisState) -> dict:
    return await _run_analyst(
        state,
        system=prompts.EXTRACTION_SYSTEM,
        user=prompts.extraction_user(_full_content(state), state.get("context")),
        schema=ExtractionOutput,
        temperature=0.2,
        key="extraction",
    )


async def risk_node(state: AnalysisState) -> dict:
    return await _run_analyst(
        state,
        system=prompts.RISK_SYSTEM,
        user=prompts.risk_user(_full_content(state), state.get("context")),
        schema=RiskOutput,
        temperature=0.4,
        key="risk",
    )


async def summary_node(state: AnalysisState) -> dict:
    consolidated = {
        "sentiment": state.get("sentiment", {}),
        "extraction": state.get("extraction", {}),
        "risk": state.get("risk", {}),
    }
    return await _run_analyst(
        state,
        system=prompts.SUMMARY_SYSTEM,
        user=prompts.summary_user(json.dumps(consolidated, ensure_ascii=False, indent=2)),
        schema=SummaryOutput,
        temperature=0.5,
        key="summary",
    )


async def persist_node(state: AnalysisState) -> dict:
    """Save analysis results and the news embedding to the database."""
    news_id = state.get("news_id")
    if not news_id:
        return {}
    try:
        async with session_scope() as session:
            # Ensure the news row exists.
            news = await session.get(News, news_id)
            if news is None:
                news = News(
                    id=news_id,
                    title=state.get("title") or state.get("content", "")[:200],
                    content=state.get("content", ""),
                    source="Direct Input",
                    news_type="text",
                    processed=True,
                )
                session.add(news)
                await session.flush()
            else:
                news.processed = True

            # This run's successful analyses. Replace the whole prior set only when
            # we have something to store: a total failure keeps previously-good
            # data, and a partial failure never leaves a stale mix of old + new.
            fresh = {
                agent_type: data
                for agent_type in ("sentiment", "extraction", "risk", "summary")
                if isinstance((data := state.get(agent_type)), dict) and "error" not in data
            }
            if fresh:
                await session.execute(
                    delete(AnalysisResult).where(AnalysisResult.news_id == news_id)
                )
                for agent_type, data in fresh.items():
                    session.add(
                        AnalysisResult(
                            news_id=news_id,
                            agent_type=agent_type,
                            result=data,
                            confidence=float(data.get("confidence", 0.8)),
                            model_used=state["llm"].model,
                            analysis_date=datetime.now(UTC),
                        )
                    )

            await store_embedding(session, news_id, _full_content(state))
            await session.commit()
        return {}
    except Exception as exc:
        logger.error("Persist node failed: %s", exc)
        return {"errors": [{"node": "persist", "error": str(exc)}]}
