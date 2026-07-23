from __future__ import annotations

from datetime import timedelta
from typing import Any

from parallax.domains.macro_intel._constants import MACRO_EVIDENCE_PROJECTION_VERSION
from parallax.domains.macro_intel.services.macro_concept_manifest import (
    MACRO_CONCEPT_MANIFEST,
    concepts_for_page,
)
from parallax.domains.macro_intel.services.macro_dominant_shock import build_dominant_shock
from parallax.domains.macro_intel.services.macro_evidence_snapshot import build_macro_evidence_snapshot
from tests.unit.domains.macro_intel.macro_evidence_test_support import (
    COMPUTED_AT_MS,
    COMPUTED_DATE,
    flatten,
    observation,
    series,
)

PAGE_IDS = (
    "overview",
    "cross_asset",
    "rates_inflation",
    "growth_labor",
    "liquidity_funding",
    "credit",
)
COMMON_PAGE_KEYS = {
    "page_id",
    "snapshot",
    "conclusion",
    "horizon",
    "drivers",
    "confirmations",
    "contradictions",
    "upgrade_invalidation",
    "evidence_refs",
    "freshness",
    "evidence",
    "unavailable_evidence",
}
PAGE_SPECIFIC_KEYS = {
    "overview": {
        "shock_summary",
        "risk_lanes",
        "key_changes",
        "nearest_catalyst",
        "core_invalidation",
        "official_catalysts",
    },
    "cross_asset": {"asset_returns", "volatility", "correlations_20", "correlations_60", "divergences"},
    "rates_inflation": {
        "nominal_curve",
        "curve_slopes",
        "real_yields",
        "breakevens",
        "term_premium",
        "policy_funding_corridor",
        "inflation_releases",
        "curve_shape",
    },
    "growth_labor": {
        "growth_leading",
        "growth_lagging",
        "labor_leading",
        "labor_lagging",
        "growth_metrics",
    },
    "liquidity_funding": {
        "central_bank_balance_sheet",
        "treasury_cash",
        "reverse_repo",
        "reserves",
        "net_liquidity",
        "secured_funding",
        "unsecured_funding",
    },
    "credit": {
        "aggregate_spreads",
        "rating_tail",
        "effective_yields",
        "credit_supply",
        "realized_damage",
        "financial_conditions_liquidity",
        "treasury_spread_quadrant",
        "credit_state",
    },
}
RISK_LANE_IDS = (
    "us_equities",
    "long_duration_treasuries",
    "credit",
    "usd",
    "gold",
    "oil",
    "crypto",
    "market_volatility",
)


def test_builds_exact_six_page_documents() -> None:
    snapshot = build_macro_evidence_snapshot([], computed_at_ms=COMPUTED_AT_MS)

    assert set(snapshot) == {
        "projection_version",
        "fact_watermark",
        "market_cutoff",
        "computed_at_ms",
        *PAGE_IDS,
    }
    assert snapshot["projection_version"] == MACRO_EVIDENCE_PROJECTION_VERSION
    assert snapshot["fact_watermark"] is None
    assert snapshot["market_cutoff"] == COMPUTED_DATE
    for page_id in PAGE_IDS:
        page = snapshot[page_id]
        assert set(page) == COMMON_PAGE_KEYS | PAGE_SPECIFIC_KEYS[page_id]
        assert page["page_id"] == page_id
        assert page["snapshot"] == {
            "projection_version": MACRO_EVIDENCE_PROJECTION_VERSION,
            "fact_watermark": None,
            "market_cutoff": COMPUTED_DATE,
            "computed_at_ms": COMPUTED_AT_MS,
        }
        assert page["conclusion"]["status"] == "insufficient_evidence"
        assert page["conclusion"]["judgment"] == "insufficient_evidence"
        assert page["conclusion"]["rule_version"].endswith("_v1")
        assert page["horizon"] == "1_4_weeks"
        assert set(page["freshness"]) == {
            "status",
            "critical_missing",
            "critical_stale",
            "optional_unavailable",
        }


