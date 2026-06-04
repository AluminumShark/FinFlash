"""Request/response models for the public API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TextAnalysisRequest(BaseModel):
    content: str = Field(min_length=1)
    title: str = ""
    enable_rag: bool = True


class SearchAnalysisRequest(BaseModel):
    query: str = Field(min_length=1)
    num_results: int = Field(default=5, ge=1, le=20)
    days_back: int = Field(default=7, ge=1, le=90)
    enable_rag: bool = True


class YouTubeAnalysisRequest(BaseModel):
    url: str
    enable_rag: bool = True


class CompanyAnalysisRequest(BaseModel):
    company: str = Field(min_length=1, description="Company name or ticker")
    num_results: int = Field(default=5, ge=1, le=15)
    days_back: int = Field(default=14, ge=1, le=90)


class CompanyAnalysisResponse(BaseModel):
    company: str
    verdict: dict[str, Any] | None = None
    articles_analyzed: int
    sources: list[dict[str, Any]] = []
    aggregate: dict[str, Any] = {}
    usage: dict[str, Any] | None = None
    model: str | None = None


class AnalysisResponse(BaseModel):
    news_id: str | None = None
    status: str
    analyses: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    errors: list[dict[str, str]] = []
    usage: dict[str, Any] | None = None
    model: str | None = None


class SearchAnalysisResponse(BaseModel):
    query: str
    total_articles: int
    analyzed_successfully: int
    results: list[AnalysisResponse]
    aggregate: dict[str, Any]


class CreateKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class CreateKeyResponse(BaseModel):
    name: str
    api_key: str = Field(description="Shown only once — store it securely.")
