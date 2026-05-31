from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger(__name__)


def fetch_evidence_event_urls(pool: Any, *, event_ids: list[str]) -> dict[str, str]:
    if not event_ids:
        return {}
    placeholders = ",".join(["%s"] * len(event_ids))
    try:
        with pool.connection() as conn:
            cur = conn.execute(
                f"""
                SELECT
                  event_id,
                  author_handle,
                  tweet_id,
                  canonical_url
                FROM events
                WHERE event_id IN ({placeholders})
                """,
                tuple(event_ids),
            )
            rows = cur.fetchall()
    except Exception as exc:
        _logger.warning("fetch_evidence_event_urls_failed err=%s", str(exc)[:300])
        return {}
    urls: dict[str, str] = {}
    for row in rows:
        event_id = row.get("event_id")
        canonical_url = row.get("canonical_url")
        url = canonical_url.strip() if isinstance(canonical_url, str) else ""
        if not url:
            url = _build_tweet_url(row.get("author_handle"), row.get("tweet_id")) or ""
        if event_id and url:
            urls[str(event_id)] = url
    return urls


def _build_tweet_url(handle: str | None, tweet_id: str | None) -> str | None:
    if not handle or not tweet_id:
        return None
    cleaned = str(handle).lstrip("@")
    if not cleaned:
        return None
    return f"https://x.com/{cleaned}/status/{tweet_id}"


__all__ = ["fetch_evidence_event_urls"]
