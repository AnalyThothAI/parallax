from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WindowBounds:
    name: str
    start_ms: int
    end_ms: int
    duration_ms: int


def window_bounds(window: str, *, now_ms: int) -> WindowBounds:
    duration_ms = parse_window_ms(window)
    return WindowBounds(name=window, start_ms=now_ms - duration_ms, end_ms=now_ms, duration_ms=duration_ms)


def previous_window(bounds: WindowBounds) -> WindowBounds:
    return WindowBounds(
        name=bounds.name,
        start_ms=bounds.start_ms - bounds.duration_ms,
        end_ms=bounds.start_ms,
        duration_ms=bounds.duration_ms,
    )


def parse_window_ms(window: str) -> int:
    match = re.fullmatch(r"(\d+)([mhd])", window.strip().lower())
    if not match:
        raise ValueError("window must look like 5m, 1h, 6h, or 24h")
    amount = int(match.group(1))
    unit = match.group(2)
    multiplier = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}[unit]
    return amount * multiplier
