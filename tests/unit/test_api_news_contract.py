from __future__ import annotations

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
    NEWS_ITEM_AGENT_ADMISSION_VERSION,
    NEWS_MARKET_SCOPE_VERSION,
    NEWS_PAGE_PROJECTION_VERSION,
    NEWS_STORY_BRIEF_GUARDRAIL_VERSION,
    NEWS_STORY_BRIEF_PROMPT_VERSION,
    NEWS_STORY_BRIEF_SCHEMA_VERSION,
    NEWS_STORY_BRIEF_VALIDATOR_VERSION,
)
from parallax.domains.news_intel.repositories.news_repository_support import (
    _public_agent_brief_payload,
)


def test_news_api_lists_agent_signal_news_rows_without_postgres() -> None:
    news = FakeNewsRepository()
    app = _app(news)

    with TestClient(app) as client:
        response = client.get(
            "/api/news",
            params={
                "limit": 1,
                "cursor": "2000:row-old",
                "signal": "bullish",
                "q": " btc ",
            },
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert news.calls == [
        {
            "cursor": "2000:row-old",
            "limit": 2,
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
                    "duplicate_count": 1,
                    "source_ids": ["opennews-realtime"],
                    "source_domains": ["example.com"],
                    "token_lanes": [{"lane": "resolved", "symbol": "BTC"}],
                    "fact_lanes": [],
                    "signal": {
                        "display_signal": {
                            "source": "agent",
                            "status": "ready",
                            "direction": "bullish",
                            "label_zh": "利好",
                            "title_zh": "AI 标题：SOL ETF approved",
                            "summary_zh": "Agent summary.",
                            "method": "news_story_brief",
                        },
                        "agent_signal": {
                            "status": "ready",
                            "direction": "bullish",
                            "decision_class": "driver",
                        },
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": False,
                            "agent_status": "ready",
                            "decision_class": "driver",
                            "market_scope": _market_scope(),
                        },
                    },
                    "provider_rating": {},
                    "token_impacts": [],
                    "content_class": "regulation",
                    "content_tags": ["sec"],
                    "content_classification": {"status": "classified"},
                    "agent_brief": {
                        "status": "ready",
                        "direction": "bullish",
                        "decision_class": "driver",
                    },
                    "source": _news_source_summary(),
                    "agent_status": "ready",
                    "agent_brief_computed_at_ms": 3_050,
                    "agent_admission_status": "eligible",
                    "agent_admission_reason": "ready_market_driver",
                    "agent_admission": _agent_admission(),
                    "agent_representative_news_item_id": "news-1",
                    "computed_at_ms": 3_100,
                    "projection_version": NEWS_PAGE_PROJECTION_VERSION,
                }
            ],
            "next_cursor": "3000:row-1",
        },
    }
    _assert_no_legacy_admission_fields(response.json()["data"]["items"][0])


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
            "q": "zec",
            "signal": None,
            "status": None,
        }
    ]
    data = response.json()["data"]
    assert [row["row_id"] for row in data["items"]] == ["row-1", "row-2"]
    assert data["next_cursor"] is None


@pytest.mark.parametrize("field_name", ("source_domain", "content_tags", "content_classification"))
def test_news_list_fails_closed_when_current_row_field_is_missing(field_name: str) -> None:
    news = FakeNewsRepository()
    news.rows[0].pop(field_name)
    app = _app(news)

    with TestClient(app) as client, pytest.raises(ValidationError, match=field_name):
        client.get("/api/news", headers={"Authorization": "Bearer secret"})


@pytest.mark.parametrize(
    "retired_alias",
    ("provider_type", "source_role", "trust_tier", "coverage_tags", "source_quality_status"),
)
def test_news_list_fails_closed_on_retired_top_level_source_alias(retired_alias: str) -> None:
    news = FakeNewsRepository()
    news.rows[0][retired_alias] = "legacy"
    app = _app(news)

    with TestClient(app) as client, pytest.raises(ValidationError, match=retired_alias):
        client.get("/api/news", headers={"Authorization": "Bearer secret"})


def test_news_list_fails_closed_when_nested_source_contract_is_incomplete() -> None:
    news = FakeNewsRepository()
    source = news.rows[0]["source"]
    assert isinstance(source, dict)
    source.pop("source_quality_status")
    app = _app(news)

    with TestClient(app) as client, pytest.raises(ValidationError, match="source_quality_status"):
        client.get("/api/news", headers={"Authorization": "Bearer secret"})


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
            "q": "zec",
            "signal": None,
            "status": None,
        },
        {
            "cursor": "9995:row-5",
            "limit": 6,
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
        "q": None,
        "signal": None,
        "status": None,
    }


