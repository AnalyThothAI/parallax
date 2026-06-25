from __future__ import annotations

from typing import Any

from parallax.domains.pulse_lab.queries.pulse_freshness_health_queries import (
    fetch_pulse_health_candidates,
    fetch_pulse_health_clocks,
    fetch_pulse_health_jobs,
    fetch_pulse_health_runs,
)
from parallax.domains.pulse_lab.types.pulse_freshness_health import (
    PulseFreshnessThresholds,
    PulsePublishStatus,
    classify_pulse_freshness_health,
    pulse_freshness_since_hours,
    pulse_freshness_since_ms,
)


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
        since_hours: int,
    ) -> dict[str, Any]:
        since_hour_count = pulse_freshness_since_hours(since_hours)
        since_ms = pulse_freshness_since_ms(now_ms=now_ms, since_hours=since_hours)
        clocks = fetch_pulse_health_clocks(self.conn, window=window, scope=scope)
        jobs = fetch_pulse_health_jobs(self.conn, window=window, scope=scope, now_ms=now_ms, since_ms=since_ms)
        runs = fetch_pulse_health_runs(self.conn, window=window, scope=scope, since_ms=since_ms)
        candidates = fetch_pulse_health_candidates(self.conn, window=window, scope=scope, since_ms=since_ms)
        status, reasons = self._classify(clocks=clocks, jobs=jobs, runs=runs, now_ms=now_ms)
        return {
            "window": window,
            "scope": scope,
            "since_hours": since_hour_count,
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
        return classify_pulse_freshness_health(
            clocks=clocks,
            jobs=jobs,
            runs=runs,
            now_ms=now_ms,
            thresholds=self.thresholds,
        )


__all__ = ["PulseFreshnessHealthService", "PulseFreshnessThresholds", "PulsePublishStatus"]
