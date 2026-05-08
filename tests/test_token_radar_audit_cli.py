from __future__ import annotations

from gmgn_twitter_intel.cli import _audit_token_radar_rows
from gmgn_twitter_intel.pipeline.token_radar_contract import TOKEN_RADAR_PROJECTION_VERSION


def test_audit_token_radar_rows_rejects_legacy_price_health():
    audit = _audit_token_radar_rows(
        [
            {
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "score_json": {"heat": block(), "price_health": block(), "opportunity": block()},
                "decision": "driver",
                "market_json": {"market_observation_status": "ready"},
            }
        ],
        now_ms=1_700_000_000_000,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_price_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is False
    assert any(item["code"] == "legacy_price_health" for item in audit["violations"])


def test_audit_token_radar_rows_accepts_v5_auditable_scores():
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
                "decision": "watch",
                "market_json": {"market_observation_status": "ready"},
            }
        ],
        now_ms=1_700_000_000_000,
        source_max_resolution_ms=1_699_999_999_000,
        source_max_price_observed_at_ms=1_699_999_999_500,
    )

    assert audit["ok"] is True
    assert audit["social_lag_ms"] == 1_000
    assert audit["market_lag_ms"] == 500


def block():
    return {
        "score": 80,
        "score_version": "social_opportunity_v3",
        "reasons": ["ready"],
        "risks": [],
        "contributions": [{"feature": "x", "value": 1, "reason": "ready"}],
        "risk_caps": [],
    }
