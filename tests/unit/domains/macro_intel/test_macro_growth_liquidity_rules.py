from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from parallax.domains.macro_intel.services.macro_evidence import build_evidence_index
from parallax.domains.macro_intel.services.macro_growth_liquidity_rules import (
    build_growth_labor_rules,
    build_liquidity_funding_rules,
)
from tests.unit.domains.macro_intel.macro_evidence_test_support import (
    COMPUTED_AT_MS,
    COMPUTED_DATE,
    flatten,
    observation,
    series,
)


def test_growth_and_labor_keep_release_aware_resilience_inputs_separate() -> None:
    observations = flatten(
        (
            series("economy:gdp_real", [100.0, 100.6], step_days=90),
            series("labor:payrolls", [150_000.0, 150_250.0], step_days=30),
        )
    )
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_growth_labor_rules(observations, evidence=evidence)
    gdp = _metric(result, "economy:gdp_real")

    assert gdp["status"] == "available"
    assert gdp["unit"] == "percent_saar"
    assert gdp["value"] == pytest.approx(((100.6 / 100.0) ** 4 - 1) * 100)
    assert gdp["window"] == "1_release"
    assert result["judgment"] == "growth_labor_resilient"
    assert {item["rule_id"] for item in result["rule_hits"]} == {
        "payroll_growth_above_200k",
        "real_gdp_at_least_two_pct_saar",
    }


def test_growth_and_labor_cooling_requires_leading_and_lagging_confirmations() -> None:
    observations = flatten(
        (
            series("labor:initial_claims", [200_000.0, 205_000.0, 210_000.0, 220_000.0, 230_000.0], step_days=7),
            series("labor:unemployment", [4.0, 4.3], step_days=30),
            series("labor:payrolls", [150_000.0, 150_050.0], step_days=30),
            series("economy:gdp_real", [100.0, 100.2], step_days=90),
        )
    )
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_growth_labor_rules(observations, evidence=evidence)

    assert result["judgment"] == "growth_labor_cooling"
    assert {item["rule_id"] for item in result["rule_hits"]} >= {
        "claims_up_four_releases",
        "unemployment_rate_up",
        "payroll_growth_below_100k",
        "real_gdp_below_one_pct_saar",
    }