def test_overview_exposes_fixed_decision_map_without_prohibited_outputs() -> None:
    overview = build_macro_evidence_snapshot([], computed_at_ms=COMPUTED_AT_MS)["overview"]

    assert overview["shock_summary"]["state"] == "insufficient_evidence"
    assert overview["shock_summary"]["candidate"] is None
    assert overview["shock_summary"]["confidence"] == "insufficient_evidence"
    assert [lane["lane_id"] for lane in overview["risk_lanes"]] == list(RISK_LANE_IDS)
    assert {lane["direction"] for lane in overview["risk_lanes"]} == {"insufficient_evidence"}
    assert {lane["trend"] for lane in overview["risk_lanes"]} == {"insufficient_evidence"}
    assert overview["key_changes"] == []
    assert overview["nearest_catalyst"] is None
    assert overview["core_invalidation"] is None
    assert not (
        _all_keys(overview)
        & {
            "position",
            "position_size",
            "holdings",
            "buy",
            "sell",
            "target_price",
            "allocation",
            "probability",
            "confidence_score",
            "llm",
        }
    )


def test_overview_distinguishes_no_dominant_shock_and_uses_five_completed_sessions() -> None:
    sessions = _completed_sessions(COMPUTED_DATE, count=30)
    observations: list[dict[str, Any]] = []
    stable_concepts = {
        "asset:tlt": 100.0,
        "asset:hyg": 100.0,
        "fx:dxy": 100.0,
        "asset:gld": 100.0,
        "asset:uso": 100.0,
        "crypto:btc": 50_000.0,
        "vol:vix": 16.0,
        "asset:qqq": 100.0,
        "rates:dgs10": 4.0,
        "credit:hy_oas": 300.0,
        "rates:real_10y": 1.8,
        "inflation:10y_breakeven": 2.2,
        "crypto:eth": 3_000.0,
        "vol:vix3m": 18.0,
    }
    for concept_key, value in stable_concepts.items():
        observations.extend(observation(concept_key, value, observed_at=day) for day in sessions)
    spy_values = [100.0] * 20 + [100.2, 100.4, 100.8, 101.2, 101.6, 102.2, 102.8, 103.4, 104.0, 105.0]
    observations.extend(
        observation("asset:spy", value, observed_at=day) for day, value in zip(sessions, spy_values, strict=True)
    )

    overview = build_macro_evidence_snapshot(observations, computed_at_ms=COMPUTED_AT_MS)["overview"]
    equity_lane = next(lane for lane in overview["risk_lanes"] if lane["lane_id"] == "us_equities")

    assert overview["shock_summary"]["state"] == "no_dominant_shock"
    assert overview["shock_summary"]["candidate"] is None
    assert equity_lane["direction"] == "tailwind"
    assert equity_lane["trend"] == "strengthening"
    assert equity_lane["confidence"] in {"medium", "high"}
    assert equity_lane["comparison_session"] == sessions[-6]
    assert overview["key_changes"][0]["lane_id"] == "us_equities"


def test_judgment_uses_rule_hits_without_global_score_or_confidence() -> None:
    observations = flatten(
        (
            series("asset:spy", [100.0] * 60 + [95.0]),
            series("asset:hyg", [100.0] * 60 + [97.0]),
            series("fx:dxy", [100.0] * 60 + [103.0]),
            series("vol:vix", [15.0] * 60 + [20.0]),
        )
    )

    page = build_macro_evidence_snapshot(observations, computed_at_ms=COMPUTED_AT_MS)["cross_asset"]

    assert page["conclusion"]["status"] == "degraded"
    assert page["conclusion"]["judgment"] == "risk_off_confirmation"
    assert {item["rule_id"] for item in page["conclusion"]["rule_hits"]} >= {
        "spy_down",
        "hyg_down",
        "dollar_up",
        "vix_up",
    }
    assert page["drivers"] == [{"code": "spy_down", "evidence_refs": ["asset:spy"]}]
    assert not (_all_keys(page) & {"score", "overall_score", "confidence", "probability", "trade"})


