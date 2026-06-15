from __future__ import annotations

from parallax.app.runtime.job_queue import (
    JOB_QUEUE_DESCRIPTORS,
    NOTIFICATION_DELIVERIES,
    PULSE_AGENT_JOBS,
)


def test_job_queue_module_exposes_only_ops_diagnostic_descriptors() -> None:
    assert set(JOB_QUEUE_DESCRIPTORS) == {"pulse_agent_jobs", "notification_deliveries"}
    assert JOB_QUEUE_DESCRIPTORS["pulse_agent_jobs"] is PULSE_AGENT_JOBS
    assert JOB_QUEUE_DESCRIPTORS["notification_deliveries"] is NOTIFICATION_DELIVERIES


def test_pulse_agent_jobs_descriptor_is_read_only_ops_metadata() -> None:
    assert PULSE_AGENT_JOBS.name == "pulse_agent_jobs"
    assert PULSE_AGENT_JOBS.table == "pulse_agent_jobs"
    assert PULSE_AGENT_JOBS.id_column == "job_id"
    assert PULSE_AGENT_JOBS.priority_order == "priority DESC, next_run_at_ms ASC, created_at_ms ASC, job_id ASC"
    assert PULSE_AGENT_JOBS.success_status == "done"


def test_notification_deliveries_descriptor_is_read_only_ops_metadata() -> None:
    assert NOTIFICATION_DELIVERIES.name == "notification_deliveries"
    assert NOTIFICATION_DELIVERIES.table == "notification_deliveries"
    assert NOTIFICATION_DELIVERIES.id_column == "delivery_id"
    assert NOTIFICATION_DELIVERIES.success_status == "delivered"
    assert NOTIFICATION_DELIVERIES.last_attempt_at_column == "last_attempt_at_ms"
    assert NOTIFICATION_DELIVERIES.delivered_at_column == "delivered_at_ms"
