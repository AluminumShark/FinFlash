"""Pydantic schemas for agent structured outputs.

These replace the hand-written ``json.loads`` + ``_validate_*`` logic in the old
agents. Passing them as ``response_format`` makes the provider emit schema-valid
JSON via constrained decoding.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field


def _to_unit(v: object) -> object:
    """Normalize a 0-1 score that a model returned as a 0-100 percentage."""
    if isinstance(v, (int, float)) and 1 < v <= 100:
        return v / 100
    return v


# A 0..1 score that tolerates models emitting 0..100 (common with small LLMs).
UnitFloat = Annotated[float, BeforeValidator(_to_unit)]


class Sentiment(StrEnum):
    positive = "positive"
    negative = "negative"
    neutral = "neutral"


class RiskLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


# ---- Sentiment ----

class MarketImpact(BaseModel):
    immediate: str = Field(description="high/medium/low")
    short_term: str = Field(description="positive/negative/neutral")
    long_term: str = Field(description="positive/negative/neutral")


class SentimentBreakdown(BaseModel):
    positive_aspects: list[str] = []
    negative_aspects: list[str] = []
    neutral_aspects: list[str] = []


class SentimentOutput(BaseModel):
    overall_sentiment: Sentiment
    sentiment_score: UnitFloat = Field(ge=0, le=1, description="intensity 0..1")
    confidence: UnitFloat = Field(ge=0, le=1)
    fear_greed_index: int = Field(ge=0, le=100, description="0=extreme fear, 100=extreme greed")
    market_impact: MarketImpact
    key_phrases: list[str] = []
    sentiment_breakdown: SentimentBreakdown
    investor_sentiment: str = Field(description="risk-on/risk-off/neutral")
    recommendation: str


# ---- Extraction ----

class Company(BaseModel):
    name: str
    ticker: str | None = None
    role: str | None = Field(default=None, description="subject/mentioned/competitor")


class Person(BaseModel):
    name: str
    title: str | None = None
    company: str | None = None


class Entities(BaseModel):
    companies: list[Company] = []
    persons: list[Person] = []
    locations: list[str] = []


class EventDetails(BaseModel):
    description: str = ""
    date: str | None = None
    status: str | None = Field(default=None, description="announced/completed/pending/rumored")


class Metric(BaseModel):
    name: str
    value: str
    unit: str | None = None
    change: str | None = None


class ExtractionOutput(BaseModel):
    entities: Entities
    event_type: str = Field(description="primary event category")
    event_details: EventDetails
    financial_metrics: list[Metric] = []
    products_services: list[str] = []
    sectors: list[str] = []
    confidence: UnitFloat = Field(default=0.8, ge=0, le=1)


# ---- Risk ----

class RiskSummary(BaseModel):
    overall_risk_level: RiskLevel
    primary_risks: list[str] = []
    risk_score: int = Field(ge=0, le=100)


class DetailedRisk(BaseModel):
    risk_type: str
    specific_risk: str
    probability: str = Field(description="low/medium/high")
    impact: str = Field(description="low/medium/high/severe")
    mitigation: str | None = None


class ImpactAnalysis(BaseModel):
    scope: str = Field(description="company/sector/market/global")
    affected_entities: list[str] = []


class InvestmentImplications(BaseModel):
    recommendation: str = Field(description="buy/hold/sell/avoid")
    confidence_level: str = Field(description="low/medium/high")
    key_watchpoints: list[str] = []


class RiskOutput(BaseModel):
    risk_summary: RiskSummary
    detailed_risks: list[DetailedRisk] = []
    impact_analysis: ImpactAnalysis
    opportunities: list[str] = []
    investment_implications: InvestmentImplications
    confidence: UnitFloat = Field(default=0.8, ge=0, le=1)


# ---- Summary ----

class ExecutiveSummary(BaseModel):
    key_findings: list[str]
    market_outlook: str
    immediate_actions: list[str] = []
    confidence_level: str = Field(description="high/medium/low")


class SummaryOutput(BaseModel):
    executive_summary: ExecutiveSummary
    key_insights: list[str] = []
    buy_signals: list[str] = []
    sell_signals: list[str] = []
    watch_list: list[str] = []
    action_items: list[str] = []
    data_limitations: list[str] = []


# ---- Investment verdict (company-level synthesis) ----

class Recommendation(StrEnum):
    buy = "buy"
    hold = "hold"
    sell = "sell"


class InvestmentVerdict(BaseModel):
    """A single, decision-oriented answer: is this company worth investing in?"""

    company: str
    recommendation: Recommendation
    confidence: UnitFloat = Field(ge=0, le=1, description="confidence in the recommendation")
    rationale: str = Field(description="2-3 sentence plain-language justification")
    key_catalysts: list[str] = Field(default=[], description="positive drivers / upside")
    key_risks: list[str] = Field(default=[], description="main downside risks")
    sentiment_summary: str = Field(default="", description="overall news sentiment in a line")
    risk_summary: str = Field(default="", description="overall risk picture in a line")
    time_horizon: str = Field(default="medium", description="short/medium/long term view")
