from __future__ import annotations

from parallax.app.surfaces.cli.commands import ops as cli_ops
from parallax.app.surfaces.cli.commands.ops import _audit_token_radar_current_rows
from parallax.domains.token_intel.interfaces import (
    TOKEN_RADAR_FACTOR_FAMILIES,
    TOKEN_RADAR_PROJECTION_VERSION,
)
from parallax.domains.token_intel.scoring.factor_snapshot import TOKEN_FACTOR_SNAPSHOT_VERSION


def test_audit_token_radar_current_rows_rejects_missing_factor_snapshot():
    audit = _audit_token_radar_current_rows(
        [
            {
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "decision": "driver",
            }
        ],
        now_ms=1_700_000_000_000,
        source_current_window_rows=1,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_market_tick_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is False
    assert any(item["code"] == "missing_factor_snapshot" for item in audit["violations"])


def test_audit_token_radar_current_rows_accepts_factor_snapshot_contract():
    audit = _audit_token_radar_current_rows(
        [
            {
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
                "factor_snapshot_json": factor_snapshot(),
                "decision": "watch",
            }
        ],
        now_ms=1_700_000_000_000,
        source_current_window_rows=1,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_market_tick_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is True
    assert audit["social_lag_ms"] == 1_000
    assert audit["market_lag_ms"] == 500


def test_audit_token_radar_current_rows_rejects_empty_projection_when_sources_exist():
    audit = _audit_token_radar_current_rows(
        [],
        now_ms=1_700_000_000_000,
        source_current_window_rows=1,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_market_tick_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is False
    assert any(item["code"] == "empty_projection_rows" for item in audit["violations"])


def test_audit_token_radar_current_rows_accepts_empty_projection_when_current_scope_is_empty():
    audit = _audit_token_radar_current_rows(
        [],
        now_ms=1_700_000_000_000,
        source_current_window_rows=0,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_market_tick_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is True
    assert audit["source_current_window_rows"] == 0


def test_audit_token_radar_current_rows_rejects_missing_factor_family_contract():
    snapshot = factor_snapshot()
    del snapshot["families"]["social_heat"]
    audit = _audit_token_radar_current_rows(
        [
            {
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
                "factor_snapshot_json": snapshot,
                "decision": "watch",
            }
        ],
        now_ms=1_700_000_000_000,
        source_current_window_rows=1,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_market_tick_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is False
    assert any(item["code"] == "missing_factor_families" for item in audit["violations"])


def test_audit_token_radar_current_rows_rejects_extra_old_factor_family_contract():
    snapshot = factor_snapshot()
    snapshot["families"]["market_quality"] = family({"market_status": "fresh"})

    audit = _audit_token_radar_current_rows(
        [
            {
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
                "factor_snapshot_json": snapshot,
                "decision": "watch",
            }
        ],
        now_ms=1_700_000_000_000,
        source_current_window_rows=1,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_market_tick_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is False
    assert any(item["code"] == "extra_factor_families" for item in audit["violations"])


def test_audit_token_radar_current_rows_rejects_hard_gates_key():
    snapshot = factor_snapshot()
    snapshot["hard_gates"] = {"eligible_for_high_alert": True}

    audit = _audit_token_radar_current_rows(
        [
            {
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
                "factor_snapshot_json": snapshot,
                "decision": "watch",
            }
        ],
        now_ms=1_700_000_000_000,
        source_current_window_rows=1,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_market_tick_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is False
    assert any(item["code"] == "hard_gates_present" for item in audit["violations"])
    assert any(
        item["code"] == "invalid_factor_snapshot_contract" and "hard_gates" in item["error"]
        for item in audit["violations"]
    )


def test_audit_token_radar_current_rows_rejects_malformed_v3_contract():
    snapshot = factor_snapshot()
    snapshot["nested"] = {"volume_24h_usd": 123.45}

    audit = _audit_token_radar_current_rows(
        [
            {
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
                "factor_snapshot_json": snapshot,
                "decision": "watch",
            }
        ],
        now_ms=1_700_000_000_000,
        source_current_window_rows=1,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_market_tick_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is False
    assert any(
        item["code"] == "invalid_factor_snapshot_contract" and "nested" in item["error"] for item in audit["violations"]
    )


def test_audit_token_radar_current_rows_rejects_empty_v3_provenance():
    snapshot = factor_snapshot()
    snapshot["provenance"] = {}

    audit = _audit_token_radar_current_rows(
        [
            {
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
                "factor_snapshot_json": snapshot,
                "decision": "watch",
            }
        ],
        now_ms=1_700_000_000_000,
        source_current_window_rows=1,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_market_tick_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is False
    assert any(
        item["code"] == "invalid_factor_snapshot_contract" and "provenance.computed_at_ms" in item["error"]
        for item in audit["violations"]
    )


def test_audit_token_radar_current_rows_rejects_empty_v3_source_event_ids():
    snapshot = factor_snapshot()
    snapshot["provenance"]["source_event_ids"] = []

    audit = _audit_token_radar_current_rows(
        [
            {
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
                "factor_snapshot_json": snapshot,
                "decision": "watch",
            }
        ],
        now_ms=1_700_000_000_000,
        source_current_window_rows=1,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_market_tick_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is False
    assert any(
        item["code"] == "invalid_factor_snapshot_contract" and "provenance.source_event_ids" in item["error"]
        for item in audit["violations"]
    )


def test_audit_token_radar_current_rows_rejects_empty_v3_family_block():
    snapshot = factor_snapshot()
    snapshot["families"]["social_heat"] = {}

    audit = _audit_token_radar_current_rows(
        [
            {
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
                "factor_snapshot_json": snapshot,
                "decision": "watch",
            }
        ],
        now_ms=1_700_000_000_000,
        source_current_window_rows=1,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_market_tick_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is False
    assert any(
        item["code"] == "invalid_factor_snapshot_contract" and "families.social_heat.data_health" in item["error"]
        for item in audit["violations"]
    )


def test_audit_token_radar_current_rows_rejects_wrong_factor_version():
    audit = _audit_token_radar_current_rows(
        [
            {
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "factor_version": "token_factor_snapshot_v1",
                "factor_snapshot_json": factor_snapshot(),
                "decision": "watch",
            }
        ],
        now_ms=1_700_000_000_000,
        source_current_window_rows=1,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_market_tick_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is False
    assert any(item["code"] == "wrong_factor_version" for item in audit["violations"])


def test_audit_token_radar_current_rows_rejects_high_alert_when_gate_is_not_eligible():
    snapshot = factor_snapshot()
    snapshot["gates"]["eligible_for_high_alert"] = False
    snapshot["gates"]["blocked_reasons"] = ["market_stale"]
    snapshot["composite"]["recommended_decision"] = "high_alert"

    audit = _audit_token_radar_current_rows(
        [
            {
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
                "factor_snapshot_json": snapshot,
                "decision": "high_alert",
            }
        ],
        now_ms=1_700_000_000_000,
        source_current_window_rows=1,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_market_tick_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is False
    assert any(item["code"] == "high_alert_without_gate_eligibility" for item in audit["violations"])


def test_audit_token_radar_current_rows_uses_domain_factor_snapshot_version(monkeypatch):
    runtime_version = "token_factor_snapshot_runtime_test"
    monkeypatch.setattr(cli_ops, "TOKEN_FACTOR_SNAPSHOT_VERSION", runtime_version)
    snapshot = factor_snapshot()
    snapshot["schema_version"] = runtime_version

    audit = cli_ops._audit_token_radar_current_rows(
        [
            {
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "factor_version": runtime_version,
                "factor_snapshot_json": snapshot,
                "decision": "watch",
            }
        ],
        now_ms=1_700_000_000_000,
        source_current_window_rows=1,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_market_tick_observed_at_ms=1_699_999_999_500,
    )

    assert TOKEN_FACTOR_SNAPSHOT_VERSION == "token_factor_snapshot_v3_social_attention"
    assert audit["ok"] is False
    assert any(
        item["code"] == "invalid_factor_snapshot_contract" and "schema_version" in item["error"]
        for item in audit["violations"]
    )


def factor_snapshot():
    families = {
        "social_heat": family({"mentions_1h": 4, "unique_authors": 3}),
        "social_propagation": family({"duplicate_text_share": 0.0}),
        "semantic_catalyst": family({"direction_counts": {"bullish": 1}}),
        "timing_risk": family({"social_signal_start_ms": 1_700_000_000_000}),
    }
    return {
        "schema_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "subject": {"target_type": "Asset", "target_id": "asset:pepe", "symbol": "PEPE"},
        "market": {
            "event_anchor": market_observation("event_anchor"),
            "decision_latest": market_observation("decision_latest"),
            "readiness": {
                "anchor_status": "ready",
                "latest_status": "live",
                "dex_floor_status": "ready",
                "missing_fields": [],
                "stale_fields": [],
            },
        },
        "gates": {
            "eligible_for_high_alert": True,
            "max_decision": "high_alert",
            "blocked_reasons": [],
            "risk_reasons": [],
        },
        "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
        "families": families,
        "normalization": {"status": "ready", "cohort": {}, "factor_ranks": {}, "alpha_rank": None},
        "composite": {
            "family_scores": {family: families[family]["score"] for family in TOKEN_RADAR_FACTOR_FAMILIES},
            "rank_score": 55,
            "recommended_decision": "watch",
        },
        "provenance": {
            "source_event_ids": ["event-1"],
            "computed_at_ms": 1_700_000_000_000,
        },
    }


def family(facts: dict):
    return {
        "raw_score": 80,
        "score": 80,
        "weight": 0.25,
        "data_health": "ready",
        "facts": facts,
        "factors": {"test": {"score": 80, "data_health": "ready"}},
    }


def market_observation(source: str) -> dict:
    return {
        "target_type": "Asset",
        "target_id": "asset:pepe",
        "source": source,
        "provider": "okx",
        "pricefeed_id": None,
        "price_usd": 0.42,
        "price_quote": None,
        "quote_symbol": "USD",
        "price_basis": "usd",
        "market_cap_usd": 120_000,
        "liquidity_usd": 55_000,
        "holders": 800,
        "volume_24h_usd": None,
        "open_interest_usd": None,
        "observed_at_ms": 1_700_000_000_000,
        "received_at_ms": 1_700_000_000_000,
        "raw_payload_hash": None,
    }
