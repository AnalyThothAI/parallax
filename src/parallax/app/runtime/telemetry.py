from __future__ import annotations

import time
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest

PROMETHEUS_CONTENT_TYPE = CONTENT_TYPE_LATEST


class TelemetryRegistry:
    def __init__(self, *, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or CollectorRegistry(auto_describe=True)
        self.processing_seconds = Histogram(
            "gmgn_worker_processing_seconds",
            "Worker processing duration in seconds.",
            ("worker",),
            registry=self.registry,
        )
        self.jobs_total = Counter(
            "gmgn_worker_jobs_total",
            "Worker jobs by terminal status.",
            ("worker", "status"),
            registry=self.registry,
        )
        self.last_run_timestamp = Gauge(
            "gmgn_worker_last_run_timestamp_seconds",
            "Unix timestamp of the last worker run.",
            ("worker",),
            registry=self.registry,
        )
        self.lag_seconds = Gauge(
            "gmgn_worker_lag_seconds",
            "Worker lag in seconds.",
            ("worker",),
            registry=self.registry,
        )
        self.pool_wait_ms = Histogram(
            "gmgn_db_pool_wait_ms",
            "Database pool checkout wait in milliseconds.",
            ("pool",),
            registry=self.registry,
        )
        self.queue_depth = Gauge(
            "gmgn_worker_queue_depth",
            "Worker queue depth.",
            ("worker", "queue", "status"),
            registry=self.registry,
        )
        self.agent_execution_calls_total = Counter(
            "gmgn_agent_execution_calls_total",
            "Agent execution calls by lane, stage, model, status, and error class.",
            ("lane", "stage", "model", "status", "error_class"),
            registry=self.registry,
        )
        self.agent_execution_seconds = Histogram(
            "gmgn_agent_execution_seconds",
            "Agent execution duration in seconds.",
            ("lane", "stage", "model", "status"),
            registry=self.registry,
        )
        self.agent_execution_in_flight = Gauge(
            "gmgn_agent_execution_in_flight",
            "Agent executions currently in flight.",
            ("lane", "stage"),
            registry=self.registry,
        )
        self.agent_execution_backpressure_total = Counter(
            "gmgn_agent_execution_backpressure_total",
            "Agent execution backpressure denials by lane and reason.",
            ("lane", "reason"),
            registry=self.registry,
        )

    def record_processing_seconds(self, worker: str, seconds: float) -> None:
        self.processing_seconds.labels(worker=_label(worker)).observe(max(0.0, float(seconds)))

    def record_job(self, worker: str, status: str, count: int = 1) -> None:
        self.jobs_total.labels(worker=_label(worker), status=_label(status)).inc(max(0, int(count)))

    def mark_last_run(self, worker: str, *, timestamp: float | None = None) -> None:
        resolved_timestamp = float(timestamp if timestamp is not None else time.time())
        self.last_run_timestamp.labels(worker=_label(worker)).set(resolved_timestamp)

    def set_lag_seconds(self, worker: str, seconds: float) -> None:
        self.lag_seconds.labels(worker=_label(worker)).set(max(0.0, float(seconds)))

    def record_pool_wait(self, pool: str, wait_ms: float) -> None:
        pool_label = _label(pool)
        normalized_wait_ms = max(0.0, float(wait_ms))
        self.pool_wait_ms.labels(pool=pool_label).observe(normalized_wait_ms)

    def set_queue_depth(self, worker: str, queue: str, status: str, depth: int) -> None:
        self.queue_depth.labels(
            worker=_label(worker),
            queue=_label(queue),
            status=_label(status),
        ).set(max(0, int(depth)))

    def record_agent_execution_call(
        self,
        *,
        lane: str,
        stage: str,
        model: str,
        status: str,
        error_class: str | None = None,
        seconds: float | None = None,
    ) -> None:
        lane_label = _label(lane)
        stage_label = _label(stage)
        model_label = _label(model)
        status_label = _label(status)
        self.agent_execution_calls_total.labels(
            lane=lane_label,
            stage=stage_label,
            model=model_label,
            status=status_label,
            error_class=_label(error_class or "none"),
        ).inc()
        if seconds is not None:
            self.agent_execution_seconds.labels(
                lane=lane_label,
                stage=stage_label,
                model=model_label,
                status=status_label,
            ).observe(max(0.0, float(seconds)))

    def increment_agent_execution_in_flight(self, *, lane: str, stage: str) -> None:
        self.agent_execution_in_flight.labels(lane=_label(lane), stage=_label(stage)).inc()

    def decrement_agent_execution_in_flight(self, *, lane: str, stage: str) -> None:
        self.agent_execution_in_flight.labels(lane=_label(lane), stage=_label(stage)).dec()

    def record_agent_execution_backpressure(self, *, lane: str, reason: str) -> None:
        self.agent_execution_backpressure_total.labels(lane=_label(lane), reason=_label(reason)).inc()

    def render_prometheus_text(self) -> str:
        return generate_latest(self.registry).decode("utf-8")


def _label(value: Any) -> str:
    return str(value).strip() or "unknown"
