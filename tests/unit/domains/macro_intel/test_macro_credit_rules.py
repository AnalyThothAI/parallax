from __future__ import annotations

from datetime import date, timedelta

import pytest

from parallax.domains.macro_intel.services.macro_credit_rules import (
    build_credit_rules,
    classify_credit_state,
    treasury_spread_quadrant,
)
from parallax.domains.macro_intel.services.macro_evidence import build_evidence_index
from parallax.domains.macro_intel.services.macro_evidence_snapshot import build_macro_evidence_snapshot
from tests.unit.domains.macro_intel.macro_evidence_test_support import (
    COMPUTED_AT_MS,
    COMPUTED_DATE,
    flatten,
    observation,
    series,
)


def test_credit_stage_and_direction_are_separate_and_quadrant_is_explicit() -> None:
    observations = flatten(
        (
            series("credit:hy_oas", [4.8] * 20 + [5.5]),
            series("credit:ig_oas", [1.2] * 20 + [1.4]),
            series("credit:hy_ccc_oas", [8.0] * 20 + [11.0]),
            series("credit:hy_bb_oas", [4.0] * 20 + [4.5]),
            series("rates:dgs10", [4.5] * 20 + [4.2]),
        )
    )
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_credit_rules(evidence=evidence)

    assert result["credit_state"] == {
        "status": "supported",
        "stage": "broadening",
        "direction": "widening",
        "evidence_refs": ["credit:hy_oas", "credit:ig_oas", "credit:hy_ccc_oas"],
        "rule_version": "macro_credit_state_v1",
    }
    assert result["treasury_spread_quadrant"] == {
        "status": "supported",
        "quadrant": "yields_down_spreads_wider",
        "yield_change": pytest.approx(-0.3),
        "spread_change": pytest.approx(70.0),
        "change_window": "20_sessions",
        "evidence_refs": ["rates:dgs10", "credit:hy_oas"],
        "rule_version": "macro_treasury_spread_quadrant_v1",
    }
    assert {item["rule_id"] for item in result["rule_hits"]} == {
        "credit_stage_broadening",
        "credit_spreads_widening",
        "growth_scare_quadrant",
    }
    assert result["ccc_minus_bb_oas"]["value"] == pytest.approx(650.0)
    assert result["ccc_minus_bb_oas"]["unit"] == "basis_points"
    assert result["ccc_minus_bb_oas"]["derivation"] == {
        "formula": "CCC OAS - BB OAS",
        "inputs": [
            {"concept_key": "credit:hy_ccc_oas", "observed_at": "2026-07-23", "value": 1100.0},
            {"concept_key": "credit:hy_bb_oas", "observed_at": "2026-07-23", "value": 450.0},
        ],
        "references": ["credit:hy_ccc_oas", "credit:hy_bb_oas"],
    }


def test_credit_oas_is_normalized_to_basis_points_while_effective_yield_stays_percent() -> None:
    observations = flatten(
        (
            series("credit:hy_oas", [4.8] * 20 + [5.5]),
            series("credit:hy_yield", [7.0] * 20 + [7.4]),
        )
    )
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    assert evidence["credit:hy_oas"]["value"] == pytest.approx(550.0)
    assert evidence["credit:hy_oas"]["change"] == pytest.approx(70.0)
    assert evidence["credit:hy_oas"]["unit"] == "basis_points"
    assert evidence["credit:hy_oas"]["derivation"]["formula"] == "source_percent * 100"
    assert evidence["credit:hy_oas"]["derivation"]["inputs"][-1]["value"] == pytest.approx(5.5)
    assert evidence["credit:hy_yield"]["value"] == pytest.approx(7.4)
    assert evidence["credit:hy_yield"]["unit"] == "percent"