def test_news_api_rejects_retired_signal_alias_without_postgres() -> None:
    news = FakeNewsRepository()
    app = _app(news)

    with TestClient(app) as client:
        response = client.get(
            "/api/news",
            params={"signal": "long"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "invalid_news_signal"}
    assert news.calls == []


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


@pytest.mark.parametrize(
    ("provider_health", "error"),
    [
        (None, "news_source_status_provider_health_required"),
        ("degraded", "news_source_status_provider_health_required"),
        ({}, "news_source_status_provider_health_status_required"),
        ({"status": " "}, "news_source_status_provider_health_status_required"),
    ],
)
def test_news_api_source_hygiene_requires_projected_provider_health_without_quality_status_fallback(
    provider_health: object,
    error: str,
) -> None:
    news = FakeNewsRepository()
    row: dict[str, object] = {
        "source_id": "legacy-health",
        "provider_type": "rss",
        "coverage_tags": ["crypto_market"],
        "enabled": True,
        "source_quality_status": "degraded",
    }
    if provider_health is not None:
        row["provider_health"] = provider_health
    news.source_status_rows = [row]
    app = _app(news)

    with TestClient(app) as client, pytest.raises(ValueError, match=error):
        client.get("/api/news/sources/status", headers={"Authorization": "Bearer secret"})


@pytest.mark.parametrize(
    ("row_patch", "error"),
    [
        ({"provider_type": None}, "news_source_status_provider_type_required"),
        ({"provider_type": " "}, "news_source_status_provider_type_required"),
        ({"coverage_tags": None}, "news_source_status_coverage_tags_required"),
        ({"coverage_tags": "crypto_market"}, "news_source_status_coverage_tags_required"),
        ({"coverage_tags": ["crypto_market", {"tag": "macro"}]}, "news_source_status_coverage_tags_required"),
    ],
)
def test_news_api_source_status_requires_projected_provider_type_and_coverage_tags(
    row_patch: dict[str, object],
    error: str,
) -> None:
    news = FakeNewsRepository()
    row: dict[str, object] = {
        "source_id": "projected-source",
        "provider_type": "rss",
        "coverage_tags": ["crypto_market"],
        "enabled": True,
        "provider_health": {"status": "healthy"},
    }
    row.update(row_patch)
    news.source_status_rows = [row]
    app = _app(news)

    with TestClient(app) as client, pytest.raises(ValueError, match=error):
        client.get("/api/news/sources/status", headers={"Authorization": "Bearer secret"})


def test_news_item_detail_hides_retired_brief_fields() -> None:
    news = FakeNewsRepository()
    news.item_detail = _news_detail()
    news.item_detail.update(
        {
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
            "signal": _news_signal(),
            "agent_admission_status": "eligible",
            "agent_admission_reason": "ready_market_driver",
            "agent_admission": _agent_admission(),
            "agent_representative_news_item_id": "news-1",
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
                "research_todos_zh": ["retired"],
                "confidence": 0.9,
                "prompt_version": "news-item-brief-v2",
                "schema_version": NEWS_STORY_BRIEF_SCHEMA_VERSION,
                "validator_version": NEWS_STORY_BRIEF_VALIDATOR_VERSION,
                "computed_at_ms": 123,
            },
        }
    )
    app = _app(news)

    with TestClient(app) as client:
        response = client.get("/api/news/items/news-1", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    agent_brief = response.json()["data"]["agent_brief"]
    assert agent_brief == {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "computed_at_ms": 123,
    }
    assert "summary_zh" not in agent_brief
    assert "retrieval_notes_zh" not in agent_brief
    assert "source_consensus_zh" not in agent_brief
    assert "confirmation_state" not in agent_brief
    assert "novelty_status" not in agent_brief
    assert "used_tool_call_ids" not in agent_brief
    assert "impact_zh" not in agent_brief
    assert "watch_items_zh" not in agent_brief
    assert "research_todos_zh" not in agent_brief
    assert "confidence" not in agent_brief
    assert "prompt_version" not in agent_brief
    assert "schema_version" not in agent_brief
    assert "validator_version" not in agent_brief
    data = response.json()["data"]
    assert data["representative_news_item_id"] == "news-1"
    assert data["story_key"] == "news-story:subject:btc-detail:t412000"
    assert data["story"]["member_count"] == 1
    assert data["signal"]["alert_eligibility"]["market_scope"] == _market_scope()
    assert "market_scope" not in data
    assert data["agent_admission_status"] == "eligible"
    assert data["agent_admission_reason"] == "ready_market_driver"
    assert data["agent_admission"] == _agent_admission()
    assert data["agent_representative_news_item_id"] == "news-1"
    _assert_no_legacy_admission_fields(data)


@pytest.mark.parametrize("field_name", ("provider_item", "content_tags", "source"))
def test_news_item_detail_fails_closed_when_required_shape_is_missing(field_name: str) -> None:
    news = FakeNewsRepository()
    news.item_detail = _news_detail()
    news.item_detail.pop(field_name)
    app = _app(news)

    with TestClient(app) as client, pytest.raises(ValidationError, match=field_name):
        client.get("/api/news/items/news-1", headers={"Authorization": "Bearer secret"})


def test_news_item_detail_fails_closed_on_list_only_or_retired_alias() -> None:
    news = FakeNewsRepository()
    news.item_detail = _news_detail()
    news.item_detail["headline"] = "legacy list alias"
    app = _app(news)

    with TestClient(app) as client, pytest.raises(ValidationError, match="headline"):
        client.get("/api/news/items/news-1", headers={"Authorization": "Bearer secret"})


def test_news_public_agent_brief_requires_status_without_pending_default() -> None:
    with pytest.raises(ValueError, match="news_public_agent_brief_status_required"):
        _public_agent_brief_payload({"summary_zh": "Projected story current without status."})


@pytest.mark.parametrize("field_name", ["direction", "decision_class"])
def test_news_public_ready_agent_brief_requires_signal_fields_without_projection_repair(field_name: str) -> None:
    payload = {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "summary_zh": "Projected ready row.",
        "brief_json": {
            "direction": "bullish",
            "decision_class": "driver",
            "summary_zh": "Nested fields must not repair ready public fields.",
        },
    }
    payload.pop(field_name)

    with pytest.raises(ValueError, match=f"news_public_agent_brief_{field_name}_required"):
        _public_agent_brief_payload(payload)


def test_news_public_agent_brief_ignores_present_brief_json_without_scalar_repair() -> None:
    assert _public_agent_brief_payload(
        {
            "status": "ready",
            "direction": "bullish",
            "decision_class": "driver",
            "brief_json": {
                "summary_zh": "Nested summary must not repair public payload.",
                "data_gaps": [{"kind": "missing"}],
            },
        }
    ) == {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
    }


def test_news_public_agent_brief_rejects_malformed_scalar_list_fields() -> None:
    with pytest.raises(ValueError, match="news_public_agent_brief_data_gaps_required"):
        _public_agent_brief_payload(
            {
                "status": "ready",
                "direction": "bullish",
                "decision_class": "driver",
                "data_gaps": {"kind": "missing"},
            }
        )


@pytest.mark.parametrize("field_name", ["label", "symbol", "name", "entity_type", "reason_zh"])
def test_news_public_agent_brief_rejects_malformed_affected_entity_text_fields(field_name: str) -> None:
    payload = {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "affected_entities": [
            {
                "label": "BTC",
                "symbol": "BTC",
                field_name: 123,
            }
        ],
    }

    with pytest.raises(ValueError, match=f"news_public_agent_brief_affected_entities_{field_name}_required"):
        _public_agent_brief_payload(payload)


def test_news_public_agent_brief_rejects_malformed_affected_entity_evidence_refs() -> None:
    payload = {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "affected_entities": [{"symbol": "BTC", "evidence_refs": ["news:item", 123]}],
    }

    with pytest.raises(ValueError, match="news_public_agent_brief_affected_entities_evidence_refs_required"):
        _public_agent_brief_payload(payload)


@pytest.mark.parametrize("field_name", ["title_zh", "summary_zh", "market_read_zh", "event_type"])
def test_news_public_agent_brief_rejects_malformed_optional_text_fields(field_name: str) -> None:
    payload = {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        field_name: 123,
    }

    with pytest.raises(ValueError, match=f"news_public_agent_brief_{field_name}_required"):
        _public_agent_brief_payload(payload)


@pytest.mark.parametrize("field_name", ["bull_view", "bear_view"])
def test_news_public_agent_brief_rejects_malformed_optional_mapping_fields(field_name: str) -> None:
    payload = {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        field_name: ["bad"],
    }

    with pytest.raises(ValueError, match=f"news_public_agent_brief_{field_name}_required"):
        _public_agent_brief_payload(payload)


@pytest.mark.parametrize("field_name", ["computed_at_ms", "data_gap_count"])
def test_news_public_agent_brief_rejects_malformed_optional_nonnegative_int_fields(field_name: str) -> None:
    payload = {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        field_name: True,
    }

    with pytest.raises(ValueError, match=f"news_public_agent_brief_{field_name}_required"):
        _public_agent_brief_payload(payload)


def test_news_item_detail_hides_agent_brief_runtime_audit_fields() -> None:
    news = FakeNewsRepository()
    news.item_detail = _news_detail()
    news.item_detail.update(
        {
            "news_item_id": "news-1",
            "agent_brief": {
                "prompt_version": NEWS_STORY_BRIEF_PROMPT_VERSION,
                "schema_version": NEWS_STORY_BRIEF_SCHEMA_VERSION,
                "validator_version": NEWS_STORY_BRIEF_VALIDATOR_VERSION,
                "guardrail_version": NEWS_STORY_BRIEF_GUARDRAIL_VERSION,
                "status": "ready",
                "direction": "bullish",
                "decision_class": "driver",
                "summary_zh": "当前简报",
                "market_read_zh": "市场解读",
                "bull_view": {"strength": "strong", "thesis_zh": "多头", "evidence_refs": []},
                "bear_view": {"strength": "weak", "thesis_zh": "空头", "evidence_refs": []},
                "data_gaps": [],
                "evidence_refs": ["news:item"],
                "agent_run_id": "run-news-1",
                "artifact_version_hash": "artifact-hash",
                "input_hash": "input-hash",
                "output_hash": "output-hash",
                "brief_json": {
                    "summary_zh": "当前简报",
                    "market_read_zh": "市场解读",
                    "bull_view": {"strength": "strong", "thesis_zh": "多头", "evidence_refs": []},
                    "bear_view": {"strength": "weak", "thesis_zh": "空头", "evidence_refs": []},
                    "data_gaps": [],
                    "evidence_refs": ["news:item"],
                    "research_todos_zh": ["retired"],
                },
            },
        }
    )
    app = _app(news)

    with TestClient(app) as client:
        response = client.get("/api/news/items/news-1", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["agent_brief"] == {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "summary_zh": "当前简报",
        "market_read_zh": "市场解读",
        "bull_view": {"strength": "strong", "thesis_zh": "多头", "evidence_refs": []},
        "bear_view": {"strength": "weak", "thesis_zh": "空头", "evidence_refs": []},
        "data_gap_count": 0,
        "data_gaps": [],
        "evidence_refs": ["news:item"],
    }
    for key in (
        "agent_run_id",
        "artifact_version_hash",
        "input_hash",
        "output_hash",
        "prompt_version",
        "schema_version",
        "validator_version",
        "brief_json",
        "research_todos_zh",
    ):
        assert key not in data["agent_brief"]


def test_news_openapi_schema_exposes_one_nested_current_contract() -> None:
    app = _app(FakeNewsRepository())

    schema = app.openapi()
    serialized = str(schema)
    schemas = schema["components"]["schemas"]
    row_props = schemas["NewsRow"]["properties"]
    detail_props = schemas["NewsObjectData"]["properties"]
    source_props = schemas["NewsSourceSummary"]["properties"]
    eligibility_props = schemas["NewsAlertEligibility"]["properties"]
    provider_rating_props = schemas["NewsProviderRating"]["properties"]
    signal_props = schemas["NewsSignalEnvelope"]["properties"]
    agent_signal_props = schemas["NewsAgentSignal"]["properties"]
    signal_summary_props = schemas["NewsSignalSummary"]["properties"]
    token_lane_props = schemas["NewsTokenLane"]["properties"]
    fact_lane_props = schemas["NewsFactLane"]["properties"]
    agent_brief_props = schemas["NewsAgentBrief"]["properties"]
    news_query_params = {param["name"] for param in schema["paths"]["/api/news"]["get"]["parameters"]}

    assert {"agent_admission", "agent_admission_status", "provider_rating"} <= set(row_props)
    assert {"agent_admission", "agent_admission_status", "provider_rating"} <= set(detail_props)
    assert schemas["NewsRow"]["additionalProperties"] is False
    assert schemas["NewsObjectData"]["additionalProperties"] is False
    assert schemas["NewsData"]["additionalProperties"] is False
    assert set(schemas["NewsData"]["required"]) == {"items", "next_cursor"}
    assert schemas["NewsSourceSummary"]["additionalProperties"] is False
    assert (
        set(schemas["NewsSourceSummary"]["required"])
        == set(source_props)
        == {
            "source_id",
            "source_name",
            "source_domain",
            "provider_type",
            "source_role",
            "trust_tier",
            "coverage_tags",
            "source_quality_status",
        }
    )
    assert {"source_domain", "source", "content_tags", "content_classification"} <= set(schemas["NewsRow"]["required"])
    for retired_alias in ("provider_type", "source_role", "trust_tier", "coverage_tags", "source_quality_status"):
        assert retired_alias not in row_props
    assert "market_scope" not in row_props
    assert "market_scope" not in detail_props
    assert "headline" not in detail_props
    assert "row_id" not in detail_props
    assert {"title", "provider_item", "fetch_run", "observation_edges", "fact_candidates"} <= set(
        schemas["NewsObjectData"]["required"]
    )
    assert {"provider", "status", "direction", "signal", "score", "grade", "method"} <= set(provider_rating_props)
    assert "market_scope" in eligibility_props
    assert "agent_admission_status" not in eligibility_props
    assert "agent_admission_reason" not in eligibility_props
    assert schemas["NewsAlertEligibility"]["additionalProperties"] is False
    assert schemas["NewsSignalEnvelope"]["additionalProperties"] is False
    assert set(schemas["NewsSignalEnvelope"]["required"]) == {
        "display_signal",
        "agent_signal",
        "alert_eligibility",
    }
    assert {"source", "status", "direction"} <= set(schemas["NewsSignalSummary"]["required"])
    assert "status" in agent_signal_props
    assert "status" in schemas["NewsAgentSignal"]["required"]
    assert "lane" in schemas["NewsTokenLane"]["required"]
    assert "status" in fact_lane_props
    assert "status" in schemas["NewsFactLane"]["required"]
    assert "status" in schemas["NewsAgentBrief"]["required"]
    assert {"signal", "token_impacts", "token_lanes", "fact_lanes", "agent_brief"} <= set(
        schemas["NewsRow"]["required"]
    )
    assert "provider_signal" not in detail_props
    assert "provider_token_impacts" not in detail_props
    assert "provider_signal" not in signal_props
    assert "score" not in signal_summary_props
    assert "grade" not in signal_summary_props
    assert "min_score" not in news_query_params
    assert "provider_score" not in eligibility_props
    assert "provider_score" not in token_lane_props
    assert "provider_signal" not in token_lane_props
    assert "agent_run" not in detail_props
    for field in (
        "agent_run_id",
        "artifact_version_hash",
        "input_hash",
        "output_hash",
        "brief_json",
        "research_todos_zh",
    ):
        assert field not in agent_brief_props
    assert "market_scope" in serialized
    assert "agent_admission" in serialized
    assert _legacy_admission_prefix() not in serialized


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
        q: str | None = None,
    ):
        self.calls.append(
            {
                "cursor": cursor,
                "limit": limit,
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
        item_detail = (
            dict(self.item_detail) if self.item_detail is not None else _news_detail(news_item_id=news_item_id)
        )
        item_detail["agent_brief"] = _public_agent_brief_payload(item_detail.get("agent_brief"))
        return item_detail

    def get_news_fact_detail(self, *, fact_candidate_id: str):
        return {"fact_candidate_id": fact_candidate_id}

    def list_source_status(self):
        return self.source_status_rows


class FakeRepositoryContext:
    def __init__(self, news: FakeNewsRepository) -> None:
        self.news_pages = news
        self.news_sources = news

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
        "duplicate_count": 1,
        "source_ids": ["opennews-realtime"],
        "source_domains": ["example.com"],
        "token_lanes": [{"lane": "resolved", "symbol": "BTC"}],
        "fact_lanes": [],
        "signal": {
            "display_signal": {
                "source": "agent",
                "status": "ready",
                "direction": "bullish",
                "label_zh": "利好",
                "title_zh": "AI 标题：SOL ETF approved",
                "summary_zh": "Agent summary.",
                "method": "news_story_brief",
            },
            "agent_signal": {
                "status": "ready",
                "direction": "bullish",
                "decision_class": "driver",
            },
            "alert_eligibility": {
                "in_app_eligible": True,
                "external_push_ready": False,
                "agent_status": "ready",
                "decision_class": "driver",
                "market_scope": _market_scope(),
            },
        },
        "provider_rating": {},
        "token_impacts": [],
        "content_class": "regulation",
        "content_tags": ["sec"],
        "content_classification": {"status": "classified"},
        "agent_brief": {
            "status": "ready",
            "direction": "bullish",
            "decision_class": "driver",
        },
        "source": _news_source_summary(),
        "agent_status": "ready",
        "agent_brief_computed_at_ms": 3_050,
        "agent_admission_status": "eligible",
        "agent_admission_reason": "ready_market_driver",
        "agent_admission": _agent_admission(),
        "agent_representative_news_item_id": "news-1",
        "computed_at_ms": 3_100,
        "projection_version": NEWS_PAGE_PROJECTION_VERSION,
    }


def _news_source_summary() -> dict[str, object]:
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


def _news_detail(*, news_item_id: str = "news-1") -> dict[str, object]:
    return {
        "news_item_id": news_item_id,
        "source_id": "opennews-realtime",
        "source_domain": "example.com",
        "canonical_url": "https://example.com/story",
        "title": "SOL ETF approved",
        "summary": "Issuer confirms launch.",
        "body_text": "Issuer confirms the SOL ETF launch.",
        "language": "en",
        "published_at_ms": 3_000,
        "fetched_at_ms": 3_010,
        "lifecycle_status": "raw",
        "content_class": "regulation",
        "processed_at_ms": None,
        "processing_error": None,
        "created_at_ms": 3_020,
        "updated_at_ms": 3_030,
        "duplicate_observation_count": 1,
        "representative_news_item_id": news_item_id,
        "story_key": "news-story:subject:btc-detail:t412000",
        "story": {
            "story_key": "news-story:subject:btc-detail:t412000",
            "representative_news_item_id": news_item_id,
            "member_news_item_ids": [news_item_id],
            "member_count": 1,
            "source_domains": ["example.com"],
        },
        "agent_admission_status": "eligible",
        "agent_admission_reason": "ready_market_driver",
        "agent_admission": _agent_admission(),
        "agent_representative_news_item_id": news_item_id,
        "agent_admission_computed_at_ms": 3_040,
        "content_tags": ["sec"],
        "content_classification": {"status": "classified"},
        "signal": _news_signal(),
        "provider_rating": {},
        "token_impacts": [],
        "token_lanes": [],
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
        "agent_brief": {"status": "ready", "direction": "bullish", "decision_class": "driver"},
        "observation_edges": [],
        "provider_observations": [],
        "entities": [],
        "token_mentions": [],
        "fact_candidates": [],
    }


def _market_scope() -> dict[str, object]:
    return {
        "scope": ["crypto"],
        "primary": "crypto",
        "status": "classified",
        "reason": "market_scope_classified",
        "basis": {"subject": "sol_etf"},
        "version": NEWS_MARKET_SCOPE_VERSION,
    }


def _news_signal() -> dict[str, object]:
    return {
        "display_signal": {
            "source": "agent",
            "status": "ready",
            "direction": "bullish",
        },
        "agent_signal": {
            "status": "ready",
            "direction": "bullish",
            "decision_class": "driver",
        },
        "alert_eligibility": {
            "in_app_eligible": True,
            "external_push_ready": False,
            "agent_status": "ready",
            "decision_class": "driver",
            "market_scope": _market_scope(),
        },
    }


def _agent_admission() -> dict[str, object]:
    return {
        "eligible": True,
        "status": "eligible",
        "reason": "ready_market_driver",
        "representative_news_item_id": "news-1",
        "basis": {"subject": "sol_etf"},
        "version": NEWS_ITEM_AGENT_ADMISSION_VERSION,
    }


def _legacy_admission_prefix() -> str:
    return "analysis" + "_admission"


def _assert_no_legacy_admission_fields(payload: dict[str, object]) -> None:
    legacy_prefix = _legacy_admission_prefix()
    assert legacy_prefix not in payload
    assert f"{legacy_prefix}_status" not in payload
    assert f"{legacy_prefix}_reason" not in payload


def _app(news: FakeNewsRepository) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(lambda _: {"ok": True}))
    app.state.service = FakeRuntime(news)
    return app
