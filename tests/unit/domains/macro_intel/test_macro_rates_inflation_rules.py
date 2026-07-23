from __future__ import annotations

from datetime import timedelta

import pytest

from parallax.domains.macro_intel.services.macro_evidence import build_evidence_index
from parallax.domains.macro_intel.services.macro_rates_inflation_rules import build_rates_inflation_rules
from tests.unit.domains.macro_intel.macro_evidence_test_support import (
    COMPUTED_AT_MS,
    COMPUTED_DATE,
    flatten,
    observation,
    series,
)


def test_nominal_curve_uses_tenor_axes_and_derives_missing_slopes() -> None:
    observations = [
        observation("rates:dgs2", 4.0),
        observation("rates:dgs3mo", 4.25),
        observation("rates:dgs10", 4.5),
    ]
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_rates_inflation_rules(observations, evidence=evidence)

    assert result["nominal_tenor_order"] == [
        "rates:dgs1mo",
        "rates:dgs3mo",
        "rates:dgs6mo",
        "rates:dgs1",
        "rates:dgs2",
        "rates:dgs3",
        "rates:dgs5",
        "rates:dgs7",
        "rates:dgs10",
        "rates:dgs20",
        "rates:dgs30",
    ]
    slopes = {item["concept_key"]: item for item in result["curve_slopes"]}
    assert slopes["rates:10y2y"]["value"] == pytest.approx(0.5)
    assert slopes["rates:10y2y"]["derivation"]["formula"] == "long_yield - short_yield"
    assert slopes["rates:10y2y"]["sample"] == {
        "start": COMPUTED_DATE.isoformat(),
        "end": COMPUTED_DATE.isoformat(),
        "count": 2,
    }
    assert slopes["rates:10y2y"]["derivation"]["inputs"] == [
        {
            "concept_key": "rates:dgs10",
            "observed_at": COMPUTED_DATE.isoformat(),
            "value": 4.5,
        },
        {
            "concept_key": "rates:dgs2",
            "observed_at": COMPUTED_DATE.isoformat(),
            "value": 4.0,
        },
    ]
    assert slopes["rates:10y3m"]["value"] == pytest.approx(0.25)
    assert result["curve_shape"] == {
        "status": "insufficient_evidence",
        "level_classification": "upward_sloping",
        "move_classification": "insufficient_evidence",
        "two_year_change": None,
        "ten_year_change": None,
        "change_window": "20_sessions",
        "evidence_refs": ["rates:10y2y", "rates:10y3m", "rates:dgs2", "rates:dgs10"],
        "rule_version": "macro_curve_shape_v1",
    }


def test_derived_curve_slope_rejects_unaligned_input_dates() -> None:
    observations = [
        observation("rates:dgs2", 4.0, observed_at=COMPUTED_DATE - timedelta(days=1)),
        observation("rates:dgs10", 4.5),
        observation("rates:dgs3mo", 4.25),
    ]
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_rates_inflation_rules(observations, evidence=evidence)
    slope = next(item for item in result["curve_slopes"] if item["concept_key"] == "rates:10y2y")

    assert slope["status"] == "unavailable"
    assert slope["reason"] == "unaligned_input_dates"
    assert slope["value"] is None
    assert slope["observed_at"] is None
    assert slope["sample"] == {
        "start": (COMPUTED_DATE - timedelta(days=1)).isoformat(),
        "end": COMPUTED_DATE.isoformat(),
        "count": 2,
    }
    assert slope["derivation"]["inputs"] == [
        {
            "concept_key": "rates:dgs10",
            "observed_at": COMPUTED_DATE.isoformat(),
            "value": 4.5,
        },
        {
            "concept_key": "rates:dgs2",
            "observed_at": (COMPUTED_DATE - timedelta(days=1)).isoformat(),
            "value": 4.0,
        },
    ]
    assert result["curve_shape"]["level_classification"] == "insufficient_evidence"


@pytest.mark.parametrize(
    ("two_year_last", "ten_year_last", "expected_move"),
    [
        (3.5, 4.2, "bull_steepener"),
        (3.8, 4.0, "bull_flattener"),
        (4.2, 4.9, "bear_steepener"),
        (4.4, 4.7, "bear_flattener"),
    ],
)
def test_curve_move_uses_aligned_two_and_ten_year_changes(
    two_year_last: float,
    ten_year_last: float,
    expected_move: str,
) -> None:
    observations = flatten(
        (
            series("rates:dgs2", [4.0] * 20 + [two_year_last]),
            series("rates:dgs10", [4.5] * 20 + [ten_year_last]),
            series("rates:dgs3mo", [4.25] * 20 + [4.25]),
        )
    )
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    curve_shape = build_rates_inflation_rules(observations, evidence=evidence)["curve_shape"]

    assert curve_shape["status"] == "supported"
    assert curve_shape["move_classification"] == expected_move
    assert curve_shape["two_year_change"] == pytest.approx(two_year_last - 4.0)
    assert curve_shape["ten_year_change"] == pytest.approx(ten_year_last - 4.5)
    assert curve_shape["change_window"] == "20_sessions"


