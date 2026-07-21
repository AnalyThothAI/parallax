from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from parallax.app.surfaces.api import routes_events, routes_radar, routes_status
from parallax.app.surfaces.api.http import create_api_router
from parallax.app.surfaces.api.schemas import (
    NewsFactDetailData,
    NotificationItemData,
    NotificationSummary,
    ReadinessData,
    SearchData,
    StocksRadarData,
    WorkerStatusData,
)


def test_openapi_publishes_exact_macro_stocks_notifications_ops_and_worker_contracts() -> None:
    app = FastAPI()
    app.include_router(create_api_router(lambda _: {"ok": True}))

    @app.get("/_readiness-contract", response_model=ReadinessData)
    def readiness_contract() -> dict[str, object]:
        return {}

    schemas = app.openapi()["components"]["schemas"]

    _assert_exact_required(
        schemas["StocksRadarData"],
        {"window", "scope", "query", "rows", "health"},
    )
    _assert_exact_required(
        schemas["NotificationSummary"],
        {
            "subscriber_key",
            "unread_count",
            "high_unread_count",
            "critical_unread_count",
            "highest_unread_severity",
            "account_unread_counts",
        },
    )
    _assert_exact_required(schemas["NotificationsData"], {"items", "summary"})
    _assert_exact_required(schemas["NotificationItemData"], set(NotificationItemData.model_fields))
    _assert_exact_required(
        schemas["OpsDiagnosticsData"],
        {
            "schema_version",
            "generated_at_ms",
            "overall",
            "config",
            "database",
            "collector",
            "providers",
            "workers",
            "queues",
            "agent_execution",
            "domains",
            "suggested_checks",
        },
    )
    agent_execution_schema = schemas["OpsAgentExecutionData"]
    assert set(agent_execution_schema["properties"]) == {
        "status",
        "policy",
        "counters",
        "status_reason",
        "error",
    }
    assert set(agent_execution_schema["required"]) == {"status", "policy", "counters"}
    assert agent_execution_schema["additionalProperties"] is False
    assert "OpsAgentExecutionLaneData" not in schemas
    agent_policy_fields = {
        "lane",
        "model",
        "provider_family",
        "output_strategy",
        "schema_enforcement",
        "max_concurrency",
        "rpm_limit",
        "timeout_seconds",
    }
    agent_counter_fields = {
        "in_flight",
        "provider_running",
        "circuit_state",
        "circuit_open_until_ms",
        "capacity_denied_total",
        "circuit_open_total",
        "timeout_total",
        "last_denied_at_ms",
        "last_timeout_at_ms",
        "oldest_in_flight_age_ms",
    }
    _assert_exact_required(schemas["OpsAgentExecutionPolicyData"], agent_policy_fields)
    _assert_exact_required(schemas["OpsAgentExecutionCountersData"], agent_counter_fields)
    _assert_exact_required(
        schemas["AgentExecutionStatusData"],
        agent_policy_fields | agent_counter_fields,
    )
    _assert_exact_required(schemas["AgentExecutionUnavailableData"], {"status", "error"})
    _assert_exact_required(
        schemas["OpsQueueData"],
        {"schema_version", "queue_name", "status_filter", "counts_by_status", "summary", "items"},
    )
    _assert_exact_required(
        schemas["MacroData"],
        {
            "snapshot",
            "currentness",
            "panels",
            "indicators",
            "triggers",
            "data_gaps",
            "source_coverage",
            "features",
            "chain",
            "scenario",
            "scorecard",
        },
    )
    _assert_exact_required(
        schemas["MacroCurrentnessData"],
        {
            "publication_status",
            "publication_row_count",
            "publication_finished_at_ms",
            "facts_max_observed_at",
            "projection_lag_days",
            "projection_behind_facts",
        },
    )
    _assert_exact_required(
        schemas["MacroModuleChartData"],
        {
            "id",
            "kind",
            "title",
            "subtitle",
            "status",
            "status_label",
            "min_points",
            "missing_concept_keys",
            "series",
        },
    )
    _assert_exact_required(
        schemas["WorkerStatusData"],
        {
            "enabled",
            "running",
            "effective_status",
            "unavailable_reason",
            "last_started_at_ms",
            "last_finished_at_ms",
            "last_result",
            "last_error",
            "iteration_duration_p99_ms",
        },
    )
    _assert_exact_required(
        schemas["StatusData"],
        {
            "ok",
            "reasons",
            "handles",
            "store",
            "snapshot_gate",
            "db",
            "provider_states",
            "agent_execution",
            "news_provider_contract",
            "workers",
        },
    )
    _assert_exact_required(
        schemas["TokenRadarData"],
        {"window", "scope", "venue", "targets", "attention", "projection"},
    )
    _assert_exact_required(
        schemas["TokenRadarProjectionData"],
        {
            "status",
            "version",
            "source",
            "venue",
            "reason",
            "latest_attempt_status",
            "row_count",
            "source_rows",
            "source_max_received_at_ms",
            "source_frontier_ms",
            "computed_at_ms",
            "error",
            "anchor_coverage",
            "quality_status",
            "degraded_reasons",
            "unresolved",
        },
    )
    _assert_exact_required(
        schemas["LiveMarketData"],
        {
            "target_type",
            "target_id",
            "status",
            "price_usd",
            "price_quote",
            "quote_symbol",
            "price_basis",
            "market_cap_usd",
            "liquidity_usd",
            "holders",
            "volume_24h_usd",
            "open_interest_usd",
            "observed_at_ms",
            "received_at_ms",
            "age_ms",
            "provider",
        },
    )
    _assert_exact_required(schemas["BootstrapData"], {"ws_token", "handles", "replay_limit"})
    _assert_exact_required(
        schemas["ReadinessData"],
        {"ok", "reasons", "handles", "store", "db", "composition"},
    )
    _assert_exact_required(schemas["RecentData"], {"scope", "events", "items"})
    _assert_exact_required(schemas["SourceEventsByIdsData"], {"events", "not_found"})
    _assert_exact_required(
        schemas["SearchData"],
        {"query", "page", "target_candidates", "items"},
    )
    _assert_exact_required(
        schemas["SearchInspectData"],
        {"query", "resolver", "token_result", "topic_result", "ambiguous_result"},
    )
    _assert_exact_required(
        schemas["TokenCaseData"],
        {"target", "profile", "timeline", "posts", "narrative_admission", "market_live"},
    )
    _assert_exact_required(
        schemas["TargetPostsData"],
        {
            "query",
            "score_window",
            "total_count",
            "returned_count",
            "has_more",
            "next_cursor",
            "items",
        },
    )
    _assert_exact_required(
        schemas["TargetSocialTimelineData"],
        {
            "query",
            "summary",
            "market_candles",
            "stages",
            "buckets",
            "authors",
            "posts",
            "cascade",
            "returned_count",
            "has_more",
            "next_cursor",
        },
    )
    _assert_exact_required(
        schemas["NewsFactDetailData"],
        {
            "fact_candidate_id",
            "news_item_id",
            "event_type",
            "claim",
            "realis",
            "evidence_quote",
            "evidence_span_start",
            "evidence_span_end",
            "source_role",
            "required_slots_json",
            "affected_targets_json",
            "validation_status",
            "rejection_reasons_json",
            "extraction_method",
            "policy_version",
            "created_at_ms",
            "updated_at_ms",
            "headline",
            "canonical_url",
            "source_domain",
        },
    )
    _assert_exact_required(
        schemas["NewsSourceStatusData"],
        {"provider_capabilities", "source_hygiene", "sources"},
    )
    _assert_exact_required(
        schemas["WatchlistHandleTimelineData"],
        {"query", "items", "has_more", "next_cursor"},
    )
    _assert_exact_required(
        schemas["WatchlistTimelineItem"],
        {
            "event_id",
            "received_at_ms",
            "author_handle",
            "action",
            "text_clean",
            "canonical_url",
            "cashtags",
            "hashtags",
            "mentions",
            "event",
            "token_resolutions",
        },
    )