def test_judgment_dominant_shock_uses_an_actual_trigger_hit() -> None:
    dominant = build_dominant_shock(
        cross_asset={"judgment": "risk_off_confirmation", "rule_hits": []},
        rates_inflation={"judgment": "mixed", "rule_hits": [], "curve_shape": {"status": "supported"}},
        growth_labor={
            "judgment": "growth_labor_cooling",
            "rule_hits": [
                {"rule_id": "unemployment_rate_up"},
                {"rule_id": "payroll_growth_below_100k"},
                {"rule_id": "real_gdp_below_one_pct_saar"},
            ],
        },
        liquidity_funding={"judgment": "mixed", "rule_hits": []},
        credit={
            "credit_state": {"status": "supported", "stage": "contained", "direction": "stable"},
            "rule_hits": [],
            "treasury_spread_quadrant": {"quadrant": "stable_or_mixed"},
        },
    )

    assert dominant["candidate"] == "growth"
    assert dominant["primary_trigger"] == {
        "code": "unemployment_rate_up",
        "evidence_refs": ["labor:unemployment"],
    }
    assert dominant["cross_domain_confirmations"] == [
        {"code": "cross_asset_risk_off", "evidence_refs": ["asset:spy", "asset:hyg"]}
    ]
    assert dominant["status"] == "confirmed"


def test_dominant_shock_cross_asset_confirmation_is_not_a_family_or_term_premium_proxy() -> None:
    dominant = build_dominant_shock(
        cross_asset={"judgment": "risk_off_confirmation", "rule_hits": [{"rule_id": "vix_up"}]},
        rates_inflation={
            "judgment": "mixed",
            "rule_hits": [],
            "curve_shape": {"status": "supported"},
            "term_premium": {
                "capability": "treasury_term_premium",
                "status": "not_assessed",
                "reason": "source_not_ingested",
            },
        },
        growth_labor={"judgment": "mixed", "rule_hits": []},
        liquidity_funding={"judgment": "mixed", "rule_hits": []},
        credit={
            "credit_state": {"status": "supported", "stage": "contained", "direction": "stable"},
            "rule_hits": [],
            "treasury_spread_quadrant": {"quadrant": "stable_or_mixed"},
        },
    )

    assert dominant["candidate"] is None
    assert dominant["status"] == "insufficient_evidence"
    assert dominant["cross_domain_confirmations"] == []


def test_dominant_shock_statuses_are_confirmed_provisional_or_divergent() -> None:
    base = {
        "growth_labor": {"judgment": "mixed", "rule_hits": []},
        "liquidity_funding": {"judgment": "mixed", "rule_hits": []},
        "credit": {
            "credit_state": {"status": "supported", "stage": "contained", "direction": "stable"},
            "rule_hits": [],
            "treasury_spread_quadrant": {"quadrant": "stable_or_mixed"},
        },
    }
    provisional = build_dominant_shock(
        cross_asset={"judgment": "divergent", "rule_hits": []},
        rates_inflation={
            "judgment": "real_rate_tightening",
            "rule_hits": [{"rule_id": "real_rate_up_20_sessions"}],
        },
        **base,
    )
    divergent = build_dominant_shock(
        cross_asset={"judgment": "risk_on_confirmation", "rule_hits": []},
        rates_inflation={
            "judgment": "real_rate_tightening",
            "rule_hits": [{"rule_id": "real_rate_up_20_sessions"}],
        },
        **base,
    )

    assert (provisional["candidate"], provisional["status"]) == ("policy_real_rates", "provisional")
    assert (divergent["candidate"], divergent["status"]) == ("policy_real_rates", "divergent")
    assert {provisional["status"], divergent["status"]} <= {
        "confirmed",
        "provisional",
        "divergent",
        "insufficient_evidence",
    }


def test_overview_critical_gaps_override_provisional_dominant_shock() -> None:
    observations = flatten(
        (
            series("rates:dgs10", [4.0] * 20 + [4.3]),
            series("rates:real_10y", [1.5] * 20 + [1.8]),
        )
    )

    page = build_macro_evidence_snapshot(observations, computed_at_ms=COMPUTED_AT_MS)["overview"]

    assert page["shock_summary"]["candidate"] == "policy_real_rates"
    assert page["shock_summary"]["state"] == "dominant"
    assert page["shock_summary"]["confidence"] == "medium"
    assert page["freshness"]["critical_missing"]
    assert page["conclusion"]["status"] == "insufficient_evidence"
    assert page["conclusion"]["judgment"] == "insufficient_evidence"


