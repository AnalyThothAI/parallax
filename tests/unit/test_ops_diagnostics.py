from __future__ import annotations

from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any

from parallax.app.runtime.ops_diagnostics import (
    INVALID_QUEUE,
    ops_diagnostics_payload,
    ops_queue_payload,
    redact_diagnostics,
)
from parallax.domains.asset_market.providers import MarketCapability, ProviderHealth
from parallax.platform.db.postgres_migrations import latest_migration_version


def test_redact_diagnostics_masks_secret_like_keys() -> None:
    payload = redact_diagnostics(
        {
            "api_key": "sk-live",
            "nested": {"ws_token": "secret-token", "safe": "ok"},
            "items": [{"dsn": "postgres://secret"}],
        }
    )

    assert payload["api_key"] == "<redacted>"
    assert payload["nested"]["ws_token"] == "<redacted>"
    assert payload["nested"]["safe"] == "ok"
    assert payload["items"][0]["dsn"] == "<redacted>"


def test_redact_diagnostics_keeps_business_token_keys() -> None:
    payload = redact_diagnostics(
        {
            "domains": {"token_radar": {"status": "ok"}},
            "provider": "token_profile_current",
        }
    )

    assert payload["domains"]["token_radar"] == {"status": "ok"}
    assert payload["provider"] == "token_profile_current"


def test_ops_diagnostics_survives_news_section_failure() -> None:
    runtime = FakeRuntime(news_error=RuntimeError("feed exploded"))

    payload = ops_diagnostics_payload(runtime, now_ms=10_000, since_hours=4, window="1h", scope="all")

    assert payload["schema_version"] == "ops.diagnostics.v1"
    assert payload["domains"]["news"]["status"] == "unknown"
    assert payload["domains"]["news"]["error_type"] == "RuntimeError"
    assert payload["workers"]
    assert set(payload["worker_lanes"]) >= {"ingest", "projection", "agent"}
    assert payload["worker_lanes"]["projection"]["running_workers"] >= 1
    assert payload["providers"]
    assert payload["queues"]


def test_ops_diagnostics_reuses_effective_worker_lane_counts() -> None:
    runtime = FakeRuntime()
    runtime.scheduler.status_payload = lambda: {
        "collector": {
            "enabled": False,
            "running": False,
            "effective_status": "intentionally_not_started",
            "unavailable_reason": None,
        },
        "market_tick_stream": {
            "enabled": True,
            "running": True,
            "effective_status": "running",
            "unavailable_reason": None,
        },
        "market_tick_poll": {
            "enabled": True,
            "running": False,
            "effective_status": "stopped",
            "unavailable_reason": None,
        },
        "token_radar_projection": {
            "enabled": True,
            "running": False,
            "effective_status": "unavailable",
            "unavailable_reason": "missing_projection_dependency",
        },
        "token_profile_current": {
            "enabled": True,
            "running": True,
            "effective_status": "degraded",
            "unavailable_reason": "optional_profile_source_missing",
        },
        "pulse_candidate": {
            "enabled": True,
            "running": False,
            "last_error": "agent lane failed",
            "effective_status": "failed",
            "unavailable_reason": None,
        },
    }

    payload = ops_diagnostics_payload(runtime, now_ms=10_000, since_hours=4, window="1h", scope="all")

    lane_totals = {
        key: sum(int(lane.get(key, 0)) for lane in payload["worker_lanes"].values())
        for key in (
            "disabled_workers",
            "intentionally_not_started_workers",
            "unavailable_workers",
            "degraded_workers",
            "running_workers",
            "stopped_workers",
            "failed_workers",
        )
    }
    assert lane_totals["disabled_workers"] >= 1
    assert lane_totals["intentionally_not_started_workers"] == 1
    assert lane_totals["unavailable_workers"] == 1
    assert lane_totals["degraded_workers"] == 1
    assert lane_totals["running_workers"] >= 1
    assert lane_totals["stopped_workers"] >= 1
    assert lane_totals["failed_workers"] == 1


