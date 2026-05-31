from __future__ import annotations

SIGNAL_PULSE_WINDOWS = ("1h", "4h")
SIGNAL_PULSE_WINDOW_SET = frozenset(SIGNAL_PULSE_WINDOWS)
SIGNAL_PULSE_DEFAULT_WINDOW = "4h"
SIGNAL_PULSE_STALE_JOB_TTL_SECONDS = {"1h": 3600, "4h": 14400}


def validate_signal_pulse_window(value: str) -> str:
    window = str(value or "").strip()
    if window not in SIGNAL_PULSE_WINDOW_SET:
        allowed = ", ".join(SIGNAL_PULSE_WINDOWS)
        raise ValueError(f"signal pulse window must be one of: {allowed}")
    return window


def validate_signal_pulse_windows(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    windows = tuple(str(value or "").strip() for value in values if str(value or "").strip())
    if not windows:
        raise ValueError("signal pulse windows are required")
    invalid = tuple(window for window in windows if window not in SIGNAL_PULSE_WINDOW_SET)
    if invalid:
        allowed = ", ".join(SIGNAL_PULSE_WINDOWS)
        rejected = ", ".join(invalid)
        raise ValueError(f"signal pulse windows must be one of: {allowed}; got: {rejected}")
    return windows


__all__ = [
    "SIGNAL_PULSE_DEFAULT_WINDOW",
    "SIGNAL_PULSE_STALE_JOB_TTL_SECONDS",
    "SIGNAL_PULSE_WINDOWS",
    "SIGNAL_PULSE_WINDOW_SET",
    "validate_signal_pulse_window",
    "validate_signal_pulse_windows",
]
