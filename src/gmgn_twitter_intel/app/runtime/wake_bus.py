from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any


class WakeBus:
    def __init__(self, conn_factory: Callable[[], Any]) -> None:
        self._conn_factory = conn_factory

    def notify_market_observation_written(self, *, target_type: str, target_id: str) -> None:
        self._notify(
            "market_observation_written",
            {
                "target_type": str(target_type),
                "target_id": str(target_id),
            },
        )

    def notify_resolution_updated(self, *, lookup_keys: Sequence[str]) -> None:
        self._notify("resolution_updated", {"lookup_keys": [str(item) for item in lookup_keys]})

    def notify_token_radar_updated(self, *, window: str, scope: str) -> None:
        self._notify("token_radar_updated", {"window": str(window), "scope": str(scope)})

    def _notify(self, channel: str, payload: dict[str, Any]) -> None:
        conn_or_context = self._conn_factory()
        if hasattr(conn_or_context, "__enter__"):
            with conn_or_context as conn:
                _execute_notify(conn, channel=channel, payload=payload)
                _commit(conn)
            return
        _execute_notify(conn_or_context, channel=channel, payload=payload)
        _commit(conn_or_context)


class WakeListener:
    def __init__(self, conn_factory: Callable[[], Any]) -> None:
        self._conn_factory = conn_factory

    def listen_projection_wakes(
        self,
        *,
        on_wake: Callable[[], None],
        should_stop: Callable[[], bool],
        interval_seconds: float,
    ) -> None:
        conn_or_context = self._conn_factory()
        if hasattr(conn_or_context, "__enter__"):
            with conn_or_context as conn:
                _listen_projection_wakes(
                    conn,
                    on_wake=on_wake,
                    should_stop=should_stop,
                    interval_seconds=interval_seconds,
                )
            return
        _listen_projection_wakes(
            conn_or_context,
            on_wake=on_wake,
            should_stop=should_stop,
            interval_seconds=interval_seconds,
        )

    def listen_pulse_wakes(
        self,
        *,
        on_wake: Callable[[], None],
        should_stop: Callable[[], bool],
        interval_seconds: float,
    ) -> None:
        conn_or_context = self._conn_factory()
        if hasattr(conn_or_context, "__enter__"):
            with conn_or_context as conn:
                _listen_wakes(
                    conn,
                    channels=("token_radar_updated",),
                    on_wake=on_wake,
                    should_stop=should_stop,
                    interval_seconds=interval_seconds,
                )
            return
        _listen_wakes(
            conn_or_context,
            channels=("token_radar_updated",),
            on_wake=on_wake,
            should_stop=should_stop,
            interval_seconds=interval_seconds,
        )


def _execute_notify(conn: Any, *, channel: str, payload: dict[str, Any]) -> None:
    conn.execute(
        "SELECT pg_notify(%s, %s)",
        (channel, json.dumps(payload, sort_keys=True, separators=(",", ":"))),
    )


def _commit(conn: Any) -> None:
    commit = getattr(conn, "commit", None)
    if commit:
        commit()


def _listen_projection_wakes(
    conn: Any,
    *,
    on_wake: Callable[[], None],
    should_stop: Callable[[], bool],
    interval_seconds: float,
) -> None:
    _listen_wakes(
        conn,
        channels=("market_observation_written", "resolution_updated"),
        on_wake=on_wake,
        should_stop=should_stop,
        interval_seconds=interval_seconds,
    )


def _listen_wakes(
    conn: Any,
    *,
    channels: Sequence[str],
    on_wake: Callable[[], None],
    should_stop: Callable[[], bool],
    interval_seconds: float,
) -> None:
    for channel in channels:
        conn.execute(f"LISTEN {channel}")
    _commit(conn)
    notifies = getattr(conn, "notifies", None)
    if not notifies:
        return
    while not should_stop():
        for _notify in notifies(timeout=max(0.1, float(interval_seconds)), stop_after=1):
            on_wake()
            return
        return
