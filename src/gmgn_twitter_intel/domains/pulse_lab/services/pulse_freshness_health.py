from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from gmgn_twitter_intel.domains.pulse_lab.queries.pulse_freshness_health_queries import (
    fetch_pulse_health_candidates,
    fetch_pulse_health_clocks,
    fetch_pulse_health_jobs,
    fetch_pulse_health_runs,
)

PulsePublishStatus = Literal["healthy", "degraded", "hold_publish"]

_HOUR_MS = 60 * 60 * 1000


@dataclass(frozen=True, slots=True)
class PulseFreshnessThresholds:
    stale_public_ms: int = 2 * _HOUR_MS
    degraded_agent_failure_rate: float = 0.15
    hold_agent_failure_rate: float = 0.30
    degraded_unknown_ref_rate: float = 0.05
    degraded_unsupported_claim_rate: float = 0.05


class PulseFreshnessHealthService:
    def __init__(self, conn: Any, *, thresholds: PulseFreshnessThresholds | None = None) -> None:
        self.conn = conn
        self.thresholds = thresholds or PulseFreshnessThresholds()

    def health(
        self,
        *,
        window: str,
        scope: str,
        now_ms: int,
        since_hours: int = 4,
    ) -> dict[str, Any]:
        since_ms = max(0, int(now_ms) - max(1, int(since_hours)) * _HOUR_MS)
        clocks = fetch_pulse_health_clocks(self.conn, window=window, scope=scope)
        jobs = fetch_pulse_health_jobs(self.conn, window=window, scope=scope, now_ms=now_ms, since_ms=since_ms)
        runs = fetch_pulse_health_runs(self.conn, window=window, scope=scope, since_ms=since_ms)
        candidates = fetch_pulse_health_candidates(self.conn, window=window, scope=scope, since_ms=since_ms)
        status, reasons = self._classify(clocks=clocks, jobs=jobs, runs=runs, now_ms=now_ms)
        return {
            "window": window,
            "scope": scope,
            "since_hours": max(1, int(since_hours)),
            "publish_status": status,
            "reasons": reasons,
            **clocks,
            **jobs,
            **runs,
            **candidates,
        }

    def _classify(
        self,
        *,
        clocks: dict[str, int | None],
        jobs: dict[str, int],
        runs: dict[str, int | float],
        now_ms: int,
    ) -> tuple[PulsePublishStatus, list[str]]:
        reasons: list[str] = []
        total_runs = _int(runs.get("agent_runs_4h"))
        failed_runs = _int(runs.get("agent_failed_4h"))
        successful_runs = max(0, total_runs - failed_runs)
        failure_rate = float(runs.get("agent_failure_rate_4h") or 0.0)
        unknown_rate = float(runs.get("unknown_ref_failure_rate_4h") or 0.0)
        unsupported_rate = float(runs.get("unsupported_claim_failure_rate_4h") or 0.0)
        latest_packet = clocks.get("latest_packet_created_at_ms")
        latest_public = clocks.get("latest_public_candidate_updated_at_ms")
        if failure_rate >= self.thresholds.hold_agent_failure_rate and successful_runs == 0:
            reasons.append("agent_failure_rate_hold")
        elif failure_rate >= self.thresholds.hold_agent_failure_rate:
            reasons.append("agent_failure_rate_high")
        if unknown_rate >= self.thresholds.degraded_unknown_ref_rate:
            reasons.append("unknown_ref_failures")
        if unsupported_rate >= self.thresholds.degraded_unsupported_claim_rate:
            reasons.append("unsupported_claim_failures")
        if _int(jobs.get("dead_jobs")) > 0:
            reasons.append("dead_jobs_present")
        if latest_packet and (
            latest_public is None or int(now_ms) - int(latest_public) > self.thresholds.stale_public_ms
        ):
            reasons.append("public_candidate_stale_while_packets_fresh")
        if "agent_failure_rate_hold" in reasons:
            return "hold_publish", reasons
        if reasons or failure_rate >= self.thresholds.degraded_agent_failure_rate:
            if failure_rate >= self.thresholds.degraded_agent_failure_rate:
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


__all__ = ["PulseFreshnessHealthService", "PulseFreshnessThresholds", "PulsePublishStatus"]
