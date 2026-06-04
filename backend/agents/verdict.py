"""Synthesize per-article analyses into a single company investment verdict."""
from __future__ import annotations

import json
from typing import Any

from agents import prompts
from agents.outputs import InvestmentVerdict
from services.llm import LLMConfig, Usage, get_llm_client


def _condense(analyses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only the fields the verdict needs, to fit many articles in one prompt."""
    out = []
    for r in analyses:
        a = r.get("analyses") or {}
        sent = a.get("sentiment") or {}
        risk = a.get("risk") or {}
        out.append(
            {
                "sentiment": sent.get("overall_sentiment"),
                "sentiment_score": sent.get("sentiment_score"),
                "fear_greed": sent.get("fear_greed_index"),
                "risk_level": (risk.get("risk_summary") or {}).get("overall_risk_level"),
                "risk_score": (risk.get("risk_summary") or {}).get("risk_score"),
                "primary_risks": (risk.get("risk_summary") or {}).get("primary_risks"),
                "recommendation": (risk.get("investment_implications") or {}).get("recommendation"),
            }
        )
    return out


async def synthesize_verdict(
    company: str,
    analyses: list[dict[str, Any]],
    *,
    llm: LLMConfig,
    usage: Usage | None = None,
) -> dict[str, Any]:
    """Produce a buy/hold/sell verdict for a company from its article analyses."""
    consolidated = json.dumps(_condense(analyses), ensure_ascii=False, indent=2)
    client = get_llm_client()
    verdict = await client.structured(
        messages=[
            {"role": "system", "content": prompts.VERDICT_SYSTEM},
            {"role": "user", "content": prompts.verdict_user(company, consolidated)},
        ],
        schema=InvestmentVerdict,
        cfg=llm,
        usage=usage,
    )
    return verdict.model_dump(mode="json")
