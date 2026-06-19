from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import parse_qsl, quote, urlsplit

from parallax.domains.news_intel.services.opennews_provider_signal import (
    provider_signal_from_opennews_payload,
    provider_token_impacts_from_opennews_payload,
)
from parallax.integrations.news_feeds.feed_client import FeedFetchResult

DEFAULT_OPENNEWS_API_BASE_URL = "https://ai.6551.io"
MAX_REST_LIMIT = 100
_REMOVED_WEBSOCKET_POLICY_KEYS = {
    "fetch_mode",
    "wss_url",
    "stream_timeout_seconds",
    "streamTimeoutSeconds",
    "max_messages",
    "maxMessages",
    "connect_timeout_seconds",
    "connectTimeoutSeconds",
}


class _OpenNewsPostJson(Protocol):
    def __call__(self, url: str, *, token: str, body: Mapping[str, Any]) -> Awaitable[Mapping[str, Any]]: ...


class OpenNewsFeedClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        api_base_url: str = DEFAULT_OPENNEWS_API_BASE_URL,
        post_json: _OpenNewsPostJson | None = None,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        self._token = _optional_text(token)
        self._api_base_url = (
            str(api_base_url or DEFAULT_OPENNEWS_API_BASE_URL).strip().rstrip("/") or DEFAULT_OPENNEWS_API_BASE_URL
        )
        self._post_json = post_json or _default_post_json
        self._now_ms = now_ms or _now_ms

    def fetch(
        self,
        url: str,
        *,
        source: dict[str, Any] | None = None,
        cursor: Mapping[str, Any] | None = None,
        since_ms: int | None = None,
        limit: int | None = None,
    ) -> FeedFetchResult:
        if not self._token:
            raise ValueError("OpenNews token is not configured")
        policy = _source_fetch_policy(source or {})
        _reject_removed_websocket_policy(policy)
        subscription = _subscription_params(url, policy)
        entries, next_cursor = _run_rest_fetch(
            self._fetch_rest_entries(
                subscription=subscription,
                policy=policy,
                cursor=cursor or {},
                since_ms=since_ms,
                limit=limit,
            )
        )
        visible_entries = [entry for entry in entries if _entry_is_visible(entry)]
        return FeedFetchResult(
            status_code=200,
            entries=visible_entries,
            not_modified=False,
            feed={
                "provider": "opennews",
                "transport": "rest",
                "subscription": subscription,
                "rest_received": int(next_cursor.get("rest_received") or len(entries)),
                "received": len(visible_entries),
            },
            next_cursor=next_cursor,
        )

    def close(self) -> None:
        return None

    async def _fetch_rest_entries(
        self,
        *,
        subscription: Mapping[str, Any],
        policy: Mapping[str, Any],
        cursor: Mapping[str, Any],
        since_ms: int | None,
        limit: int | None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        previous_high_watermark_ms = _cursor_int(cursor, "high_watermark_ms")
        published_after_ms = _positive_int_or_none(since_ms) or 0
        overlap_ms = _rest_overlap_ms(policy=policy, cursor=cursor)
        max_pages = _max_rest_pages(policy)
        stop_threshold_ms = previous_high_watermark_ms - overlap_ms
        entries_by_id: dict[str, dict[str, Any]] = {}
        high_watermark_ms = previous_high_watermark_ms
        oldest_seen_ms = 0
        rest_received = 0
        pages_scanned = 0
        stop_reason = "max_pages"
        for page in range(1, max_pages + 1):
            body = _rest_search_body(
                subscription=subscription,
                policy=policy,
                limit=limit,
                page=page,
                since_ms=published_after_ms,
            )
            payload_result = await self._post_json(
                f"{self._api_base_url}/open/news_search",
                token=self._token or "",
                body=body,
            )
            if not isinstance(payload_result, Mapping):
                raise ValueError("OpenNews REST search returned a non-object response")
            data = payload_result.get("data")
            pages_scanned += 1
            if not isinstance(data, list) or not data:
                stop_reason = "empty_page"
                break
            page_oldest_ms: int | None = None
            for item in data:
                if not isinstance(item, Mapping):
                    continue
                entry = _entry_from_params(item, method="news.rest", now_ms=self._now_ms)
                if entry is None:
                    continue
                entry_key = _entry_key(entry)
                if not entry_key:
                    continue
                published_ms = int(entry.get("published_at_ms") or 0)
                high_watermark_ms = max(high_watermark_ms, published_ms)
                oldest_seen_ms = published_ms if oldest_seen_ms <= 0 else min(oldest_seen_ms, published_ms)
                page_oldest_ms = published_ms if page_oldest_ms is None else min(page_oldest_ms, published_ms)
                rest_received += 1
                if published_after_ms > 0 and published_ms < published_after_ms:
                    continue
                entries_by_id[entry_key] = _merge_entry(entries_by_id.get(entry_key), entry)
            if published_after_ms > 0 and page_oldest_ms is not None and page_oldest_ms < published_after_ms:
                stop_reason = "oldest_before_since"
                break
            if previous_high_watermark_ms > 0 and page_oldest_ms is not None and page_oldest_ms < stop_threshold_ms:
                stop_reason = "oldest_before_overlap"
                break
        next_cursor = {
            "high_watermark_ms": high_watermark_ms,
            "overlap_ms": overlap_ms,
            "pages_scanned": pages_scanned,
            "rest_received": rest_received,
            "oldest_seen_ms": oldest_seen_ms,
            "stop_reason": stop_reason,
        }
        return list(entries_by_id.values()), next_cursor


async def _default_post_json(url: str, *, token: str, body: Mapping[str, Any]) -> dict[str, Any]:
    import httpx

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), headers=headers) as client:
        response = await client.post(url, json=dict(body))
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("OpenNews REST search returned a non-object response")
    return payload


