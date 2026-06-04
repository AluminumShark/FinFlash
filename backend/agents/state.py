"""Shared state for the analysis LangGraph."""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from services.llm import LLMConfig


class AnalysisState(TypedDict, total=False):
    # --- input ---
    news_id: str
    title: str
    content: str

    # --- per-request config (not persisted) ---
    llm: LLMConfig
    llm_key: str | None
    enable_rag: bool

    # --- retrieved context ---
    context: str

    # --- analysis results (each node writes its own key, so no reducer needed) ---
    sentiment: dict[str, Any]
    extraction: dict[str, Any]
    risk: dict[str, Any]
    summary: dict[str, Any]

    # --- concurrently-written aggregates need reducers ---
    usage_log: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[dict[str, str]], operator.add]
