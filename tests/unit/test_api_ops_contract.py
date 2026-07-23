from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from parallax.app.runtime.runtime_snapshot import RuntimeSnapshot, capture_runtime_snapshot
from parallax.app.runtime.worker_manifest import worker_names
from parallax.app.surfaces.api.exceptions import (
    ApiBadRequest,
    ApiUnauthorized,
    api_bad_request_response,
    api_unauthorized_response,
)
from parallax.app.surfaces.api.http import create_api_router


def test_ops_diagnostics_requires_authentication() -> None:
    app = _app(FakeRuntime())

    with TestClient(app) as client:
        response = client.get("/api/ops/diagnostics")

    assert response.status_code == 401


def test_ops_diagnostics_returns_aggregate_payload() -> None:
    app = _app(FakeRuntime())

    with TestClient(app) as client:
        response = client.get(
            "/api/ops/diagnostics",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["schema_version"] == "ops.diagnostics.v1"
    assert "workers" in body["data"]


def test_ops_diagnostics_fails_closed_when_producer_omits_required_section(monkeypatch) -> None:
    monkeypatch.setattr(
        "parallax.app.surfaces.api.routes_ops.ops_diagnostics_payload",
        lambda runtime, now_ms: {"schema_version": "ops.diagnostics.v1"},
    )
    app = _app(FakeRuntime())

    with TestClient(app) as client, pytest.raises(ValidationError, match="generated_at_ms"):
        client.get("/api/ops/diagnostics", headers={"Authorization": "Bearer secret"})


def test_ops_queue_rejects_invalid_queue() -> None:
    app = _app(FakeRuntime())

    with TestClient(app) as client:
        response = client.get(
            "/api/ops/queues/not-real",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_queue"


def test_ops_queue_fails_closed_when_producer_omits_summary(monkeypatch) -> None:
    monkeypatch.setattr(
        "parallax.app.surfaces.api.routes_ops.ops_queue_payload",
        lambda runtime, **kwargs: {
            "schema_version": "ops.queue.v1",
            "queue_name": "notification_deliveries",
            "status_filter": None,
            "counts_by_status": {},
            "items": [],
        },
    )
    app = _app(FakeRuntime())

    with TestClient(app) as client, pytest.raises(ValidationError, match="summary"):
        client.get(
            "/api/ops/queues/notification_deliveries",
            headers={"Authorization": "Bearer secret"},
        )


class FakeRows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class FakeConn:
    def execute(self, sql: str, params: object = ()) -> FakeRows:
        if "FROM worker_queue_terminal_events" in sql:
            if "GROUP BY final_reason_bucket" in sql:
                return FakeRows([])
            return FakeRows([{"terminal_count": 0, "unresolved_terminal_count": 0}])
        if "COUNT(*)" in sql and "GROUP BY status" in sql:
            return FakeRows([])
        if "oldest_due_at_ms" in sql:
            return FakeRows(
                [
                    {
                        "total_count": 0,
                        "active_count": 0,
                        "due_count": 0,
                        "running_count": 0,
                        "failed_count": 0,
                        "source_terminal_count": 0,
                        "oldest_due_at_ms": None,
                        "oldest_running_at_ms": None,
                        "max_attempt_count": None,
                    }
                ]
            )
        if "SELECT *" in sql and "FROM notification_deliveries" in sql:
            return FakeRows([])
        return FakeRows([{"ok": True, "probe": "postgres_liveness"}])


class FakeConnectionContext:
    def __init__(self) -> None:
        self.conn = FakeConn()

    def __enter__(self) -> FakeConn:
        return self.conn

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class FakePool:
    def connection(self) -> FakeConnectionContext:
        return FakeConnectionContext()


class FakeRepos:
    def __init__(self) -> None:
        self.conn = FakeConn()
        self.news_sources = SimpleNamespace(list_source_status=lambda: [])
        self.notifications = SimpleNamespace(
            summary=lambda subscriber_key="local", since_ms=None: {
                "subscriber_key": subscriber_key,
                "unread_count": 0,
                "high_unread_count": 0,
                "critical_unread_count": 0,
                "highest_unread_severity": None,
                "account_unread_counts": {},
            }
        )

    def __enter__(self) -> FakeRepos:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class FakeRuntime:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            app_home=Path("/var/lib/parallax-test"),
            ws_token="secret",
            handles=("alpha",),
            upstream=SimpleNamespace(channels=("twitter_monitor_basic",)),
            gmgn_configured=True,
            okx_dex_configured=False,
            news_intel=SimpleNamespace(enabled=True),
            notifications=SimpleNamespace(enabled=True),
        )
        self.db = SimpleNamespace(api_pool=FakePool())
        self.collector = SimpleNamespace(
            upstream_client=None,
            status=SimpleNamespace(to_dict=lambda: {"frames_received": 0, "snapshot_gate_outcomes": {}}),
        )
        self.providers = SimpleNamespace(asset_market=SimpleNamespace(stream_dex_market=None, provider_health=()))
        self.scheduler = SimpleNamespace(
            tasks={},
            status_payload=lambda: {
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
            },
        )
        self.snapshot = RuntimeSnapshot.startup(
            startup_db_status={"ok": True},
            composition={"ok": True},
            news_provider_contract={"ok": True},
        )

    def current_snapshot(self) -> RuntimeSnapshot:
        self.snapshot = capture_runtime_snapshot(self)
        return self.snapshot

    def repositories(self) -> FakeRepos:
        return FakeRepos()


def _app(runtime: FakeRuntime) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(lambda _: {"ok": True}))
    app.state.service = runtime
    return app