def test_overview_freshness_uses_canonical_claim_gaps_for_available_rows() -> None:
    critical_concepts = (
        "asset:spy",
        "asset:hyg",
        "fx:dxy",
        "vol:vix",
        "rates:dgs10",
        "rates:real_10y",
        "inflation:10y_breakeven",
        "labor:initial_claims",
        "labor:payrolls",
        "liquidity:sofr",
        "fed:iorb",
        "liquidity:reserve_balances",
        "credit:hy_oas",
        "credit:ig_oas",
        "credit:hy_ccc_oas",
    )
    observations = [observation(concept_key, 100.0) for concept_key in critical_concepts]

    page = build_macro_evidence_snapshot(observations, computed_at_ms=COMPUTED_AT_MS)["overview"]

    assert set(critical_concepts) <= set(page["freshness"]["critical_missing"])
    assert page["conclusion"]["status"] == "insufficient_evidence"


def test_evidence_gap_in_critical_history_fails_claim_closed() -> None:
    observations = [
        observation("asset:spy", 100.0),
        observation("asset:hyg", 99.0),
        observation("fx:dxy", 101.0),
        observation("vol:vix", 18.0),
    ]

    page = build_macro_evidence_snapshot(observations, computed_at_ms=COMPUTED_AT_MS)["cross_asset"]

    assert page["conclusion"]["status"] == "insufficient_evidence"
    assert page["conclusion"]["judgment"] == "insufficient_evidence"
    assert {"asset:hyg", "asset:spy", "fx:dxy", "vol:vix"} <= set(page["freshness"]["critical_missing"])
    spy = next(item for item in page["evidence"] if item["concept_key"] == "asset:spy")
    assert spy["status"] == "available"
    assert spy["reason"] == "insufficient_history:20_sessions"


def test_cross_asset_freshness_fails_closed_when_60_session_outputs_are_missing() -> None:
    observations = flatten(
        series(concept_key, [100.0 + index for index in range(21)]) for concept_key in concepts_for_page("cross_asset")
    )

    page = build_macro_evidence_snapshot(observations, computed_at_ms=COMPUTED_AT_MS)["cross_asset"]

    assert page["freshness"]["status"] == "insufficient_evidence"
    assert {
        "cross_asset_return_60:asset:spy",
        "cross_asset_return_60:asset:hyg",
        "cross_asset_return_60:fx:dxy",
        "cross_asset_correlation_60:asset:spy:asset:hyg",
        "cross_asset_correlation_60:asset:spy:fx:dxy",
    } <= set(page["freshness"]["critical_missing"])
    assert page["conclusion"]["status"] == "insufficient_evidence"


def test_cross_asset_freshness_is_fresh_when_all_60_session_outputs_are_available() -> None:
    observations = flatten(
        series(concept_key, [100.0 + index for index in range(61)]) for concept_key in concepts_for_page("cross_asset")
    )

    page = build_macro_evidence_snapshot(observations, computed_at_ms=COMPUTED_AT_MS)["cross_asset"]

    assert page["freshness"] == {
        "status": "fresh",
        "critical_missing": [],
        "critical_stale": [],
        "optional_unavailable": [],
    }
    assert page["conclusion"]["status"] == "supported"
    assert all(item["return_60"]["status"] == "available" for item in page["asset_returns"])
    assert all(item["status"] == "available" for item in page["correlations_60"])


def test_cross_asset_optional_60_session_gap_degrades_without_failing_closed() -> None:
    observations = flatten(
        series(
            concept_key,
            [100.0 + index for index in range(21 if concept_key == "crypto:btc" else 61)],
        )
        for concept_key in concepts_for_page("cross_asset")
    )

    page = build_macro_evidence_snapshot(observations, computed_at_ms=COMPUTED_AT_MS)["cross_asset"]

    assert page["freshness"]["status"] == "degraded"
    assert page["freshness"]["critical_missing"] == []
    assert "cross_asset_return_60:crypto:btc" in page["freshness"]["optional_unavailable"]
    assert page["conclusion"]["status"] == "degraded"


