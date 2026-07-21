from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from parallax.domains.evidence.types.watchlist import normalize_watchlist_handle
from parallax.platform.validation import require_positive_int


@dataclass(frozen=True, slots=True)
class WatchlistReadConfig:
    window_days: int
    overview_source_limit: int
    overview_cluster_limit: int


class WatchlistReadService:
    def __init__(self, *, query: Any, config: WatchlistReadConfig):
        self.query = query
        self.config = config

    def handles_overview(
        self,
        *,
        configured_handles: Sequence[str],
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        window_days = require_positive_int(self.config.window_days, error_code="watchlist_window_days_required")
        rows = self.query.handles_overview(
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
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        normalized = _configured_handle(handle, tuple(configured_handles))
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        window_days = require_positive_int(self.config.window_days, error_code="watchlist_window_days_required")
        overview = cast(
            dict[str, Any],
            self.query.handle_overview(
                handle=normalized,
                since_ms=_window_since_ms(now_ms=resolved_now_ms, window_days=window_days),
                source_limit=require_positive_int(
                    self.config.overview_source_limit,
                    error_code="watchlist_overview_source_limit_required",
                ),
                cluster_limit=require_positive_int(
                    self.config.overview_cluster_limit,
                    error_code="watchlist_overview_cluster_limit_required",
                ),
            ),
        )
        overview["query"] = {
            "handle": normalized,
            "window": f"{window_days}d",
        }
        return overview

    def timeline(
        self,
        *,
        handle: str,
        configured_handles: tuple[str, ...],
        cursor: str | None,
        limit: int,
    ) -> dict[str, Any]:
        normalized = _configured_handle(handle, configured_handles)
        return cast(
            dict[str, Any],
            self.query.timeline(handle=normalized, cursor=cursor, limit=limit),
        )


def _configured_handle(handle: str, configured_handles: tuple[str, ...]) -> str:
    normalized = normalize_watchlist_handle(handle)
    configured = {normalize_watchlist_handle(item) for item in configured_handles}
    if normalized not in configured:
        raise LookupError("handle_not_found")
    return normalized


def _window_since_ms(*, now_ms: int, window_days: int) -> int:
    required_window_days = require_positive_int(window_days, error_code="watchlist_window_days_required")
    return now_ms - required_window_days * 24 * 60 * 60 * 1000


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = [
    "WatchlistReadConfig",
    "WatchlistReadService",
]
