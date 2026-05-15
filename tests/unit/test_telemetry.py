from __future__ import annotations

from gmgn_twitter_intel.app.runtime.telemetry import TelemetryRegistry


def test_telemetry_registries_do_not_collide_and_render_prometheus_text() -> None:
    first = TelemetryRegistry()
    second = TelemetryRegistry()

    first.record_job("worker-a", "processed")
    second.record_job("worker-b", "failed")

    first_text = first.render_prometheus_text()
    second_text = second.render_prometheus_text()
    assert "worker-a" in first_text
    assert "worker-b" not in first_text
    assert "worker-b" in second_text


def test_telemetry_records_pool_wait_samples_and_returns_p99_by_pool() -> None:
    telemetry = TelemetryRegistry()

    telemetry.record_pool_wait("worker", 10)
    telemetry.record_pool_wait("worker", 20)
    telemetry.record_pool_wait("api", 100)

    assert telemetry.pool_wait_p99_ms("worker") == 20
    assert telemetry.pool_wait_p99_ms("api") == 100
    assert telemetry.pool_wait_p99_ms("missing") is None
