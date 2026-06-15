from fastapi import FastAPI
from fastapi.testclient import TestClient

from parallax.app.surfaces.api.exceptions import (
    ApiBadRequest,
    ApiUnauthorized,
    api_bad_request_response,
    api_unauthorized_response,
)
from parallax.app.surfaces.api.http import create_api_router
from parallax.domains.watchlist_intel.types import encode_watchlist_timeline_cursor
from parallax.platform.config.settings import Settings


def test_watchlist_handle_timeline_endpoint_validates_cursor_and_scope():
    app = _app(FakeWatchlistIntelRepository())
    cursor = encode_watchlist_timeline_cursor(received_at_ms=2_000, event_id="event-2")

    with TestClient(app) as client:
        ok = client.get(f"/api/watchlist/handle/toly/timeline?token=secret&scope=signal&cursor={cursor}")
        bad_cursor = client.get("/api/watchlist/handle/toly/timeline?token=secret&cursor=broken")
        bad_scope = client.get("/api/watchlist/handle/toly/timeline?token=secret&scope=legacy")

    assert ok.status_code == 200
    assert ok.json()["data"]["query"]["scope"] == "signal"
    item = ok.json()["data"]["items"][0]
    assert item["event_id"] == "event-1"
    assert item["social_event"] is None
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


def test_watchlist_handle_overview_endpoint_requires_configured_handle():
    app = _app(FakeWatchlistIntelRepository())

    with TestClient(app) as client:
        ok = client.get("/api/watchlist/handle/toly/overview?token=secret")
        missing = client.get("/api/watchlist/handle/unknown/overview?token=secret")

    assert ok.status_code == 200
    assert ok.json()["data"]["query"]["handle"] == "toly"
    assert ok.json()["data"]["metrics"]["source_event_count"] == 1
    assert missing.status_code == 404
    assert missing.json()["error"] == "handle_not_found"


class FakeWatchlistIntelRepository:
    def timeline(self, *, handle, scope, cursor, limit):
        from parallax.domains.watchlist_intel.types import decode_watchlist_timeline_cursor

        if cursor:
            decode_watchlist_timeline_cursor(cursor)
        return {
            "query": {"handle": handle, "scope": scope, "limit": limit},
            "items": [
                {
                    "event_id": "event-1",
                    "received_at_ms": 1_000,
                    "text_clean": "$SOL launch",
                    "social_event": None,
                }
            ],
            "has_more": False,
            "next_cursor": None,
        }

    def handles_overview(self, *, handles, since_ms):
        return [
            {
                "handle": handle,
                "last_source_event_at_ms": 1_000,
                "recent_source_event_count": 1,
                "recent_signal_event_count": 0,
                "total_signal_event_count": 0,
            }
            for handle in handles
        ]

    def handle_overview(self, *, handle, scope, since_ms, source_limit, cluster_limit):
        assert source_limit == 500
        assert cluster_limit == 500
        return {
            "query": {"handle": handle, "scope": scope},
            "metrics": {
                "source_event_count": 1,
                "signal_event_count": 0,
                "resolved_token_count": 0,
                "candidate_mention_count": 1,
                "narrative_count": 0,
                "last_source_event_at_ms": 1_000,
            },
            "resolved_token_clusters": [],
            "candidate_mention_clusters": [{"label": "$SOL", "count": 1, "query": "$SOL", "kind": "candidate_mention"}],
            "narrative_clusters": [],
            "clusters_truncated": False,
            "risk_notes": ["candidate_mentions_unresolved"],
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
