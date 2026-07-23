from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from parallax.app.operations.diagnostics import (
    INVALID_QUEUE,
    _asset_market_provider_health,
    _config_payload,
    _queues_payload,
    _section,
    _watchlist_domain,
    _worker_group,
    ops_diagnostics_payload,
    ops_queue_payload,
    redact_diagnostics,
)
from parallax.app.runtime.runtime_snapshot import RuntimeSnapshot, capture_runtime_snapshot
from parallax.app.runtime.worker_manifest import worker_names
from parallax.domains.asset_market.providers import MarketCapability, ProviderHealth
from parallax.platform.config.settings import Settings
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


def test_worker_group_only_recognizes_current_narrative_worker_names() -> None:
    assert _worker_group("mention_semantics") != "narrative"
    assert _worker_group("token_discussion_digest") != "narrative"


def test_ops_diagnostics_survives_news_section_failure() -> None:
    runtime = FakeRuntime(news_error=RuntimeError("feed exploded"))

    payload = ops_diagnostics_payload(runtime, now_ms=10_000)

    assert payload["schema_version"] == "ops.diagnostics.v1"
    assert payload["domains"]["news"]["status"] == "unknown"
    assert payload["domains"]["news"]["error_type"] == "RuntimeError"
    assert payload["domains"]["token_radar"]["status"] == "ok"
    assert payload["domains"]["token_radar"]["publication"]["status"] == "ready"
    assert "projection" not in payload["domains"]["token_radar"]
    assert payload["workers"]
    assert "worker_lanes" not in payload
    assert payload["providers"]
    assert payload["queues"]
    assert "agent_execution" not in payload
    assert "llm_configured" not in payload["config"]


def test_ops_diagnostics_requires_asset_market_provider_bundle_root() -> None:
    runtime = FakeRuntime()
    runtime.providers = SimpleNamespace()

    try:
        ops_diagnostics_payload(runtime, now_ms=10_000)
    except AttributeError as exc:
        assert "asset_market" in str(exc)
    else:
        raise AssertionError("ops diagnostics must not convert missing provider root into an empty provider list")


def test_ops_diagnostics_requires_asset_market_provider_health_contract() -> None:
    runtime = FakeRuntime()
    runtime.providers.asset_market = SimpleNamespace(stream_dex_market=runtime.providers.asset_market.stream_dex_market)

    try:
        _asset_market_provider_health(runtime)
    except AttributeError as exc:
        assert "provider_health" in str(exc)
    else:
        raise AssertionError("asset-market diagnostics must not hide missing provider_health as an empty list")


def test_ops_diagnostics_rejects_reflective_asset_market_provider_health_items() -> None:
    runtime = FakeRuntime()
    runtime.providers.asset_market.provider_health = (
        SimpleNamespace(provider="gmgn", capabilities=(), configured=True),
    )

    try:
        _asset_market_provider_health(runtime)
    except TypeError as exc:
        assert "asset_market_provider_health_item" in str(exc)
    else:
        raise AssertionError("asset-market diagnostics must not accept provider_health items via vars() reflection")


def test_ops_diagnostics_collector_status_contract_failure_is_unknown_section() -> None:
    runtime = FakeRuntime()
    runtime.collector = SimpleNamespace(upstream_client=runtime.collector.upstream_client)

    try:
        runtime.current_snapshot()
    except AttributeError as exc:
        assert "status" in str(exc)
    else:
        raise AssertionError("collector diagnostics must not hide missing collector.status as empty details")


def test_ops_diagnostics_config_requires_runtime_settings_contract() -> None:
    runtime = FakeRuntime()
    del runtime.settings

    try:
        _config_payload(runtime)
    except AttributeError as exc:
        assert "settings" in str(exc)
    else:
        raise AssertionError("ops diagnostics config must not hide missing runtime.settings as empty config")


def test_ops_diagnostics_config_uses_canonical_nested_settings(tmp_path) -> None:
    settings = Settings(news_intel={"enabled": False}, notifications={"enabled": False})
    settings.set_config_dir(tmp_path)

    payload = _config_payload(SimpleNamespace(settings=settings))

    assert payload["app_home"] == str(tmp_path)
    assert payload["config_path"] == str(tmp_path / "config.yaml")
    assert payload["workers_config_path"] == str(tmp_path / "workers.yaml")
    assert payload["news_enabled"] is False
    assert payload["notifications_enabled"] is False


def test_ops_diagnostics_section_missing_status_fails_closed() -> None:
    payload = _section("probe", lambda: {"value": 1})

    assert payload["status"] == "unknown"
    assert payload["error_type"] == "ValueError"
    assert payload["reason"].endswith("diagnostic_section_status_invalid:probe")


def test_ops_diagnostics_watchlist_requires_runtime_settings_contract() -> None:
    runtime = FakeRuntime()
    del runtime.settings

    try:
        _watchlist_domain(runtime)
    except AttributeError as exc:
        assert "settings" in str(exc)
    else:
        raise AssertionError("watchlist diagnostics must not hide missing runtime.settings as idle")


def test_ops_diagnostics_queues_require_api_pool_connection_contract() -> None:
    runtime = FakeRuntime()
    runtime.db = SimpleNamespace()

    try:
        _queues_payload(runtime, now_ms=10_000)
    except AttributeError as exc:
        assert "api_pool" in str(exc)
    else:
        raise AssertionError("ops diagnostics queues must not hide missing db.api_pool as an empty queue list")