def test_ops_diagnostics_worker_rows_and_overall_counts_use_effective_status() -> None:
    runtime = FakeRuntime()
    runtime.scheduler.status_payload = lambda: {
        "market_tick_stream": {
            "enabled": True,
            "running": False,
            "effective_status": "unavailable",
            "unavailable_reason": "missing_asset_market_stream_provider",
            "last_error": None,
        },
        "token_radar_projection": {
            "enabled": True,
            "running": True,
            "effective_status": "failed",
            "unavailable_reason": None,
            "last_error": None,
            "last_result": {"ok": False},
        },
        "token_profile_current": {
            "enabled": True,
            "running": True,
            "effective_status": "degraded",
            "unavailable_reason": None,
            "last_error": None,
            "last_result": {"notes": {"degraded": True}},
        },
    }

    payload = ops_diagnostics_payload(runtime, now_ms=10_000, since_hours=4, window="1h", scope="all")

    workers_by_name = {worker["name"]: worker for worker in payload["workers"]}
    assert workers_by_name["market_tick_stream"]["effective_status"] == "unavailable"
    assert workers_by_name["market_tick_stream"]["status"] == "unavailable"
    assert workers_by_name["market_tick_stream"]["reason"] == "missing_asset_market_stream_provider"
    assert workers_by_name["token_radar_projection"]["effective_status"] == "failed"
    assert workers_by_name["token_radar_projection"]["status"] == "failed"
    assert workers_by_name["token_radar_projection"]["reason"] == "worker_failed"
    assert workers_by_name["token_profile_current"]["effective_status"] == "degraded"
    assert workers_by_name["token_profile_current"]["status"] == "degraded"
    assert workers_by_name["token_profile_current"]["reason"] == "worker_degraded"
    assert payload["overall"]["section_status_counts"]["unavailable"] == 1
    assert payload["overall"]["section_status_counts"]["failed"] == 1
    assert payload["overall"]["section_status_counts"]["degraded"] >= 1
    assert payload["overall"]["status"] == "blocked"


def test_ops_queue_payload_rejects_unknown_queue_without_sql() -> None:
    runtime = FakeRuntime()

    payload = ops_queue_payload(runtime, queue_name="events;drop table events", status=None, limit=20, now_ms=10_000)

    assert payload == INVALID_QUEUE
    assert runtime.db.api_pool.conn.executed == []


def test_ops_queue_payload_marks_dead_queue_blocked() -> None:
    runtime = FakeRuntime(queue_rows=[{"status": "dead", "count": 1}])

    payload = ops_queue_payload(runtime, queue_name="pulse_agent_jobs", status=None, limit=20, now_ms=10_000)

    assert payload["counts_by_status"]["dead"] == 1
    assert payload["summary"]["status"] == "blocked"


def test_ops_queue_payload_uses_pulse_agent_queue_contract() -> None:
    runtime = FakeRuntime()

    payload = ops_queue_payload(
        runtime,
        queue_name="pulse_agent_jobs",
        status=None,
        limit=20,
        now_ms=10_000,
    )
    old_payload = ops_queue_payload(
        runtime,
        queue_name="watchlist_handle_summary_jobs",
        status=None,
        limit=20,
        now_ms=10_000,
    )

    assert payload["queue_name"] == "pulse_agent_jobs"
    assert payload["summary"]["worker_name"] == "pulse_candidate"
    assert old_payload == INVALID_QUEUE


def test_ops_diagnostics_agent_execution_sanitizes_snapshot() -> None:
    runtime = FakeRuntime(
        agent_execution_snapshot={
            "global_max_concurrency": 4,
            "global_in_flight": 1,
            "prompt": "do not expose",
            "api_key": "sk-live",
            "lanes": {
                "pulse.decision": {
                    "policy": {"priority": "high", "max_concurrency": 1},
                    "in_flight": 1,
                    "input_payload": {"secret": "value"},
                    "provider_running": 1,
                }
            },
        }
    )

    payload = ops_diagnostics_payload(runtime, now_ms=10_000, since_hours=4, window="1h", scope="all")

    assert payload["agent_execution"]["status"] == "ok"
    assert "prompt" not in payload["agent_execution"]
    assert "api_key" not in payload["agent_execution"]
    assert set(payload["agent_execution"]["lanes"]["pulse.decision"]) <= {
        "status",
        "reason",
        "policy",
        "counters",
    }
    assert "input_payload" not in payload["agent_execution"]["lanes"]["pulse.decision"]


