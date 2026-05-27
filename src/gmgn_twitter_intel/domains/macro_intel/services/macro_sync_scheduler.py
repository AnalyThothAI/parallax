from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gmgn_twitter_intel.app.runtime.repository_session import RepositorySession


def ensure_due_macro_sync_windows(
    *,
    repos: RepositorySession,
    source_name: str,
    bundle_name: str,
    now: date,
    now_ms: int,
    bootstrap_lookback_days: int,
    max_window_days: int,
    steady_overlap_days: int,
    steady_interval_seconds: float,
    max_bootstrap_windows_per_cycle: int,
    max_attempts: int,
) -> dict[str, Any]:
    max_observed_at = repos.macro_intel.macro_observations_max_observed_at()
    enqueued_bootstrap = 0
    enqueued_gap = 0
    enqueued_steady = 0
    steady_trigger_reason = _steady_trigger_reason(
        now_ms=now_ms,
        interval_seconds=steady_interval_seconds,
    )

    if max_observed_at is None:
        bootstrap_start = now - timedelta(days=max(1, int(bootstrap_lookback_days)))
        for window_start, window_end in _split_windows(
            bootstrap_start,
            now,
            max_window_days=max_window_days,
        )[: max(1, int(max_bootstrap_windows_per_cycle))]:
            repos.macro_intel.enqueue_macro_sync_window(
                source_name=source_name,
                bundle_name=bundle_name,
                window_start=window_start,
                window_end=window_end,
                trigger_reason="bootstrap",
                priority=10,
                due_at_ms=now_ms,
                max_attempts=max_attempts,
                now_ms=now_ms,
            )
            enqueued_bootstrap += 1
    elif max_observed_at < now:
        for window_start, window_end in _split_windows(
            max_observed_at + timedelta(days=1),
            now,
            max_window_days=max_window_days,
        ):
            repos.macro_intel.enqueue_macro_sync_window(
                source_name=source_name,
                bundle_name=bundle_name,
                window_start=window_start,
                window_end=window_end,
                trigger_reason="gap",
                priority=20,
                due_at_ms=now_ms,
                max_attempts=max_attempts,
                now_ms=now_ms,
            )
            enqueued_gap += 1

    steady_start = now - timedelta(days=max(1, int(steady_overlap_days)))
    repos.macro_intel.enqueue_macro_sync_window(
        source_name=source_name,
        bundle_name=bundle_name,
        window_start=steady_start,
        window_end=now,
        trigger_reason=steady_trigger_reason,
        priority=100,
        due_at_ms=now_ms,
        max_attempts=max_attempts,
        now_ms=now_ms,
    )
    enqueued_steady += 1

    return {
        "max_observed_at": str(max_observed_at) if max_observed_at else None,
        "enqueued_bootstrap_windows": enqueued_bootstrap,
        "enqueued_gap_windows": enqueued_gap,
        "enqueued_steady_windows": enqueued_steady,
        "enqueued_windows": enqueued_bootstrap + enqueued_gap + enqueued_steady,
    }


def _split_windows(start: date, end: date, *, max_window_days: int) -> list[tuple[date, date]]:
    if start > end:
        return []
    bounded_days = max(1, int(max_window_days))
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        window_end = min(end, cursor + timedelta(days=bounded_days - 1))
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows


def _steady_trigger_reason(*, now_ms: int, interval_seconds: float) -> str:
    interval_ms = max(1, int(float(interval_seconds) * 1000))
    bucket_start_ms = (int(now_ms) // interval_ms) * interval_ms
    return f"steady_overlap:{bucket_start_ms}"


__all__ = ["ensure_due_macro_sync_windows"]
