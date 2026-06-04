"""News search with a free default (Google News RSS) and optional Exa upgrade.

If ``EXA_API_KEY`` is configured, Exa is used (richer full-text results). Otherwise
the system falls back to Google News RSS, which needs no API key — so anyone can run
the search feature for free.
"""
from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote_plus

import httpx

from core.config import get_settings

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_USER_AGENT = "Mozilla/5.0 (compatible; FinFlash/1.0; +https://github.com/AluminumShark/FinFlash)"


def using_exa() -> bool:
    return bool(get_settings().exa_api_key)


async def search_news(
    query: str, *, num_results: int = 5, days_back: int = 7
) -> list[dict[str, Any]]:
    """Return financial-news articles for a query. Source depends on config."""
    if using_exa():
        from services.exa import ExaService

        return await ExaService().search_financial_news(
            query, days_back=days_back, num_results=num_results
        )
    return await _google_news_rss(query, num_results)


def _has_cjk(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in text)


def _locale(query: str) -> tuple[str, str, str]:
    """Pick a Google News locale so non-English company names return results."""
    if _has_cjk(query):
        return "zh-TW", "TW", "TW:zh"
    return "en-US", "US", "US:en"


async def _google_news_rss(query: str, num_results: int) -> list[dict[str, Any]]:
    # Note: the `when:Nd` operator silently returns 0 results for CJK queries,
    # so we rely on RSS already returning recent items instead.
    hl, gl, ceid = _locale(query)
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl={hl}&gl={gl}&ceid={ceid}"
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": _USER_AGENT})
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    articles: list[dict[str, Any]] = []
    for item in root.findall(".//item")[:num_results]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        snippet = _strip_html(item.findtext("description") or "")
        source_el = item.find("{http://www.w3.org/2005/Atom}source") or item.find("source")
        source = (source_el.text if source_el is not None else None) or _domain(link)
        articles.append(
            {
                "id": hashlib.md5(link.encode()).hexdigest(),
                "title": title,
                "url": link,
                "source": source,
                "author": None,
                "published_date": item.findtext("pubDate"),
                "score": None,
                # RSS gives a snippet, not full text; combine for the analysts.
                "content": f"{title}. {snippet}".strip(),
                "highlights": [],
            }
        )
    logger.info("Google News RSS returned %d articles for '%s'", len(articles), query)
    return articles


def _strip_html(text: str) -> str:
    return _TAG_RE.sub(" ", text).replace("&nbsp;", " ").strip()


def _domain(url: str) -> str:
    from urllib.parse import urlparse

    netloc = urlparse(url).netloc.replace("www.", "")
    return netloc.split(".")[0].title() if netloc else "News"
