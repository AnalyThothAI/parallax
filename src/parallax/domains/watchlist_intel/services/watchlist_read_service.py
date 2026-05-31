from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from parallax.domains.watchlist_intel.types import normalize_watchlist_handle


@dataclass(frozen=True, slots=True)
class WatchlistReadWindowConfig:
    window_days: int = 3


class WatchlistHandleReadService:
    def __init__(self, *, repository: Any, config: WatchlistReadWindowConfig | None = None):
        self.repository = repository
        self.config = config or WatchlistReadWindowConfig()

    def handles_overview(
        self,
        *,
        configured_handles: Sequence[str],
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        window_days = max(1, int(self.config.window_days))
        rows = self.repository.handles_overview(
            handles=tuple(normalize_watchlist_handle(handle) for handle in configured_handles),
            since_ms=_window_since_ms(now_ms=resolved_now_ms, window_days=window_days),
        )
        return {
            "window": f"{window_days}d",
            "items": [dict(row) for row in rows],
        }

    def overview(
        self,
        *,
        handle: str,
        configured_handles: Sequence[str],
        scope: str,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        normalized = _configured_handle(handle, tuple(configured_handles))
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        window_days = max(1, int(self.config.window_days))
        overview = cast(
            dict[str, Any],
            self.repository.handle_overview(
                handle=normalized,
                scope=scope,
                since_ms=_window_since_ms(now_ms=resolved_now_ms, window_days=window_days),
            ),
        )
        query = dict(overview.get("query") or {})
        overview["query"] = {
            "handle": normalized,
            "scope": str(query.get("scope") or scope),
            "window": f"{window_days}d",
        }
        return overview

    def timeline(
        self,
        *,
        handle: str,
        configured_handles: tuple[str, ...],
        scope: str,
        cursor: str | None,
        limit: int,
    ) -> dict[str, Any]:
        normalized = _configured_handle(handle, configured_handles)
        return cast(
            dict[str, Any],
            self.repository.timeline(handle=normalized, scope=scope, cursor=cursor, limit=limit),
        )


def _configured_handle(handle: str, configured_handles: tuple[str, ...]) -> str:
    normalized = normalize_watchlist_handle(handle)
    configured = {normalize_watchlist_handle(item) for item in configured_handles}
    if normalized not in configured:
        raise LookupError("handle_not_found")
    return normalized


def _window_since_ms(*, now_ms: int, window_days: int) -> int:
    return now_ms - max(1, int(window_days)) * 24 * 60 * 60 * 1000


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = [
    "WatchlistHandleReadService",
    "WatchlistReadWindowConfig",
]
