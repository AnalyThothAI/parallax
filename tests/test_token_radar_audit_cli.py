from __future__ import annotations

from gmgn_twitter_intel.cli import _audit_token_radar_rows
from gmgn_twitter_intel.pipeline.token_radar_contract import TOKEN_RADAR_PROJECTION_VERSION


def test_audit_token_radar_rows_rejects_legacy_price_health():
    audit = _audit_token_radar_rows(
        [
            {
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "score_json": {"heat": block(), "price_health": block(), "opportunity": block()},
                "attention_json": attention(),
                "decision": "driver",
                "market_json": {"market_observation_status": "ready"},
            }
        ],
        now_ms=1_700_000_000_000,
        source_current_window_rows=1,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_price_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is False
    assert any(item["code"] == "legacy_price_health" for item in audit["violations"])


def test_audit_token_radar_rows_accepts_v6_auditable_scores():
    score = {
        "heat": block(data_health=baseline_health()),
        "quality": block(),
        "propagation": block(),
        "tradeability": block(),
        "timing": block(),
        "opportunity": {**block(), "components": {"tradeability": 80}},
    }
    audit = _audit_token_radar_rows(
        [
            {
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "score_json": score,
                "attention_json": attention(),
                "decision": "watch",
                "market_json": {"market_observation_status": "ready"},
            }
        ],
        now_ms=1_700_000_000_000,
        source_current_window_rows=1,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_price_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is True
    assert audit["social_lag_ms"] == 1_000
    assert audit["market_lag_ms"] == 500


def test_audit_token_radar_rows_rejects_empty_v6_projection_when_sources_exist():
    audit = _audit_token_radar_rows(
        [],
        now_ms=1_700_000_000_000,
        source_current_window_rows=1,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_price_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is False
    assert any(item["code"] == "empty_projection_rows" for item in audit["violations"])


def test_audit_token_radar_rows_accepts_empty_projection_when_current_scope_is_empty():
    audit = _audit_token_radar_rows(
        [],
        now_ms=1_700_000_000_000,
        source_current_window_rows=0,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_price_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is True
    assert audit["source_current_window_rows"] == 0


def test_audit_token_radar_rows_rejects_missing_baseline_contract():
    score = {
        "heat": block(),
        "quality": block(),
        "propagation": block(),
        "tradeability": block(),
        "timing": block(),
        "opportunity": {**block(), "components": {"tradeability": 80}},
    }
    audit = _audit_token_radar_rows(
        [
            {
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "score_json": score,
                "attention_json": {"mentions_window": 2},
                "decision": "watch",
                "market_json": {"market_observation_status": "ready"},
            }
        ],
        now_ms=1_700_000_000_000,
        source_current_window_rows=1,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_price_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is False
    assert any(item["code"] == "missing_attention_fields" for item in audit["violations"])
    assert any(item["code"] == "missing_heat_data_health_fields" for item in audit["violations"])


def block(*, data_health: dict | None = None):
    return {
        "score": 80,
        "score_version": "social_opportunity_v3",
        "reasons": ["ready"],
        "risks": [],
        "contributions": [{"feature": "x", "value": 1, "reason": "ready"}],
        "risk_caps": [],
        "data_health": data_health or {"source": "test"},
    }


def attention():
    return {
        "mentions_5m": 2,
        "mentions_1h": 4,
        "mentions_4h": 8,
        "mentions_24h": 12,
        "mentions_window": 4,
        "unique_authors": 3,
        "watched_mentions": 1,
        "latest_seen_ms": 1_700_000_000_000,
        "previous_mentions": 1,
        "mention_delta": 3,
        "mention_delta_pct": 3.0,
        "z_score": 3.0,
        "z_ewma": 2.8,
        "robust_z": 3.0,
        "new_burst_score": 0,
        "stream_share": 0.1,
        "baseline_version": "token_baseline_v2",
        "baseline_status": "ready",
        "baseline_sample_count": 6,
        "baseline_nonzero_sample_count": 6,
        "zero_slot_count": 0,
    }


def baseline_health():
    return {
        "baseline_ready": True,
        "baseline_status": "ready",
        "sample_count": 6,
        "nonzero_sample_count": 6,
        "zero_slot_count": 0,
        "baseline_version": "token_baseline_v2",
        "public_stream_coverage": True,
    }
