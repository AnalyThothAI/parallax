from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from gmgn_twitter_intel.domains.pulse_lab.interfaces import PULSE_RECOMMENDATION_SCHEMA_VERSION
from gmgn_twitter_intel.domains.pulse_lab.types.pulse_recommendation import (
    PulseRecommendationPayload,
    collect_factor_keys,
    payload_from_output,
    pulse_recommendation_agent_input,
    pulse_recommendation_agent_instructions,
    validate_pulse_recommendation_payload,
)

AVAILABLE_FACTOR_KEYS = {
    "attention_heat",
    "attention_heat.data_health",
    "attention_heat.raw_score",
    "attention_heat.score",
    "attention_heat.unique_authors",
    "attention_heat.weight",
    "composite",
    "composite.family_scores.attention_heat",
    "composite.family_scores.diffusion_quality",
    "composite.family_scores.semantic_quality",
    "composite.family_scores.timing_response",
    "composite.rank_score",
    "composite.recommended_decision",
    "data_health",
    "data_health.alpha",
    "data_health.identity",
    "data_health.market",
    "data_health.social",
    "diffusion_quality",
    "diffusion_quality.data_health",
    "diffusion_quality.independent_authors",
    "diffusion_quality.duplicate_text_share",
    "diffusion_quality.raw_score",
    "diffusion_quality.score",
    "diffusion_quality.weight",
    "gates",
    "gates.blocked_reasons",
    "gates.eligible_for_high_alert",
    "gates.max_decision",
    "normalization",
    "normalization.status",
    "semantic_quality",
    "semantic_quality.data_health",
    "semantic_quality.phase",
    "semantic_quality.raw_score",
    "semantic_quality.score",
    "semantic_quality.weight",
    "timing_response",
    "timing_response.data_health",
    "timing_response.price_change_status",
    "timing_response.raw_score",
    "timing_response.score",
    "timing_response.weight",
}


def _valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": PULSE_RECOMMENDATION_SCHEMA_VERSION,
        "recommendation": "research",
        "summary_zh": "PEPE 的社交扩散有效，但成交质量和重复文本风险仍需继续确认。",
        "primary_reasons": [
            {
                "factor_key": "attention_heat.unique_authors",
                "explanation_zh": "独立作者数量增加，扩散不只来自单一来源。",
            }
        ],
        "upgrade_conditions": [
            {
                "factor_key": "diffusion_quality.independent_authors",
                "operator": ">=",
                "value": 4,
                "description_zh": "独立作者扩散继续增加。",
            }
        ],
        "invalidation_conditions": [
            {
                "factor_key": "diffusion_quality.duplicate_text_share",
                "operator": ">=",
                "value": 0.5,
                "description_zh": "重复文本继续升高。",
            }
        ],
        "residual_risks": [
            {
                "factor_key": "diffusion_quality.duplicate_text_share",
                "description_zh": "重复文本比例仍可能放大噪声。",
            }
        ],
        "evidence_event_ids": ["event-1", "event-2", "event-1"],
        "confidence": 0.68,
    }
    payload.update(overrides)
    return payload


def test_valid_recommendation_passes_with_factor_and_event_backing() -> None:
    payload = validate_pulse_recommendation_payload(
        _valid_payload(),
        available_factor_keys=AVAILABLE_FACTOR_KEYS,
        input_source_event_ids={"event-1", "event-2", "event-3"},
        max_recommendation="research",
    )

    assert payload.schema_version == "pulse_recommendation_v1"
    assert payload.recommendation == "research"
    assert payload.evidence_event_ids == ["event-1", "event-2"]


def test_extra_fields_are_forbidden_on_payload_and_nested_items() -> None:
    with pytest.raises(ValidationError):
        PulseRecommendationPayload.model_validate({**_valid_payload(), "legacy_thesis": "nope"})

    bad = _valid_payload()
    bad["primary_reasons"] = [{**bad["primary_reasons"][0], "score": 99}]  # type: ignore[index]
    with pytest.raises(ValidationError):
        PulseRecommendationPayload.model_validate(bad)


def test_factor_keys_must_be_available_for_reasons_conditions_and_risks() -> None:
    with pytest.raises(ValueError, match="factor_key"):
        validate_pulse_recommendation_payload(
            _valid_payload(),
            available_factor_keys={"attention_heat", "diffusion_quality.independent_authors"},
            input_source_event_ids={"event-1", "event-2", "event-3"},
        )


def test_evidence_event_ids_are_sanitized_to_input_backed_ids() -> None:
    payload = validate_pulse_recommendation_payload(
        _valid_payload(evidence_event_ids=["event-1", "model-mutated-event"]),
        available_factor_keys=AVAILABLE_FACTOR_KEYS,
        input_source_event_ids=["event-1", "event-2"],
    )

    assert payload.evidence_event_ids == ["event-1"]


