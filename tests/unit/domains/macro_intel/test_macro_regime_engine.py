from __future__ import annotations

from datetime import date, timedelta

import pytest

from parallax.domains.macro_intel._constants import (
    MACRO_CORE_CONCEPTS,
    MACRO_HISTORY_REQUIRED_CONCEPTS,
)
from parallax.domains.macro_intel.services.macro_regime_engine import (
    _credit_chain_node,
    _cross_asset_chain_node,
    _feature_has_required_history,
    _has_stale_required_features,
    _liquidity_chain_node,
    _scorecard,
    _snapshot_status,
    _volatility_chain_node,
    build_macro_view_snapshot,
)

NOW_MS = 1_779_000_000_000


def test_empty_observations_emit_degraded_snapshot() -> None:
    snapshot = build_macro_view_snapshot([], computed_at_ms=NOW_MS)

    assert snapshot["projection_version"] == "macro_regime_v4"
    assert snapshot["status"] == "missing"
    assert snapshot["regime"] == "data_gap"
    assert snapshot["overall_score"] is None
    assert set(snapshot["panels_json"]) == {"liquidity", "rates", "volatility", "credit", "cross_asset"}
    assert set(snapshot["chain_json"]) == {
        "liquidity",
        "rates",
        "fed_corridor",
        "volatility",
        "credit",
        "positioning",
        "cross_asset",
    }
    assert snapshot["features_json"] == {}
    assert snapshot["scenario_json"]["current_regime"] == "data_gap"
    assert snapshot["scorecard_json"]["projection_version"] == "macro_regime_v4"
    assert any(gap["code"] == "missing_liquidity_fed_assets" for gap in snapshot["data_gaps_json"])
    assert any(gap["code"] == "missing_liquidity_sofr" for gap in snapshot["data_gaps_json"])
    assert any(
        gap["code"] == "missing_liquidity_fed_assets" for gap in snapshot["panels_json"]["liquidity"]["data_gaps"]
    )
    assert any(
        gap["code"] == "missing_liquidity_fed_assets" for gap in snapshot["chain_json"]["liquidity"]["data_gaps"]
    )
    assert snapshot["source_coverage_json"] == {
        "observed_concept_count": 0,
        "required_concept_count": len(MACRO_HISTORY_REQUIRED_CONCEPTS),
        "latest_coverage_ratio": 0.0,
        "history_coverage_ratio": 0.0,
        "required_history_concept_count": len(MACRO_HISTORY_REQUIRED_CONCEPTS),
        "history_ready_concept_count": 0,
        "concepts_below_min_history": list(MACRO_HISTORY_REQUIRED_CONCEPTS),
        "latest_observed_at": None,
    }


def test_representative_observations_emit_scores_and_triggers() -> None:
    snapshot = build_macro_view_snapshot(
        [
            _obs("liquidity:fed_assets", 7_500_000, unit="millions_usd", series_key="fred:WALCL"),
            _obs("liquidity:on_rrp", 100, unit="billions_usd", series_key="fred:RRPONTSYD"),
            _obs(
                "liquidity:tga",
                900_000,
                unit="millions_usd",
                series_key="treasury_fiscal:operating_cash_balance",
            ),
            _obs("liquidity:sofr", 4.55, unit="percent", series_key="nyfed:SOFR"),
            _obs("fed:iorb", 4.40, unit="percent", series_key="fred:IORB"),
            _obs("rates:dgs2", 3.90, unit="percent", series_key="fred:DGS2"),
            _obs("rates:dgs10", 4.70, unit="percent", series_key="fred:DGS10"),
            _obs("vol:vix", 24.0, unit="index", series_key="fred:VIXCLS"),
            _obs("credit:hy_oas", 5.80, unit="percent", series_key="fred:BAMLH0A0HYM2"),
            _obs("credit:ig_oas", 1.50, unit="percent", series_key="fred:BAMLC0A0CM"),
        ],
        computed_at_ms=NOW_MS,
    )

    assert snapshot["status"] == "partial"
    assert snapshot["regime"] == "funding_stress"
    assert snapshot["overall_score"] >= 6.0
    assert snapshot["features_json"]["rates:dgs10"]["latest"]["value"] == 4.7
    assert snapshot["chain_json"]["liquidity"]["regime"] == "funding_stress"
    assert snapshot["chain_json"]["fed_corridor"]["regime"] in {"corridor_pressure", "data_gap"}
    assert snapshot["scenario_json"]["current_regime"] in {"funding_stress", "tightening"}
    assert snapshot["scenario_json"]["confirmations"]
    assert snapshot["scenario_json"]["watch_triggers"]
    assert snapshot["scorecard_json"]["observed_concept_count"] == 10
    assert snapshot["panels_json"]["liquidity"]["regime"] == "funding_stress"
    assert snapshot["panels_json"]["rates"]["regime"] == "term_premium_pressure"
    assert snapshot["panels_json"]["volatility"]["regime"] == "near_term_stress"
    assert snapshot["panels_json"]["credit"]["regime"] == "low_quality_stress"
    assert snapshot["indicators_json"]["net_liquidity_usd_millions"]["value"] == 6_500_000.0
    trigger_codes = {trigger["code"] for trigger in snapshot["triggers_json"]}
    assert {
        "sofr_above_iorb",
        "rrp_buffer_low",
        "tga_high",
        "vix_elevated",
        "hy_oas_stress",
    }.issubset(trigger_codes)
    assert {
        "code": "sofr_above_iorb",
        "label": "SOFR 高于 IORB",
        "description": "SOFR is above IORB",
        "node": "funding",
        "kind": "trigger",
        "indicator_keys": ["sofr_iorb_spread_bps"],
        "value": 15.0,
    } in snapshot["triggers_json"]
    assert any(gap["code"] == "missing_asset_spx" for gap in snapshot["data_gaps_json"])
    assert snapshot["source_coverage_json"]["observed_concept_count"] == 10


