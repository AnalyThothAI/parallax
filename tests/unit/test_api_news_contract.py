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


def test_news_api_lists_provider_signal_news_rows_without_postgres() -> None:
    news = FakeNewsRepository()
    app = _app(news)

    with TestClient(app) as client:
        response = client.get(
            "/api/news",
            params={
                "limit": 1,
                "cursor": "2000:row-old",
                "has_token": "true",
                "signal": "bullish",
                "min_score": "70",
                "q": "btc",
            },
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert news.calls == [
        {
            "cursor": "2000:row-old",
            "has_token": True,
            "limit": 1,
            "min_score": 70,
            "q": "btc",
            "signal": "bullish",
            "status": None,
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
                    "token_lanes": [{"symbol": "BTC", "provider_score": 82, "provider_signal": "long"}],
                    "fact_lanes": [],
                    "signal": {
                        "source": "provider",
                        "provider": "opennews",
                        "status": "ready",
                        "direction": "bullish",
                        "label_zh": "利好",
                        "score": 82,
                        "grade": "A",
                    },
                    "token_impacts": [{"symbol": "BTC", "score": 82, "signal": "long"}],
                    "story": {},
                    "source": {"source_id": "opennews-realtime", "provider_type": "opennews"},
                    "computed_at_ms": 3_100,
                    "projection_version": "news_page_v1",
                }
            ],
            "next_cursor": "3000:row-1",
        },
    }


def test_news_api_ignores_retired_source_classification_filters_without_postgres() -> None:
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
                "content_class": "regulation",
                "content_tag": "sec",
                "decision_class": "driver",
                "lane": "resolved",
                "source": "example.com",
                "target": "BTC",
            },
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert news.calls[-1] == {
        "cursor": None,
        "has_token": None,
        "limit": 100,
        "min_score": None,
        "q": None,
        "signal": None,
        "status": None,
    }


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
        },
    ]
    app = _app(news)

    with TestClient(app) as client:
        response = client.get("/api/news/sources/status", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "data": {
            "provider_capabilities": {
                "supported_provider_types": ["atom", "cryptopanic", "json_feed", "opennews", "rss"],
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
        has_token: bool | None = None,
        signal: str | None = None,
        min_score: int | None = None,
        q: str | None = None,
    ):
        self.calls.append(
            {
                "cursor": cursor,
                "has_token": has_token,
                "limit": limit,
                "min_score": min_score,
                "q": q,
                "signal": signal,
                "status": status,
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
                "token_lanes": [{"symbol": "BTC", "provider_score": 82, "provider_signal": "long"}],
                "fact_lanes": [],
                "signal": {
                    "source": "provider",
                    "provider": "opennews",
                    "status": "ready",
                    "direction": "bullish",
                    "label_zh": "利好",
                    "score": 82,
                    "grade": "A",
                },
                "token_impacts": [{"symbol": "BTC", "score": 82, "signal": "long"}],
                "story": {},
                "source": {"source_id": "opennews-realtime", "provider_type": "opennews"},
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
