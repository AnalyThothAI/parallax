from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from inspect import isawaitable
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from gmgn_twitter_intel.domains.news_intel.services.opennews_provider_signal import (
    provider_signal_from_opennews_payload,
    provider_token_impacts_from_opennews_payload,
)
from gmgn_twitter_intel.integrations.news_feeds.feed_client import FeedFetchResult

DEFAULT_OPENNEWS_WSS_URL = "wss://ai.6551.io/open/news_wss"
DEFAULT_OPENNEWS_API_BASE_URL = "https://ai.6551.io"
DEFAULT_CONNECT_TIMEOUT_SECONDS = 3.0
DEFAULT_STREAM_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_MESSAGES = 20
DEFAULT_REST_PAGE = 1
MAX_REST_LIMIT = 100
_PUSH_METHODS = {"news.update", "news.ai_update"}


class OpenNewsFeedClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        api_base_url: str = DEFAULT_OPENNEWS_API_BASE_URL,
        wss_url: str = DEFAULT_OPENNEWS_WSS_URL,
        connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
        connect: Callable[..., Any] | None = None,
        post_json: Callable[..., Any] | None = None,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        self._token = _optional_text(token)
        self._api_base_url = str(api_base_url or DEFAULT_OPENNEWS_API_BASE_URL).strip().rstrip(
            "/"
        ) or DEFAULT_OPENNEWS_API_BASE_URL
        self._wss_url = str(wss_url or DEFAULT_OPENNEWS_WSS_URL).strip() or DEFAULT_OPENNEWS_WSS_URL
        self._connect_timeout_seconds = max(0.1, float(connect_timeout_seconds))
        self._connect = connect or _default_connect
        self._post_json = post_json or _default_post_json
        self._now_ms = now_ms or _now_ms
        self._request_id = 0

    def fetch(
        self,
        url: str,
        *,
        source: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> FeedFetchResult:
        if not self._token:
            raise ValueError("OpenNews token is not configured")
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._fetch_async(url, source=source or {}, limit=limit))
        raise RuntimeError("OpenNewsFeedClient.fetch must be called from a synchronous worker thread")

    def close(self) -> None:
        return None

    async def _fetch_async(
        self,
        url: str,
        *,
        source: Mapping[str, Any],
        limit: int | None,
    ) -> FeedFetchResult:
        policy = _source_fetch_policy(source)
        subscription = _subscription_params(url, policy)
        fetch_mode = _fetch_mode(policy)
        max_messages = _max_messages(policy=policy, limit=limit)
        stream_timeout_seconds = _stream_timeout_seconds(policy)
        websocket_received = 0
        rest_received = 0
        rest_error: str | None = None
        rest_success = False
        entries_by_id: dict[str, dict[str, Any]] = {}
        if fetch_mode in {"hybrid", "websocket"}:
            connected_url = _with_token(self._wss_url, self._token or "")
            async with self._connect(
                connected_url,
                open_timeout=self._connect_timeout_seconds,
                ping_interval=20,
                close_timeout=1,
            ) as websocket:
                subscribe_id = self._next_request_id("opennews_subscribe")
                await _send_json(
                    websocket,
                    {
                        "jsonrpc": "2.0",
                        "id": subscribe_id,
                        "method": "news.subscribe",
                        "params": subscription,
                    },
                )
                ack = await _recv_json(websocket, timeout_seconds=self._connect_timeout_seconds)
                _validate_subscribe_ack(ack)

                deadline = time.monotonic() + stream_timeout_seconds
                messages_seen = 0
                while messages_seen < max_messages:
                    remaining_seconds = deadline - time.monotonic()
                    if remaining_seconds <= 0:
                        break
                    try:
                        message = await _recv_json(websocket, timeout_seconds=remaining_seconds)
                    except TimeoutError:
                        break
                    messages_seen += 1
                    entry = _entry_from_message(message, now_ms=self._now_ms)
                    if entry is None:
                        continue
                    entry_key = _entry_key(entry)
                    if not entry_key:
                        continue
                    websocket_received += 1
                    merged_entry = _merge_entry(entries_by_id.get(entry_key), entry)
                    entries_by_id[entry_key] = merged_entry

                await _send_json(
                    websocket,
                    {
                        "jsonrpc": "2.0",
                        "id": self._next_request_id("opennews_unsubscribe"),
                        "method": "news.unsubscribe",
                    },
                )
        if fetch_mode in {"hybrid", "rest"}:
            try:
                for entry in await self._fetch_rest_entries(
                    subscription=subscription,
                    policy=policy,
                    limit=limit,
                ):
                    entry_key = _entry_key(entry)
                    if not entry_key:
                        continue
                    rest_received += 1
                    entries_by_id[entry_key] = _merge_entry(entries_by_id.get(entry_key), entry)
                rest_success = True
            except Exception as exc:
                if fetch_mode == "rest":
                    raise
                rest_error = _compact_error(exc)
        entries = [entry for entry in entries_by_id.values() if _entry_is_visible(entry)]
        feed = {
            "provider": "opennews",
            "subscription": subscription,
            "received": len(entries),
        }
        if fetch_mode in {"hybrid", "rest"}:
            feed.update(
                {
                    "fetch_mode": fetch_mode,
                    "websocket_received": websocket_received,
                    "rest_received": rest_received,
                }
            )
            if rest_error:
                feed["rest_error"] = rest_error
        return FeedFetchResult(
            status_code=200 if rest_success else 101,
            entries=entries,
            not_modified=False,
            feed=feed,
        )

    async def _fetch_rest_entries(
        self,
        *,
        subscription: Mapping[str, Any],
        policy: Mapping[str, Any],
        limit: int | None,
    ) -> list[dict[str, Any]]:
        body = _rest_search_body(subscription=subscription, policy=policy, limit=limit)
        payload_result = self._post_json(
            f"{self._api_base_url}/open/news_search",
            token=self._token or "",
            body=body,
        )
        if isawaitable(payload_result):
            payload_result = await payload_result
        if not isinstance(payload_result, Mapping):
            raise ValueError("OpenNews REST search returned a non-object response")
        data = payload_result.get("data")
        if not isinstance(data, list):
            return []
        entries: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, Mapping):
                continue
            entry = _entry_from_params(item, method="news.rest", now_ms=self._now_ms)
            if entry is not None:
                entries.append(entry)
        return entries

    def _next_request_id(self, prefix: str) -> str:
        self._request_id += 1
        return f"{prefix}_{self._request_id}"


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


