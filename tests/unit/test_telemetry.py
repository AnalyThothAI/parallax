from __future__ import annotations

from parallax.app.runtime.telemetry import TelemetryRegistry


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


def test_telemetry_records_pool_wait_histogram() -> None:
    telemetry = TelemetryRegistry()

    telemetry.record_pool_wait("worker", 10)
    telemetry.record_pool_wait("worker", 20)
    telemetry.record_pool_wait("api", 100)

    text = telemetry.render_prometheus_text()
    assert 'gmgn_db_pool_wait_ms_count{pool="worker"} 2.0' in text
    assert 'gmgn_db_pool_wait_ms_count{pool="api"} 1.0' in text
