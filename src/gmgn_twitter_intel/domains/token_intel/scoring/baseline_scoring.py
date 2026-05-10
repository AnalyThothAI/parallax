from __future__ import annotations

import math
from statistics import median
from typing import Any

EWMA_ALPHA = 0.3


def token_baseline_v2(
    *,
    slot_counts: list[int],
    current_mentions: int,
    current_weighted_mentions: float | None = None,
    min_nonzero_samples: int = 3,
) -> dict[str, Any]:
    counts = [float(count) for count in slot_counts]
    sample_count = len(counts)
    zero_slot_count = sum(1 for count in counts if count == 0)
    nonzero_sample_count = sample_count - zero_slot_count
    baseline_status = (
        "empty_history"
        if sample_count == 0
        else "ready"
        if nonzero_sample_count >= min_nonzero_samples
        else "insufficient_history"
    )
    current = float(current_mentions)
    ewma_mean, ewma_stddev = ewma_stats(counts)
    median_count = median(counts) if counts else None
    mad = _mad(counts, median_count) if median_count is not None else None
    z_ewma = (
        _z_score(current=current, baseline_mean=ewma_mean, baseline_stddev=ewma_stddev)
        if baseline_status == "ready"
        else None
    )
    robust_z = robust_z_score(current=current, counts=counts) if baseline_status == "ready" else None
    new_burst_score = math.log1p(current) if baseline_status != "ready" and current > 0 else 0.0
    return {
        "baseline_version": "token_baseline_v2",
        "baseline_status": baseline_status,
        "sample_count": sample_count,
        "nonzero_sample_count": nonzero_sample_count,
        "zero_slot_count": zero_slot_count,
        "ewma_mean": ewma_mean,
        "ewma_stddev": ewma_stddev,
        "z_ewma": z_ewma,
        "median_count": median_count,
        "mad": mad,
        "robust_z": robust_z,
        "new_burst_score": new_burst_score,
        "current_weighted_mentions": current_weighted_mentions,
        "data_health": baseline_health(
            baseline_status=baseline_status,
            sample_count=sample_count,
            nonzero_sample_count=nonzero_sample_count,
            zero_slot_count=zero_slot_count,
        ),
    }


def baseline_health(
    *,
    baseline_status: str,
    sample_count: int,
    nonzero_sample_count: int,
    zero_slot_count: int,
) -> dict[str, Any]:
    return {
        "history_ready": baseline_status == "ready",
        "sparse_history": baseline_status != "ready",
        "zero_inflated": sample_count > 0 and zero_slot_count / sample_count >= 0.5,
        "sample_count": sample_count,
        "nonzero_sample_count": nonzero_sample_count,
    }


def robust_z_score(*, current: float, counts: list[float]) -> float | None:
    if not counts:
        return None
    center = float(median(counts))
    mad = _mad(counts, center)
    denom = max(1.4826 * mad, 1.0)
    return (float(current) - center) / denom


def ewma_stats(counts: list[float], *, alpha: float = EWMA_ALPHA) -> tuple[float | None, float | None]:
    if not counts:
        return None, None
    ewma_mean = counts[0]
    ewma_variance = 0.0
    for count in counts[1:]:
        previous_mean = ewma_mean
        ewma_mean = alpha * count + (1 - alpha) * ewma_mean
        ewma_variance = alpha * ((count - previous_mean) ** 2) + (1 - alpha) * ewma_variance
    return ewma_mean, math.sqrt(max(0.0, ewma_variance))


def _z_score(*, current: float, baseline_mean: float | None, baseline_stddev: float | None) -> float | None:
    if baseline_mean is None or baseline_stddev is None:
        return None
    return (current - baseline_mean) / max(baseline_stddev, 1.0)


def _mad(counts: list[float], center: float | None) -> float | None:
    if center is None:
        return None
    return float(median([abs(count - center) for count in counts]))