def test_ops_diagnostics_exposes_flat_effective_worker_statuses() -> None:
    runtime = FakeRuntime()
    statuses = _all_worker_statuses()
    statuses["collector"].update({"enabled": False, "effective_status": "intentionally_not_started"})
    statuses["market_tick_stream"].update({"running": True, "effective_status": "running"})
    statuses["token_radar_projection"].update(
        {"effective_status": "unavailable", "unavailable_reason": "missing_projection_dependency"}
    )
    statuses["token_profile_current"].update({"running": True, "effective_status": "degraded"})
    statuses["news_page_projection"].update({"last_error": "projection failed", "effective_status": "failed"})
    runtime.scheduler.status_payload = lambda: statuses

    payload = ops_diagnostics_payload(runtime, now_ms=10_000)

    assert "worker_lanes" not in payload
    statuses = {row["name"]: row["effective_status"] for row in payload["workers"]}
    assert statuses["collector"] == "intentionally_not_started"
    assert statuses["market_tick_stream"] == "running"
    assert statuses["market_tick_poll"] == "stopped"
    assert statuses["token_radar_projection"] == "unavailable"
    assert statuses["token_profile_current"] == "degraded"
    assert statuses["news_page_projection"] == "failed"


def test_ops_diagnostics_worker_rows_and_overall_counts_use_effective_status() -> None:
    runtime = FakeRuntime()
    statuses = _all_worker_statuses()
    statuses["market_tick_stream"].update(
        {
            "effective_status": "unavailable",
            "unavailable_reason": "missing_asset_market_stream_provider",
        }
    )
    statuses["token_radar_projection"].update(
        {"running": True, "effective_status": "failed", "last_result": {"ok": False}}
    )
    statuses["token_profile_current"].update(
        {"running": True, "effective_status": "degraded", "last_result": {"notes": {"degraded": True}}}
    )
    runtime.scheduler.status_payload = lambda: statuses

    payload = ops_diagnostics_payload(runtime, now_ms=10_000)

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

    payload = ops_queue_payload(runtime, queue_name="notification_deliveries", status=None, limit=20, now_ms=10_000)

    assert payload["counts_by_status"]["dead"] == 1
    assert payload["summary"]["status"] == "blocked"


def test_ops_queue_payload_uses_notification_delivery_queue_contract() -> None:
    runtime = FakeRuntime()

    payload = ops_queue_payload(
        runtime,
        queue_name="notification_deliveries",
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

    assert payload["queue_name"] == "notification_deliveries"
    assert payload["summary"]["worker_name"] == "notification_delivery"
    assert old_payload == INVALID_QUEUE


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
        self.commit_calls = 0
        self.rollback_calls = 0

    def execute(self, sql: str, params: object = ()) -> FakeRows:
        self.executed.append(sql)
        if "SELECT version_num FROM alembic_version" in sql:
            return FakeRows([{"version_num": latest_migration_version()}])
        if "FROM worker_queue_terminal_events" in sql:
            if "GROUP BY final_reason_bucket" in sql:
                return FakeRows([])
            return FakeRows([{"terminal_count": 0, "unresolved_terminal_count": 0}])
        if "COUNT(*)" in sql and "GROUP BY status" in sql:
            return FakeRows(self.queue_rows)
        if "oldest_due_at_ms" in sql:
            counts = {str(row["status"]): int(row["count"]) for row in self.queue_rows}
            return FakeRows(
                [
                    {
                        "total_count": sum(counts.values()),
                        "active_count": sum(counts.get(status, 0) for status in ("pending", "failed", "running")),
                        "due_count": 0,
                        "running_count": counts.get("running", 0),
                        "failed_count": counts.get("failed", 0),
                        "source_terminal_count": counts.get("dead", 0),
                        "oldest_due_at_ms": None,
                        "oldest_running_at_ms": None,
                        "max_attempt_count": None,
                    }
                ]
            )
        if "SELECT *" in sql and "FROM notification_deliveries" in sql:
            return FakeRows([])
        if "FROM token_radar_publication_state" in sql:
            return FakeRows(
                [
                    {
                        "projection_version": "token-radar-v-test",
                        "window": "5m",
                        "scope": "all",
                        "venue": "all",
                        "current_generation_id": "gen-ready",
                        "latest_attempt_status": "ready",
                    }
                ]
            )
        return FakeRows([{"ok": True, "probe": "postgres_liveness"}])

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


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
        self.news_sources = FakeNewsRepository(news_error)
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
    ) -> None:
        self.settings = SimpleNamespace(
            app_home=Path("/var/lib/parallax-test"),
            handles=("alpha",),
            upstream=SimpleNamespace(channels=("twitter_monitor_basic",)),
            gmgn_configured=True,
            okx_dex_configured=True,
            news_intel=SimpleNamespace(enabled=True),
            notifications=SimpleNamespace(enabled=True),
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
            tasks={},
            status_payload=_running_worker_statuses,
        )
        self.snapshot = RuntimeSnapshot.startup(
            startup_db_status={"ok": True, "migration_version": latest_migration_version()},
            composition={"ok": True},
            news_provider_contract={"ok": True},
        )
        self._news_error = news_error

    def current_snapshot(self) -> RuntimeSnapshot:
        self.snapshot = capture_runtime_snapshot(self)
        return self.snapshot

    def repositories(self) -> FakeRepos:
        return FakeRepos(self._news_error)


def _running_worker_statuses() -> dict[str, dict[str, Any]]:
    statuses = _all_worker_statuses()
    statuses["token_radar_projection"].update(
        {
            "running": True,
            "effective_status": "running",
            "last_started_at_ms": 8_000,
            "last_finished_at_ms": 9_000,
            "last_result": {"status": "ready"},
            "iteration_duration_p99_ms": 15.0,
        }
    )
    return statuses


def _all_worker_statuses() -> dict[str, dict[str, Any]]:
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