def test_inflation_changes_use_release_intervals_and_actual_samples() -> None:
    values = [100.0 + index for index in range(13)]
    observations = series("inflation:cpi", values, step_days=30)
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_rates_inflation_rules(observations, evidence=evidence)
    cpi = _release(result, "inflation:cpi")

    assert cpi["release_change"]["status"] == "available"
    assert cpi["release_change"]["value"] == pytest.approx((112 / 111 - 1) * 100)
    assert cpi["release_change"]["window"] == "1_release"
    assert cpi["release_change"]["sample"]["count"] == 2
    assert cpi["year_over_year"]["status"] == "available"
    assert cpi["year_over_year"]["value"] == pytest.approx(12.0)
    assert cpi["year_over_year"]["window"] == "12_releases"
    assert cpi["year_over_year"]["sample"]["start"] == observations[0]["observed_at"].isoformat()


def test_policy_and_funding_corridor_uses_basis_point_spreads() -> None:
    observations = [
        observation("fed:target_lower", 4.25),
        observation("fed:target_upper", 4.50),
        observation("fed:effr", 4.40),
        observation("fed:iorb", 4.40),
        observation("liquidity:sofr", 4.55),
    ]
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_rates_inflation_rules(observations, evidence=evidence)
    corridor = result["policy_funding_corridor"]

    assert corridor["status"] == "supported"
    assert corridor["state"] == "secured_funding_pressure"
    spreads = {item["concept_key"]: item for item in corridor["spreads"]}
    assert spreads["derived:sofr_minus_iorb_bps"]["value"] == pytest.approx(15.0)
    assert spreads["derived:effr_minus_iorb_bps"]["value"] == pytest.approx(0.0)
    assert all(item["unit"] == "basis_points" for item in spreads.values())
    assert spreads["derived:sofr_minus_iorb_bps"]["sample"] == {
        "start": COMPUTED_DATE.isoformat(),
        "end": COMPUTED_DATE.isoformat(),
        "count": 2,
    }
    assert spreads["derived:sofr_minus_iorb_bps"]["derivation"]["inputs"] == [
        {
            "concept_key": "liquidity:sofr",
            "observed_at": COMPUTED_DATE.isoformat(),
            "value": 4.55,
        },
        {
            "concept_key": "fed:iorb",
            "observed_at": COMPUTED_DATE.isoformat(),
            "value": 4.4,
        },
    ]


def test_policy_corridor_rejects_unaligned_critical_rates() -> None:
    observations = [
        observation("fed:target_lower", 4.25),
        observation("fed:target_upper", 4.50),
        observation("fed:effr", 4.40, observed_at=COMPUTED_DATE - timedelta(days=1)),
        observation("fed:iorb", 4.40),
        observation("liquidity:sofr", 4.55),
    ]
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    corridor = build_rates_inflation_rules(observations, evidence=evidence)["policy_funding_corridor"]
    spreads = {item["concept_key"]: item for item in corridor["spreads"]}

    assert corridor["status"] == "insufficient_evidence"
    assert corridor["state"] == "insufficient_evidence"
    assert spreads["derived:sofr_minus_iorb_bps"]["status"] == "available"
    assert spreads["derived:effr_minus_iorb_bps"]["status"] == "unavailable"
    assert spreads["derived:effr_minus_iorb_bps"]["reason"] == "unaligned_input_dates"


def test_invalid_release_metadata_cannot_produce_release_changes() -> None:
    observations = series("inflation:core_cpi", [100.0, 101.0], step_days=30)
    observations[-1]["frequency"] = "daily"
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_rates_inflation_rules(observations, evidence=evidence)
    core_cpi = _release(result, "inflation:core_cpi")

    assert evidence["inflation:core_cpi"]["status"] == "invalid"
    assert core_cpi["release_change"]["status"] == "unavailable"
    assert core_cpi["year_over_year"]["status"] == "unavailable"


def test_real_yield_and_breakeven_changes_are_separate_rule_inputs() -> None:
    observations = flatten(
        (
            series("rates:dgs10", [4.0] * 20 + [4.3]),
            series("rates:real_10y", [1.5] * 20 + [1.8]),
            series("inflation:10y_breakeven", [2.0] * 20 + [2.1]),
        )
    )
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_rates_inflation_rules(observations, evidence=evidence)

    assert result["judgment"] == "real_rate_tightening"
    assert {item["rule_id"] for item in result["rule_hits"]} >= {
        "long_rate_up_20_sessions",
        "real_rate_up_20_sessions",
    }
    assert "breakeven_up_20_sessions" not in {item["rule_id"] for item in result["rule_hits"]}


def _release(result: dict[str, object], concept_key: str) -> dict[str, object]:
    releases = result["inflation_releases"]
    assert isinstance(releases, list)
    return next(item for item in releases if item["evidence"]["concept_key"] == concept_key)