def test_narrow_aggregate_spreads_with_extreme_ccc_minus_bb_remain_tail_stress() -> None:
    observations = flatten(
        (
            series("credit:ig_oas", [0.90] * 20 + [0.78]),
            series("credit:hy_oas", [3.00] * 20 + [2.69]),
            series("credit:hy_bb_oas", [1.70] * 20 + [1.58]),
            series("credit:hy_b_oas", [3.10] * 20 + [2.86]),
            series("credit:hy_ccc_oas", [10.20] * 20 + [9.78]),
            [observation("credit:nfci", -0.55)],
        )
    )
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_credit_rules(evidence=evidence)

    assert evidence["credit:ig_oas"]["value"] == pytest.approx(78.0)
    assert evidence["credit:hy_oas"]["value"] == pytest.approx(269.0)
    assert result["ccc_minus_bb_oas"]["value"] == pytest.approx(820.0)
    assert result["credit_state"] == {
        "status": "supported",
        "stage": "tail_stress",
        "direction": "narrowing",
        "evidence_refs": [
            "credit:hy_oas",
            "credit:ig_oas",
            "credit:hy_ccc_oas",
            "credit:hy_bb_oas",
        ],
        "rule_version": "macro_credit_state_v1",
    }
    rule_ids = {item["rule_id"] for item in result["rule_hits"]}
    assert "ccc_minus_bb_at_least_750bps" in rule_ids
    assert "credit_stage_tail_stress" in rule_ids
    assert "credit_spreads_narrowing" in rule_ids
    assert not ({"credit_stage_broadening", "credit_stage_systemic_tightening"} & rule_ids)


@pytest.mark.parametrize(
    ("hy_values", "ig_values", "ccc_values", "expected_stage", "expected_direction"),
    [
        ([4.4] * 20 + [4.5], [1.15] * 20 + [1.2], [9.5] * 20 + [10.5], "tail_stress", "widening"),
        ([6.0] * 20 + [5.5], [1.7] * 20 + [1.5], [11.0] * 20 + [9.5], "repairing", "narrowing"),
        ([4.0] * 20 + [4.0], [1.0] * 20 + [1.0], [6.0] * 20 + [6.0], "contained", "stable"),
    ],
)
def test_credit_state_uses_approved_stage_enum(
    hy_values: list[float],
    ig_values: list[float],
    ccc_values: list[float],
    expected_stage: str,
    expected_direction: str,
) -> None:
    observations = flatten(
        (
            series("credit:hy_oas", hy_values),
            series("credit:ig_oas", ig_values),
            series("credit:hy_ccc_oas", ccc_values),
        )
    )
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    state = classify_credit_state(evidence)

    assert state["stage"] == expected_stage
    assert state["direction"] == expected_direction
    assert state["direction"] in {"widening", "narrowing", "stable", "insufficient_evidence"}
    assert state["stage"] in {
        "contained",
        "tail_stress",
        "broadening",
        "systemic_tightening",
        "repairing",
        "insufficient_evidence",
    }


def test_missing_history_makes_credit_state_and_quadrant_insufficient() -> None:
    observations = [
        observation("credit:hy_oas", 5.0),
        observation("credit:ig_oas", 1.5),
        observation("credit:hy_ccc_oas", 10.0),
        observation("rates:dgs10", 4.2),
    ]
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    state = classify_credit_state(evidence)
    quadrant = treasury_spread_quadrant(evidence)

    assert state["stage"] == "insufficient_evidence"
    assert state["direction"] == "insufficient_evidence"
    assert quadrant["status"] == "insufficient_evidence"
    assert quadrant["quadrant"] == "insufficient_evidence"


def test_narrowing_direction_uses_narrowing_rule_id_without_tightening_alias() -> None:
    observations = flatten(
        (
            series("credit:hy_oas", [6.0] * 20 + [5.5]),
            series("credit:ig_oas", [1.7] * 20 + [1.5]),
            series("credit:hy_ccc_oas", [11.0] * 20 + [9.5]),
        )
    )
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_credit_rules(evidence=evidence)
    rule_ids = {item["rule_id"] for item in result["rule_hits"]}

    assert result["credit_state"]["direction"] == "narrowing"
    assert "credit_spreads_narrowing" in rule_ids
    assert "credit_spreads_tightening" not in rule_ids


