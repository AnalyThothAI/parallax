from fastapi import FastAPI
from fastapi.testclient import TestClient

from gmgn_twitter_intel.app.surfaces.api.http import (
    ApiBadRequest,
    ApiUnauthorized,
    _watchlist_handle_summary_config,
    api_bad_request_response,
    api_unauthorized_response,
    create_api_router,
)
from gmgn_twitter_intel.domains.watchlist_intel.types import encode_watchlist_timeline_cursor
from gmgn_twitter_intel.platform.config.settings import Settings

DEFAULT_SUMMARY = object()


def test_watchlist_handle_summary_endpoint_requires_configured_handle():
    app = _app(FakeWatchlistIntelRepository())

    with TestClient(app) as client:
        ok = client.get("/api/watchlist/handle/toly/summary?token=secret")
        missing = client.get("/api/watchlist/handle/unknown/summary?token=secret")

    assert ok.status_code == 200
    assert ok.json()["data"]["handle"] == "toly"
    assert ok.json()["data"]["summary_zh"] == "Toly 正在反复讨论 SOL 与 BONK。"
    assert missing.status_code == 404
    assert missing.json()["error"] == "handle_not_found"


def test_watchlist_handle_summary_endpoint_returns_not_ready_with_pending_recompute():
    app = _app(FakeWatchlistIntelRepository(summary=False, pending_job={"status": "pending"}))

    with TestClient(app) as client:
        response = client.get("/api/watchlist/handle/toly/summary?token=secret")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "not_ready"
    assert data["summary_zh"] == ""
    assert data["is_stale"] is False
    assert data["pending_recompute"] is True
    assert "pending_job" not in data


def test_watchlist_handle_summary_endpoint_marks_old_summary_stale():
    app = _app(FakeWatchlistIntelRepository(summary={"generated_at_ms": 1}))

    with TestClient(app) as client:
        response = client.get("/api/watchlist/handle/toly/summary?token=secret")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ready"
    assert data["is_stale"] is True
    assert data["pending_recompute"] is False


def test_watchlist_handle_summary_config_uses_worker_settings():
    runtime = type(
        "Runtime",
        (),
        {
            "settings": Settings(
                ws_token="secret",
                workers={
                    "handle_summary": {
                        "signal_threshold": 17,
                        "time_threshold_ms": 123_000,
                        "min_interval_ms": 45_000,
                        "input_limit": 9,
                        "window_days": 3,
                        "max_attempts": 6,
                    }
                },
            )
        },
    )()

    config = _watchlist_handle_summary_config(runtime)

    assert config.signal_threshold == 17
    assert config.time_threshold_ms == 123_000
    assert config.min_interval_ms == 45_000
    assert config.input_limit == 9
    assert config.window_days == 3
    assert config.max_attempts == 6


def test_watchlist_handle_timeline_endpoint_validates_cursor_and_scope():
    app = _app(FakeWatchlistIntelRepository())
    cursor = encode_watchlist_timeline_cursor(received_at_ms=2_000, event_id="event-2")

    with TestClient(app) as client:
        ok = client.get(f"/api/watchlist/handle/toly/timeline?token=secret&scope=signal&cursor={cursor}")
        bad_cursor = client.get("/api/watchlist/handle/toly/timeline?token=secret&cursor=broken")
        bad_scope = client.get("/api/watchlist/handle/toly/timeline?token=secret&scope=legacy")

    assert ok.status_code == 200
    assert ok.json()["data"]["query"]["scope"] == "signal"
    assert ok.json()["data"]["items"][0]["social_event"]["summary_zh"] == "SOL 讨论升温。"
    assert bad_cursor.status_code == 400
    assert bad_cursor.json()["error"] == "invalid_cursor"
    assert bad_scope.status_code == 400
    assert bad_scope.json()["error"] == "invalid_scope"


def test_watchlist_handle_timeline_endpoint_uses_spec_limit_contract():
    app = _app(FakeWatchlistIntelRepository())

    with TestClient(app) as client:
        default_response = client.get("/api/watchlist/handle/toly/timeline?token=secret")
        zero_limit = client.get("/api/watchlist/handle/toly/timeline?token=secret&limit=0")
        over_limit = client.get("/api/watchlist/handle/toly/timeline?token=secret&limit=101")

    assert default_response.status_code == 200
    assert default_response.json()["data"]["query"]["limit"] == 30
    assert zero_limit.status_code == 422
    assert over_limit.status_code == 422


class FakeWatchlistIntelRepository:
    def __init__(self, *, summary=DEFAULT_SUMMARY, pending_job=None):
        self._summary = (
            {
                "handle": "toly",
                "generated_at_ms": 2_000,
                "input_event_count": 2,
                "signal_count_at_generation": 2,
                "model": "test-model",
                "summary_zh": "Toly 正在反复讨论 SOL 与 BONK。",
                "topics": [{"title": "SOL", "description": "SOL 生态讨论升温。", "event_count": 1}],
            }
            if summary is DEFAULT_SUMMARY
            else None
            if summary is False
            else summary
        )
        self._pending_job = pending_job

    def get_handle_summary(self, handle):
        if handle != "toly":
            return None
        if self._summary is None:
            return None
        return {
            "handle": "toly",
            "input_event_count": 2,
            "signal_count_at_generation": 2,
            "model": "test-model",
            "summary_zh": "Toly 正在反复讨论 SOL 与 BONK。",
            "topics": [{"title": "SOL", "description": "SOL 生态讨论升温。", "event_count": 1}],
            **self._summary,
        }

    def pending_summary_job(self, handle):
        return self._pending_job

    def count_signal_events_total(self, handle):
        return 2 if handle == "toly" else 0

    def timeline(self, *, handle, scope, cursor, limit):
        from gmgn_twitter_intel.domains.watchlist_intel.types import decode_watchlist_timeline_cursor

        if cursor:
            decode_watchlist_timeline_cursor(cursor)
        return {
            "query": {"handle": handle, "scope": scope, "limit": limit},
            "items": [
                {
                    "event_id": "event-1",
                    "received_at_ms": 1_000,
                    "text_clean": "$SOL launch",
                    "social_event": {"summary_zh": "SOL 讨论升温。"},
                }
            ],
            "has_more": False,
            "next_cursor": None,
        }


class FakeRepositoryContext:
    def __init__(self, watchlist_intel):
        self.watchlist_intel = watchlist_intel

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRuntime:
    def __init__(self, watchlist_intel):
        self.settings = Settings(ws_token="secret", handles=("toly",))
        self._watchlist_intel = watchlist_intel

    def repositories(self):
        return FakeRepositoryContext(self._watchlist_intel)


def _app(watchlist_intel):
    app = FastAPI()
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(lambda _: ({"ok": True}, 200)))
    app.state.service = FakeRuntime(watchlist_intel)
    return app