def _default_connect(url: str, **kwargs: Any) -> Any:
    import websockets

    return websockets.connect(url, **kwargs)


async def _send_json(websocket: Any, payload: Mapping[str, Any]) -> None:
    await websocket.send(json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":")))


async def _recv_json(websocket: Any, *, timeout_seconds: float) -> dict[str, Any]:
    try:
        raw = await asyncio.wait_for(websocket.recv(), timeout=max(0.001, float(timeout_seconds)))
    except TimeoutError as exc:
        raise TimeoutError("OpenNews websocket receive timed out") from exc
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        payload = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise ValueError("OpenNews websocket returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("OpenNews websocket returned a non-object message")
    return payload


def _validate_subscribe_ack(payload: Mapping[str, Any]) -> None:
    error = payload.get("error")
    if isinstance(error, Mapping):
        message = _optional_text(error.get("message")) or "OpenNews subscription failed"
        raise ValueError(message)
    result = payload.get("result")
    if isinstance(result, Mapping) and result.get("success") is False:
        raise ValueError("OpenNews subscription failed")


def _source_fetch_policy(source: Mapping[str, Any]) -> dict[str, Any]:
    raw = source.get("fetch_policy_json")
    if raw is None:
        raw = source.get("fetch_policy")
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}
    return {}


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


def _max_messages(*, policy: Mapping[str, Any], limit: int | None) -> int:
    value = policy.get("max_messages", policy.get("maxMessages"))
    if value is None:
        value = limit
    if value is None:
        value = DEFAULT_MAX_MESSAGES
    return max(1, int(value))


def _stream_timeout_seconds(policy: Mapping[str, Any]) -> float:
    value = policy.get("stream_timeout_seconds", policy.get("streamTimeoutSeconds"))
    if value is None:
        value = DEFAULT_STREAM_TIMEOUT_SECONDS
    return max(0.001, float(value))


def _fetch_mode(policy: Mapping[str, Any]) -> str:
    raw_mode = _optional_text(policy.get("fetch_mode") or policy.get("fetchMode") or policy.get("mode"))
    mode = str(raw_mode or "").strip().lower()
    if mode in {"rest", "poll", "search"}:
        return "rest"
    if mode in {"websocket", "ws", "stream"}:
        return "websocket"
    if mode in {"hybrid", "websocket+rest", "ws+rest"}:
        return "hybrid"
    if "rest_backfill" in policy or "restBackfill" in policy:
        return "hybrid" if _truthy(policy.get("rest_backfill", policy.get("restBackfill"))) else "websocket"
    return "hybrid"


