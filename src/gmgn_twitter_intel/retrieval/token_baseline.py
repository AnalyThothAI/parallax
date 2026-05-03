from __future__ import annotations

from math import sqrt
from statistics import mean
from typing import Any

EWMA_ALPHA = 0.3


def token_baseline(*, slot_counts: list[int], current_mentions: int) -> dict[str, Any]:
    counts = [float(count) for count in slot_counts]
    sample_count = len(counts)
    zero_slot_count = sum(1 for count in counts if count == 0)
    simple_mean = mean(counts) if counts else None
    ewma_mean, ewma_stddev = _ewma_stats(counts)
    nonzero_sample_count = sample_count - zero_slot_count
    baseline_status = "ready" if nonzero_sample_count >= 3 else "insufficient_history"
    new_burst_score = _new_burst_score(current=float(current_mentions), baseline_mean=ewma_mean)
    z_score = (
        _z_score(
            current=float(current_mentions),
            baseline_mean=ewma_mean,
            baseline_stddev=ewma_stddev,
        )
        if baseline_status == "ready"
        else None
    )
    return {
        "baseline_status": baseline_status,
        "sample_count": sample_count,
        "zero_slot_count": zero_slot_count,
        "ewma_mean": ewma_mean,
        "ewma_stddev": ewma_stddev,
        "simple_mean": simple_mean,
        "z_score": z_score,
        "new_burst_score": new_burst_score,
    }


def _ewma_stats(counts: list[float]) -> tuple[float | None, float | None]:
    if not counts:
        return None, None
    ewma_mean = counts[0]
    ewma_variance = 0.0
    for count in counts[1:]:
        previous_mean = ewma_mean
        ewma_mean = EWMA_ALPHA * count + (1 - EWMA_ALPHA) * ewma_mean
        ewma_variance = EWMA_ALPHA * ((count - previous_mean) ** 2) + (1 - EWMA_ALPHA) * ewma_variance
    return ewma_mean, sqrt(max(0.0, ewma_variance))


def _z_score(*, current: float, baseline_mean: float | None, baseline_stddev: float | None) -> float | None:
    if baseline_mean is None or baseline_stddev is None:
        return None
    if baseline_stddev > 0:
        return (current - baseline_mean) / baseline_stddev
    if current > baseline_mean:
        return current - baseline_mean
    return 0.0


def _new_burst_score(*, current: float, baseline_mean: float | None) -> float | None:
    if baseline_mean is None:
        return current if current > 0 else None
    burst = current - baseline_mean
    return burst if burst > 0 else None