def _run_rest_fetch[ResultT](coro: Coroutine[Any, Any, ResultT]) -> ResultT:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    coro.close()
    raise RuntimeError("OpenNewsFeedClient.fetch must be called from a synchronous worker thread")


def _source_fetch_policy(source: Mapping[str, Any]) -> dict[str, Any]:
    raw = source.get("fetch_policy_json")
    if isinstance(raw, Mapping):
        return dict(raw)
    if raw is not None:
        raise ValueError("OpenNews fetch_policy_json must be a mapping")
    return {}


def _reject_removed_websocket_policy(policy: Mapping[str, Any]) -> None:
    removed = sorted(key for key in _REMOVED_WEBSOCKET_POLICY_KEYS if key in policy)
    if removed:
        raise ValueError(f"removed OpenNews websocket policy keys: {', '.join(removed)}")


def _subscription_params(url: str, policy: Mapping[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    engine_types = _engine_types(policy.get("engineTypes") or policy.get("engine_types"))
    if not engine_types:
        engine_types = _engine_types_from_url(url)
    if engine_types:
        params["engineTypes"] = engine_types

    coins = _string_list(policy.get("coins")) or _csv_query_values(url, "coins")
    if coins:
        params["coins"] = coins

    if "hasCoin" in policy or "has_coin" in policy:
        params["hasCoin"] = _truthy(policy.get("hasCoin", policy.get("has_coin")))
    else:
        has_coin = _first_query_value(url, "hasCoin") or _first_query_value(url, "has_coin")
        if has_coin is not None:
            params["hasCoin"] = _truthy(has_coin)
    return params


def _engine_types(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, list[str]] = {}
    for engine_type, news_types in value.items():
        key = str(engine_type or "").strip()
        if not key:
            continue
        result[key] = _string_list(news_types)
    return result


def _engine_types_from_url(url: str) -> dict[str, list[str]]:
    query = _query_params(url)
    result: dict[str, list[str]] = {}
    for key, values in query.items():
        if not key.startswith("engine."):
            continue
        engine_type = key.removeprefix("engine.").strip()
        if not engine_type:
            continue
        result[engine_type] = _split_csv_values(values)
    return result


def _rest_search_body(
    *,
    subscription: Mapping[str, Any],
    policy: Mapping[str, Any],
    limit: int | None,
    page: int,
    since_ms: int | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "limit": _rest_limit(policy=policy, limit=limit),
        "page": max(1, int(page)),
    }
    for key in ("engineTypes", "coins", "hasCoin"):
        if key in subscription:
            body[key] = subscription[key]
    query = _optional_text(policy.get("q") or policy.get("query") or policy.get("keyword"))
    if query:
        body["q"] = query
    score = _positive_int_or_none(policy.get("score", policy.get("min_score", policy.get("minScore"))))
    if score is not None:
        body["score"] = score
    published_after_ms = _positive_int_or_none(since_ms)
    if published_after_ms is not None:
        body["publishedAfterMs"] = published_after_ms
    return body


def _rest_limit(*, policy: Mapping[str, Any], limit: int | None) -> int:
    value = policy.get("rest_limit")
    if value is None:
        value = limit
    return min(MAX_REST_LIMIT, _required_positive_int(value, "rest_limit"))


def _max_rest_pages(policy: Mapping[str, Any]) -> int:
    value = policy.get("max_rest_pages")
    return _required_positive_int(value, "max_rest_pages")


def _rest_overlap_ms(*, policy: Mapping[str, Any], cursor: Mapping[str, Any]) -> int:
    value = policy.get("rest_overlap_ms")
    if value is None:
        value = cursor.get("overlap_ms")
    return _required_positive_int(value, "rest_overlap_ms")


def _cursor_int(cursor: Mapping[str, Any], key: str) -> int:
    try:
        value = int(cursor.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def _required_positive_int(value: Any, field_name: str) -> int:
    if value is None:
        raise ValueError(f"OpenNews REST fetch policy missing {field_name}")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"OpenNews REST fetch policy invalid {field_name}") from exc
    if parsed <= 0:
        raise ValueError(f"OpenNews REST fetch policy invalid {field_name}")
    return parsed


def _positive_int_or_none(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _entry_from_params(params: Mapping[str, Any], *, method: str, now_ms: Callable[[], int]) -> dict[str, Any] | None:
    provider_article_id = _provider_article_id(params)
    source_item_key = _optional_text(params.get("sourceItemKey"))
    observation_key = source_item_key or provider_article_id
    identity_key = provider_article_id or source_item_key
    link = _optional_text(params.get("link") or params.get("url")) or _fallback_link(identity_key or "")
    title = _optional_text(params.get("title") or params.get("text"))
    if not identity_key:
        return None
    ai_rating = params.get("aiRating") if isinstance(params.get("aiRating"), Mapping) else {}
    summary = _optional_text(ai_rating.get("summary")) or _optional_text(params.get("summary")) or ""
    en_summary = _optional_text(ai_rating.get("enSummary")) or ""
    body = en_summary or summary or title
    entry = {
        "guid": observation_key,
        "summary": summary,
        "language": _optional_text(params.get("language")) or "en",
        "published_at_ms": _epoch_ms(params.get("ts") or params.get("published_at_ms"), now_ms=now_ms),
        "source_domain": _optional_text(params.get("newsType")),
        "opennews_method": method,
        "provider_signal": provider_signal_from_opennews_payload(params),
        "provider_token_impacts": provider_token_impacts_from_opennews_payload(params),
        "raw": _json_safe_dict(params),
    }
    if provider_article_id:
        entry["id"] = provider_article_id
        entry["provider_article_id"] = provider_article_id
        entry["provider_article_key"] = f"opennews:{provider_article_id}"
    if source_item_key:
        entry["source_item_key"] = source_item_key
    if link:
        entry["link"] = link
    if title:
        entry["title"] = title
    if body:
        entry["content"] = [{"value": body}]
    return entry


def _entry_key(entry: Mapping[str, Any]) -> str:
    return (
        _optional_text(entry.get("provider_article_id"))
        or _optional_text(entry.get("id"))
        or _optional_text(entry.get("guid"))
        or ""
    )


def _merge_entry(existing: Mapping[str, Any] | None, patch: Mapping[str, Any]) -> dict[str, Any]:
    if existing is None:
        return dict(patch)
    merged = dict(existing)
    keep_ready_payload = _entry_payload_ready(existing) and not _entry_payload_ready(patch)
    for key, value in patch.items():
        if keep_ready_payload and key in _READY_PROTECTED_ENTRY_FIELDS:
            continue
        if key == "raw" and isinstance(merged.get("raw"), Mapping) and isinstance(value, Mapping):
            merged["raw"] = {**dict(merged["raw"]), **dict(value)}
            continue
        if key == "provider_signal" and _keeps_existing_provider_signal(merged.get(key), value):
            continue
        if key == "link" and _keeps_existing_link(merged.get(key), value):
            continue
        if _is_present(value):
            merged[key] = value
    return merged


def _entry_is_visible(entry: Mapping[str, Any]) -> bool:
    return bool(
        (_optional_text(entry.get("id")) or _optional_text(entry.get("guid")))
        and _optional_text(entry.get("link"))
        and _optional_text(entry.get("title"))
    )


def _fallback_link(article_id: str) -> str:
    return f"opennews://item/{quote(article_id, safe='')}"


def _provider_article_id(params: Mapping[str, Any]) -> str:
    for field_name in ("provider_article_id", "article_id", "id"):
        value = _optional_text(params.get(field_name))
        if value:
            return value
    return ""


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list | tuple | set | dict):
        return bool(value)
    return True


def _keeps_existing_provider_signal(existing: Any, patch: Any) -> bool:
    if not isinstance(existing, Mapping) or not isinstance(patch, Mapping):
        return False
    return str(existing.get("status") or "") == "ready" and str(patch.get("status") or "") != "ready"


_READY_PROTECTED_ENTRY_FIELDS = frozenset(
    {
        "raw",
        "link",
        "title",
        "summary",
        "content",
        "provider_token_impacts",
        "published_at_ms",
        "language",
        "source_domain",
    }
)


def _entry_payload_ready(value: Mapping[str, Any]) -> bool:
    provider_signal = value.get("provider_signal")
    if isinstance(provider_signal, Mapping) and str(provider_signal.get("status") or "") == "ready":
        return True
    raw = value.get("raw")
    ai_rating = raw.get("aiRating") if isinstance(raw, Mapping) else None
    return isinstance(ai_rating, Mapping) and str(ai_rating.get("status") or "") == "done"


def _keeps_existing_link(existing: Any, patch: Any) -> bool:
    existing_link = _optional_text(existing)
    patch_link = _optional_text(patch)
    return bool(existing_link and patch_link and not _is_fallback_link(existing_link) and _is_fallback_link(patch_link))


def _is_fallback_link(value: str) -> bool:
    return value.startswith("opennews://item/")


def _query_params(url: str) -> dict[str, list[str]]:
    return {key: values for key, values in _raw_query_params(url).items()}


def _raw_query_params(url: str) -> dict[str, list[str]]:
    split = urlsplit(url)
    params: dict[str, list[str]] = {}
    for key, value in parse_qsl(split.query, keep_blank_values=True):
        params.setdefault(key, []).append(value)
    return params


def _first_query_value(url: str, key: str) -> str | None:
    values = _raw_query_params(url).get(key)
    if not values:
        return None
    return values[0]


def _csv_query_values(url: str, key: str) -> list[str]:
    return _split_csv_values(_raw_query_params(url).get(key, []))


def _split_csv_values(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        result.extend(_string_list(value))
    return result


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, list | tuple | set):
        parts = value
    else:
        parts = (value,)
    return [text for item in parts if (text := str(item or "").strip())]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _epoch_ms(value: Any, *, now_ms: Callable[[], int]) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        parsed = _iso_epoch_ms(value)
        return parsed if parsed is not None else now_ms()
    if numeric <= 0:
        return now_ms()
    if numeric < 10_000_000_000:
        numeric *= 1000
    return int(numeric)


def _iso_epoch_ms(value: Any) -> int | None:
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


def _json_safe_dict(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(dict(value), default=str, ensure_ascii=False, sort_keys=True))


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["DEFAULT_OPENNEWS_API_BASE_URL", "OpenNewsFeedClient"]
