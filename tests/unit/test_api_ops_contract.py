from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

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
            params={"since_hours": 4, "window": "1h", "scope": "all"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["schema_version"] == "ops.diagnostics.v1"
    assert "workers" in body["data"]


def test_ops_queue_rejects_invalid_queue() -> None:
    app = _app(FakeRuntime())

    with TestClient(app) as client:
        response = client.get(
            "/api/ops/queues/not-real",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_queue"


class FakeRows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class FakeConn:
    def execute(self, sql: str, params: object = ()) -> FakeRows:
        if "COUNT(*)" in sql and "GROUP BY status" in sql:
            return FakeRows([])
        if "oldest_due_at_ms" in sql:
            return FakeRows(
                [
                    {
                        "due_count": 0,
                        "running_count": 0,
                        "dead_count": 0,
                        "oldest_due_at_ms": None,
                        "oldest_running_at_ms": None,
                    }
                ]
            )
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
        self.news = SimpleNamespace(list_source_status=lambda: [])
        self.notifications = SimpleNamespace(summary=lambda subscriber_key="local", since_ms=None: {})

    def __enter__(self) -> FakeRepos:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class FakeRuntime:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            app_home="/var/lib/parallax-test",
            ws_token="secret",
            handles=("alpha",),
            upstream_channels=("twitter_monitor_basic",),
            gmgn_configured=True,
            okx_dex_configured=False,
            llm_configured=False,
            news_intel_enabled=True,
            notification_rules={},
        )
        self.db = SimpleNamespace(api_pool=FakePool())
        self.collector = SimpleNamespace(
            upstream_client=None,
            status=SimpleNamespace(to_dict=lambda: {"frames_received": 0, "snapshot_gate_outcomes": {}}),
        )
        self.providers = SimpleNamespace(asset_market=SimpleNamespace(stream_dex_market=None, provider_health=()))
        self.scheduler = SimpleNamespace(
            unhealthy_reasons=lambda: [],
            status_payload=lambda: {},
        )

    def repositories(self) -> FakeRepos:
        return FakeRepos()


def _app(runtime: FakeRuntime) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(lambda _: ({"ok": True}, 200)))
    app.state.service = runtime
    return app
