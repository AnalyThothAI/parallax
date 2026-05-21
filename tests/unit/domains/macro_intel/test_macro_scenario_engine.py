from __future__ import annotations

from gmgn_twitter_intel.domains.macro_intel.services.macro_scenario_engine import (
    build_macro_scenario,
)


def test_build_macro_scenario_emits_funding_stress_trade_map() -> None:
    scenario = build_macro_scenario(
        chain={
            "liquidity": {
                "score": 9.0,
                "regime": "funding_stress",
                "evidence": ["sofr_iorb_spread_bps=15.0"],
                "data_gaps": [],
            },
            "fed_corridor": {
                "score": 8.0,
                "regime": "corridor_pressure",
                "evidence": ["sofr_above_iorb"],
                "data_gaps": [],
            },
            "volatility": {
                "score": 7.0,
                "regime": "near_term_stress",
                "evidence": ["vix=24.0"],
                "data_gaps": [],
            },
        },
        panels={"credit": {"regime": "low_quality_stress", "score": 7.0}},
        features={"fred:BAMLH0A0HYM2": {"delta": {"5d": 0.35}}},
        triggers=[
            {"code": "sofr_above_iorb", "description": "SOFR is above IORB", "value": 15.0},
            {"code": "hy_oas_stress", "description": "HY OAS is above 5%", "value": 5.8},
        ],
        data_gaps=["missing:stooq:spy.us"],
    )

    assert scenario["current_regime"] == "funding_stress"
    assert scenario["confidence"] > 0
    assert scenario["time_window"] == "1w"
    assert {item["code"] for item in scenario["confirmations"]} >= {"sofr_above_iorb", "hy_oas_stress"}
    assert scenario["watch_triggers"]
    assert scenario["invalidations"]
    assert scenario["trade_map"][0]["expression"] == "risk_down_credit_sensitive"


def test_build_macro_scenario_reports_data_gap_without_chain_evidence() -> None:
    scenario = build_macro_scenario(
        chain={
            "liquidity": {"score": 0.0, "regime": "data_gap", "evidence": [], "data_gaps": ["missing:fred:WALCL"]},
            "rates": {"score": 0.0, "regime": "data_gap", "evidence": [], "data_gaps": ["missing:fred:DGS10"]},
        },
        panels={},
        features={},
        triggers=[],
        data_gaps=["missing:fred:WALCL", "missing:fred:DGS10"],
    )

    assert scenario["current_regime"] == "data_gap"
    assert scenario["confidence"] == 0.0
    assert scenario["confirmations"] == []
    assert scenario["watch_triggers"]
    assert scenario["trade_map"] == []
