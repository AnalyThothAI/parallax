from __future__ import annotations

import calendar
import json
import re
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlsplit

from tracefold.news.ingest.normalized_item import NormalizedNewsItem
from tracefold.news.ingest.text_normalization import clean_news_text
from tracefold.news.ingest.url_identity import public_url_identity_policy

_OPENNEWS_FALLBACK_INVALID_RE = re.compile(r"[\s\x00-\x1f\x7f]")


def normalize_feed_entry(
    source_domain: str,
    entry: Mapping[str, Any],
    fetched_at_ms: int,
) -> NormalizedNewsItem | None:
    link = _first_text(entry, "link", "href")
    canonical_url = _canonical_news_url_or_fallback(link, entry)
    title = clean_news_text(entry.get("title"), max_chars=500)
    if not title:
        return None
    if not canonical_url:
        return None
    source_item_key = (
        _first_text(entry, "source_item_key", "provider_article_id", "id", "guid", "link") or canonical_url
    )
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


def _canonical_news_url_or_fallback(link: object, entry: Mapping[str, Any]) -> str:
    public_policy = public_url_identity_policy(link)
    if public_policy.allowed:
        return public_policy.normalized_url

    fallback_url = _opennews_fallback_url(link, entry)
    if fallback_url:
        return fallback_url
    if _is_opennews_item_url(link):
        return ""

    fallback_url = _opennews_provider_fallback_url(entry)
    if fallback_url:
        return fallback_url

    return ""


def _opennews_fallback_url(link: object, entry: Mapping[str, Any]) -> str:
    explicit_provider_article_id = _first_text(entry, "provider_article_id")
    provider_article_key = _first_text(entry, "provider_article_key")
    provider_article_key_id = _opennews_provider_article_key_id(provider_article_key)
    has_opennews_marker = (
        bool(explicit_provider_article_id)
        or bool(provider_article_key_id)
        or bool(_first_text(entry, "opennews_method"))
    )
    if not has_opennews_marker:
        return ""
    raw = str(link or "").strip()
    if _OPENNEWS_FALLBACK_INVALID_RE.search(raw):
        return ""
    try:
        split = urlsplit(raw)
    except ValueError:
        return ""
    if split.scheme.lower() != "opennews" or (split.netloc or "").lower() != "item":
        return ""
    item_id = str(split.path or "").strip("/")
    if not item_id:
        return ""
    if explicit_provider_article_id and item_id != explicit_provider_article_id:
        return ""
    if provider_article_key_id and item_id != provider_article_key_id:
        return ""
    return f"opennews://item/{item_id}"


def _is_opennews_item_url(link: object) -> bool:
    raw = str(link or "").strip()
    if not raw:
        return False
    try:
        split = urlsplit(raw)
    except ValueError:
        return raw.lower().startswith("opennews://item/")
    return split.scheme.lower() == "opennews" and (split.netloc or "").lower() == "item"


def _opennews_provider_fallback_url(entry: Mapping[str, Any]) -> str:
    provider_article_key = _first_text(entry, "provider_article_key")
    explicit_provider_article_id = _first_text(entry, "provider_article_id")
    provider_article_key_id = _opennews_provider_article_key_id(provider_article_key)
    opennews_method = _first_text(entry, "opennews_method")
    if not (provider_article_key_id or opennews_method):
        return ""
    item_id = explicit_provider_article_id or provider_article_key_id or _first_text(entry, "id")
    if (
        explicit_provider_article_id
        and provider_article_key_id
        and explicit_provider_article_id != provider_article_key_id
    ):
        return ""
    if not item_id or _OPENNEWS_FALLBACK_INVALID_RE.search(item_id):
        return ""
    return f"opennews://item/{item_id.strip()}"


def _opennews_provider_article_key_id(provider_article_key: str) -> str:
    prefix = "opennews:"
    normalized = str(provider_article_key or "").strip()
    if not normalized.lower().startswith(prefix):
        return ""
    return normalized[len(prefix) :].strip()


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