@pytest.mark.parametrize(
    ("bb_end", "bb_step_days", "expected_reason"),
    [
        (COMPUTED_DATE - timedelta(days=1), 1, "unaligned_input_dates"),
        (COMPUTED_DATE, 2, "unaligned_sample_endpoints"),
    ],
)
def test_ccc_minus_bb_and_tail_claim_fail_closed_when_inputs_are_unaligned(
    bb_end: date,
    bb_step_days: int,
    expected_reason: str,
) -> None:
    observations = flatten(
        (
            series("credit:hy_oas", [2.69] * 21),
            series("credit:ig_oas", [0.78] * 21),
            series("credit:hy_ccc_oas", [9.78] * 21),
            series("credit:hy_bb_oas", [1.58] * 21, end=bb_end, step_days=bb_step_days),
        )
    )
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_credit_rules(evidence=evidence)

    assert result["ccc_minus_bb_oas"]["status"] == "unavailable"
    assert result["ccc_minus_bb_oas"]["reason"] == expected_reason
    assert result["ccc_minus_bb_oas"]["value"] is None
    assert result["ccc_minus_bb_oas"]["change"] is None
    assert result["credit_state"]["stage"] == "contained"
    assert "credit:hy_bb_oas" not in result["credit_state"]["evidence_refs"]
    assert "ccc_minus_bb_at_least_750bps" not in {item["rule_id"] for item in result["rule_hits"]}


@pytest.mark.parametrize(
    ("ig_end", "ig_step_days"),
    [
        (COMPUTED_DATE - timedelta(days=1), 1),
        (COMPUTED_DATE, 2),
    ],
)
def test_hy_ig_credit_state_claim_is_insufficient_when_inputs_are_unaligned(
    ig_end: date,
    ig_step_days: int,
) -> None:
    observations = flatten(
        (
            series("credit:hy_oas", [4.8] * 20 + [5.5]),
            series("credit:ig_oas", [1.2] * 20 + [1.4], end=ig_end, step_days=ig_step_days),
            series("credit:hy_ccc_oas", [8.0] * 20 + [9.0]),
        )
    )
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_credit_rules(evidence=evidence)

    assert result["credit_state"] == {
        "status": "insufficient_evidence",
        "stage": "insufficient_evidence",
        "direction": "insufficient_evidence",
        "evidence_refs": ["credit:hy_oas", "credit:ig_oas", "credit:hy_ccc_oas"],
        "rule_version": "macro_credit_state_v1",
    }
    direction_rule_ids = {"credit_spreads_widening", "credit_spreads_narrowing"}
    assert not (direction_rule_ids & {item["rule_id"] for item in result["rule_hits"]})


@pytest.mark.parametrize(
    ("dgs10_end", "dgs10_step_days"),
    [
        (COMPUTED_DATE - timedelta(days=1), 1),
        (COMPUTED_DATE, 2),
    ],
)
def test_dgs10_hy_quadrant_claim_is_insufficient_when_inputs_are_unaligned(
    dgs10_end: date,
    dgs10_step_days: int,
) -> None:
    observations = flatten(
        (
            series("credit:hy_oas", [4.8] * 20 + [5.5]),
            series("rates:dgs10", [4.5] * 20 + [4.2], end=dgs10_end, step_days=dgs10_step_days),
        )
    )
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    quadrant = treasury_spread_quadrant(evidence)

    assert quadrant == {
        "status": "insufficient_evidence",
        "quadrant": "insufficient_evidence",
        "yield_change": pytest.approx(-0.3),
        "spread_change": pytest.approx(70.0),
        "change_window": "20_sessions",
        "evidence_refs": ["rates:dgs10", "credit:hy_oas"],
        "rule_version": "macro_treasury_spread_quadrant_v1",
    }


def test_credit_page_exposes_exact_six_evidence_layers() -> None:
    page = build_macro_evidence_snapshot([], computed_at_ms=COMPUTED_AT_MS)["credit"]

    assert {
        "aggregate_spreads",
        "rating_tail",
        "effective_yields",
        "credit_supply",
        "realized_damage",
        "financial_conditions_liquidity",
    } <= set(page)
    assert page["unavailable_evidence"] == [
        {"capability": "trace_transactions", "status": "not_assessed", "reason": "source_not_ingested"},
        {"capability": "etf_premium_discount", "status": "not_assessed", "reason": "source_not_ingested"},
        {"capability": "dealer_inventory", "status": "not_assessed", "reason": "source_not_ingested"},
    ]
