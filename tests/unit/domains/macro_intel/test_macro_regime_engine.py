from __future__ import annotations

from gmgn_twitter_intel.domains.macro_intel._constants import MACRO_CORE_CONCEPTS
from gmgn_twitter_intel.domains.macro_intel.services.macro_regime_engine import (
    build_macro_view_snapshot,
)

NOW_MS = 1_779_000_000_000


def test_empty_observations_emit_degraded_snapshot() -> None:
    snapshot = build_macro_view_snapshot([], computed_at_ms=NOW_MS)

    assert snapshot["projection_version"] == "macro_regime_v3"
    assert snapshot["status"] == "empty"
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
    assert snapshot["scorecard_json"]["projection_version"] == "macro_regime_v3"
    assert "missing:liquidity:fed_assets" in snapshot["data_gaps_json"]
    assert "missing:liquidity:sofr" in snapshot["data_gaps_json"]
    assert snapshot["source_coverage_json"] == {
        "observed_concept_count": 0,
        "required_concept_count": len(MACRO_CORE_CONCEPTS),
        "coverage_ratio": 0.0,
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
    assert "missing:asset:spx" in snapshot["data_gaps_json"]
    assert snapshot["source_coverage_json"]["observed_concept_count"] == 10


def test_regime_v3_emits_chain_and_scenario_for_funding_stress() -> None:
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

    assert snapshot["projection_version"] == "macro_regime_v3"
    assert snapshot["chain_json"]["liquidity"]["regime"] in {"tightening", "funding_stress"}
    assert snapshot["scenario_json"]["current_regime"] in {"funding_stress", "tightening"}
    assert snapshot["scenario_json"]["confirmations"]
    assert snapshot["scenario_json"]["watch_triggers"]
    assert "trade_map" in snapshot["scenario_json"]


def _obs(
    concept_key: str,
    value: float,
    *,
    unit: str,
    series_key: str,
    observed_at: str = "2026-05-20",
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
        "data_quality": "ok",
        "source_ts": observed_at,
    }
