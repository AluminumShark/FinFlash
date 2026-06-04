"""Exa API client for financial news retrieval (async wrapper over the sync SDK)."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from exa_py import Exa

from core.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_EXCLUDE = ["twitter.com", "facebook.com", "instagram.com"]
FINANCIAL_DOMAINS = [
    "bloomberg.com", "reuters.com", "cnbc.com", "ft.com", "wsj.com",
    "marketwatch.com", "investing.com", "seekingalpha.com",
    "finance.yahoo.com", "businessinsider.com",
]


class ExaService:
    """Searches financial news via Exa, returning plain dicts."""

    def __init__(self, api_key: str | None = None, max_retries: int = 3) -> None:
        key = api_key or get_settings().exa_api_key
        if not key:
            raise ValueError("EXA_API_KEY is not configured.")
        self.client = Exa(api_key=key)
        self.max_retries = max_retries
        self.total_requests = 0
        self.total_results = 0

    async def search_financial_news(
        self, query: str, *, days_back: int = 7, num_results: int = 10
    ) -> list[dict[str, Any]]:
        """Search recent financial news and return articles with text content."""
        end = datetime.now(UTC)
        start = end - timedelta(days=days_back)

        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                result = await asyncio.to_thread(
                    lambda: self.client.search_and_contents(
                        f"financial news: {query}",
                        num_results=num_results,
                        category="news",
                        start_published_date=start.strftime("%Y-%m-%d"),
                        end_published_date=end.strftime("%Y-%m-%d"),
                        exclude_domains=DEFAULT_EXCLUDE,
                        text=True,
                        highlights=True,
                    )
                )
                self.total_requests += 1
                articles = self._convert(result)
                self.total_results += len(articles)
                logger.info("Exa returned %d articles for '%s'", len(articles), query)
                return articles
            except Exception as exc:
                last_err = exc
                logger.error("Exa error (attempt %d): %s", attempt + 1, exc)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)
        raise RuntimeError(f"Exa search failed after {self.max_retries} attempts: {last_err}")

    @staticmethod
    def _convert(response: Any) -> list[dict[str, Any]]:
        articles: list[dict[str, Any]] = []
        for r in getattr(response, "results", []):
            text = getattr(r, "text", "") or ""
            if not text:
                continue
            url = getattr(r, "url", "") or ""
            articles.append(
                {
                    "id": getattr(r, "id", url) or url,
                    "title": getattr(r, "title", "") or "",
                    "url": url,
                    "source": _source_from_url(url),
                    "author": getattr(r, "author", None),
                    "published_date": getattr(r, "published_date", None),
                    "score": getattr(r, "score", 0.0),
                    "content": text,
                    "highlights": getattr(r, "highlights", []) or [],
                }
            )
        return articles

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "total_results": self.total_results,
        }


def _source_from_url(url: str) -> str:
    from urllib.parse import urlparse

    netloc = urlparse(url).netloc.replace("www.", "")
    return netloc.split(".")[0].title() if netloc else "Unknown"
