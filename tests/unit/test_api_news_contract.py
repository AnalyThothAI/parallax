from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gmgn_twitter_intel.app.surfaces.api.exceptions import (
    ApiBadRequest,
    ApiUnauthorized,
    api_bad_request_response,
    api_unauthorized_response,
)
from gmgn_twitter_intel.app.surfaces.api.http import create_api_router


def test_news_api_lists_raw_news_page_rows_without_postgres() -> None:
    news = FakeNewsRepository()
    app = _app(news)

    with TestClient(app) as client:
        response = client.get(
            "/api/news",
            params={"limit": 1, "cursor": "2000:row-old"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert news.calls == [
        {
            "cursor": "2000:row-old",
            "lane": None,
            "limit": 1,
            "q": None,
            "source": None,
            "status": None,
            "target": None,
        }
    ]
    assert response.json() == {
        "ok": True,
        "data": {
            "items": [
                {
                    "row_id": "row-1",
                    "news_item_id": "news-1",
                    "story_id": None,
                    "latest_at_ms": 3_000,
                    "lifecycle_status": "raw",
                    "headline": "SOL ETF approved",
                    "summary": "Issuer confirms launch.",
                    "source_domain": "example.com",
                    "canonical_url": "https://example.com/story",
                    "token_lanes_json": [],
                    "fact_lanes_json": [],
                    "story_json": {},
                    "source_json": {"source_id": "example-rss"},
                    "agent_brief_json": {"status": "pending"},
                    "agent_brief": {"status": "pending"},
                    "agent_status": "pending",
                    "agent_brief_status": "pending",
                    "agent_brief_computed_at_ms": None,
                    "computed_at_ms": 3_100,
                    "projection_version": "news_page_v1",
                }
            ],
            "next_cursor": "3000:row-1",
        },
    }


class FakeNewsRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def list_news_page_rows(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        status: str | None = None,
        lane: str | None = None,
        source: str | None = None,
        target: str | None = None,
        q: str | None = None,
    ):
        self.calls.append(
            {
                "cursor": cursor,
                "lane": lane,
                "limit": limit,
                "q": q,
                "source": source,
                "status": status,
                "target": target,
            }
        )
        return [
            {
                "row_id": "row-1",
                "news_item_id": "news-1",
                "story_id": None,
                "latest_at_ms": 3_000,
                "lifecycle_status": "raw",
                "headline": "SOL ETF approved",
                "summary": "Issuer confirms launch.",
                "source_domain": "example.com",
                "canonical_url": "https://example.com/story",
                "token_lanes_json": [],
                "fact_lanes_json": [],
                "story_json": {},
                "source_json": {"source_id": "example-rss"},
                "agent_brief_json": {"status": "pending"},
                "agent_brief": {"status": "pending"},
                "agent_status": "pending",
                "agent_brief_status": "pending",
                "agent_brief_computed_at_ms": None,
                "computed_at_ms": 3_100,
                "projection_version": "news_page_v1",
            }
        ]

    def get_news_item_detail(self, *, news_item_id: str):
        return {"news_item_id": news_item_id}

    def get_news_story_detail(self, *, story_id: str):
        return {"story_id": story_id}

    def get_news_fact_detail(self, *, fact_candidate_id: str):
        return {"fact_candidate_id": fact_candidate_id}

    def list_source_status(self):
        return []


class FakeRepositoryContext:
    def __init__(self, news: FakeNewsRepository) -> None:
        self.news = news

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRuntime:
    def __init__(self, news: FakeNewsRepository) -> None:
        self.settings = type("FakeSettings", (), {"ws_token": "secret"})()
        self.news = news

    def repositories(self):
        return FakeRepositoryContext(self.news)


def _app(news: FakeNewsRepository) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(lambda _: ({"ok": True}, 200)))
    app.state.service = FakeRuntime(news)
    return app
