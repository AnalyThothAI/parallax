from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from parallax.app.surfaces.api.exceptions import (
    ApiBadRequest,
    ApiUnauthorized,
    api_bad_request_response,
    api_unauthorized_response,
)
from parallax.app.surfaces.api.http import create_api_router
from parallax.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from parallax.domains.news_intel.repositories.news_repository import _public_agent_brief_payload


def test_news_api_lists_provider_signal_news_rows_without_postgres() -> None:
    news = FakeNewsRepository()
    app = _app(news)

    with TestClient(app) as client:
        response = client.get(
            "/api/news",
            params={
                "limit": 1,
                "cursor": "2000:row-old",
                "signal": "bullish",
                "min_score": "70",
                "q": " btc ",
            },
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert news.calls == [
        {
            "cursor": "2000:row-old",
            "limit": 2,
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
                    "representative_news_item_id": "news-1",
                    "story_key": "news-story:subject:sol-etf:t412000",
                    "story": {
                        "story_key": "news-story:subject:sol-etf:t412000",
                        "representative_news_item_id": "news-1",
                        "member_news_item_ids": ["news-1"],
                        "member_count": 1,
                        "source_domains": ["example.com"],
                    },
                    "latest_at_ms": 3_000,
                    "lifecycle_status": "raw",
                    "headline": "SOL ETF approved",
                    "summary": "Issuer confirms launch.",
                    "source_domain": "example.com",
                    "canonical_url": "https://example.com/story",
                    "token_lanes": [{"symbol": "BTC", "provider_score": 82, "provider_signal": "long"}],
                    "fact_lanes": [],
                    "signal": {
                        "display_signal": {
                            "source": "provider",
                            "provider": "opennews",
                            "status": "ready",
                            "direction": "bullish",
                            "label_zh": "利好",
                            "score": 82,
                            "grade": "A",
                        },
                        "provider_signal": {
                            "source": "provider",
                            "provider": "opennews",
                            "status": "ready",
                            "direction": "bullish",
                            "score": 82,
                        },
                        "agent_signal": {"status": "pending"},
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": False,
                            "provider_score": 82,
                            "decision_class": "driver",
                        },
                    },
                    "token_impacts": [{"symbol": "BTC", "score": 82, "signal": "long"}],
                    "source": {"source_id": "opennews-realtime", "provider_type": "opennews"},
                    "analysis_admission_status": "admitted",
                    "analysis_admission_reason": "crypto_native_subject",
                    "analysis_admission": {
                        "status": "admitted",
                        "reason": "crypto_native_subject",
                        "basis": {"subject": "sol_etf"},
                    },
                    "computed_at_ms": 3_100,
                    "projection_version": NEWS_PAGE_PROJECTION_VERSION,
                }
            ],
            "next_cursor": "3000:row-1",
        },
    }