def test_ops_diagnostics_agent_execution_disabled_without_gateway() -> None:
    runtime = FakeRuntime()

    payload = ops_diagnostics_payload(runtime, now_ms=10_000, since_hours=4, window="1h", scope="all")

    assert payload["agent_execution"]["status"] == "disabled"
    assert payload["agent_execution"]["policy"] == {}
    assert payload["agent_execution"]["counters"] == {}


def test_ops_diagnostics_agent_execution_snapshot_failure_is_unavailable() -> None:
    runtime = FakeRuntime(agent_execution_error=RuntimeError("snapshot exploded"))

    payload = ops_diagnostics_payload(runtime, now_ms=10_000, since_hours=4, window="1h", scope="all")

    assert payload["agent_execution"]["status"] == "unknown"
    assert payload["agent_execution"]["status_reason"] == "unavailable"


def test_ops_diagnostics_overall_includes_blocked_agent_execution() -> None:
    runtime = FakeRuntime(
        agent_execution_snapshot={
            "global_max_concurrency": 4,
            "global_in_flight": 0,
            "lanes": {
                "pulse.decision": {
                    "policy": {"priority": "high", "max_concurrency": 1},
                    "circuit_state": "open",
                    "last_circuit_open_at_ms": 9_900,
                    "circuit_open_total": 1,
                }
            },
        }
    )

    payload = ops_diagnostics_payload(runtime, now_ms=10_000, since_hours=4, window="1h", scope="all")

    assert payload["agent_execution"]["status"] == "blocked"
    assert payload["overall"]["status"] == "blocked"
    assert payload["overall"]["section_status_counts"]["blocked"] >= 1


def test_ops_diagnostics_agent_execution_degraded_requires_recent_signal() -> None:
    runtime = FakeRuntime(
        agent_execution_snapshot={
            "global_max_concurrency": 4,
            "global_in_flight": 0,
            "lanes": {
                "narrative.mention_semantics": {
                    "policy": {"priority": "standard", "max_concurrency": 2},
                    "capacity_denied_total": 17,
                    "timeout_total": 3,
                    "circuit_open_total": 2,
                    "last_denied_at_ms": 100,
                    "last_timeout_at_ms": 200,
                    "last_rpm_wait_at_ms": 300,
                    "rpm_waiting_count": 0,
                    "provider_running": 0,
                }
            },
        }
    )

    stale_payload = ops_diagnostics_payload(runtime, now_ms=1_000_000, since_hours=4, window="1h", scope="all")
    assert stale_payload["agent_execution"]["status"] == "ok"
    assert stale_payload["overall"]["status"] == "ok"

    runtime.agent_execution_gateway.snapshot["lanes"]["narrative.mention_semantics"]["last_rpm_wait_at_ms"] = 999_800
    recent_payload = ops_diagnostics_payload(runtime, now_ms=1_000_000, since_hours=4, window="1h", scope="all")

    assert recent_payload["agent_execution"]["status"] == "degraded"
    assert recent_payload["overall"]["status"] == "degraded"


class FakeRows:
    def __init__(self, rows: Iterable[dict[str, Any]]) -> None:
        self.rows = list(rows)

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class FakeConn:
    def __init__(self, queue_rows: list[dict[str, Any]] | None = None) -> None:
        self.queue_rows = queue_rows or []
        self.executed: list[str] = []

    def execute(self, sql: str, params: object = ()) -> FakeRows:
        self.executed.append(sql)
        if "SELECT version_num FROM alembic_version" in sql:
            return FakeRows([{"version_num": latest_migration_version()}])
        if "COUNT(*)" in sql and "GROUP BY status" in sql:
            return FakeRows(self.queue_rows)
        if "oldest_due_at_ms" in sql:
            return FakeRows(
                [
                    {
                        "due_count": 0,
                        "running_count": 0,
                        "dead_count": sum(int(row["count"]) for row in self.queue_rows if row["status"] == "dead"),
                        "oldest_due_at_ms": None,
                        "oldest_running_at_ms": None,
                    }
                ]
            )
        if "FROM projection_offsets" in sql:
            return FakeRows([])
        return FakeRows([{"ok": True, "probe": "postgres_liveness"}])


