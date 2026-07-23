from fastapi import FastAPI
from fastapi.testclient import TestClient

from parallax.app.surfaces.api.exceptions import (
    ApiBadRequest,
    ApiUnauthorized,
    api_bad_request_response,
    api_unauthorized_response,
)
from parallax.app.surfaces.api.http import create_api_router
from parallax.platform.config.settings import Settings


def test_watchlist_handle_overview_endpoint_validates_configured_handle():
    app = _app(FakeWatchlistQuery(), handles=("marionawfal", "toly"))

    with TestClient(app) as client:
        ok = client.get("/api/watchlist/handle/marionawfal/overview?token=secret")
        unknown = client.get("/api/watchlist/handle/unknown/overview?token=secret")
        invalid_handle = client.get("/api/watchlist/handle/%20/overview?token=secret")

    assert ok.status_code == 200
    data = ok.json()["data"]
    assert data["query"] == {"handle": "marionawfal", "window": "3d"}
    assert data["metrics"]["candidate_mention_count"] == 1
    assert data["candidate_mention_clusters"][0]["label"] == "$ALOY"
    assert unknown.status_code == 404
    assert unknown.json()["error"] == "handle_not_found"
    assert invalid_handle.status_code == 400
    assert invalid_handle.json()["error"] == "invalid_handle"


def test_watchlist_handles_overview_endpoint_returns_configured_rows_only():
    app = _app(FakeWatchlistQuery(), handles=("marionawfal", "toly"))

    with TestClient(app) as client:
        response = client.get("/api/watchlist/handles/overview?token=secret")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["window"] == "3d"
    assert [row["handle"] for row in data["items"]] == ["marionawfal", "toly"]
    assert data["items"][0]["recent_source_event_count"] == 2
    assert data["items"][1]["recent_source_event_count"] == 0


class FakeWatchlistQuery:
    def handles_overview(self, *, handles, since_ms):
        del since_ms
        rows = {
            "marionawfal": {
                "handle": "marionawfal",
                "last_source_event_at_ms": 2_000,
                "recent_source_event_count": 2,
            },
            "toly": {
                "handle": "toly",
                "last_source_event_at_ms": None,
                "recent_source_event_count": 0,
            },
        }
        return [rows[handle] for handle in handles if handle in rows]

    def handle_overview(self, *, handle, since_ms, source_limit, cluster_limit):
        del since_ms
        assert source_limit == 500
        assert cluster_limit == 500
        return {
            "query": {"handle": handle},
            "metrics": {
                "source_event_count": 2,
                "resolved_token_count": 0,
                "candidate_mention_count": 1,
                "hashtag_count": 0,
                "last_source_event_at_ms": 2_000,
            },
            "resolved_token_clusters": [],
            "candidate_mention_clusters": [
                {
                    "label": "$ALOY",
                    "count": 1,
                    "query": "$ALOY",
                    "kind": "candidate_mention",
                    "target_type": None,
                    "target_id": None,
                    "symbol": None,
                    "source": "event_cashtags",
                }
            ],
            "hashtag_clusters": [],
            "clusters_truncated": False,
            "risk_notes": ["candidate_mentions_unresolved"],
        }


class FakeRepositoryContext:
    def __init__(self, watchlist):
        self.watchlist = watchlist

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRuntime:
    def __init__(self, watchlist, *, handles):
        self.settings = Settings(ws_token="secret", handles=handles)
        self._watchlist = watchlist

    def repositories(self):
        return FakeRepositoryContext(self._watchlist)


def _app(watchlist, *, handles):
    app = FastAPI()
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(lambda _: {"ok": True}))
    app.state.service = FakeRuntime(watchlist, handles=handles)
    return app
