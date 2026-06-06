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


def _agent_config() -> NewsItemBriefAgentConfig:
    return NewsItemBriefAgentConfig(
        model="gpt-5-mini",
        artifact_version_hash="artifact-v1",
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        validator_version="validator-v1",
        guardrail_version="guardrail-v1",
    )


def _crypto_packet():
    return build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-1",
            "title": "Exchange lists ABC perpetuals",
            "summary": "ABC perpetual contract will be available today.",
            "body_text": "The exchange says ABC perpetual contract support is live for eligible users.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:item",
            "market_scope_json": ["crypto"],
            "agent_admission_json": {"status": "eligible", "reason": "provider_score_high"},
        },
        entities=[],
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
        agent_config=_agent_config(),
    )


def _equity_macro_packet():
    return build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-equity-macro",
            "title": "NVIDIA rallies as Treasury yields fall after CPI",
            "summary": "NVIDIA and AI semiconductor shares rose while CPI cooled and Treasury yields fell.",
            "body_text": "The CPI print lowered rate expectations and supported AI semiconductor risk appetite.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:equity-macro",
            "market_scope_json": ["us_equity", "ai_semiconductors", "macro_rates"],
            "agent_admission_json": {"status": "eligible", "reason": "market_wide_driver"},
        },
        entities=[
            {
                "entity_id": "entity-nvda",
                "raw_value": "NVIDIA",
                "normalized_value": "nvidia",
                "entity_type": "company",
                "confidence": 0.96,
            },
            {
                "entity_id": "entity-cpi",
                "raw_value": "CPI",
                "normalized_value": "cpi",
                "entity_type": "macro_factor",
                "confidence": 0.9,
            },
        ],
        token_mentions=[],
        fact_candidates=[
            {
                "fact_candidate_id": "fact-cpi",
                "event_type": "macro_data",
                "claim": "CPI cooled and Treasury yields fell while NVIDIA rose.",
                "realis": "actual",
                "validation_status": "accepted",
                "affected_targets_json": [{"symbol": "NVDA"}, {"label": "CPI"}],
                "evidence_quote": "CPI cooled and Treasury yields fell",
            }
        ],
        agent_config=_agent_config(),
    )


def _ready_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "event_type": "listing",
        "title_zh": "ABC 永续合约上线带来交易覆盖变化",
        "summary_zh": "交易所上线 ABC 永续合约，事件本身提高了该资产的可交易关注度。",
        "market_read_zh": "影响主要来自交易入口和衍生品关注度增加，但仍需核对流动性和真实成交反应。",
        "market_domains": ["crypto"],
        "transmission_paths": [
            {
                "market_domain": "crypto",
                "channel": "derivatives_access",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "永续合约上线扩大交易覆盖。",
                "evidence_refs": ["fact:fact-1"],
            }
        ],
        "bull_view": {
            "strength": "moderate",
            "thesis_zh": "上线永续合约可能扩大 ABC 的交易覆盖面。",
            "evidence_refs": ["fact:fact-1", "entity:token-1"],
        },
        "bear_view": {
            "strength": "weak",
            "thesis_zh": "公告没有提供成交深度或持续需求证据。",
            "evidence_refs": ["item:summary"],
        },
        "affected_entities": [
            {
                "label": "ABC",
                "symbol": "ABC",
                "name": "ABC Token",
                "entity_type": "crypto_asset",
                "market_domain": "crypto",
                "resolution_status": "known_symbol",
                "target_type": "asset",
                "target_id": "asset:abc",
                "impact_direction": "bullish",
                "reason_zh": "输入 entity lane 直接提到 ABC。",
                "evidence_refs": ["entity:token-1"],
            }
        ],
        "watch_triggers": ["后续公告补充市场深度或交易量证据"],
        "invalidation_conditions": ["公告被撤回或 entity 身份被证伪"],
        "data_gaps": [],
        "evidence_refs": ["item:summary", "fact:fact-1", "entity:token-1"],
    }
    payload.update(overrides)
    return payload


def test_valid_ready_payload_is_publishable_and_hashes_normalized_output() -> None:
    packet = _crypto_packet()
    result = validate_news_item_brief_output(payload=_ready_payload(), packet=packet, audit={})

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []
    assert result.payload is not None
    assert result.output_hash == json_sha256(result.payload)


def test_validation_rejects_unknown_evidence_refs() -> None:
    packet = _crypto_packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(evidence_refs=["item:summary", "fact:missing"]),
        packet=packet,
        audit={},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unknown_evidence_ref", "message": "fact:missing"} in result.errors