def test_evidence_event_ids_fall_back_to_first_input_event_when_model_copies_ids_badly() -> None:
    payload = validate_pulse_recommendation_payload(
        _valid_payload(evidence_event_ids=["model-mutated-event"]),
        available_factor_keys=AVAILABLE_FACTOR_KEYS,
        input_source_event_ids=["event-1", "event-2"],
    )

    assert payload.evidence_event_ids == ["event-1"]


def test_recommendation_cannot_exceed_gate_result_max_recommendation() -> None:
    with pytest.raises(ValueError, match="max_recommendation"):
        validate_pulse_recommendation_payload(
            _valid_payload(recommendation="trade_candidate"),
            available_factor_keys=AVAILABLE_FACTOR_KEYS,
            input_source_event_ids={"event-1", "event-2", "event-3"},
            max_recommendation="alert",
        )


def test_forbidden_trading_execution_language_is_neutralized() -> None:
    payload = validate_pulse_recommendation_payload(
        _valid_payload(summary_zh="满足条件后可以买入 PEPE。"),
        available_factor_keys=AVAILABLE_FACTOR_KEYS,
        input_source_event_ids={"event-1", "event-2", "event-3"},
    )

    assert payload.summary_zh == "满足条件后可以观察 PEPE。"


def test_payload_from_output_accepts_dict_and_model() -> None:
    from_dict = payload_from_output(_valid_payload())
    from_model = payload_from_output(from_dict)

    assert isinstance(from_dict, PulseRecommendationPayload)
    assert from_model is from_dict


def test_family_level_factor_keys_are_valid_but_still_bounded_to_available_context() -> None:
    payload = validate_pulse_recommendation_payload(
        _valid_payload(
            primary_reasons=[
                {
                    "factor_key": "attention_heat",
                    "explanation_zh": "热度 family 已经进入可解释集合。",
                }
            ],
            residual_risks=[
                {
                    "factor_key": "gates.blocked_reasons",
                    "description_zh": "硬门槛原因仍要作为风险边界。",
                }
            ],
        ),
        available_factor_keys=collect_factor_keys(_v2_factor_snapshot()),
        input_source_event_ids={"event-1", "event-2", "event-3"},
        max_recommendation="research",
    )

    assert payload.primary_reasons[0].factor_key == "attention_heat"
    assert payload.residual_risks[0].factor_key == "gates.blocked_reasons"


def test_condition_values_accept_structured_factor_maps() -> None:
    payload = validate_pulse_recommendation_payload(
        _valid_payload(
            invalidation_conditions=[
                {
                    "factor_key": "semantic_quality.direction_counts",
                    "operator": "==",
                    "value": {"bearish": 10, "neutral": 0, "bullish": 0},
                    "description_zh": "方向计数转弱会降低信号质量。",
                }
            ],
        ),
        available_factor_keys={*AVAILABLE_FACTOR_KEYS, "semantic_quality.direction_counts"},
        input_source_event_ids=["event-1", "event-2"],
    )

    assert payload.invalidation_conditions[0].value.model_dump() == {"bearish": 10, "neutral": 0, "bullish": 0}


def test_instructions_require_factor_backing_and_no_fabrication() -> None:
    instructions = pulse_recommendation_agent_instructions()

    assert "Do not invent facts" in instructions
    assert (
        "Every primary reason, upgrade condition, invalidation condition, and residual risk must cite a factor_key "
        "present in available_factor_keys"
    ) in instructions
    assert "Recommendation cannot upgrade beyond gate_result.max_recommendation" in instructions
    assert "Return typed output matching PulseRecommendationPayload" in instructions
    assert "buy" not in instructions.lower()
    assert "sell" not in instructions.lower()
    assert "买入" not in instructions
    assert "卖出" not in instructions


