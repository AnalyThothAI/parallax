from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from parallax.app.surfaces.api.exceptions import (
    ApiBadRequest,
    ApiUnauthorized,
    api_bad_request_response,
    api_unauthorized_response,
)
from parallax.app.surfaces.api.http import create_api_router
from parallax.domains.news_intel._constants import (
    NEWS_MARKET_SCOPE_VERSION,
    NEWS_PAGE_PROJECTION_VERSION,
)


def test_news_api_lists_source_facts_without_product_ai() -> None:
    news = FakeNewsRepository()
    app = _app(news)

    with TestClient(app) as client:
        response = client.get(
            "/api/news",
            params={"limit": 1, "cursor": "2000:row-old", "q": " btc "},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert news.calls == [
        {
            "cursor": "2000:row-old",
            "limit": 2,
            "q": "btc",
            "status": None,
        }
    ]
    item = response.json()["data"]["items"][0]
    assert item == _news_row(row_id="row-1", latest_at_ms=3_000)
    assert set(item).isdisjoint(
        {
            "signal",
            "token_impacts",
            "agent_brief",
            "agent_status",
            "macro_event_flow",
            "agent_admission",
            "agent_admission_status",
        }
    )


@pytest.mark.parametrize(
    "retired_param",
    (
        "signal",
        "decision_class",
        "has_token",
        "lane",
        "provider_type",
        "source_role",
        "content_class",
    ),
)
def test_news_api_rejects_retired_product_filters(retired_param: str) -> None:
    news = FakeNewsRepository()
    app = _app(news)

    with TestClient(app) as client:
        response = client.get(
            "/api/news",
            params={retired_param: "retired"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {
        "ok": False,
        "error": "unsupported_query_param",
        "field": retired_param,
    }
    assert news.calls == []


def test_news_list_fails_closed_on_retired_ai_field() -> None:
    news = FakeNewsRepository()
    news.rows[0]["agent_brief"] = {"status": "ready"}
    app = _app(news)

    with TestClient(app) as client, pytest.raises(ValidationError, match="agent_brief"):
        client.get("/api/news", headers={"Authorization": "Bearer secret"})


def test_news_item_detail_is_fact_only_and_exact() -> None:
    news = FakeNewsRepository()
    app = _app(news)

    with TestClient(app) as client:
        response = client.get(
            "/api/news/items/news-1",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "data": _news_detail()}
    assert set(response.json()["data"]).isdisjoint(
        {
            "signal",
            "token_impacts",
            "agent_brief",
            "agent_admission",
            "agent_admission_status",
        }
    )


def test_news_item_detail_fails_closed_on_retired_ai_field() -> None:
    news = FakeNewsRepository()
    news.item_detail = {**_news_detail(), "signal": {"direction": "bullish"}}
    app = _app(news)

    with TestClient(app) as client, pytest.raises(ValidationError, match="signal"):
        client.get("/api/news/items/news-1", headers={"Authorization": "Bearer secret"})


def test_news_source_status_preserves_provider_fact_diagnostics() -> None:
    news = FakeNewsRepository()
    news.source_status_rows = [
        {
            "source_id": "example-rss",
            "provider_type": "rss",
            "coverage_tags": ["crypto_market"],
            "enabled": True,
            "provider_health": {"status": "healthy"},
        }
    ]
    app = _app(news)

    with TestClient(app) as client:
        response = client.get(
            "/api/news/sources/status",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider_capabilities"]["configured_provider_types"] == ["rss"]
    assert data["source_hygiene"]["warnings"] == []
    assert data["sources"] == news.source_status_rows


def test_news_openapi_contains_only_fact_contract_fields() -> None:
    schemas = _app(FakeNewsRepository()).openapi()["components"]["schemas"]
    row_fields = set(schemas["NewsRow"]["properties"])
    detail_fields = set(schemas["NewsObjectData"]["properties"])

    assert {
        "story",
        "canonical_item_key",
        "provider_article_keys",
        "token_lanes",
        "fact_lanes",
        "provider_rating",
        "market_scope",
    } <= row_fields
    assert row_fields.isdisjoint(
        {
            "signal",
            "token_impacts",
            "agent_brief",
            "agent_status",
            "macro_event_flow",
            "agent_admission",
        }
    )
    assert detail_fields.isdisjoint(
        {
            "signal",
            "token_impacts",
            "agent_brief",
            "agent_admission",
            "agent_admission_status",
        }
    )
    for retired_schema in (
        "NewsAgentAdmission",
        "NewsAgentBrief",
        "NewsAgentSignal",
        "NewsAlertEligibility",
        "NewsSignalEnvelope",
        "NewsSignalSummary",
    ):
        assert retired_schema not in schemas


class FakeNewsRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.rows = [
            _news_row(row_id="row-1", latest_at_ms=3_000),
            _news_row(row_id="row-2", latest_at_ms=2_000),
        ]
        self.source_status_rows: list[dict[str, Any]] = []
        self.item_detail: dict[str, Any] | None = None

    def list_news_page_rows(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        status: str | None = None,
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "cursor": cursor,
                "limit": limit,
                "q": q,
                "status": status,
            }
        )
        return self.rows[:limit]

    def get_news_item_detail(self, *, news_item_id: str) -> dict[str, Any] | None:
        if news_item_id != "news-1":
            return None
        return dict(self.item_detail or _news_detail())

    def get_news_fact_detail(self, *, fact_candidate_id: str) -> None:
        return None

    def list_source_status(self) -> list[dict[str, Any]]:
        return self.source_status_rows


class FakeRepositoryContext:
    def __init__(self, news: FakeNewsRepository) -> None:
        self.news_pages = news
        self.news_sources = news

    def __enter__(self) -> FakeRepositoryContext:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class FakeRuntime:
    def __init__(self, news: FakeNewsRepository) -> None:
        self.settings = type("FakeSettings", (), {"ws_token": "secret"})()
        self.news = news

    def repositories(self) -> FakeRepositoryContext:
        return FakeRepositoryContext(self.news)


def _news_row(*, row_id: str, latest_at_ms: int) -> dict[str, Any]:
    return {
        "row_id": row_id,
        "news_item_id": "news-1",
        "representative_news_item_id": "news-1",
        "story_key": "news-story:subject:sol-etf:t412000",
        "story": {
            "story_key": "news-story:subject:sol-etf:t412000",
            "representative_news_item_id": "news-1",
            "member_news_item_ids": ["news-1"],
            "member_count": 1,
            "source_domains": ["example.com"],
            "source_ids": ["opennews-realtime"],
            "provider_article_keys": ["provider-article-1"],
        },
        "latest_at_ms": latest_at_ms,
        "lifecycle_status": "accepted",
        "headline": "SOL ETF approved",
        "summary": "Issuer confirms launch.",
        "source_domain": "example.com",
        "canonical_url": "https://example.com/story",
        "canonical_item_key": "example.com:story",
        "duplicate_count": 1,
        "source_ids": ["opennews-realtime"],
        "source_domains": ["example.com"],
        "provider_article_keys": ["provider-article-1"],
        "token_lanes": [{"lane": "resolved", "symbol": "SOL"}],
        "fact_lanes": [
            {
                "fact_candidate_id": "fact-1",
                "claim": "Issuer confirms launch.",
                "event_type": "product_launch",
                "realis": "actual",
                "status": "accepted",
            }
        ],
        "provider_rating": {"provider": "opennews", "status": "published"},
        "content_class": "regulation",
        "content_tags": ["sec"],
        "content_classification": {"status": "classified"},
        "source": _news_source_summary(),
        "market_scope": _market_scope(),
        "computed_at_ms": 3_100,
        "projection_version": NEWS_PAGE_PROJECTION_VERSION,
    }


def _news_source_summary() -> dict[str, Any]:
    return {
        "source_id": "opennews-realtime",
        "source_name": None,
        "source_domain": "example.com",
        "provider_type": "opennews",
        "source_role": "specialist_media",
        "trust_tier": "standard",
        "coverage_tags": ["crypto_market"],
        "source_quality_status": "ready",
    }


def _news_detail() -> dict[str, Any]:
    return {
        "news_item_id": "news-1",
        "source_id": "opennews-realtime",
        "source_domain": "example.com",
        "canonical_url": "https://example.com/story",
        "title": "SOL ETF approved",
        "summary": "Issuer confirms launch.",
        "body_text": "Issuer confirms the SOL ETF launch.",
        "language": "en",
        "published_at_ms": 3_000,
        "fetched_at_ms": 3_010,
        "lifecycle_status": "accepted",
        "content_class": "regulation",
        "processed_at_ms": 3_015,
        "processing_error": None,
        "created_at_ms": 3_020,
        "updated_at_ms": 3_030,
        "duplicate_observation_count": 1,
        "representative_news_item_id": "news-1",
        "story_key": "news-story:subject:sol-etf:t412000",
        "story": _news_row(row_id="unused", latest_at_ms=1)["story"],
        "content_tags": ["sec"],
        "content_classification": {"status": "classified"},
        "provider_rating": {"provider": "opennews", "status": "published"},
        "market_scope": _market_scope(),
        "token_lanes": [{"lane": "resolved", "symbol": "SOL"}],
        "fact_lanes": [],
        "source": {
            **_news_source_summary(),
            "asset_universe": ["SOL"],
            "authority_scope": {},
            "enabled": True,
            "managed_by_config": True,
            "refresh_interval_seconds": 300,
            "created_at_ms": 1_000,
            "updated_at_ms": 2_000,
        },
        "provider_item": {"source_id": "opennews-realtime"},
        "fetch_run": None,
        "observation_edges": [],
        "provider_observations": [],
        "entities": [],
        "token_mentions": [],
        "fact_candidates": [],
    }


def _market_scope() -> dict[str, Any]:
    return {
        "scope": ["crypto"],
        "primary": "crypto",
        "status": "classified",
        "reason": "market_scope_classified",
        "basis": {"subject": "sol_etf"},
        "version": NEWS_MARKET_SCOPE_VERSION,
    }


def _app(news: FakeNewsRepository) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(lambda _: {"ok": True}))
    app.state.service = FakeRuntime(news)
    return app