def test_validation_rejects_ready_without_source_backed_refs() -> None:
    packet = _crypto_packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(
            evidence_refs=[],
            bull_view={"strength": "moderate", "thesis_zh": "上线永续合约扩大交易覆盖。", "evidence_refs": []},
            bear_view={"strength": "absent", "thesis_zh": "", "evidence_refs": []},
            transmission_paths=[],
            affected_entities=[
                {
                    **_ready_payload()["affected_entities"][0],
                    "evidence_refs": [],
                }
            ],
        ),
        packet=packet,
        audit={},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert {
        "code": "missing_ready_evidence_ref",
        "message": "ready output requires at least one valid evidence ref",
    } in result.errors


def test_validation_rejects_unsupported_entities() -> None:
    packet = _crypto_packet()
    payload = _ready_payload(
        affected_entities=[
            *_ready_payload()["affected_entities"],
            {
                "label": "XYZ",
                "symbol": "XYZ",
                "name": "Unsupported Token",
                "entity_type": "crypto_asset",
                "market_domain": "crypto",
                "resolution_status": "unknown",
                "target_type": "asset",
                "target_id": "asset:xyz",
                "impact_direction": "bullish",
                "reason_zh": "模型输出了输入中没有来源支撑的资产。",
                "evidence_refs": ["item:summary"],
            },
        ],
    )

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unsupported_entity", "message": "XYZ"} in result.errors


@pytest.mark.parametrize(
    "phrase",
    [
        "建议开仓做多 ABC，并使用 5 倍杠杆。",
        "可以卖出 ABC，并设置止损和止盈。",
        "long this after the listing and use a 5x leverage order.",
        "Recommended position size is 5% with a target price.",
    ],
)
def test_validation_rejects_trading_instruction_language(phrase: str) -> None:
    packet = _crypto_packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(market_read_zh=phrase),
        packet=packet,
        audit={},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert any(error["code"] == "trading_instruction" for error in result.errors)


@pytest.mark.parametrize(
    "phrase",
    [
        "open interest 上升说明衍生品关注度增加，但方向仍需成交确认。",
        "Deleveraging and liquidations could increase near-term volatility.",
        "现有杠杆头寸的清算风险可能放大 sell pressure。",
        "The event may draw derivatives attention without proving spot demand.",
    ],
)
def test_validation_allows_descriptive_derivatives_mechanics(phrase: str) -> None:
    packet = _crypto_packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(market_read_zh=phrase),
        packet=packet,
        audit={},
    )

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


def test_valid_equity_and_macro_payload_is_publishable() -> None:
    packet = _equity_macro_packet()
    payload = {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "event_type": "macro_data",
        "title_zh": "CPI 降温支撑 AI 半导体风险偏好",
        "summary_zh": "CPI 降温和美债收益率回落，与 NVIDIA 及 AI 半导体上涨同向出现。",
        "market_read_zh": "宏观利率路径通过贴现率和成长股风险偏好传导到 AI 半导体板块。",
        "market_domains": ["macro_rates", "us_equity", "ai_semiconductors"],
        "transmission_paths": [
            {
                "market_domain": "macro_rates",
                "channel": "discount_rate",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "CPI 降温压低收益率预期，改善成长股贴现率叙事。",
                "evidence_refs": ["fact:fact-cpi"],
            }
        ],
        "bull_view": {
            "strength": "moderate",
            "thesis_zh": "收益率回落支持 AI 半导体估值弹性。",
            "evidence_refs": ["fact:fact-cpi", "entity:entity-nvda"],
        },
        "bear_view": {
            "strength": "weak",
            "thesis_zh": "单次 CPI 不能证明需求或盈利持续改善。",
            "evidence_refs": ["item:summary"],
        },
        "affected_entities": [
            {
                "label": "NVIDIA",
                "symbol": "NVDA",
                "name": "NVIDIA",
                "entity_type": "equity",
                "market_domain": "us_equity",
                "impact_direction": "bullish",
                "reason_zh": "新闻和 entity lane 均提到 NVIDIA。",
                "evidence_refs": ["entity:entity-nvda"],
            },
            {
                "label": "CPI",
                "entity_type": "macro_factor",
                "market_domain": "macro_rates",
                "impact_direction": "bullish",
                "reason_zh": "CPI 是本次宏观触发因素。",
                "evidence_refs": ["entity:entity-cpi"],
            },
        ],
        "watch_triggers": ["后续收益率和 AI 半导体成交是否延续"],
        "invalidation_conditions": ["后续通胀数据重新抬升利率预期"],
        "data_gaps": [],
        "evidence_refs": ["item:summary", "fact:fact-cpi", "entity:entity-nvda", "entity:entity-cpi"],
    }

    result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


def test_validation_rejects_unexpected_tool_or_handoff_audit() -> None:
    packet = _crypto_packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(),
        packet=packet,
        audit={"tool_calls": [{"name": "web"}], "handoffs": []},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unexpected_agent_action", "message": "tool_calls"} in result.errors
