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

    def render_prometheus_text(self) -> str:
        return generate_latest(self.registry).decode("utf-8")


def _label(value: Any) -> str:
    return str(value).strip() or "unknown"
