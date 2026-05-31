from __future__ import annotations

import base64
import json
import re
from typing import Any

WATCHLIST_HANDLE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class WatchlistTimelineCursorError(ValueError):
    pass


def normalize_watchlist_handle(value: str) -> str:
    normalized = str(value or "").strip().lstrip("@").lower()
    if not WATCHLIST_HANDLE_RE.fullmatch(normalized):
        raise ValueError("invalid_handle")
    return normalized


def encode_watchlist_timeline_cursor(*, received_at_ms: int, event_id: str) -> str:
    payload = {"received_at_ms": int(received_at_ms), "event_id": str(event_id)}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_watchlist_timeline_cursor(cursor: str) -> tuple[int, str]:
    raw = str(cursor or "").strip()
    if not raw:
        raise WatchlistTimelineCursorError("empty_cursor")
    try:
        padded = raw + "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise WatchlistTimelineCursorError("invalid_cursor") from exc
    if not isinstance(payload, dict):
        raise WatchlistTimelineCursorError("invalid_cursor")
    event_id = str(payload.get("event_id") or "")
    raw_received_at_ms = payload.get("received_at_ms")
    if raw_received_at_ms is None:
        raise WatchlistTimelineCursorError("invalid_cursor")
    try:
        received_at_ms = int(raw_received_at_ms)
    except (TypeError, ValueError) as exc:
        raise WatchlistTimelineCursorError("invalid_cursor") from exc
    if received_at_ms <= 0 or not event_id:
        raise WatchlistTimelineCursorError("invalid_cursor")
    return received_at_ms, event_id


def json_default(value: Any) -> Any:
    if isinstance(value, tuple | set):
        return list(value)
    return str(value)


__all__ = [
    "WATCHLIST_HANDLE_RE",
    "WatchlistTimelineCursorError",
    "decode_watchlist_timeline_cursor",
    "encode_watchlist_timeline_cursor",
    "json_default",
    "normalize_watchlist_handle",
]
