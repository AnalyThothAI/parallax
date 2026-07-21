from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from parallax.app.runtime.repository_session import RepositorySession


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
    parsed_bootstrap_lookback_days = _required_positive_int(
        bootstrap_lookback_days,
        "macro_sync_bootstrap_lookback_days_required",
    )
    parsed_max_window_days = _required_positive_int(max_window_days, "macro_sync_max_window_days_required")
    parsed_steady_overlap_days = _required_positive_int(
        steady_overlap_days,
        "macro_sync_steady_overlap_days_required",
    )
    parsed_max_bootstrap_windows_per_cycle = _required_positive_int(
        max_bootstrap_windows_per_cycle,
        "macro_sync_max_bootstrap_windows_per_cycle_required",
    )
    parsed_max_attempts = _required_positive_int(max_attempts, "macro_sync_max_attempts_required")
    _required_nonnegative_float(
        steady_interval_seconds,
        "macro_sync_steady_interval_seconds_required",
    )
    max_observed_at = repos.macro_intel.macro_sync_state_max_observed_at(
        source_name=source_name,
        bundle_name=bundle_name,
    )
    enqueued_bootstrap = 0
    enqueued_gap = 0
    enqueued_steady = 0

    if max_observed_at is None:
        bootstrap_start = now - timedelta(days=parsed_bootstrap_lookback_days)
        for window_start, window_end in _split_windows(
            bootstrap_start,
            now,
            max_window_days=parsed_max_window_days,
        )[:parsed_max_bootstrap_windows_per_cycle]:
            repos.macro_intel.enqueue_macro_sync_window(
                source_name=source_name,
                bundle_name=bundle_name,
                window_start=window_start,
                window_end=window_end,
                trigger_reason="bootstrap",
                priority=10,
                due_at_ms=now_ms,
                max_attempts=parsed_max_attempts,
                now_ms=now_ms,
            )
            enqueued_bootstrap += 1
    elif max_observed_at < now:
        for window_start, window_end in _split_windows(
            max_observed_at + timedelta(days=1),
            now,
            max_window_days=parsed_max_window_days,
        ):
            repos.macro_intel.enqueue_macro_sync_window(
                source_name=source_name,
                bundle_name=bundle_name,
                window_start=window_start,
                window_end=window_end,
                trigger_reason="gap",
                priority=20,
                due_at_ms=now_ms,
                max_attempts=parsed_max_attempts,
                now_ms=now_ms,
            )
            enqueued_gap += 1

    steady_start = now - timedelta(days=parsed_steady_overlap_days)
    repos.macro_intel.enqueue_macro_sync_window(
        source_name=source_name,
        bundle_name=bundle_name,
        window_start=steady_start,
        window_end=now,
        trigger_reason="steady_overlap",
        priority=100,
        due_at_ms=now_ms,
        max_attempts=parsed_max_attempts,
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
    bounded_days = _required_positive_int(max_window_days, "macro_sync_max_window_days_required")
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        window_end = min(end, cursor + timedelta(days=bounded_days - 1))
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows


def _required_positive_int(value: object, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(error_code)
    return int(value)


def _required_nonnegative_float(value: object, error_code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(error_code)
    parsed = float(value)
    if parsed < 0:
        raise ValueError(error_code)
    return parsed


__all__ = ["ensure_due_macro_sync_windows"]
