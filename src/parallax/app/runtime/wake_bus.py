from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any


class WakeBus:
    def __init__(self, conn_factory: Callable[[], Any]) -> None:
        self._conn_factory = conn_factory

    def notify_market_tick_written(self, *, target_type: str, target_id: str) -> None:
        self._notify(
            "market_tick_written",
            {
                "target_type": str(target_type),
                "target_id": str(target_id),
            },
        )

    def notify_market_tick_current_updated(self, *, target_type: str, target_id: str) -> None:
        self._notify(
            "market_tick_current_updated",
            {
                "target_type": str(target_type),
                "target_id": str(target_id),
            },
        )

    def notify_resolution_updated(self, *, lookup_keys: Sequence[str]) -> None:
        self._notify("resolution_updated", {"lookup_keys": [str(item) for item in lookup_keys]})

    def notify_token_radar_updated(self, *, window: str, scope: str) -> None:
        self._notify("token_radar_updated", {"window": str(window), "scope": str(scope)})

    def notify_news_item_written(self, *, source_id: str, count: int) -> None:
        self._notify("news_item_written", {"source_id": str(source_id), "count": int(count)})

    def notify_news_item_processed(self, *, count: int) -> None:
        self._notify("news_item_processed", {"count": int(count)})

    def notify_news_item_brief_updated(self, *, count: int) -> None:
        self._notify("news_item_brief_updated", {"count": int(count)})

    def notify_news_page_dirty(self, *, count: int, reason: str) -> None:
        self._notify("news_page_dirty", {"count": int(count), "reason": str(reason)})

    def notify_macro_observations_imported(
        self,
        *,
        count: int,
        max_observed_at: str | None,
        asof_date: str | None,
    ) -> None:
        self._notify(
            "macro_observations_imported",
            {
                "count": int(count),
                "max_observed_at": max_observed_at,
                "asof_date": asof_date,
            },
        )

    def notify_macro_view_snapshot_updated(self, *, projection_version: str, status: str, regime: str) -> None:
        self._notify(
            "macro_view_snapshot_updated",
            {
                "projection_version": str(projection_version),
                "status": str(status),
                "regime": str(regime),
            },
        )

    def _notify(self, channel: str, payload: dict[str, Any]) -> None:
        context = self._conn_factory()
        _require_connection_context(context)
        with context as conn:
            _execute_notify(conn, channel=channel, payload=payload)
            _commit(conn)


def _require_connection_context(context: Any) -> None:
    try:
        enter = context.__enter__
        exit_ = context.__exit__
    except AttributeError as exc:
        raise RuntimeError("wake_bus_connection_context_required") from exc
    if not callable(enter) or not callable(exit_):
        raise RuntimeError("wake_bus_connection_context_required")


def _execute_notify(conn: Any, *, channel: str, payload: dict[str, Any]) -> None:
    conn.execute(
        "SELECT pg_notify(%s, %s)",
        (channel, json.dumps(payload, sort_keys=True, separators=(",", ":"))),
    )


def _commit(conn: Any) -> None:
    try:
        commit = conn.commit
    except AttributeError as exc:
        raise RuntimeError("wake_bus_commit_required") from exc
    if not callable(commit):
        raise RuntimeError("wake_bus_commit_required")
    commit()