def test_evidence_gap_in_required_metadata_cannot_drive_rules() -> None:
    observations = flatten(
        (
            series("asset:spy", [100.0] * 20 + [90.0]),
            series("asset:hyg", [100.0] * 20 + [90.0]),
            series("fx:dxy", [100.0] * 20 + [110.0]),
            series("vol:vix", [15.0] * 20 + [25.0]),
        )
    )
    observations[-1]["unit"] = "percent"

    page = build_macro_evidence_snapshot(observations, computed_at_ms=COMPUTED_AT_MS)["cross_asset"]
    vix_return = next(item for item in page["asset_returns"] if item["concept_key"] == "asset:spy")

    assert page["conclusion"]["status"] == "insufficient_evidence"
    assert "vol:vix" in page["freshness"]["critical_missing"]
    assert "vix_up" not in {item["rule_id"] for item in page["conclusion"]["rule_hits"]}
    assert vix_return["return_20"]["status"] == "available"


def test_future_non_catalyst_fact_cannot_enter_evidence_or_watermark() -> None:
    observations = [
        observation("asset:spy", 100.0, observed_at=COMPUTED_DATE),
        observation("rates:dgs2", 4.0, observed_at=COMPUTED_DATE),
        observation("rates:dgs2", 9.9, observed_at=COMPUTED_DATE + timedelta(days=1)),
    ]

    snapshot = build_macro_evidence_snapshot(observations, computed_at_ms=COMPUTED_AT_MS)
    dgs2 = next(item for item in snapshot["rates_inflation"]["nominal_curve"] if item["concept_key"] == "rates:dgs2")

    assert snapshot["market_cutoff"] == COMPUTED_DATE
    assert snapshot["fact_watermark"] == COMPUTED_DATE
    assert dgs2["value"] == 4.0
    assert dgs2["observed_at"] == COMPUTED_DATE.isoformat()


def test_unavailable_capabilities_are_not_assessed_without_proxy_values() -> None:
    snapshot = build_macro_evidence_snapshot([], computed_at_ms=COMPUTED_AT_MS)

    unsupported = {
        item["capability"]: item for page_id in PAGE_IDS for item in snapshot[page_id]["unavailable_evidence"]
    }
    assert {
        "etf_premium_discount",
        "dealer_inventory",
        "treasury_term_premium",
        "fedwatch",
        "consensus_forecasts",
        "economic_surprise",
        "trace_transactions",
    } <= set(unsupported)
    assert all(
        item == {"capability": key, "status": "not_assessed", "reason": "source_not_ingested"}
        for key, item in unsupported.items()
    )
    assert snapshot["rates_inflation"]["term_premium"] == unsupported["treasury_term_premium"]


def test_unavailable_not_assessed_capabilities_do_not_change_claim_readiness() -> None:
    step_days = {"daily": 1, "weekly": 7, "monthly": 30, "quarterly": 90, "irregular": 30}
    observations = []
    for concept_key in concepts_for_page("rates_inflation"):
        spec = MACRO_CONCEPT_MANIFEST[concept_key]
        observations.extend(
            series(
                concept_key,
                [100.0 + index for index in range(spec.change_periods + 1)],
                step_days=step_days[spec.frequency],
            )
        )

    page = build_macro_evidence_snapshot(observations, computed_at_ms=COMPUTED_AT_MS)["rates_inflation"]

    assert page["freshness"]["status"] == "fresh"
    assert page["conclusion"]["status"] == "supported"
    assert {item["capability"] for item in page["unavailable_evidence"]} == {
        "treasury_term_premium",
        "fedwatch",
    }