def _rest_search_body(
    *,
    subscription: Mapping[str, Any],
    policy: Mapping[str, Any],
    limit: int | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "limit": _rest_limit(policy=policy, limit=limit),
        "page": _positive_int_or_default(policy.get("page"), DEFAULT_REST_PAGE),
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
    return body


def _rest_limit(*, policy: Mapping[str, Any], limit: int | None) -> int:
    value = policy.get(
        "rest_limit",
        policy.get("restLimit", policy.get("search_limit", policy.get("searchLimit"))),
    )
    if value is None:
        value = _max_messages(policy=policy, limit=limit)
    return max(1, min(MAX_REST_LIMIT, _positive_int_or_default(value, DEFAULT_MAX_MESSAGES)))


def _positive_int_or_default(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return int(default)
    return parsed if parsed > 0 else int(default)


def _positive_int_or_none(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _entry_from_message(message: Mapping[str, Any], *, now_ms: Callable[[], int]) -> dict[str, Any] | None:
    method = str(message.get("method") or "")
    if method not in _PUSH_METHODS:
        return None
    params = message.get("params")
    if not isinstance(params, Mapping):
        return None
    return _entry_from_params(params, method=method, now_ms=now_ms)


def _entry_from_params(params: Mapping[str, Any], *, method: str, now_ms: Callable[[], int]) -> dict[str, Any] | None:
    article_id = _optional_text(params.get("id")) or _optional_text(params.get("sourceItemKey"))
    link = _optional_text(params.get("link") or params.get("url")) or _fallback_link(article_id)
    title = _optional_text(params.get("title") or params.get("text"))
    if not article_id:
        return None
    ai_rating = params.get("aiRating") if isinstance(params.get("aiRating"), Mapping) else {}
    summary = _optional_text(ai_rating.get("summary")) or _optional_text(params.get("summary")) or ""
    en_summary = _optional_text(ai_rating.get("enSummary")) or ""
    body = en_summary or summary or title
    entry = {
        "id": article_id,
        "guid": article_id,
        "summary": summary,
        "language": _optional_text(params.get("language")) or "en",
        "published_at_ms": _epoch_ms(params.get("ts") or params.get("published_at_ms"), now_ms=now_ms),
        "source_domain": _optional_text(params.get("newsType")),
        "opennews_method": method,
        "provider_signal": provider_signal_from_opennews_payload(params),
        "provider_token_impacts": provider_token_impacts_from_opennews_payload(params),
        "raw": _json_safe_dict(params),
    }
    if link:
        entry["link"] = link
    if title:
        entry["title"] = title
    if body:
        entry["content"] = [{"value": body}]
    return entry


def _entry_key(entry: Mapping[str, Any]) -> str:
    return _optional_text(entry.get("id")) or _optional_text(entry.get("guid")) or ""


def _merge_entry(existing: Mapping[str, Any] | None, patch: Mapping[str, Any]) -> dict[str, Any]:
    if existing is None:
        return dict(patch)
    merged = dict(existing)
    for key, value in patch.items():
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
        _optional_text(entry.get("id"))
        and _optional_text(entry.get("link"))
        and _optional_text(entry.get("title"))
    )


def _fallback_link(article_id: str) -> str:
    return f"opennews://item/{quote(article_id, safe='')}"


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


def _keeps_existing_link(existing: Any, patch: Any) -> bool:
    existing_link = _optional_text(existing)
    patch_link = _optional_text(patch)
    return bool(existing_link and patch_link and not _is_fallback_link(existing_link) and _is_fallback_link(patch_link))


def _is_fallback_link(value: str) -> bool:
    return value.startswith("opennews://item/")


def _with_token(wss_url: str, token: str) -> str:
    split = urlsplit(wss_url)
    query = [(key, value) for key, value in parse_qsl(split.query, keep_blank_values=True) if key != "token"]
    query.append(("token", token))
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


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


def _compact_error(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    if "Bearer " in text:
        text = text.split("Bearer ", 1)[0] + "Bearer <redacted>"
    return text[:240]


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["DEFAULT_OPENNEWS_WSS_URL", "OpenNewsFeedClient"]
