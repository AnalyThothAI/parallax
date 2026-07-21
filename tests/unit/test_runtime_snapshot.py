from __future__ import annotations

from types import SimpleNamespace

from parallax.app.runtime.runtime_snapshot import RuntimeSnapshot, capture_runtime_snapshot
from parallax.app.runtime.worker_manifest import worker_names


def test_capture_runtime_snapshot_is_the_single_current_state_composer() -> None:
    calls = {"workers": 0, "collector": 0, "gmgn": 0, "okx": 0, "agent": 0}

    def worker_status() -> dict[str, dict[str, object]]:
        calls["workers"] += 1
        statuses = _all_worker_statuses()
        statuses["collector"].update({"running": True, "effective_status": "running"})
        statuses["news_story_brief"].update({"effective_status": "failed"})
        return statuses

    def collector_status() -> dict[str, object]:
        calls["collector"] += 1
        return {"frames_received": 7, "snapshot_gate_outcomes": {"complete": 2}}

    def connection(name: str, state: str):
        def payload() -> dict[str, object]:
            calls[name] += 1
            return {"state": state, "last_state_change_at_ms": 9_000}

        return SimpleNamespace(connection_state_payload=payload)

    def agent_status() -> dict[str, object]:
        calls["agent"] += 1
        return {
            "lane": "news.story_brief",
            "model": "gpt-news",
            "provider_family": "openai",
            "output_strategy": "json_object",
            "schema_enforcement": "client_validate",
            "max_concurrency": 1,
            "rpm_limit": 60,
            "timeout_seconds": 180.0,
            "in_flight": 1,
            "provider_running": 1,
            "circuit_state": "closed",
            "circuit_open_until_ms": None,
            "capacity_denied_total": 0,
            "circuit_open_total": 0,
            "timeout_total": 0,
            "last_denied_at_ms": None,
            "last_timeout_at_ms": None,
            "oldest_in_flight_age_ms": 25,
        }

    cached = RuntimeSnapshot.startup(
        startup_db_status={"ok": True, "migration_version": "0186"},
        composition={"ok": True},
        news_provider_contract={"ok": True, "configured_provider_types": ["opennews"]},
    )
    runtime = SimpleNamespace(
        snapshot=cached,
        scheduler=SimpleNamespace(
            status_payload=worker_status,
            tasks={
                "news_fetch": SimpleNamespace(
                    done=lambda: True,
                    cancelled=lambda: False,
                    exception=lambda: RuntimeError("task crashed"),
                )
            },
        ),
        collector=SimpleNamespace(
            status=SimpleNamespace(to_dict=collector_status),
            upstream_client=connection("gmgn", "connected"),
        ),
        providers=SimpleNamespace(asset_market=SimpleNamespace(stream_dex_market=connection("okx", "circuit_open"))),
        agent_execution_gateway=SimpleNamespace(status_snapshot=agent_status),
    )

    snapshot = capture_runtime_snapshot(runtime)

    assert calls == {"workers": 1, "collector": 1, "gmgn": 1, "okx": 1, "agent": 1}
    assert snapshot.collector["frames_received"] == 7
    assert "details" not in snapshot.workers["collector"]
    assert snapshot.provider_states["gmgn_direct_ws"]["state"] == "connected"
    assert snapshot.provider_states["okx_dex_ws"]["state"] == "circuit_open"
    assert snapshot.agent_execution == {
        "lane": "news.story_brief",
        "model": "gpt-news",
        "provider_family": "openai",
        "output_strategy": "json_object",
        "schema_enforcement": "client_validate",
        "max_concurrency": 1,
        "rpm_limit": 60,
        "timeout_seconds": 180.0,
        "in_flight": 1,
        "provider_running": 1,
        "circuit_state": "closed",
        "circuit_open_until_ms": None,
        "capacity_denied_total": 0,
        "circuit_open_total": 0,
        "timeout_total": 0,
        "last_denied_at_ms": None,
        "last_timeout_at_ms": None,
        "oldest_in_flight_age_ms": 25,
    }
    assert snapshot.startup_db_status == cached.startup_db_status
    assert snapshot.composition == {"ok": True}
    assert snapshot.news_provider_contract == cached.news_provider_contract
    assert snapshot.degradation_reasons == (
        "worker:news_fetch:errored:task crashed",
        "worker:news_story_brief:failed",
        "provider:okx_dex_ws:circuit_open",
    )


def test_capture_runtime_snapshot_represents_missing_or_broken_optional_providers() -> None:
    cached = RuntimeSnapshot.startup(
        startup_db_status={"ok": True},
        composition={"ok": True},
        news_provider_contract={"ok": True},
    )
    runtime = SimpleNamespace(
        snapshot=cached,
        scheduler=SimpleNamespace(status_payload=_all_worker_statuses, tasks={}),
        collector=SimpleNamespace(
            status=SimpleNamespace(to_dict=lambda: {}),
            upstream_client=None,
        ),
        providers=SimpleNamespace(
            asset_market=SimpleNamespace(
                stream_dex_market=SimpleNamespace(
                    connection_state_payload=lambda: (_ for _ in ()).throw(ConnectionError("closed"))
                )
            )
        ),
        agent_execution_gateway=SimpleNamespace(
            status_snapshot=lambda: (_ for _ in ()).throw(RuntimeError("unavailable"))
        ),
    )

    snapshot = capture_runtime_snapshot(runtime)

    assert snapshot.provider_states["gmgn_direct_ws"] == {
        "state": "disabled",
        "last_state_change_at_ms": None,
    }
    assert snapshot.provider_states["okx_dex_ws"] == {
        "state": "failed",
        "last_state_change_at_ms": None,
        "error": "ConnectionError",
    }
    assert snapshot.agent_execution == {"status": "unavailable", "error": "RuntimeError"}
    assert snapshot.degradation_reasons == ("provider:okx_dex_ws:failed",)