def test_catalysts_are_limited_to_seven_days_and_require_official_metadata() -> None:
    event_date = COMPUTED_DATE + timedelta(days=3)
    outside_date = COMPUTED_DATE + timedelta(days=8)
    observations = [
        observation(
            "event:fomc_decision_next",
            3,
            observed_at=event_date,
            event_metadata_json={
                "event_time_et": "2:00 PM",
                "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            },
        ),
        observation(
            "event:bea_gdp_next",
            3,
            observed_at=event_date,
            event_metadata_json={
                "event_time": "08:30 AM",
                "source_url": "https://apps.bea.gov/API/signup/release_dates.json",
            },
        ),
        observation(
            "event:bea_pce_next",
            4,
            observed_at=event_date + timedelta(days=1),
            event_metadata_json={
                "event_time": "08:30 AM",
                "timezone": "America/New_York",
                "source_url": "https://apps.bea.gov/API/signup/release_dates.json",
            },
        ),
        observation(
            "event:bls_cpi_next",
            8,
            observed_at=outside_date,
            event_metadata_json={
                "event_time_et": "08:30 AM",
                "source_url": "https://www.bls.gov/schedule/news_release/cpi.htm",
            },
        ),
    ]
    present_concepts = {str(item["concept_key"]) for item in observations}
    observations.extend(
        item for item in _outside_catalyst_observations() if item["concept_key"] not in present_concepts
    )

    page = build_macro_evidence_snapshot(observations, computed_at_ms=COMPUTED_AT_MS)["overview"]

    assert page["official_catalysts"] == [
        {
            "concept_key": "event:fomc_decision_next",
            "event_date": event_date,
            "event_time": "2:00 PM",
            "timezone": "America/New_York",
            "source_name": "fixture",
            "series_key": "fixture:event:fomc_decision_next",
            "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            "event_at_ms": 1_785_088_800_000,
            "release_status": "upcoming",
            "evidence_ref": "event:fomc_decision_next",
        },
        {
            "concept_key": "event:bea_pce_next",
            "event_date": event_date + timedelta(days=1),
            "event_time": "08:30 AM",
            "timezone": "America/New_York",
            "source_name": "fixture",
            "series_key": "fixture:event:bea_pce_next",
            "source_url": "https://apps.bea.gov/API/signup/release_dates.json",
            "event_at_ms": 1_785_155_400_000,
            "release_status": "upcoming",
            "evidence_ref": "event:bea_pce_next",
        },
    ]
    assert page["unavailable_evidence"] == [
        {
            "capability": "official_catalyst:event:bea_gdp_next",
            "status": "not_assessed",
            "reason": "missing_timezone",
        }
    ]
    assert page["conclusion"]["status"] == "insufficient_evidence"
    assert not (_all_keys(page["official_catalysts"]) & {"consensus", "forecast", "surprise", "score"})


def test_missing_official_catalyst_feed_degrades_but_valid_empty_window_does_not() -> None:
    supporting = _overview_supporting_observations()
    outside = _outside_catalyst_observations()

    complete = build_macro_evidence_snapshot(
        [*supporting, *outside],
        computed_at_ms=COMPUTED_AT_MS,
    )["overview"]
    missing_feed = build_macro_evidence_snapshot(
        [
            *supporting,
            *(item for item in outside if item["concept_key"] != "event:bls_cpi_next"),
        ],
        computed_at_ms=COMPUTED_AT_MS,
    )["overview"]

    assert complete["official_catalysts"] == []
    assert complete["freshness"]["status"] == "fresh"
    assert complete["conclusion"]["status"] == "supported"
    assert complete["unavailable_evidence"] == []
    assert missing_feed["official_catalysts"] == []
    assert missing_feed["freshness"]["status"] == "degraded"
    assert "official_catalyst:event:bls_cpi_next" in missing_feed["freshness"]["optional_unavailable"]
    assert missing_feed["conclusion"]["status"] == "degraded"
    assert missing_feed["unavailable_evidence"] == [
        {
            "capability": "official_catalyst:event:bls_cpi_next",
            "status": "not_assessed",
            "reason": "source_not_ingested",
        }
    ]


def test_out_of_window_catalyst_metadata_does_not_degrade_overview() -> None:
    outside = _outside_catalyst_observations()
    outside[0]["event_metadata_json"] = {}

    page = build_macro_evidence_snapshot(
        [*_overview_supporting_observations(), *outside],
        computed_at_ms=COMPUTED_AT_MS,
    )["overview"]

    assert page["official_catalysts"] == []
    assert page["freshness"]["status"] == "fresh"
    assert page["conclusion"]["status"] == "supported"
    assert page["unavailable_evidence"] == []


def test_official_catalyst_metadata_gap_degrades_supported_overview() -> None:
    catalysts = _outside_catalyst_observations()
    gdp = next(item for item in catalysts if item["concept_key"] == "event:bea_gdp_next")
    gdp["observed_at"] = COMPUTED_DATE + timedelta(days=3)
    gdp["event_metadata_json"].pop("event_time_et")
    gdp["event_metadata_json"]["event_time"] = "08:30 AM"

    page = build_macro_evidence_snapshot(
        [*_overview_supporting_observations(), *catalysts],
        computed_at_ms=COMPUTED_AT_MS,
    )["overview"]

    assert page["freshness"]["status"] == "degraded"
    assert "official_catalyst:event:bea_gdp_next" in page["freshness"]["optional_unavailable"]
    assert page["conclusion"]["status"] == "degraded"
    assert page["unavailable_evidence"] == [
        {
            "capability": "official_catalyst:event:bea_gdp_next",
            "status": "not_assessed",
            "reason": "missing_timezone",
        }
    ]


def test_non_manifest_fact_does_not_change_snapshot_watermark() -> None:
    snapshot = build_macro_evidence_snapshot(
        [{"concept_key": "unknown:future", "observed_at": COMPUTED_DATE + timedelta(days=30)}],
        computed_at_ms=COMPUTED_AT_MS,
    )

    assert snapshot["fact_watermark"] is None


def test_future_catalysts_and_future_material_dates_do_not_advance_fact_watermark() -> None:
    past_material_date = COMPUTED_DATE - timedelta(days=1)
    snapshot = build_macro_evidence_snapshot(
        [
            observation("rates:dgs10", 4.2, observed_at=past_material_date),
            observation("rates:dgs2", 4.0, observed_at=COMPUTED_DATE + timedelta(days=1)),
            observation(
                "event:fomc_decision_next",
                3,
                observed_at=COMPUTED_DATE + timedelta(days=3),
                event_metadata_json={
                    "event_time_et": "2:00 PM",
                    "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                },
            ),
        ],
        computed_at_ms=COMPUTED_AT_MS,
    )

    assert snapshot["fact_watermark"] == past_material_date


def _overview_supporting_observations() -> list[dict[str, Any]]:
    return flatten(
        (
            series("asset:spy", [100.0] * 20 + [95.0]),
            series("asset:hyg", [100.0] * 20 + [97.0]),
            series("fx:dxy", [100.0] * 20 + [103.0]),
            series("vol:vix", [15.0] * 20 + [20.0]),
            series("rates:dgs10", [4.0] * 20 + [4.3]),
            series("rates:real_10y", [1.5] * 20 + [1.8]),
            series("inflation:10y_breakeven", [2.0] * 21),
            series("labor:initial_claims", [200_000.0] * 5, step_days=7),
            series("labor:payrolls", [150_000.0, 150_150.0], step_days=30),
            series("liquidity:sofr", [4.4] * 21),
            series("fed:iorb", [4.4] * 21),
            series("liquidity:reserve_balances", [3_400_000.0] * 5, step_days=7),
            series("credit:hy_oas", [300.0] * 21),
            series("credit:ig_oas", [80.0] * 21),
            series("credit:hy_ccc_oas", [900.0] * 21),
        )
    )


def _outside_catalyst_observations() -> list[dict[str, Any]]:
    return [
        observation(
            concept_key,
            8,
            observed_at=COMPUTED_DATE + timedelta(days=8),
            event_metadata_json={
                "event_time_et": "08:30 AM",
                "source_url": f"https://official.example/{concept_key}",
            },
        )
        for concept_key, spec in MACRO_CONCEPT_MANIFEST.items()
        if spec.claim_effect == "catalyst_only"
    ]


def _completed_sessions(end: Any, *, count: int) -> list[Any]:
    sessions: list[Any] = []
    cursor = end
    while len(sessions) < count:
        if cursor.weekday() < 5:
            sessions.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(sessions))


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _all_keys(item)}
    if isinstance(value, list | tuple):
        return {key for item in value for key in _all_keys(item)}
    return set()
