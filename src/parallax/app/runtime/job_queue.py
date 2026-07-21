from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JobQueueDescriptor:
    name: str
    table: str
    id_column: str
    next_run_column: str = "next_run_at_ms"
    priority_order: str | None = None
    success_status: str = "done"
    last_attempt_at_column: str | None = None
    delivered_at_column: str | None = None


NOTIFICATION_DELIVERIES = JobQueueDescriptor(
    name="notification_deliveries",
    table="notification_deliveries",
    id_column="delivery_id",
    priority_order="next_run_at_ms ASC, created_at_ms ASC, delivery_id ASC",
    success_status="delivered",
    last_attempt_at_column="last_attempt_at_ms",
    delivered_at_column="delivered_at_ms",
)

JOB_QUEUE_DESCRIPTORS: Mapping[str, JobQueueDescriptor] = {NOTIFICATION_DELIVERIES.name: NOTIFICATION_DELIVERIES}
