from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.macro_intel.services.macro_evidence import (
    derived_evidence,
    evidence_change,
    evidence_value,
    rule_hit,
)

_CCC_MINUS_BB_TAIL_STRESS_BPS = 750.0


def build_credit_rules(*, evidence: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    credit_state = classify_credit_state(evidence)
    quadrant = treasury_spread_quadrant(evidence)
    ccc_minus_bb_oas = _ccc_minus_bb_oas(evidence)
    rule_hits = _credit_rule_hits(credit_state=credit_state, quadrant=quadrant)
    return {
        "judgment": str(credit_state["stage"]),
        "rule_hits": rule_hits,
        "credit_state": credit_state,
        "treasury_spread_quadrant": quadrant,
        "ccc_minus_bb_oas": ccc_minus_bb_oas,
    }


def classify_credit_state(evidence: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    hy = evidence_value(evidence, "credit:hy_oas")
    ig = evidence_value(evidence, "credit:ig_oas")
    ccc = evidence_value(evidence, "credit:hy_ccc_oas")
    bb = evidence_value(evidence, "credit:hy_bb_oas")
    hy_change = evidence_change(evidence, "credit:hy_oas")
    ig_change = evidence_change(evidence, "credit:ig_oas")
    ccc_change = evidence_change(evidence, "credit:hy_ccc_oas")
    bbb_change = evidence_change(evidence, "credit:bbb_oas")
    nfci = evidence_value(evidence, "credit:nfci")
    required = {"credit:hy_oas": hy, "credit:ig_oas": ig, "credit:hy_ccc_oas": ccc}
    evidence_refs = list(required)
    if hy is None or ig is None or ccc is None or hy_change is None or ig_change is None:
        return {
            "status": "insufficient_evidence",
            "stage": "insufficient_evidence",
            "direction": "insufficient_evidence",
            "evidence_refs": evidence_refs,
            "rule_version": "macro_credit_state_v1",
        }
    if _comparison_alignment_reason(evidence, "credit:hy_oas", "credit:ig_oas") is not None:
        return {
            "status": "insufficient_evidence",
            "stage": "insufficient_evidence",
            "direction": "insufficient_evidence",
            "evidence_refs": evidence_refs,
            "rule_version": "macro_credit_state_v1",
        }
    if hy_change >= 25 or ig_change >= 10 or (ccc_change is not None and ccc_change >= 50):
        direction = "widening"
    elif hy_change <= -25 and ig_change <= -10:
        direction = "narrowing"
    else:
        direction = "stable"
    prior_hy = hy - hy_change
    prior_ccc = ccc - ccc_change if ccc_change is not None else None
    ccc_minus_bb = (
        ccc - bb
        if bb is not None and _comparison_alignment_reason(evidence, "credit:hy_ccc_oas", "credit:hy_bb_oas") is None
        else None
    )
    tail_stress = (
        ccc >= 1000
        or (ccc_minus_bb is not None and ccc_minus_bb >= _CCC_MINUS_BB_TAIL_STRESS_BPS)
        or (ccc_change is not None and ccc_change >= 75 and hy_change < 25)
    )
    aggregate_broadening = hy >= 500 and (ig >= 150 or ig_change >= 10 or (bbb_change is not None and bbb_change >= 10))
    if hy >= 700 and (ig >= 200 or (nfci is not None and nfci >= 0.5)):
        stage = "systemic_tightening"
        evidence_refs.extend(["credit:nfci"] if nfci is not None else [])
    elif direction == "narrowing" and tail_stress:
        stage = "tail_stress"
        if ccc_minus_bb is not None and ccc_minus_bb >= _CCC_MINUS_BB_TAIL_STRESS_BPS:
            evidence_refs.append("credit:hy_bb_oas")
    elif direction == "narrowing" and (prior_hy >= 500 or (prior_ccc is not None and prior_ccc >= 1000)):
        stage = "repairing"
    elif aggregate_broadening:
        stage = "broadening"
        evidence_refs.extend(["credit:bbb_oas"] if bbb_change is not None else [])
    elif tail_stress:
        stage = "tail_stress"
        if ccc_minus_bb is not None and ccc_minus_bb >= _CCC_MINUS_BB_TAIL_STRESS_BPS:
            evidence_refs.append("credit:hy_bb_oas")
    else:
        stage = "contained"
    return {
        "status": "supported",
        "stage": stage,
        "direction": direction,
        "evidence_refs": list(dict.fromkeys(evidence_refs)),
        "rule_version": "macro_credit_state_v1",
    }


def treasury_spread_quadrant(evidence: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    yield_change = evidence_change(evidence, "rates:dgs10")
    spread_change = evidence_change(evidence, "credit:hy_oas")
    evidence_refs = ["rates:dgs10", "credit:hy_oas"]
    if (
        yield_change is None
        or spread_change is None
        or _comparison_alignment_reason(evidence, "rates:dgs10", "credit:hy_oas") is not None
    ):
        return {
            "status": "insufficient_evidence",
            "quadrant": "insufficient_evidence",
            "yield_change": yield_change,
            "spread_change": spread_change,
            "change_window": "20_sessions",
            "evidence_refs": evidence_refs,
            "rule_version": "macro_treasury_spread_quadrant_v1",
        }
    yield_direction = _direction(yield_change, threshold=0.05, positive="up", negative="down")
    spread_direction = _direction(spread_change, threshold=5, positive="wider", negative="tighter")
    if yield_direction == "stable" or spread_direction == "stable":
        quadrant = "stable_or_mixed"
    else:
        quadrant = f"yields_{yield_direction}_spreads_{spread_direction}"
    return {
        "status": "supported",
        "quadrant": quadrant,
        "yield_change": round(yield_change, 10),
        "spread_change": round(spread_change, 10),
        "change_window": "20_sessions",
        "evidence_refs": evidence_refs,
        "rule_version": "macro_treasury_spread_quadrant_v1",
    }


def _credit_rule_hits(
    *,
    credit_state: Mapping[str, Any],
    quadrant: Mapping[str, Any],
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    stage = str(credit_state.get("stage") or "")
    direction = str(credit_state.get("direction") or "")
    stage_refs = _string_list(credit_state.get("evidence_refs"))
    if stage not in {"", "contained", "insufficient_evidence"}:
        hits.append(rule_hit(f"credit_stage_{stage}", "trigger", stage_refs))
    if stage == "tail_stress" and "credit:hy_bb_oas" in stage_refs:
        hits.append(
            rule_hit(
                "ccc_minus_bb_at_least_750bps",
                "trigger",
                ["credit:hy_ccc_oas", "credit:hy_bb_oas"],
            )
        )
    if direction == "widening":
        hits.append(rule_hit("credit_spreads_widening", "confirmation", ["credit:hy_oas", "credit:ig_oas"]))
    elif direction == "narrowing":
        hits.append(rule_hit("credit_spreads_narrowing", "invalidation", ["credit:hy_oas", "credit:ig_oas"]))
    quadrant_name = str(quadrant.get("quadrant") or "")
    if quadrant_name == "yields_up_spreads_wider":
        hits.append(rule_hit("yields_up_spreads_wider", "confirmation", ["rates:dgs10", "credit:hy_oas"]))
    elif quadrant_name == "yields_down_spreads_wider":
        hits.append(rule_hit("growth_scare_quadrant", "confirmation", ["rates:dgs10", "credit:hy_oas"]))
    return hits


def _ccc_minus_bb_oas(evidence: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    ccc = evidence_value(evidence, "credit:hy_ccc_oas")
    bb = evidence_value(evidence, "credit:hy_bb_oas")
    ccc_change = evidence_change(evidence, "credit:hy_ccc_oas")
    bb_change = evidence_change(evidence, "credit:hy_bb_oas")
    concept_values = (("credit:hy_ccc_oas", ccc), ("credit:hy_bb_oas", bb))
    items = [evidence.get(key) or {} for key, _ in concept_values]
    observed_dates = [str(item.get("observed_at") or "") for item in items if item.get("observed_at")]
    sample_starts = [endpoint for item in items if (endpoint := _sample_endpoint(item, "start")) is not None]
    sample_ends = [endpoint for item in items if (endpoint := _sample_endpoint(item, "end")) is not None]
    alignment_reason = _comparison_alignment_reason(
        evidence,
        "credit:hy_ccc_oas",
        "credit:hy_bb_oas",
    )
    inputs_available = ccc is not None and bb is not None
    aligned = inputs_available and alignment_reason is None
    return derived_evidence(
        concept_key="derived:credit_ccc_minus_bb_oas",
        role="confirmation",
        value=ccc - bb if aligned and ccc is not None and bb is not None else None,
        unit="basis_points",
        change=(ccc_change - bb_change if aligned and ccc_change is not None and bb_change is not None else None),
        change_window="20_sessions",
        observed_at=observed_dates[0] if aligned else None,
        frequency="daily",
        source_name="derived",
        series_key="derived:credit_ccc_minus_bb_oas",
        sample_start=min(sample_starts) if sample_starts else None,
        sample_end=max(sample_ends) if sample_ends else None,
        sample_count=sum(
            1
            for item, (_, value) in zip(items, concept_values, strict=True)
            if value is not None and item.get("observed_at")
        ),
        criticality="optional",
        claim_effect="rating_dispersion",
        formula="CCC OAS - BB OAS",
        inputs=[
            {
                "concept_key": concept_key,
                "observed_at": str(item.get("observed_at") or "") or None,
                "value": value,
            }
            for item, (concept_key, value) in zip(items, concept_values, strict=True)
        ],
        references=["credit:hy_ccc_oas", "credit:hy_bb_oas"],
        status="available" if aligned else "unavailable",
        reason=(None if aligned else "missing_rating_spread" if not inputs_available else alignment_reason),
    )


def _comparison_alignment_reason(
    evidence: Mapping[str, Mapping[str, Any]],
    left_key: str,
    right_key: str,
) -> str | None:
    items = [evidence.get(key) or {} for key in (left_key, right_key)]
    observed_dates = [str(item.get("observed_at") or "") or None for item in items]
    if any(observed_at is None for observed_at in observed_dates) or len(set(observed_dates)) != 1:
        return "unaligned_input_dates"
    sample_endpoints = [(_sample_endpoint(item, "start"), _sample_endpoint(item, "end")) for item in items]
    if any(start is None or end is None for start, end in sample_endpoints):
        return "unaligned_sample_endpoints"
    if sample_endpoints[0] != sample_endpoints[1]:
        return "unaligned_sample_endpoints"
    return None


def _sample_endpoint(item: Mapping[str, Any], name: str) -> str | None:
    sample = item.get("sample")
    if not isinstance(sample, Mapping):
        return None
    return str(sample.get(name) or "") or None


def _direction(
    value: float,
    *,
    threshold: float,
    positive: str,
    negative: str,
) -> str:
    if value > threshold:
        return positive
    if value < -threshold:
        return negative
    return "stable"


def _string_list(value: object) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [str(item) for item in value if str(item)]
    return []


__all__ = ["build_credit_rules", "classify_credit_state", "treasury_spread_quadrant"]
