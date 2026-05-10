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


def _valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": PULSE_RECOMMENDATION_SCHEMA_VERSION,
        "recommendation": "research",
        "summary_zh": "PEPE 的社交扩散有效，但成交质量和重复文本风险仍需继续确认。",
        "primary_reasons": [
            {
                "factor_key": "social_attention.author_breadth",
                "explanation_zh": "独立作者数量增加，扩散不只来自单一来源。",
            }
        ],
        "upgrade_conditions": [
            {
                "factor_key": "market_quality.liquidity_usd",
                "operator": ">=",
                "value": 25000,
                "description_zh": "流动性恢复到最低观察地板。",
            }
        ],
        "invalidation_conditions": [
            {
                "factor_key": "timeline_quality.duplicate_share",
                "operator": ">=",
                "value": 0.5,
                "description_zh": "重复文本继续升高。",
            }
        ],
        "residual_risks": [
            {
                "factor_key": "timeline_quality.duplicate_share",
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
        available_factor_keys={
            "social_attention.author_breadth",
            "market_quality.liquidity_usd",
            "timeline_quality.duplicate_share",
        },
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
            available_factor_keys={"social_attention.author_breadth", "market_quality.liquidity_usd"},
            input_source_event_ids={"event-1", "event-2", "event-3"},
        )


def test_evidence_event_ids_must_be_from_input_events() -> None:
    with pytest.raises(ValueError, match="evidence_event_ids"):
        validate_pulse_recommendation_payload(
            _valid_payload(),
            available_factor_keys={
                "social_attention.author_breadth",
                "market_quality.liquidity_usd",
                "timeline_quality.duplicate_share",
            },
            input_source_event_ids={"event-1"},
        )


def test_recommendation_cannot_exceed_gate_result_max_recommendation() -> None:
    with pytest.raises(ValueError, match="max_recommendation"):
        validate_pulse_recommendation_payload(
            _valid_payload(recommendation="trade_candidate"),
            available_factor_keys={
                "social_attention.author_breadth",
                "market_quality.liquidity_usd",
                "timeline_quality.duplicate_share",
            },
            input_source_event_ids={"event-1", "event-2", "event-3"},
            max_recommendation="alert",
        )


def test_forbidden_trading_execution_language_raises() -> None:
    with pytest.raises(ValueError, match="execution instruction"):
        validate_pulse_recommendation_payload(
            _valid_payload(summary_zh="满足条件后可以买入 PEPE。"),
            available_factor_keys={
                "social_attention.author_breadth",
                "market_quality.liquidity_usd",
                "timeline_quality.duplicate_share",
            },
            input_source_event_ids={"event-1", "event-2", "event-3"},
        )


def test_payload_from_output_accepts_dict_and_model() -> None:
    from_dict = payload_from_output(_valid_payload())
    from_model = payload_from_output(from_dict)

    assert isinstance(from_dict, PulseRecommendationPayload)
    assert from_model is from_dict


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
        "factor_snapshot": {
            "schema_version": "token_factor_snapshot_v1",
            "families": {
                "market_quality": {
                    "facts": {"liquidity_usd": 12000},
                    "factors": {"holder_count": {"value": 500}},
                },
                "social_attention": {"facts": {"author_breadth": 4}},
            },
        },
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
            "market_quality.holder_count",
            "market_quality.liquidity_usd",
            "social_attention.author_breadth",
        ],
        "factor_snapshot": {
            "families": {
                "market_quality": {
                    "facts": {"liquidity_usd": 12000},
                    "factors": {"holder_count": {"value": 500}},
                },
                "social_attention": {"facts": {"author_breadth": 4}},
            },
            "schema_version": "token_factor_snapshot_v1",
        },
        "gate_result": {"max_recommendation": "research"},
        "selected_posts": [{"event_id": "event-1", "text": "PEPE heat"}],
        "task": "write_pulse_recommendation_v1",
    }


def test_collect_factor_keys_reads_family_facts_and_factors() -> None:
    assert collect_factor_keys(
        {
            "families": {
                "market_quality": {
                    "facts": {"liquidity_usd": 12000},
                    "factors": {"holder_count": {"value": 500}},
                },
                "social_attention": {
                    "facts": {"author_breadth": 4},
                    "factors": ["not", "a", "mapping"],
                },
            }
        }
    ) == {
        "market_quality.holder_count",
        "market_quality.liquidity_usd",
        "social_attention.author_breadth",
    }
