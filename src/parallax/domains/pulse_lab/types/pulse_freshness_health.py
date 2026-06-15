from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

PulsePublishStatus = Literal["healthy", "degraded", "hold_publish"]

HOUR_MS = 60 * 60 * 1000


@dataclass(frozen=True, slots=True)
class PulseFreshnessThresholds:
    stale_public_ms: int = 2 * HOUR_MS
    degraded_agent_failure_rate: float = 0.15
    hold_agent_failure_rate: float = 0.30
    degraded_unknown_ref_rate: float = 0.05
    degraded_unsupported_claim_rate: float = 0.05


def pulse_freshness_since_ms(*, now_ms: int, since_hours: int) -> int:
    return max(0, int(now_ms) - max(1, int(since_hours)) * HOUR_MS)


def classify_pulse_freshness_health(
    *,
    clocks: dict[str, int | None],
    jobs: dict[str, int],
    runs: dict[str, int | float],
    now_ms: int,
    thresholds: PulseFreshnessThresholds | None = None,
) -> tuple[PulsePublishStatus, list[str]]:
    freshness_thresholds = thresholds or PulseFreshnessThresholds()
    reasons: list[str] = []
    total_runs = _int(runs.get("agent_runs_4h"))
    failed_runs = _int(runs.get("agent_failed_4h"))
    successful_runs = max(0, total_runs - failed_runs)
    failure_rate = float(runs.get("agent_failure_rate_4h") or 0.0)
    unknown_rate = float(runs.get("unknown_ref_failure_rate_4h") or 0.0)
    unsupported_rate = float(runs.get("unsupported_claim_failure_rate_4h") or 0.0)
    latest_packet = clocks.get("latest_packet_created_at_ms")
    latest_public = clocks.get("latest_public_candidate_updated_at_ms")
    if failure_rate >= freshness_thresholds.hold_agent_failure_rate and successful_runs == 0:
        reasons.append("agent_failure_rate_hold")
    elif failure_rate >= freshness_thresholds.hold_agent_failure_rate:
        reasons.append("agent_failure_rate_high")
    if unknown_rate >= freshness_thresholds.degraded_unknown_ref_rate:
        reasons.append("unknown_ref_failures")
    if unsupported_rate >= freshness_thresholds.degraded_unsupported_claim_rate:
        reasons.append("unsupported_claim_failures")
    if _int(jobs.get("dead_jobs")) > 0:
        reasons.append("dead_jobs_present")
    if latest_packet and (
        latest_public is None or int(now_ms) - int(latest_public) > freshness_thresholds.stale_public_ms
    ):
        reasons.append("public_candidate_stale_while_packets_fresh")
    if "agent_failure_rate_hold" in reasons:
        return "hold_publish", reasons
    if reasons or failure_rate >= freshness_thresholds.degraded_agent_failure_rate:
        if failure_rate >= freshness_thresholds.degraded_agent_failure_rate:
            reasons.append("agent_failure_rate_degraded")
        return "degraded", _dedupe(reasons)
    return "healthy", []


def _int(value: Any) -> int:
    return int(value or 0)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


__all__ = [
    "HOUR_MS",
    "PulseFreshnessThresholds",
    "PulsePublishStatus",
    "classify_pulse_freshness_health",
    "pulse_freshness_since_ms",
]
