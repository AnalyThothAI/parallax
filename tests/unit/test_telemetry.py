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


def test_telemetry_records_pool_wait_samples_and_returns_p99_by_pool() -> None:
    telemetry = TelemetryRegistry()

    telemetry.record_pool_wait("worker", 10)
    telemetry.record_pool_wait("worker", 20)
    telemetry.record_pool_wait("api", 100)

    assert telemetry.pool_wait_p99_ms("worker") == 20
    assert telemetry.pool_wait_p99_ms("api") == 100
    assert telemetry.pool_wait_p99_ms("missing") is None


def test_telemetry_exposes_agent_execution_metrics() -> None:
    telemetry = TelemetryRegistry()

    telemetry.increment_agent_execution_in_flight(lane="pulse.risk_portfolio_judge", stage="risk_portfolio_judge")
    telemetry.decrement_agent_execution_in_flight(lane="pulse.risk_portfolio_judge", stage="risk_portfolio_judge")
    telemetry.record_agent_execution_backpressure(lane="pulse.pipeline", reason="capacity_denied")
    telemetry.record_agent_execution_call(
        lane="pulse.risk_portfolio_judge",
        stage="risk_portfolio_judge",
        model="gpt-test",
        status="done",
        seconds=0.25,
    )

    text = telemetry.render_prometheus_text()
    assert "gmgn_agent_execution_calls_total" in text
    assert "gmgn_agent_execution_seconds" in text
    assert "gmgn_agent_execution_in_flight" in text
    assert "gmgn_agent_execution_backpressure_total" in text
    assert 'lane="pulse.risk_portfolio_judge"' in text
    assert 'reason="capacity_denied"' in text
