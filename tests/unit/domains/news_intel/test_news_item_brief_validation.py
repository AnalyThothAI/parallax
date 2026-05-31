from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.news_intel.services.news_item_brief_input import (
    build_news_item_brief_input_packet,
)
from parallax.domains.news_intel.services.news_item_brief_validation import (
    validate_news_item_brief_output,
)
from parallax.domains.news_intel.types.news_item_brief import NewsItemBriefAgentConfig
from parallax.platform.agent_hashing import json_sha256


def _packet():
    return build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-1",
            "title": "Exchange lists ABC perpetuals",
            "summary": "ABC perpetual contract will be available today.",
            "body_text": "The exchange says ABC perpetual contract support is live for eligible users.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:item",
        },
        token_mentions=[
            {
                "mention_id": "token-1",
                "observed_symbol": "ABC",
                "resolution_status": "known_symbol",
                "target_type": "asset",
                "target_id": "asset:abc",
                "display_symbol": "ABC",
                "display_name": "ABC Token",
            }
        ],
        fact_candidates=[
            {
                "fact_candidate_id": "fact-1",
                "event_type": "listing",
                "claim": "Exchange lists ABC perpetuals.",
                "realis": "actual",
                "validation_status": "accepted",
                "affected_targets_json": [{"symbol": "ABC"}],
                "evidence_quote": "ABC perpetual contract support is live",
            }
        ],
        agent_config=NewsItemBriefAgentConfig(
            model="gpt-5-mini",
            artifact_version_hash="artifact-v1",
            prompt_version="prompt-v1",
            schema_version="schema-v1",
            validator_version="validator-v1",
            guardrail_version="guardrail-v1",
        ),
    )


def _ready_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "title_zh": "ABC 永续合约上线带来交易覆盖变化",
        "summary_zh": "交易所上线 ABC 永续合约，事件本身提高了该资产的可交易关注度。",
        "market_read_zh": "影响主要来自交易入口和衍生品关注度增加，但仍需核对流动性和真实成交反应。",
        "bull_view": {
            "strength": "moderate",
            "thesis_zh": "上线永续合约可能扩大 ABC 的交易覆盖面。",
            "evidence_refs": ["fact:fact-1", "token:token-1"],
        },
        "bear_view": {
            "strength": "weak",
            "thesis_zh": "公告没有提供成交深度或持续需求证据。",
            "evidence_refs": ["item:summary"],
        },
        "affected_assets": [
            {
                "symbol": "ABC",
                "name": "ABC Token",
                "resolution_status": "known_symbol",
                "target_type": "asset",
                "target_id": "asset:abc",
                "impact_direction": "bullish",
                "reason_zh": "输入 token lane 直接提到 ABC。",
                "evidence_refs": ["token:token-1"],
            }
        ],
        "watch_triggers": ["后续公告补充市场深度或交易量证据"],
        "invalidation_conditions": ["公告被撤回或 token 身份被证伪"],
        "data_gaps": [],
        "evidence_refs": ["item:summary", "fact:fact-1", "token:token-1"],
    }
    payload.update(overrides)
    return payload


def test_valid_ready_payload_is_publishable_and_hashes_normalized_output() -> None:
    packet = _packet()
    result = validate_news_item_brief_output(payload=_ready_payload(), packet=packet, audit={})

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []
    assert result.payload is not None
    assert result.output_hash == json_sha256(result.payload)


def test_validation_rejects_payload_when_unsupported_asset_gap_exceeds_schema_cap() -> None:
    packet = _packet()
    existing_gaps = [{"description_zh": f"已有数据缺口 {index}", "severity": "low"} for index in range(12)]
    payload = _ready_payload(
        affected_assets=[
            *_ready_payload()["affected_assets"],
            {
                "symbol": "XYZ",
                "name": "Unsupported Token",
                "resolution_status": "unknown",
                "target_type": "asset",
                "target_id": "asset:xyz",
                "impact_direction": "bullish",
                "reason_zh": "模型输出了输入中没有来源支撑的资产。",
                "evidence_refs": ["item:summary"],
            },
        ],
        data_gaps=existing_gaps,
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is False
    assert result.status == "failed"
    assert result.payload is None
    assert any(error["code"] == "schema_invalid" for error in result.errors)


def test_valid_insufficient_payload_is_publishable_when_data_gaps_explain_missing_evidence() -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload={
            "status": "insufficient",
            "direction": "neutral",
            "decision_class": "watch",
            "summary_zh": "",
            "market_read_zh": "",
            "bull_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
            "bear_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
            "affected_assets": [],
            "watch_triggers": [],
            "invalidation_conditions": [],
            "data_gaps": [{"description_zh": "缺少官方来源和成交反应证据。", "severity": "high"}],
            "evidence_refs": ["item:title"],
        },
        packet=packet,
        audit={},
    )

    assert result.publishable is True
    assert result.status == "insufficient"
    assert result.payload is not None


def test_validation_rejects_fake_evidence_ref() -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(evidence_refs=["item:summary", "fact:missing"]),
        packet=packet,
        audit={},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert result.payload is None
    assert {"code": "unknown_evidence_ref", "message": "fact:missing"} in result.errors


def test_validation_rejects_forbidden_execution_language() -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(market_read_zh="可以开仓做多 ABC。"),
        packet=packet,
        audit={},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert any(error["code"] == "forbidden_execution_language" for error in result.errors)


def test_validation_rejects_forbidden_execution_language_in_title() -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(title_zh="ABC 可以开仓做多"),
        packet=packet,
        audit={},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert any(error["code"] == "forbidden_execution_language" for error in result.errors)


def test_validation_allows_descriptive_sell_pressure_language() -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(market_read_zh="投资者可能预期价格下跌而提前卖出，形成短期抛售压力。"),
        packet=packet,
        audit={},
    )

    assert result.publishable is True
    assert result.status == "ready"


@pytest.mark.parametrize(
    "phrase",
    [
        "This includes order instructions for ABC.",
        "Risk depends on position size.",
        "There is no execution permission in the source.",
        "This should not be treated as portfolio advice.",
    ],
)
def test_validation_rejects_forbidden_execution_language_from_plan_terms(phrase: str) -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(market_read_zh=phrase),
        packet=packet,
        audit={},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert any(error["code"] == "forbidden_execution_language" for error in result.errors)


@pytest.mark.parametrize(
    "side_patch",
    [
        {"bull_view": {"strength": "moderate", "thesis_zh": "", "evidence_refs": ["fact:fact-1"]}},
        {"bull_view": {"strength": "moderate", "thesis_zh": "上线永续合约扩大交易覆盖。", "evidence_refs": []}},
    ],
)
def test_validation_rejects_non_neutral_ready_side_without_complete_thesis_and_evidence(
    side_patch: dict[str, Any],
) -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(
            bear_view={"strength": "absent", "thesis_zh": "", "evidence_refs": []},
            **side_patch,
        ),
        packet=packet,
        audit={},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert any(error["code"] == "ready_invariant" for error in result.errors)


def test_validation_rejects_unexpected_tool_or_handoff_audit() -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(),
        packet=packet,
        audit={"tool_calls": [{"name": "web"}], "handoffs": []},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unexpected_agent_action", "message": "tool_calls"} in result.errors