def test_news_api_returns_null_next_cursor_when_no_extra_row_without_postgres() -> None:
    news = FakeNewsRepository()
    app = _app(news)

    with TestClient(app) as client:
        response = client.get(
            "/api/news",
            params={"limit": 2, "q": "zec"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert news.calls == [
        {
            "cursor": None,
            "limit": 3,
            "min_score": None,
            "q": "zec",
            "signal": None,
            "status": None,
        }
    ]
    data = response.json()["data"]
    assert [row["row_id"] for row in data["items"]] == ["row-1", "row-2"]
    assert data["next_cursor"] is None


def test_news_api_paginates_zec_keyword_results_with_true_has_more_without_postgres() -> None:
    news = FakeNewsRepository()
    news.rows = [_news_row(row_id=f"row-{index}", latest_at_ms=10_000 - index) for index in range(1, 7)]
    app = _app(news)

    with TestClient(app) as client:
        first = client.get(
            "/api/news",
            params={"limit": 5, "q": "zec"},
            headers={"Authorization": "Bearer secret"},
        )
        cursor = first.json()["data"]["next_cursor"]
        second = client.get(
            "/api/news",
            params={"limit": 5, "q": "zec", "cursor": cursor},
            headers={"Authorization": "Bearer secret"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert news.calls == [
        {
            "cursor": None,
            "limit": 6,
            "min_score": None,
            "q": "zec",
            "signal": None,
            "status": None,
        },
        {
            "cursor": "9995:row-5",
            "limit": 6,
            "min_score": None,
            "q": "zec",
            "signal": None,
            "status": None,
        },
    ]
    first_data = first.json()["data"]
    second_data = second.json()["data"]
    assert [row["row_id"] for row in first_data["items"]] == ["row-1", "row-2", "row-3", "row-4", "row-5"]
    assert first_data["next_cursor"] == "9995:row-5"
    assert [row["row_id"] for row in second_data["items"]] == ["row-6"]
    assert second_data["next_cursor"] is None


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
                "has_token": "false",
                "lane": "resolved",
                "source": "example.com",
                "target": "BTC",
            },
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert news.calls[-1] == {
        "cursor": None,
        "limit": 101,
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


def test_news_item_detail_hides_retired_brief_fields() -> None:
    news = FakeNewsRepository()
    news.item_detail = {
        "news_item_id": "news-1",
        "representative_news_item_id": "news-1",
        "story_key": "news-story:subject:btc-detail:t412000",
        "story": {
            "story_key": "news-story:subject:btc-detail:t412000",
            "representative_news_item_id": "news-1",
            "member_news_item_ids": ["news-1"],
            "member_count": 1,
            "source_domains": ["example.com"],
        },
        "analysis_admission_status": "admitted",
        "analysis_admission_reason": "crypto_native_subject",
        "analysis_admission": {
            "status": "admitted",
            "reason": "crypto_native_subject",
            "basis": {"subject": "btc"},
        },
        "agent_brief": {
            "status": "ready",
            "direction": "bullish",
            "decision_class": "driver",
            "brief_json": {
                "summary_zh": "旧简报",
                "retrieval_notes_zh": "retired",
                "source_consensus_zh": "retired",
            },
            "confirmation_state": "confirmed",
            "novelty_status": "new",
            "used_tool_call_ids": ["tool-1"],
            "impact_zh": "retired",
            "watch_items_zh": ["retired"],
            "confidence": 0.9,
            "prompt_version": "news-item-brief-v2",
            "schema_version": "news_item_brief_v1",
            "validator_version": "news_item_brief_validator_v2",
            "computed_at_ms": 123,
        },
    }
    app = _app(news)

    with TestClient(app) as client:
        response = client.get("/api/news/items/news-1", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    agent_brief = response.json()["data"]["agent_brief"]
    assert agent_brief == {"status": "pending", "brief_json": {}}
    assert "retrieval_notes_zh" not in agent_brief
    assert "source_consensus_zh" not in agent_brief
    assert "confirmation_state" not in agent_brief
    assert "novelty_status" not in agent_brief
    assert "used_tool_call_ids" not in agent_brief
    assert "impact_zh" not in agent_brief
    assert "watch_items_zh" not in agent_brief
    assert "confidence" not in agent_brief
    data = response.json()["data"]
    assert data["representative_news_item_id"] == "news-1"
    assert data["story_key"] == "news-story:subject:btc-detail:t412000"
    assert data["story"]["member_count"] == 1
    assert data["analysis_admission_status"] == "admitted"
    assert data["analysis_admission_reason"] == "crypto_native_subject"
    assert data["analysis_admission"]["basis"] == {"subject": "btc"}


class FakeNewsRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.rows = [_news_row(row_id="row-1", latest_at_ms=3_000), _news_row(row_id="row-2", latest_at_ms=2_000)]
        self.source_status_rows: list[dict[str, object]] = []
        self.item_detail: dict[str, object] | None = None

    def list_news_page_rows(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        status: str | None = None,
        signal: str | None = None,
        min_score: int | None = None,
        q: str | None = None,
    ):
        self.calls.append(
            {
                "cursor": cursor,
                "limit": limit,
                "min_score": min_score,
                "q": q,
                "signal": signal,
                "status": status,
            }
        )
        start = 0
        if cursor:
            for index, row in enumerate(self.rows):
                if f"{int(row['latest_at_ms'])}:{row['row_id']}" == cursor:
                    start = index + 1
                    break
        return self.rows[start : start + max(0, int(limit))]

    def get_news_item_detail(self, *, news_item_id: str):
        if self.item_detail is not None:
            item_detail = dict(self.item_detail)
            item_detail["agent_brief"] = _public_agent_brief_payload(item_detail.get("agent_brief"))
            return item_detail
        return {"news_item_id": news_item_id}

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
        self.providers = type(
            "FakeProviders",
            (),
            {
                "news_intel": type(
                    "FakeNewsProviders",
                    (),
                    {"feed_client": FakeNewsFeedClient()},
                )()
            },
        )()

    def repositories(self):
        return FakeRepositoryContext(self.news)


class FakeNewsFeedClient:
    def supported_provider_types(self) -> tuple[str, ...]:
        return ("atom", "cryptopanic", "json_feed", "opennews", "rss")


def _news_row(*, row_id: str, latest_at_ms: int) -> dict[str, object]:
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
        },
        "latest_at_ms": latest_at_ms,
        "lifecycle_status": "raw",
        "headline": "SOL ETF approved",
        "summary": "Issuer confirms launch.",
        "source_domain": "example.com",
        "canonical_url": "https://example.com/story",
        "token_lanes": [{"symbol": "BTC", "provider_score": 82, "provider_signal": "long"}],
        "fact_lanes": [],
        "signal": {
            "display_signal": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "bullish",
                "label_zh": "利好",
                "score": 82,
                "grade": "A",
            },
            "provider_signal": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "bullish",
                "score": 82,
            },
            "agent_signal": {"status": "pending"},
            "alert_eligibility": {
                "in_app_eligible": True,
                "external_push_ready": False,
                "provider_score": 82,
                "decision_class": "driver",
            },
        },
        "token_impacts": [{"symbol": "BTC", "score": 82, "signal": "long"}],
        "source": {"source_id": "opennews-realtime", "provider_type": "opennews"},
        "analysis_admission_status": "admitted",
        "analysis_admission_reason": "crypto_native_subject",
        "analysis_admission": {
            "status": "admitted",
            "reason": "crypto_native_subject",
            "basis": {"subject": "sol_etf"},
        },
        "computed_at_ms": 3_100,
        "projection_version": NEWS_PAGE_PROJECTION_VERSION,
    }


def _app(news: FakeNewsRepository) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(lambda _: ({"ok": True}, 200)))
    app.state.service = FakeRuntime(news)
    return app