def test_regime_v4_emits_chain_and_scenario_for_funding_stress() -> None:
    snapshot = build_macro_view_snapshot(
        [
            _obs("liquidity:fed_assets", 7_500_000, unit="millions_usd", series_key="fred:WALCL"),
            _obs("liquidity:on_rrp", 100, unit="billions_usd", series_key="fred:RRPONTSYD"),
            _obs(
                "liquidity:tga",
                900_000,
                unit="millions_usd",
                series_key="treasury_fiscal:operating_cash_balance",
            ),
            _obs("liquidity:sofr", 4.55, unit="percent", series_key="nyfed:SOFR"),
            _obs("fed:iorb", 4.40, unit="percent", series_key="fred:IORB"),
            _obs("fed:effr", 4.52, unit="percent", series_key="fred:EFFR"),
            _obs("fed:target_upper", 4.50, unit="percent", series_key="fred:DFEDTARU"),
            _obs("fed:target_lower", 4.25, unit="percent", series_key="fred:DFEDTARL"),
            _obs("rates:dgs2", 3.90, unit="percent", series_key="fred:DGS2"),
            _obs("rates:dgs10", 4.70, unit="percent", series_key="fred:DGS10"),
            _obs("vol:vix", 24.0, unit="index", series_key="fred:VIXCLS"),
            _obs("credit:hy_oas", 5.80, unit="percent", series_key="fred:BAMLH0A0HYM2"),
            _obs("credit:ig_oas", 1.50, unit="percent", series_key="fred:BAMLC0A0CM"),
            _obs("asset:spx", 5_200.0, unit="index", series_key="fred:SP500"),
        ],
        computed_at_ms=NOW_MS,
    )

    assert snapshot["projection_version"] == "macro_regime_v4"
    assert snapshot["chain_json"]["liquidity"]["regime"] in {"tightening", "funding_stress"}
    assert snapshot["scenario_json"]["current_regime"] in {"funding_stress", "tightening"}
    assert snapshot["scenario_json"]["confirmations"]
    assert snapshot["scenario_json"]["watch_triggers"]
    assert "trade_map" in snapshot["scenario_json"]


def test_one_point_per_required_concept_is_partial_with_history_coverage_below_ready() -> None:
    snapshot = build_macro_view_snapshot(
        [
            _obs(concept_key, float(index + 1), unit="index", series_key=f"fred:fixture:{index}")
            for index, concept_key in enumerate(MACRO_CORE_CONCEPTS)
        ],
        computed_at_ms=NOW_MS,
    )

    coverage = snapshot["source_coverage_json"]
    assert snapshot["status"] == "partial"
    assert coverage["latest_coverage_ratio"] == 1.0
    assert coverage["history_coverage_ratio"] < 1.0
    assert coverage["history_ready_concept_count"] == 0
    assert len(coverage["concepts_below_min_history"]) == len(MACRO_HISTORY_REQUIRED_CONCEPTS)
    assert all(feature["history_points"] == 1 for feature in snapshot["features_json"].values())
    assert all(
        feature["score_participation"] is False
        for concept_key, feature in snapshot["features_json"].items()
        if concept_key in MACRO_HISTORY_REQUIRED_CONCEPTS
    )
    assert any(gap["code"] == "insufficient_history_20d" for gap in snapshot["data_gaps_json"])


