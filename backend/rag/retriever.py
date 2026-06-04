"""Builds a compact textual context block from similar historical news."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from rag.store import search_similar


async def build_context(
    session: AsyncSession,
    text: str,
    *,
    exclude_id: str | None = None,
    limit: int = 3,
) -> str:
    """Return a short context string for prompt injection (empty if none)."""
    hits = await search_similar(session, text, limit=limit, exclude_id=exclude_id)
    if not hits:
        return ""
    lines = []
    for h in hits:
        news = h["news"]
        when = news.published_date or news.collected_date
        when_str = when.date().isoformat() if when else "unknown date"
        snippet = (news.content or "")[:300].replace("\n", " ")
        lines.append(
            f"- [{when_str}] {news.title} (similarity {h['similarity']:.2f}): {snippet}"
        )
    return "\n".join(lines)