def test_capture_runtime_snapshot_rejects_missing_provider_connection_state() -> None:
    runtime = SimpleNamespace(
        snapshot=RuntimeSnapshot.startup(
            startup_db_status={"ok": True},
            composition={"ok": True},
            news_provider_contract={"ok": True},
        ),
        scheduler=SimpleNamespace(status_payload=_all_worker_statuses, tasks={}),
        collector=SimpleNamespace(
            status=SimpleNamespace(to_dict=lambda: {}),
            upstream_client=SimpleNamespace(connection_state_payload=lambda: {"last_state_change_at_ms": 9_000}),
        ),
        providers=SimpleNamespace(asset_market=SimpleNamespace(stream_dex_market=None)),
        agent_execution_gateway=None,
    )

    snapshot = capture_runtime_snapshot(runtime)

    assert snapshot.provider_states["gmgn_direct_ws"] == {
        "state": "failed",
        "last_state_change_at_ms": None,
        "error": "provider_connection_state_invalid",
    }
    assert snapshot.degradation_reasons == ("provider:gmgn_direct_ws:failed",)


def test_capture_runtime_snapshot_reports_terminal_news_source_degradation() -> None:
    runtime = SimpleNamespace(
        snapshot=RuntimeSnapshot.startup(
            startup_db_status={"ok": True},
            composition={"ok": True},
            news_provider_contract={"ok": True},
        ),
        scheduler=SimpleNamespace(
            status_payload=_degraded_news_worker_statuses,
            tasks={},
        ),
        collector=SimpleNamespace(
            status=SimpleNamespace(to_dict=lambda: {}),
            upstream_client=None,
        ),
        providers=SimpleNamespace(asset_market=SimpleNamespace(stream_dex_market=None)),
        agent_execution_gateway=None,
    )

    snapshot = capture_runtime_snapshot(runtime)

    assert snapshot.workers["news_fetch"]["effective_status"] == "degraded"
    assert snapshot.degradation_reasons == ("worker:news_fetch:degraded",)


def test_capture_runtime_snapshot_fails_closed_for_any_news_contract_error() -> None:
    runtime = SimpleNamespace(
        snapshot=RuntimeSnapshot.startup(
            startup_db_status={"ok": True},
            composition={"ok": True},
            news_provider_contract={
                "ok": False,
                "reason": "news_provider_contract_unavailable",
            },
        ),
        scheduler=SimpleNamespace(status_payload=_all_worker_statuses, tasks={}),
        collector=SimpleNamespace(
            status=SimpleNamespace(to_dict=lambda: {}),
            upstream_client=None,
        ),
        providers=SimpleNamespace(asset_market=SimpleNamespace(stream_dex_market=None)),
        agent_execution_gateway=None,
    )

    snapshot = capture_runtime_snapshot(runtime)

    assert snapshot.degradation_reasons == ("news_provider_contract_error",)


def test_capture_runtime_snapshot_fails_closed_when_news_contract_status_is_missing() -> None:
    runtime = SimpleNamespace(
        snapshot=RuntimeSnapshot.startup(
            startup_db_status={"ok": True},
            composition={"ok": True},
            news_provider_contract={},
        ),
        scheduler=SimpleNamespace(status_payload=_all_worker_statuses, tasks={}),
        collector=SimpleNamespace(
            status=SimpleNamespace(to_dict=lambda: {}),
            upstream_client=None,
        ),
        providers=SimpleNamespace(asset_market=SimpleNamespace(stream_dex_market=None)),
        agent_execution_gateway=None,
    )

    snapshot = capture_runtime_snapshot(runtime)

    assert snapshot.degradation_reasons == ("news_provider_contract_error",)


def _degraded_news_worker_statuses() -> dict[str, dict[str, object]]:
    statuses = _all_worker_statuses()
    statuses["news_fetch"].update(
        {
            "effective_status": "degraded",
            "last_result": {
                "processed": 0,
                "failed": 0,
                "notes": {
                    "degraded": True,
                    "terminal_sources": {"source-402": "provider_payment_required"},
                },
            },
        }
    )
    return statuses


def _all_worker_statuses() -> dict[str, dict[str, object]]:
    return {
        name: {
            "enabled": True,
            "running": False,
            "effective_status": "stopped",
            "unavailable_reason": None,
            "last_started_at_ms": None,
            "last_finished_at_ms": None,
            "last_result": None,
            "last_error": None,
            "iteration_duration_p99_ms": None,
        }
        for name in worker_names()
    }
