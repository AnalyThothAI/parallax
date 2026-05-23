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
            params={
                "limit": 1,
                "cursor": "2000:row-old",
                "direction": "bullish",
                "decision_class": "driver",
                "content_tag": "sec",
            },
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert news.calls == [
        {
            "content_class": None,
            "coverage_tag": None,
            "cursor": "2000:row-old",
            "decision_class": "driver",
            "direction": "bullish",
            "include_unprojected": False,
            "lane": None,
            "limit": 1,
            "provider_type": None,
            "q": None,
            "source": None,
            "source_role": None,
            "status": None,
            "target": None,
            "trust_tier": None,
            "content_tag": "sec",
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
                    "content_class": "regulation",
                    "content_tags_json": ["sec"],
                    "content_classification_json": {"policy_version": "test"},
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


def test_news_api_accepts_source_classification_filters_without_postgres() -> None:
    news = FakeNewsRepository()
    app = _app(news)

    with TestClient(app) as client:
        response = client.get(
            "/api/news",
            params={
                "provider_type": "rss",
                "source_role": "specialist_media",
                "trust_tier": "high",
                "coverage_tag": "crypto_market",
                "content_class": "regulatory_action",
                "content_tag": "sec",
                "decision_class": "driver",
            },
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert news.calls[-1] == {
        "content_class": "regulatory_action",
        "content_tag": "sec",
        "coverage_tag": "crypto_market",
        "cursor": None,
        "decision_class": "driver",
        "direction": None,
        "include_unprojected": False,
        "lane": None,
        "limit": 100,
        "provider_type": "rss",
        "q": None,
        "source": None,
        "source_role": "specialist_media",
        "status": None,
        "target": None,
        "trust_tier": "high",
    }


def test_news_api_can_request_unprojected_fallback_without_postgres() -> None:
    news = FakeNewsRepository()
    app = _app(news)

    with TestClient(app) as client:
        response = client.get(
            "/api/news",
            params={"include_unprojected": "true"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert news.calls[-1]["include_unprojected"] is True


def test_news_api_source_status_includes_provider_diagnostics_without_postgres() -> None:
    news = FakeNewsRepository()
    news.source_status_rows = [
        {
            "source_id": "example-rss",
            "provider_type": "rss",
            "coverage_tags": ["crypto_market"],
            "enabled": True,
            "last_seen_at_ms": 3_000,
            "latest_item_published_at_ms": 2_000,
            "latest_item_fetched_at_ms": 3_000,
            "latest_context_seen_at_ms": None,
            "context_item_count": 0,
            "latest_fetch_run": {
                "status": "success",
                "started_at_ms": 2_900,
                "finished_at_ms": 3_000,
                "http_status": 200,
                "fetched_count": 1,
                "inserted_count": 1,
                "updated_count": 0,
                "duplicate_count": 0,
                "error": None,
            },
            "latest_quality_counts": {"fetch_run_count": 1},
            "provider_health": {
                "status": "healthy",
                "reason": "quality_status",
                "last_error": None,
                "consecutive_failures": 0,
                "last_success_at_ms": 3_000,
                "last_seen_at_ms": 3_000,
            },
            "provider_capability_tags": ["poll_primary_items", "http_cache"],
        },
        {
            "source_id": "unsupported-openbb",
            "provider_type": "openbb",
            "coverage_tags": [],
            "enabled": True,
            "source_quality_status": "degraded",
            "provider_health": {"status": "degraded"},
        }
    ]
    app = _app(news)

    with TestClient(app) as client:
        response = client.get("/api/news/sources/status", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "data": {
            "provider_capabilities": {
                "supported_provider_types": ["atom", "cryptopanic", "json_feed", "rss"],
                "configured_provider_types": ["openbb", "rss"],
                "unsupported_configured_provider_types": ["openbb"],
            },
            "source_hygiene": {
                "sources_missing_coverage_tags": ["unsupported-openbb"],
                "unsupported_sources": [{"source_id": "unsupported-openbb", "provider_type": "openbb"}],
                "degraded_sources": [{"source_id": "unsupported-openbb", "status": "degraded"}],
                "warnings": [
                    {"source_id": "unsupported-openbb", "reason": "unsupported_provider_type"},
                    {"source_id": "unsupported-openbb", "reason": "missing_coverage_tags"},
                    {"source_id": "unsupported-openbb", "reason": "provider_health_degraded"},
                ],
            },
            "sources": news.source_status_rows,
        },
    }


class FakeNewsRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.source_status_rows: list[dict[str, object]] = []

    def list_news_page_rows(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        status: str | None = None,
        lane: str | None = None,
        source: str | None = None,
        target: str | None = None,
        direction: str | None = None,
        provider_type: str | None = None,
        source_role: str | None = None,
        trust_tier: str | None = None,
        coverage_tag: str | None = None,
        content_class: str | None = None,
        content_tag: str | None = None,
        decision_class: str | None = None,
        q: str | None = None,
        include_unprojected: bool,
    ):
        self.calls.append(
            {
                "content_class": content_class,
                "content_tag": content_tag,
                "coverage_tag": coverage_tag,
                "cursor": cursor,
                "decision_class": decision_class,
                "direction": direction,
                "include_unprojected": include_unprojected,
                "lane": lane,
                "limit": limit,
                "provider_type": provider_type,
                "q": q,
                "source": source,
                "source_role": source_role,
                "status": status,
                "target": target,
                "trust_tier": trust_tier,
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
                "content_class": "regulation",
                "content_tags_json": ["sec"],
                "content_classification_json": {"policy_version": "test"},
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
        return self.source_status_rows


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
