"""System / user prompts for each analysis node.

Ported from the original agents. The verbose "respond in JSON" instructions are
dropped because structured outputs guarantee the shape; the domain expertise in
each system prompt is preserved.
"""
from __future__ import annotations

SENTIMENT_SYSTEM = (
    "You are an expert financial analyst specializing in market sentiment analysis. "
    "Analyze financial news and determine the overall market sentiment, intensity, "
    "and potential impact on markets. Be objective and base your analysis solely on "
    "the content provided."
)

EXTRACTION_SYSTEM = (
    "You are an expert financial analyst specializing in information extraction. "
    "Extract structured information from financial news: entities (companies, people, "
    "locations), the primary event, financial metrics, sectors, and products. "
    "Extract only information explicitly stated in the content; do not invent data."
)

RISK_SYSTEM = (
    "You are a senior risk analyst specializing in financial markets. Assess risks, "
    "evaluate potential impacts across time horizons and scopes, and provide investment "
    "recommendations. Identify both downside risks and upside opportunities. Never "
    "fabricate figures."
)

SUMMARY_SYSTEM = (
    "You are a senior financial analyst and expert report writer. Synthesize multiple "
    "analysis results into a clear, actionable report focused on key insights, trends, "
    "and recommendations. Be data-driven and professional."
)


def with_context(prompt: str, context: str | None) -> str:
    """Append retrieved historical context (RAG) to a user prompt, if any."""
    if not context:
        return prompt
    return (
        f"{prompt}\n\n"
        "----\n"
        "Relevant historical context from previously analyzed news (use it to compare "
        "trends and assess whether this is part of a larger pattern):\n"
        f"{context}"
    )


def sentiment_user(content: str, context: str | None = None) -> str:
    return with_context(
        f"Analyze the market sentiment of the following financial news.\n\n{content}",
        context,
    )


def extraction_user(content: str, context: str | None = None) -> str:
    return with_context(
        f"Extract structured information from the following financial news.\n\n{content}",
        context,
    )


def risk_user(content: str, context: str | None = None) -> str:
    return with_context(
        "Provide a balanced risk assessment of the following financial news, "
        f"considering both downside risks and opportunities.\n\n{content}",
        context,
    )


def summary_user(consolidated_json: str) -> str:
    return (
        "Generate a comprehensive financial analysis report based on the following "
        f"consolidated analysis results.\n\n{consolidated_json}"
    )


VERDICT_SYSTEM = (
    "You are a senior equity research analyst. Based on recent news analyses of a single "
    "company, deliver one clear, decision-oriented verdict on whether it is worth "
    "investing in right now: buy, hold, or sell. Weigh sentiment, risks, and catalysts. "
    "Be balanced and never fabricate figures. This is research, not personalized "
    "financial advice."
)


def verdict_user(company: str, consolidated_json: str) -> str:
    return (
        f"Company: {company}\n\n"
        "Here are structured analyses of recent news about this company. Synthesize them "
        "into a single investment verdict (buy/hold/sell) with a confidence level, a short "
        "rationale, the key catalysts (upside) and key risks (downside).\n\n"
        f"{consolidated_json}"
    )