def test_exact_public_models_fail_closed_on_missing_required_payload() -> None:
    with pytest.raises(ValidationError, match="health"):
        StocksRadarData.model_validate({"window": "1h", "scope": "all", "query": {}, "rows": []})

    with pytest.raises(ValidationError, match="account_unread_counts"):
        NotificationSummary.model_validate(
            {
                "subscriber_key": "local",
                "unread_count": 0,
                "high_unread_count": 0,
                "critical_unread_count": 0,
                "highest_unread_severity": None,
            }
        )

    with pytest.raises(ValidationError, match="items"):
        SearchData.model_validate(
            {
                "query": {},
                "page": {"returned_count": 0, "has_more": False, "next_cursor": None},
                "target_candidates": [],
            }
        )

    with pytest.raises(ValidationError, match=r"confidence|extra_forbidden"):
        NewsFactDetailData.model_validate(
            {
                "fact_candidate_id": "fact-1",
                "news_item_id": "news-1",
                "event_type": "listing",
                "claim": "listed",
                "realis": "actual",
                "evidence_quote": "listed",
                "evidence_span_start": 0,
                "evidence_span_end": 6,
                "source_role": "primary",
                "required_slots_json": {},
                "affected_targets_json": [],
                "validation_status": "accepted",
                "rejection_reasons_json": [],
                "extraction_method": "deterministic",
                "policy_version": "v1",
                "created_at_ms": 1,
                "updated_at_ms": 1,
                "headline": "Listed",
                "canonical_url": "https://example.test/listed",
                "source_domain": "example.test",
                "confidence": 0.9,
            }
        )


def test_changed_read_routes_validate_success_payloads_before_json_response(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = SimpleNamespace()
    monkeypatch.setattr(routes_radar, "_authenticated_runtime", lambda _request: runtime)
    monkeypatch.setattr(
        routes_radar,
        "_token_radar_data",
        lambda *_args, **_kwargs: {"targets": [], "attention": []},
    )
    with pytest.raises(ValidationError, match="projection"):
        routes_radar.token_radar(
            SimpleNamespace(),
            window="1h",
            limit=20,
            scope="all",
            venue="all",
        )

    monkeypatch.setattr(routes_events, "_authenticated_runtime", lambda _request: runtime)
    monkeypatch.setattr(routes_events, "_recent_data", lambda *_args, **_kwargs: {"events": []})
    with pytest.raises(ValidationError, match="items"):
        routes_events.recent(
            SimpleNamespace(),
            limit=20,
            handles="",
            ca="",
            chain="",
            symbol="",
            scope="matched",
        )

    app = FastAPI()
    app.include_router(routes_status.create_router(lambda _runtime: {"ok": True}))
    monkeypatch.setattr(routes_status, "_authenticated_runtime", lambda _request: runtime)

    with TestClient(app) as client, pytest.raises(ValidationError, match="reasons"):
        client.get("/status")

    with pytest.raises(ValidationError, match="last_error"):
        WorkerStatusData.model_validate(
            {
                "enabled": True,
                "running": False,
                "effective_status": "stopped",
            }
        )


def _assert_exact_required(schema: dict[str, object], fields: set[str]) -> None:
    assert set(schema["properties"]) == fields
    assert set(schema["required"]) == fields
    assert schema["additionalProperties"] is False