def test_liquidity_keeps_secured_and_unsecured_funding_spreads_separate() -> None:
    observations = [
        observation("liquidity:sofr", 4.55),
        observation("liquidity:bgcr", 4.50),
        observation("liquidity:tgcr", 4.48),
        observation("fed:effr", 4.41),
        observation("fed:obfr", 4.43),
        observation("fed:iorb", 4.40),
    ]
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_liquidity_funding_rules(evidence=evidence)
    secured = {item["concept_key"]: item for item in result["secured_funding_spreads"]}
    unsecured = {item["concept_key"]: item for item in result["unsecured_funding_spreads"]}

    assert set(secured) == {
        "derived:sofr_minus_iorb_bps",
        "derived:bgcr_minus_iorb_bps",
        "derived:tgcr_minus_iorb_bps",
    }
    assert set(unsecured) == {
        "derived:effr_minus_iorb_bps",
        "derived:obfr_minus_iorb_bps",
    }
    assert secured["derived:sofr_minus_iorb_bps"]["value"] == pytest.approx(15.0)
    assert unsecured["derived:effr_minus_iorb_bps"]["value"] == pytest.approx(1.0)
    assert secured["derived:sofr_minus_iorb_bps"]["sample"] == {
        "start": COMPUTED_DATE.isoformat(),
        "end": COMPUTED_DATE.isoformat(),
        "count": 2,
    }
    assert secured["derived:sofr_minus_iorb_bps"]["derivation"]["inputs"] == [
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
    assert result["judgment"] == "secured_funding_pressure"
    assert not (_all_keys(result) & {"score", "combined_score", "trade"})
    assert result["net_liquidity"]["status"] == "unavailable"


def test_funding_spread_rejects_unaligned_input_dates() -> None:
    observations = [
        observation("liquidity:sofr", 4.55),
        observation("fed:iorb", 4.40, observed_at=COMPUTED_DATE - timedelta(days=1)),
    ]
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_liquidity_funding_rules(evidence=evidence)
    spread = next(
        item for item in result["secured_funding_spreads"] if item["concept_key"] == "derived:sofr_minus_iorb_bps"
    )

    assert spread["status"] == "unavailable"
    assert spread["reason"] == "unaligned_input_dates"
    assert spread["value"] is None
    assert spread["observed_at"] is None
    assert spread["sample"] == {
        "start": (COMPUTED_DATE - timedelta(days=1)).isoformat(),
        "end": COMPUTED_DATE.isoformat(),
        "count": 2,
    }
    assert spread["derivation"]["inputs"] == [
        {
            "concept_key": "liquidity:sofr",
            "observed_at": COMPUTED_DATE.isoformat(),
            "value": 4.55,
        },
        {
            "concept_key": "fed:iorb",
            "observed_at": (COMPUTED_DATE - timedelta(days=1)).isoformat(),
            "value": 4.4,
        },
    ]
    assert result["judgment"] == "mixed"


def test_balance_sheet_rules_keep_changes_separate_and_expose_transparent_accounting_proxy() -> None:
    observations = flatten(
        (
            series(
                "liquidity:reserve_balances",
                [3_500_000.0, 3_480_000.0, 3_460_000.0, 3_440_000.0, 3_400_000.0],
                step_days=7,
            ),
            series(
                "liquidity:fed_assets", [7_500_000.0, 7_490_000.0, 7_480_000.0, 7_470_000.0, 7_450_000.0], step_days=7
            ),
            series("liquidity:tga", [700_000.0] * 20 + [750_000.0]),
            [
                observation("liquidity:on_rrp", 250.0),
                observation("liquidity:sofr", 4.40),
                observation("fed:iorb", 4.40),
                observation("fed:effr", 4.40),
            ],
        )
    )
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_liquidity_funding_rules(evidence=evidence)

    assert result["judgment"] == "balance_sheet_drain"
    assert {item["rule_id"] for item in result["rule_hits"]} >= {
        "reserve_balances_declining",
        "fed_assets_declining",
        "treasury_cash_rising",
        "reverse_repo_buffer_low",
    }
    assert result["net_liquidity"]["value"] == pytest.approx(6_450_000.0)
    assert result["net_liquidity"]["unit"] == "millions_usd"
    assert result["net_liquidity"]["claim_effect"] == "accounting_proxy_context_only"
    assert result["net_liquidity"]["sample"]["count"] == 3
    assert result["net_liquidity"]["derivation"]["formula"] == (
        "accounting proxy only: Fed assets - TGA - (RRP * 1000); no causal risk-asset inference"
    )
    assert result["net_liquidity"]["derivation"]["references"] == [
        "liquidity:fed_assets",
        "liquidity:tga",
        "liquidity:on_rrp",
    ]


def test_invalid_current_funding_metadata_cannot_create_a_spread() -> None:
    observations = [
        observation("liquidity:sofr", 4.70, data_quality="partial"),
        observation("fed:iorb", 4.40),
    ]
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_liquidity_funding_rules(evidence=evidence)
    sofr_spread = next(
        item for item in result["secured_funding_spreads"] if item["concept_key"] == "derived:sofr_minus_iorb_bps"
    )

    assert evidence["liquidity:sofr"]["status"] == "invalid"
    assert sofr_spread["status"] == "unavailable"
    assert sofr_spread["value"] is None


def _metric(result: dict[str, Any], concept_key: str) -> dict[str, Any]:
    return next(item for item in result["growth_metrics"] if item["concept_key"] == concept_key)


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _all_keys(item)}
    if isinstance(value, list | tuple):
        return {key for item in value for key in _all_keys(item)}
    return set()
