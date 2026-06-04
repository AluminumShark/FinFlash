"""LangGraph orchestration for financial news analysis.

Flow::

    START -> retrieve -> { sentiment, extraction, risk } -> summary -> persist -> END

The three analysts fan out concurrently; ``summary`` joins on all three. This
replaces the hand-rolled if/else Orchestrator and gives us streaming progress
(``astream``) and a single, inspectable graph.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from agents.nodes.analysis import (
    extraction_node,
    persist_node,
    retrieve_node,
    risk_node,
    sentiment_node,
    summary_node,
)
from agents.state import AnalysisState
from services.llm import LLMConfig


def build_graph():
    g = StateGraph(AnalysisState)  # ty: ignore[invalid-argument-type]
    g.add_node("retrieve", retrieve_node)
    g.add_node("sentiment", sentiment_node)
    g.add_node("extraction", extraction_node)
    g.add_node("risk", risk_node)
    g.add_node("summary", summary_node)
    g.add_node("persist", persist_node)

    g.add_edge(START, "retrieve")
    for analyst in ("sentiment", "extraction", "risk"):
        g.add_edge("retrieve", analyst)
        g.add_edge(analyst, "summary")
    g.add_edge("summary", "persist")
    g.add_edge("persist", END)
    return g.compile()


@lru_cache
def get_graph():
    return build_graph()


def _initial_state(
    *,
    content: str,
    title: str,
    news_id: str | None,
    llm: LLMConfig,
    llm_key: str | None,
    enable_rag: bool,
) -> AnalysisState:
    return {
        "news_id": news_id or str(uuid.uuid4()),
        "title": title,
        "content": content,
        "llm": llm,
        "llm_key": llm_key,
        "enable_rag": enable_rag,
        "usage_log": [],
        "errors": [],
    }


def assemble_response(state: dict[str, Any]) -> dict[str, Any]:
    """Shape the final graph state into the public API response."""
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}
    for u in state.get("usage_log", []):
        usage_total["prompt_tokens"] += u.get("prompt_tokens", 0)
        usage_total["completion_tokens"] += u.get("completion_tokens", 0)
        usage_total["total_tokens"] += u.get("total_tokens", 0)
        usage_total["cost_usd"] += u.get("cost_usd", 0.0)
    usage_total["cost_usd"] = round(usage_total["cost_usd"], 6)

    return {
        "news_id": state.get("news_id"),
        "status": "completed" if not state.get("errors") else "completed_with_errors",
        "analyses": {
            "sentiment": state.get("sentiment"),
            "extraction": state.get("extraction"),
            "risk": state.get("risk"),
        },
        "summary": state.get("summary"),
        "errors": state.get("errors", []),
        "usage": usage_total,
        "model": state["llm"].model if state.get("llm") else None,
    }


async def run_analysis(
    *,
    content: str,
    title: str = "",
    news_id: str | None = None,
    llm: LLMConfig,
    llm_key: str | None = None,
    enable_rag: bool = True,
) -> dict[str, Any]:
    """Run the full graph and return the assembled response."""
    state = _initial_state(
        content=content, title=title, news_id=news_id, llm=llm,
        llm_key=llm_key, enable_rag=enable_rag,
    )
    final = await get_graph().ainvoke(state)
    return assemble_response(final)


async def stream_analysis(
    *,
    content: str,
    title: str = "",
    news_id: str | None = None,
    llm: LLMConfig,
    llm_key: str | None = None,
    enable_rag: bool = True,
) -> AsyncIterator[dict[str, Any]]:
    """Yield progress events as each node completes, then a final ``result`` event."""
    state = _initial_state(
        content=content, title=title, news_id=news_id, llm=llm,
        llm_key=llm_key, enable_rag=enable_rag,
    )
    accumulated: dict[str, Any] = dict(state)
    async for update in get_graph().astream(state, stream_mode="updates"):
        for node_name, partial in update.items():
            if isinstance(partial, dict):
                for k, v in partial.items():
                    if k in ("usage_log", "errors"):
                        accumulated.setdefault(k, [])
                        accumulated[k] = accumulated[k] + v
                    else:
                        accumulated[k] = v
            yield {"event": "progress", "node": node_name}
    yield {"event": "result", "data": assemble_response(accumulated)}
