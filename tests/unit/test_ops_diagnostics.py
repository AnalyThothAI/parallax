from __future__ import annotations

from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.ops_diagnostics import (
    INVALID_QUEUE,
    ops_diagnostics_payload,
    ops_queue_payload,
    redact_diagnostics,
)
from gmgn_twitter_intel.domains.asset_market.providers import MarketCapability, ProviderHealth


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
    assert payload["providers"]
    assert payload["queues"]


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
        if "COUNT(*)" in sql and "GROUP BY status" in sql:
            return FakeRows(self.queue_rows)
        if "oldest_due_at_ms" in sql:
            return FakeRows(
                [
                    {
                        "due_count": 0,
                        "running_count": 0,
                        "dead_count": sum(
                            int(row["count"]) for row in self.queue_rows if row["status"] == "dead"
                        ),
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
    ) -> None:
        self.settings = SimpleNamespace(
            app_home="/var/lib/gmgn-twitter-intel-test",
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
        self._news_error = news_error

    def repositories(self) -> FakeRepos:
        return FakeRepos(self._news_error)
