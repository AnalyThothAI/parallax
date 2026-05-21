from __future__ import annotations

from gmgn_twitter_intel.domains.macro_intel.services.macro_regime_engine import (
    build_macro_view_snapshot,
)

NOW_MS = 1_779_000_000_000


def test_empty_observations_emit_degraded_snapshot() -> None:
    snapshot = build_macro_view_snapshot([], computed_at_ms=NOW_MS)

    assert snapshot["projection_version"] == "macro_regime_v1"
    assert snapshot["status"] == "empty"
    assert snapshot["regime"] == "data_gap"
    assert snapshot["overall_score"] is None
    assert set(snapshot["panels_json"]) == {"liquidity", "rates", "volatility", "credit", "cross_asset"}
    assert "missing:fred:WALCL" in snapshot["data_gaps_json"]
    assert "missing:nyfed:SOFR" in snapshot["data_gaps_json"]
    assert snapshot["source_coverage_json"] == {
        "observed_series_count": 0,
        "required_series_count": 10,
        "coverage_ratio": 0.0,
        "latest_observed_at": None,
    }


def test_representative_observations_emit_scores_and_triggers() -> None:
    snapshot = build_macro_view_snapshot(
        [
            _obs("fred:WALCL", 7_500_000, unit="millions_usd"),
            _obs("fred:RRPONTSYD", 100, unit="billions_usd"),
            _obs("treasury_fiscal:operating_cash_balance", 900_000, unit="millions_usd"),
            _obs("nyfed:SOFR", 4.55, unit="percent"),
            _obs("fred:IORB", 4.40, unit="percent"),
            _obs("fred:DGS2", 3.90, unit="percent"),
            _obs("fred:DGS10", 4.70, unit="percent"),
            _obs("fred:VIXCLS", 24.0, unit="index"),
            _obs("fred:BAMLH0A0HYM2", 5.80, unit="percent"),
            _obs("fred:BAMLC0A0CM", 1.50, unit="percent"),
        ],
        computed_at_ms=NOW_MS,
    )

    assert snapshot["status"] == "partial"
    assert snapshot["regime"] == "funding_stress"
    assert snapshot["overall_score"] >= 6.0
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
    assert "missing:fred:SP500" in snapshot["data_gaps_json"]
    assert snapshot["source_coverage_json"]["observed_series_count"] == 10


def _obs(
    series_key: str,
    value: float,
    *,
    unit: str,
    observed_at: str = "2026-05-20",
) -> dict[str, object]:
    return {
        "source_name": series_key.split(":", 1)[0],
        "series_key": series_key,
        "observed_at": observed_at,
        "value_numeric": value,
        "unit": unit,
        "frequency": "daily",
        "data_quality": "ok",
        "source_ts": observed_at,
    }