def test_agent_input_json_is_stable_and_contract_scoped() -> None:
    context = {
        "factor_snapshot": _v2_factor_snapshot(),
        "gate_result": {"max_recommendation": "research"},
        "available_factor_keys": ["manual.key_should_not_be_used"],
        "selected_posts": [{"event_id": "event-1", "text": "PEPE heat"}],
        "legacy_timeline": {"should": "not be passed"},
    }

    encoded = pulse_recommendation_agent_input(context)
    decoded = json.loads(encoded)

    assert encoded == pulse_recommendation_agent_input(context)
    assert decoded == {
        "available_factor_keys": [
            "attention_heat",
            "attention_heat.data_health",
            "attention_heat.raw_score",
            "attention_heat.score",
            "attention_heat.unique_authors",
            "attention_heat.weight",
            "composite",
            "composite.family_scores.attention_heat",
            "composite.family_scores.diffusion_quality",
            "composite.family_scores.semantic_quality",
            "composite.family_scores.timing_response",
            "composite.rank_score",
            "composite.recommended_decision",
            "data_health",
            "data_health.alpha",
            "data_health.identity",
            "data_health.market",
            "data_health.social",
            "diffusion_quality",
            "diffusion_quality.data_health",
            "diffusion_quality.duplicate_text_share",
            "diffusion_quality.independent_authors",
            "diffusion_quality.raw_score",
            "diffusion_quality.score",
            "diffusion_quality.weight",
            "gates",
            "gates.blocked_reasons",
            "gates.eligible_for_high_alert",
            "gates.max_decision",
            "normalization",
            "normalization.status",
            "semantic_quality",
            "semantic_quality.data_health",
            "semantic_quality.phase",
            "semantic_quality.raw_score",
            "semantic_quality.score",
            "semantic_quality.weight",
            "timing_response",
            "timing_response.data_health",
            "timing_response.price_change_status",
            "timing_response.raw_score",
            "timing_response.score",
            "timing_response.weight",
        ],
        "factor_snapshot": _v2_factor_snapshot(),
        "gate_result": {"max_recommendation": "research"},
        "selected_posts": [{"event_id": "event-1", "text": "PEPE heat"}],
        "task": "write_pulse_recommendation_v1",
    }


def test_collect_factor_keys_reads_family_facts_and_factors() -> None:
    assert collect_factor_keys(_v2_factor_snapshot()) == AVAILABLE_FACTOR_KEYS


def test_agent_input_rejects_legacy_v1_factor_snapshot() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        pulse_recommendation_agent_input(
            {
                "factor_snapshot": {
                    "schema_version": "token_factor_snapshot_v1",
                    "families": {"market_quality": {"facts": {"liquidity_usd": 12000}}},
                },
                "gate_result": {"max_recommendation": "research"},
                "selected_posts": [],
            }
        )


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda snapshot: snapshot["families"].__setitem__("market_quality", {"facts": {}}), "market_quality"),
        (lambda snapshot: snapshot.pop("normalization"), "normalization"),
        (lambda snapshot: snapshot.pop("provenance"), "provenance"),
        (lambda snapshot: snapshot.__setitem__("legacy_score", {"score": 100}), "legacy_score"),
    ],
)
def test_agent_input_rejects_malformed_v2_factor_snapshot(mutate, match: str) -> None:
    snapshot = _v2_factor_snapshot()
    mutate(snapshot)

    with pytest.raises(ValueError, match=match):
        pulse_recommendation_agent_input(
            {
                "factor_snapshot": snapshot,
                "gate_result": {"max_recommendation": "research"},
                "selected_posts": [],
            }
        )


def _v2_factor_snapshot() -> dict[str, object]:
    return {
        "schema_version": "token_factor_snapshot_v2_alpha_gated",
        "subject": {"target_type": "Asset", "target_id": "asset:pepe", "symbol": "PEPE"},
        "market": _market(),
        "gates": {"eligible_for_high_alert": True, "blocked_reasons": [], "max_decision": "high_alert"},
        "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
        "families": {
            "attention_heat": _family(76, 0.35, {"unique_authors": 4}, {}),
            "diffusion_quality": {
                "raw_score": 76,
                "score": 76,
                "weight": 0.3,
                "data_health": "ready",
                "facts": {"independent_authors": 4},
                "factors": {"duplicate_text_share": {"value": 0.12}},
            },
            "semantic_quality": _family(76, 0.25, {"phase": "ignition"}, {}),
            "timing_response": _family(76, 0.1, {"price_change_status": "ready"}, {}),
        },
        "normalization": {"status": "pending_cross_section"},
        "composite": {
            "rank_score": 76,
            "recommended_decision": "watch",
            "family_scores": {
                "attention_heat": 76,
                "diffusion_quality": 76,
                "semantic_quality": 76,
                "timing_response": 76,
            },
        },
        "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 1_700_000_000_000},
    }


def _family(score: int, weight: float, facts: dict[str, object], factors: dict[str, object]) -> dict[str, object]:
    return {
        "raw_score": score,
        "score": score,
        "weight": weight,
        "data_health": "ready",
        "facts": facts,
        "factors": factors,
    }


def _market() -> dict[str, object]:
    return {
        "market_status": "anchored",
        "price_change_status": "live_not_persisted",
        "provider": "okx",
        "anchor_price_usd": 0.42,
        "anchor_price_quote": None,
        "anchor_quote_symbol": "USD",
        "anchor_price_basis": "usd",
        "anchor_observed_at_ms": 1_700_000_000_000,
        "social_signal_start_ms": 1_700_000_000_000,
        "anchor_lag_ms": 0,
        "event_price_readiness": {"status": "ready"},
    }