class FakeConnectionContext:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    def __enter__(self) -> FakeConn:
        return self.conn

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class FakePool:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    def connection(self) -> FakeConnectionContext:
        return FakeConnectionContext(self.conn)


class FakeNewsRepository:
    def __init__(self, error: Exception | None) -> None:
        self.error = error

    def list_source_status(self) -> list[dict[str, Any]]:
        if self.error is not None:
            raise self.error
        return [{"source_id": "coindesk", "status": "ok"}]


class FakeNotificationRepository:
    def summary(self, *, subscriber_key: str = "local", since_ms: int | None = None) -> dict[str, Any]:
        return {"subscriber_key": subscriber_key, "unread_count": 0}


class FakeRepos:
    def __init__(self, news_error: Exception | None) -> None:
        self.news = FakeNewsRepository(news_error)
        self.notifications = FakeNotificationRepository()
        self.conn = FakeConn()

    def __enter__(self) -> FakeRepos:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class FakeRuntime:
    def __init__(
        self,
        *,
        news_error: Exception | None = None,
        queue_rows: list[dict[str, Any]] | None = None,
        agent_execution_snapshot: dict[str, Any] | None = None,
        agent_execution_error: Exception | None = None,
    ) -> None:
        self.settings = SimpleNamespace(
            app_home="/var/lib/parallax-test",
            handles=("alpha",),
            upstream_channels=("twitter_monitor_basic",),
            gmgn_configured=True,
            okx_dex_configured=True,
            llm_configured=False,
            news_intel_enabled=True,
            notification_rules={},
        )
        self.db = SimpleNamespace(api_pool=FakePool(FakeConn(queue_rows)))
        self.collector = SimpleNamespace(
            upstream_client=SimpleNamespace(
                connection_state_payload=lambda: {
                    "state": "connected",
                    "last_state_change_at_ms": 9_000,
                }
            ),
            status=SimpleNamespace(
                to_dict=lambda: {
                    "started_at_ms": 1_000,
                    "frames_received": 10,
                    "twitter_events": 7,
                    "matched_twitter_events": 2,
                    "snapshot_gate_outcomes": {"immediate_complete": 1},
                }
            ),
        )
        self.providers = SimpleNamespace(
            asset_market=SimpleNamespace(
                stream_dex_market=SimpleNamespace(
                    connection_state_payload=lambda: {
                        "state": "connected",
                        "last_state_change_at_ms": 9_500,
                    }
                ),
                provider_health=(
                    ProviderHealth(
                        provider="gmgn",
                        capabilities=frozenset({MarketCapability.QUOTE_DEX_EXACT}),
                        configured=True,
                    ),
                ),
            )
        )
        self.scheduler = SimpleNamespace(
            unhealthy_reasons=lambda: [],
            status_payload=lambda: {
                "token_radar_projection": {
                    "enabled": True,
                    "running": True,
                    "last_started_at_ms": 8_000,
                    "last_finished_at_ms": 9_000,
                    "last_result": {"status": "ready"},
                    "last_error": None,
                    "iteration_duration_p99_ms": 15.0,
                    "queue_depth": None,
                    "pool_wait_ms_p99": None,
                    "details": {},
                }
            },
        )
        if agent_execution_error is not None:
            self.agent_execution_gateway = SimpleNamespace(
                status_snapshot=lambda: (_ for _ in ()).throw(agent_execution_error)
            )
        elif agent_execution_snapshot is not None:
            self.agent_execution_gateway = SimpleNamespace(
                snapshot=agent_execution_snapshot,
                status_snapshot=lambda: self.agent_execution_gateway.snapshot,
            )
        else:
            self.agent_execution_gateway = None
        self._news_error = news_error

    def repositories(self) -> FakeRepos:
        return FakeRepos(self._news_error)
