from __future__ import annotations

import calendar
import json
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

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
    source_item_key = _first_text(entry, "source_item_key", "id", "guid", "link") or canonical_url
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
    for key in ("published_at_ms", "published_ms", "ts"):
        value = _epoch_ms(entry.get(key))
        if value is not None:
            return value
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
    return cast(dict[str, Any], json.loads(json.dumps(payload, default=str, ensure_ascii=False, sort_keys=True)))


def _epoch_ms(value: object) -> int | None:
    if not isinstance(value, str | bytes | bytearray | int | float):
        return _iso_epoch_ms(value)
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return _iso_epoch_ms(value)
    if numeric <= 0:
        return None
    if numeric < 10_000_000_000:
        numeric *= 1000
    return int(numeric)


def _iso_epoch_ms(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp() * 1000)
