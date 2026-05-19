from __future__ import annotations

import calendar
import json
import time
from collections.abc import Mapping
from typing import Any

from gmgn_twitter_intel.domains.news_intel.services.text_normalization import canonicalize_url, clean_news_text
from gmgn_twitter_intel.domains.news_intel.types import NormalizedNewsItem


def normalize_feed_entry(
    source_domain: str,
    entry: Mapping[str, Any],
    fetched_at_ms: int,
) -> NormalizedNewsItem | None:
    link = _first_text(entry, "link", "href")
    canonical_url = canonicalize_url(link)
    title = clean_news_text(entry.get("title"), max_chars=500)
    if not title or not canonical_url:
        return None
    source_item_key = _first_text(entry, "id", "guid", "link") or canonical_url
    summary = clean_news_text(_first_value(entry, "summary", "description", "subtitle"))
    body_text = clean_news_text(_content_value(entry))
    if not body_text:
        body_text = summary
    return NormalizedNewsItem(
        source_item_key=source_item_key,
        canonical_url=canonical_url,
        title=title,
        summary=summary,
        body_text=body_text,
        language=_language(entry),
        published_at_ms=_entry_time_ms(entry, fetched_at_ms=fetched_at_ms),
        raw_payload=_json_safe_payload(entry, source_domain=source_domain),
    )


def _first_text(entry: Mapping[str, Any], *keys: str) -> str:
    value = _first_value(entry, *keys)
    return str(value or "").strip()


def _first_value(entry: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = entry.get(key)
        if value:
            return value
    return None


def _content_value(entry: Mapping[str, Any]) -> Any:
    content = entry.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, Mapping):
            return first.get("value") or first.get("content")
        return first
    return entry.get("content") or entry.get("body") or entry.get("summary")


def _entry_time_ms(entry: Mapping[str, Any], *, fetched_at_ms: int) -> int:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if isinstance(parsed, time.struct_time):
            return int(calendar.timegm(parsed) * 1000)
    return int(fetched_at_ms)


def _language(entry: Mapping[str, Any]) -> str:
    language = str(entry.get("language") or entry.get("lang") or "en").strip().lower()
    return language or "en"


def _json_safe_payload(entry: Mapping[str, Any], *, source_domain: str) -> dict[str, Any]:
    payload = dict(entry)
    payload["source_domain"] = str(source_domain)
    return json.loads(json.dumps(payload, default=str, ensure_ascii=False, sort_keys=True))