def test_full_history_with_degraded_required_concept_is_not_ready() -> None:
    observations: list[dict[str, object]] = []
    for concept_index, concept_key in enumerate(MACRO_CORE_CONCEPTS):
        observations.extend(
            _history_obs(
                concept_key,
                start=date(2025, 11, 16),
                values=[float(concept_index + day_index + 1) for day_index in range(186)],
                series_key=f"fred:fixture:{concept_index}",
                data_quality="ok",
            )
        )
    degraded_concept_key = MACRO_HISTORY_REQUIRED_CONCEPTS[-1]
    for observation in observations:
        if observation["concept_key"] == degraded_concept_key:
            observation["data_quality"] = "degraded"

    snapshot = build_macro_view_snapshot(observations, computed_at_ms=NOW_MS)

    assert snapshot["source_coverage_json"]["latest_coverage_ratio"] == 1.0
    assert snapshot["source_coverage_json"]["history_coverage_ratio"] == 1.0
    assert snapshot["features_json"][degraded_concept_key]["data_quality"] == "degraded"
    assert snapshot["status"] == "partial"
    feature_gap = next(
        gap
        for gap in snapshot["features_json"][degraded_concept_key]["data_gaps"]
        if gap["code"] == "data_quality_degraded"
    )
    snapshot_gap = next(gap for gap in snapshot["data_gaps_json"] if gap["code"] == "data_quality_degraded")
    assert snapshot_gap == feature_gap


def test_chain_nodes_do_not_manufacture_scores_from_missing_panel_scores() -> None:
    features = {
        "liquidity:fed_assets": {"delta": {"20d": -125_000.0}},
        "vol:vix": {"delta": {"5d": 4.0}},
        "credit:hy_oas": {"delta": {"20d": 0.6}},
        "asset:spx": {"delta": {"20d": -4.0}},
        "asset:hyg": {"delta": {"20d": -2.0}},
    }

    liquidity = _liquidity_chain_node(latest={}, panel={"evidence": ["panel missing score"]}, features=features)
    volatility = _volatility_chain_node(panel={"evidence": ["panel missing score"]}, features=features)
    credit = _credit_chain_node(latest={}, panel={"evidence": ["panel missing score"]}, features=features)
    cross_asset = _cross_asset_chain_node(latest={}, panel={"evidence": ["panel missing score"]}, features=features)

    assert liquidity["regime"] == "data_gap"
    assert volatility["regime"] == "data_gap"
    assert credit["regime"] == "data_gap"
    assert cross_asset["regime"] == "data_gap"
    assert liquidity["score"] == 0.0
    assert volatility["score"] == 0.0
    assert credit["score"] == 0.0
    assert cross_asset["score"] == 0.0


def test_scorecard_requires_explicit_source_coverage_metadata_without_defaults() -> None:
    with pytest.raises(ValueError, match="Missing macro source coverage metadata: latest_coverage_ratio"):
        _scorecard(
            overall_score=None,
            chain={},
            coverage={
                "observed_concept_count": 0,
                "required_concept_count": len(MACRO_HISTORY_REQUIRED_CONCEPTS),
                "history_coverage_ratio": 0.0,
            },
            data_gaps=[],
        )


def test_snapshot_status_requires_explicit_source_coverage_ratios_without_zero_default() -> None:
    with pytest.raises(ValueError, match="Missing macro source coverage metadata: latest_coverage_ratio"):
        _snapshot_status(
            latest={"rates:dgs10": {"value_numeric": 4.5}},
            features={},
            coverage={"history_coverage_ratio": 1.0},
            data_gaps=[],
        )


def test_freshness_checks_require_feature_stale_threshold_without_daily_default() -> None:
    with pytest.raises(ValueError, match="Missing macro feature rates:dgs10 metadata: stale_after_days"):
        _has_stale_required_features(
            {
                "rates:dgs10": {
                    "freshness_days": 8,
                }
            }
        )


def test_history_readiness_requires_feature_history_points_without_zero_default() -> None:
    with pytest.raises(ValueError, match="Missing macro feature rates:dgs10 metadata: history_points"):
        _feature_has_required_history({"rates:dgs10": {"label": "10Y"}}, "rates:dgs10")


def _obs(
    concept_key: str,
    value: float,
    *,
    unit: str,
    series_key: str,
    observed_at: str = "2026-05-20",
    data_quality: str = "ok",
) -> dict[str, object]:
    return {
        "source_name": series_key.split(":", 1)[0],
        "concept_key": concept_key,
        "series_key": series_key,
        "source_priority": 100,
        "observed_at": observed_at,
        "value_numeric": value,
        "unit": unit,
        "frequency": "daily",
        "data_quality": data_quality,
        "source_ts": observed_at,
    }


def _history_obs(
    concept_key: str,
    *,
    start: date,
    values: list[float],
    series_key: str,
    data_quality: str,
) -> list[dict[str, object]]:
    return [
        _obs(
            concept_key,
            value,
            unit="index",
            series_key=series_key,
            observed_at=(start + timedelta(days=index)).isoformat(),
            data_quality=data_quality,
        )
        for index, value in enumerate(values)
    ]
