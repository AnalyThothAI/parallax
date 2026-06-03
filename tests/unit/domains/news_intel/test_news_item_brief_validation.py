from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.news_intel.services.news_item_brief_input import (
    build_news_item_brief_input_packet,
)
from parallax.domains.news_intel.services.news_item_brief_validation import (
    validate_news_item_brief_output,
)
from parallax.domains.news_intel.types.news_item_brief import NewsItemBriefAgentConfig, NewsResearchToolResult
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
        "novelty_status": "new",
        "confirmation_state": "single_source",
        "title_zh": "ABC 永续合约上线带来交易覆盖变化",
        "summary_zh": "交易所上线 ABC 永续合约，事件本身提高了该资产的可交易关注度。",
        "market_read_zh": "影响主要来自交易入口和衍生品关注度增加，但仍需核对流动性和真实成交反应。",
        "source_consensus_zh": "当前是单一来源和输入事实候选支撑。",
        "retrieval_notes_zh": "已基于输入包和本地研究上下文归纳。",
        "retrieval_evidence_refs": ["item:summary", "fact:fact-1"],
        "research_todos_zh": ["跟踪后续成交和公告更新"],
        "used_tool_call_ids": [],
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


def test_validation_caps_unsupported_asset_gaps_instead_of_blocking_publish() -> None:
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

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []
    assert result.payload is not None
    assert result.payload["affected_assets"] == _ready_payload()["affected_assets"]
    assert len(result.payload["data_gaps"]) == 12


def test_valid_insufficient_payload_is_publishable_when_data_gaps_explain_missing_evidence() -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload={
            "status": "insufficient",
            "direction": "neutral",
            "decision_class": "watch",
            "novelty_status": "unclear",
            "confirmation_state": "unclear",
            "title_zh": "",
            "summary_zh": "",
            "market_read_zh": "",
            "source_consensus_zh": "缺少足够独立确认。",
            "retrieval_notes_zh": "检索证据不足。",
            "retrieval_evidence_refs": [],
            "research_todos_zh": ["等待更多来源确认"],
            "used_tool_call_ids": [],
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


def test_validation_allows_unknown_evidence_refs_without_blocking_publish() -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(evidence_refs=["item:summary", "fact:missing"]),
        packet=packet,
        audit={},
    )

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []
    assert result.payload is not None
    assert result.payload["evidence_refs"] == ["item:summary", "fact:missing"]


def test_validation_allows_execution_language_without_blocking_publish() -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(market_read_zh="可以开仓做多 ABC。"),
        packet=packet,
        audit={},
    )

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


def test_validation_allows_explicit_leveraged_language_without_blocking_publish() -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(market_read_zh="建议做多并使用 5 倍杠杆。"),
        packet=packet,
        audit={},
    )

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


def test_validation_allows_buy_crypto_product_name() -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(market_read_zh="公告提到交易所的 Buy Crypto 产品入口，但没有给出交易执行建议。"),
        packet=packet,
        audit={},
    )

    assert result.publishable is True
    assert result.status == "ready"


def test_validation_allows_execution_language_in_title_without_blocking_publish() -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(title_zh="ABC 可以开仓做多"),
        packet=packet,
        audit={},
    )

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


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
        "DeFi 杠杆解除压力可能造成 WETH 和 wstETH 的短期抛售压力。",
        "永续合约暂停可能导致剩余持仓者集中平仓。",
        "合约上线后需关注杠杆机制带来的双向波动风险。",
        "多头仓位拥挤会放大清算和回撤风险。",
    ],
)
def test_validation_allows_descriptive_derivatives_and_position_language(phrase: str) -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(market_read_zh=phrase),
        packet=packet,
        audit={},
    )

    assert result.publishable is True
    assert result.status == "ready"


@pytest.mark.parametrize(
    "phrase",
    [
        "This includes order instructions for ABC.",
        "Recommended position size is 5%.",
        "There is no execution permission in the source.",
        "This should not be treated as portfolio advice.",
    ],
)
def test_validation_allows_execution_boundary_terms_without_blocking_publish(phrase: str) -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(market_read_zh=phrase),
        packet=packet,
        audit={},
    )

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


@pytest.mark.parametrize(
    "side_patch",
    [
        {"bull_view": {"strength": "moderate", "thesis_zh": "", "evidence_refs": ["fact:fact-1"]}},
        {"bull_view": {"strength": "moderate", "thesis_zh": "上线永续合约扩大交易覆盖。", "evidence_refs": []}},
    ],
)
def test_validation_allows_ready_side_without_evidence_refs(
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

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


def test_validation_allows_ready_without_top_level_evidence_refs() -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload=_ready_payload(evidence_refs=[]),
        packet=packet,
        audit={},
    )

    assert result.publishable is True
    assert result.status == "ready"
    assert result.errors == []


def test_validation_allows_insufficient_without_data_gaps() -> None:
    packet = _packet()
    result = validate_news_item_brief_output(
        payload={
            "status": "insufficient",
            "direction": "neutral",
            "decision_class": "context",
            "novelty_status": "unclear",
            "confirmation_state": "unclear",
            "title_zh": "",
            "summary_zh": "",
            "market_read_zh": "",
            "source_consensus_zh": "缺少足够独立确认。",
            "retrieval_notes_zh": "检索证据不足。",
            "retrieval_evidence_refs": [],
            "research_todos_zh": [],
            "used_tool_call_ids": [],
            "bull_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
            "bear_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
            "affected_assets": [],
            "watch_triggers": [],
            "invalidation_conditions": [],
            "data_gaps": [],
            "evidence_refs": [],
        },
        packet=packet,
        audit={},
    )

    assert result.publishable is True
    assert result.status == "insufficient"
    assert result.errors == []


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


@pytest.mark.parametrize(
    ("audit_key", "value"),
    [
        ("tool_calls", [{"name": "get_observation_history"}]),
        ("tools", [{"name": "search_news_archive"}]),
        ("handoffs", [{"name": "planner"}]),
    ],
)
def test_validation_rejects_any_non_empty_synthesizer_action_audit(audit_key: str, value: object) -> None:
    result = validate_news_item_brief_output(
        payload=_ready_payload(),
        packet=_packet(),
        audit={audit_key: value},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unexpected_agent_action", "message": audit_key} in result.errors


def test_validation_rejects_multi_source_confirmation_from_heuristic_archive_matches() -> None:
    result = validate_news_item_brief_output(
        payload=_ready_payload(confirmation_state="multi_source_confirmed", used_tool_call_ids=["call-archive"]),
        packet=_packet(),
        audit={
            "tool_results": [
                {
                    "tool_call_id": "call-archive",
                    "tool_name": "search_news_archive",
                    "status": "ok",
                    "rows": [
                        {
                            "news_item_id": "archive-1",
                            "source_domain": "alpha.example",
                            "matching_basis": "symbol_heuristic",
                            "match_confidence": "heuristic",
                        },
                        {
                            "news_item_id": "archive-2",
                            "source_domain": "beta.example",
                            "matching_basis": "symbol_heuristic",
                            "match_confidence": "heuristic",
                        },
                    ],
                    "evidence_refs": ["news_items:archive-1", "news_items:archive-2"],
                }
            ]
        },
    )

    assert result.publishable is False
    assert {"code": "unsupported_confirmation_state", "message": "multi_source_confirmed"} in result.errors


def test_validation_rejects_multi_source_confirmation_from_same_observation_domain() -> None:
    result = validate_news_item_brief_output(
        payload=_ready_payload(confirmation_state="multi_source_confirmed", used_tool_call_ids=["call-observe"]),
        packet=_packet(),
        audit={
            "tool_results": [
                {
                    "tool_call_id": "call-observe",
                    "tool_name": "get_observation_history",
                    "status": "ok",
                    "rows": [
                        {"source_id": "opennews-news", "source_domain": "6551.io", "match_confidence": "strong"},
                        {"source_id": "opennews-listing", "source_domain": "6551.io", "match_confidence": "strong"},
                    ],
                    "evidence_refs": ["news_item_observation_edges:item-1"],
                }
            ]
        },
    )

    assert result.publishable is False
    assert {"code": "unsupported_confirmation_state", "message": "multi_source_confirmed"} in result.errors


def test_validation_allows_multi_source_confirmation_from_distinct_observation_domains() -> None:
    result = validate_news_item_brief_output(
        payload=_ready_payload(confirmation_state="multi_source_confirmed", used_tool_call_ids=["call-observe"]),
        packet=_packet(),
        audit={
            "tool_results": [
                {
                    "tool_call_id": "call-observe",
                    "tool_name": "get_observation_history",
                    "status": "ok",
                    "rows": [
                        {"source_id": "source-a", "source_domain": "alpha.example", "match_confidence": "strong"},
                        {"source_id": "source-b", "source_domain": "beta.example", "match_confidence": "strong"},
                    ],
                    "evidence_refs": ["news_item_observation_edges:item-1"],
                }
            ]
        },
    )

    assert result.publishable is True
    assert result.status == "ready"


def test_validation_allows_multi_source_confirmation_from_observation_aggregate_domain_count() -> None:
    result = validate_news_item_brief_output(
        payload=_ready_payload(confirmation_state="multi_source_confirmed", used_tool_call_ids=["call-observe"]),
        packet=_packet(),
        audit={
            "request_json": {
                "tool_results": [
                    _research_tool_result(
                        tool_call_id="call-observe",
                        tool_name="get_observation_history",
                        rows=[
                            {
                                "news_item_id": "item-1",
                                "source_count": 2,
                                "source_domain_count": 2,
                                "source_ids": ["source-a", "source-b"],
                                "source_domains": ["alpha.example", "beta.example"],
                                "independent_source_confirmed": False,
                                "independence_class": "independent_domains",
                                "result_basis": "observation_history",
                            }
                        ],
                    )
                ]
            }
        },
    )

    assert result.publishable is True
    assert result.status == "ready"


def test_validation_allows_multi_source_confirmation_from_observation_aggregate_independence_flag() -> None:
    result = validate_news_item_brief_output(
        payload=_ready_payload(confirmation_state="multi_source_confirmed", used_tool_call_ids=["call-observe"]),
        packet=_packet(),
        audit={
            "request_json": {
                "tool_results": [
                    _research_tool_result(
                        tool_call_id="call-observe",
                        tool_name="get_observation_history",
                        rows=[
                            {
                                "news_item_id": "item-1",
                                "source_count": 2,
                                "source_domain_count": 1,
                                "source_ids": ["source-a", "source-b"],
                                "source_domains": ["alpha.example"],
                                "independent_source_confirmed": True,
                                "independence_class": "explicit_independent_sources",
                                "result_basis": "observation_history",
                            }
                        ],
                    )
                ]
            }
        },
    )

    assert result.publishable is True
    assert result.status == "ready"


def test_validation_rejects_multi_source_confirmation_from_same_domain_observation_aggregate() -> None:
    result = validate_news_item_brief_output(
        payload=_ready_payload(confirmation_state="multi_source_confirmed", used_tool_call_ids=["call-observe"]),
        packet=_packet(),
        audit={
            "request_json": {
                "tool_results": [
                    _research_tool_result(
                        tool_call_id="call-observe",
                        tool_name="get_observation_history",
                        rows=[
                            {
                                "news_item_id": "item-1",
                                "source_count": 2,
                                "source_domain_count": 1,
                                "source_ids": ["opennews-news", "opennews-listing"],
                                "source_domains": ["6551.io"],
                                "independent_source_confirmed": False,
                                "independence_class": "same_domain_only",
                                "same_domain_notes": ["Multiple observed source ids share one source domain."],
                                "result_basis": "observation_history",
                            }
                        ],
                    )
                ]
            }
        },
    )

    assert result.publishable is False
    assert {"code": "unsupported_confirmation_state", "message": "multi_source_confirmed"} in result.errors


def test_validation_keeps_assets_grounded_by_exact_tool_evidence() -> None:
    result = validate_news_item_brief_output(
        payload=_ready_payload(
            used_tool_call_ids=["call-target"],
            affected_assets=[
                {
                    "symbol": "XYZ",
                    "name": "XYZ Token",
                    "resolution_status": "known_symbol",
                    "target_type": "cex_token",
                    "target_id": "binance:XYZ",
                    "impact_direction": "bullish",
                    "reason_zh": "精确 target context 证据支撑 XYZ。",
                    "evidence_refs": ["news_token_mentions:archive-1:exact_target:XYZ"],
                }
            ],
        ),
        packet=_packet(),
        audit={
            "tool_results": [
                {
                    "tool_call_id": "call-target",
                    "tool_name": "get_target_news_context",
                    "status": "ok",
                    "rows": [
                        {
                            "news_item_id": "archive-1",
                            "target_type": "cex_token",
                            "target_id": "binance:XYZ",
                            "display_symbol": "XYZ",
                            "matching_basis": "exact_target",
                            "match_confidence": 0.91,
                        }
                    ],
                    "evidence_refs": ["news_token_mentions:archive-1:exact_target:XYZ"],
                }
            ]
        },
    )

    assert result.publishable is True
    assert result.payload is not None
    assert result.payload["affected_assets"][0]["symbol"] == "XYZ"


def test_validation_keeps_assets_grounded_by_nested_exact_target_aggregate_tool_evidence() -> None:
    result = validate_news_item_brief_output(
        payload=_ready_payload(
            used_tool_call_ids=["call-target"],
            affected_assets=[
                {
                    "symbol": "XYZ",
                    "name": "XYZ Token",
                    "resolution_status": "known_symbol",
                    "target_type": "cex_token",
                    "target_id": "binance:XYZ",
                    "impact_direction": "bullish",
                    "reason_zh": "精确 target context 证据支撑 XYZ。",
                    "evidence_refs": ["news_token_mentions:archive-1:exact_target:XYZ"],
                }
            ],
        ),
        packet=_packet(),
        audit={
            "request_json": {
                "tool_results": [
                    _research_tool_result(
                        tool_call_id="call-target",
                        tool_name="get_target_news_context",
                        rows=[
                            {
                                "counts": {"total": 1, "exact_target": 1, "symbol_heuristic": 0},
                                "top_items": [
                                    {
                                        "news_item_id": "archive-1",
                                        "target_type": "cex_token",
                                        "target_id": "binance:XYZ",
                                        "display_symbol": "XYZ",
                                        "matching_basis": "exact_target",
                                        "match_confidence": 0.91,
                                    }
                                ],
                                "latest_items": [],
                                "source_domain_count": 1,
                                "matching_basis": ["exact_target"],
                                "result_basis": "exact_target",
                            }
                        ],
                    )
                ]
            }
        },
    )

    assert result.publishable is True
    assert result.payload is not None
    assert result.payload["affected_assets"][0]["symbol"] == "XYZ"


@pytest.mark.parametrize("matching_basis", ["symbol_heuristic", "market_subject_heuristic"])
def test_validation_drops_assets_when_nested_target_aggregate_items_are_heuristic(matching_basis: str) -> None:
    result = validate_news_item_brief_output(
        payload=_ready_payload(
            used_tool_call_ids=["call-target"],
            affected_assets=[
                {
                    "symbol": "XYZ",
                    "name": "XYZ Token",
                    "resolution_status": "known_symbol",
                    "target_type": "cex_token",
                    "target_id": "binance:XYZ",
                    "impact_direction": "bullish",
                    "reason_zh": "启发式 target context 不能支撑 XYZ。",
                    "evidence_refs": [f"news_token_mentions:archive-1:{matching_basis}:XYZ"],
                }
            ],
            data_gaps=[],
        ),
        packet=_packet(),
        audit={
            "request_json": {
                "tool_results": [
                    _research_tool_result(
                        tool_call_id="call-target",
                        tool_name="get_target_news_context",
                        rows=[
                            {
                                "counts": {"total": 1, "exact_target": 0, "symbol_heuristic": 1},
                                "top_items": [
                                    {
                                        "news_item_id": "archive-1",
                                        "target_type": "cex_token",
                                        "target_id": "binance:XYZ",
                                        "display_symbol": "XYZ",
                                        "matching_basis": matching_basis,
                                        "match_confidence": "heuristic",
                                    }
                                ],
                                "latest_items": [],
                                "source_domain_count": 1,
                                "matching_basis": [matching_basis],
                                "result_basis": matching_basis,
                            }
                        ],
                    )
                ]
            }
        },
    )

    assert result.publishable is True
    assert result.payload is not None
    assert result.payload["affected_assets"] == []


def test_validation_reads_tool_evidence_from_worker_request_json_shape() -> None:
    result = validate_news_item_brief_output(
        payload=_ready_payload(
            used_tool_call_ids=["call-target"],
            affected_assets=[
                {
                    "symbol": "XYZ",
                    "name": "XYZ Token",
                    "resolution_status": "known_symbol",
                    "target_type": "cex_token",
                    "target_id": "binance:XYZ",
                    "impact_direction": "bullish",
                    "reason_zh": "精确 target context 证据支撑 XYZ。",
                    "evidence_refs": ["news_token_mentions:archive-1:exact_target:XYZ"],
                }
            ],
        ),
        packet=_packet(),
        audit={
            "trace_metadata": {"input_hash": "sha256:input"},
            "request_json": {
                "tool_results": [
                    {
                        "tool_call_id": "call-target",
                        "tool_name": "get_target_news_context",
                        "status": "ok",
                        "rows": [
                            {
                                "news_item_id": "archive-1",
                                "target_type": "cex_token",
                                "target_id": "binance:XYZ",
                                "display_symbol": "XYZ",
                                "matching_basis": "exact_target",
                                "match_confidence": 0.91,
                            }
                        ],
                    }
                ],
                "research_execution": {"tool_results": []},
            },
        },
    )

    assert result.publishable is True
    assert result.payload is not None
    assert result.payload["affected_assets"][0]["symbol"] == "XYZ"


@pytest.mark.parametrize("matching_basis", ["symbol_heuristic", "market_subject_heuristic"])
def test_validation_drops_exact_asset_confirmation_when_only_tool_match_is_heuristic(matching_basis: str) -> None:
    result = validate_news_item_brief_output(
        payload=_ready_payload(
            used_tool_call_ids=["call-target"],
            affected_assets=[
                {
                    "symbol": "XYZ",
                    "name": "XYZ Token",
                    "resolution_status": "known_symbol",
                    "target_type": "cex_token",
                    "target_id": "binance:XYZ",
                    "impact_direction": "bullish",
                    "reason_zh": "启发式匹配不能支撑精确资产确认。",
                    "evidence_refs": [f"news_token_mentions:archive-1:{matching_basis}:XYZ"],
                }
            ],
            data_gaps=[],
        ),
        packet=_packet(),
        audit={
            "tool_results": [
                {
                    "tool_call_id": "call-target",
                    "tool_name": "get_target_news_context",
                    "status": "ok",
                    "rows": [
                        {
                            "news_item_id": "archive-1",
                            "target_type": "cex_token",
                            "target_id": "binance:XYZ",
                            "display_symbol": "XYZ",
                            "matching_basis": matching_basis,
                            "match_confidence": "heuristic",
                        }
                    ],
                    "evidence_refs": [f"news_token_mentions:archive-1:{matching_basis}:XYZ"],
                }
            ]
        },
    )

    assert result.publishable is True
    assert result.payload is not None
    assert result.payload["affected_assets"] == []
    assert result.payload["data_gaps"][0]["description_zh"].startswith("模型提到的资产 XYZ")


def _research_tool_result(*, tool_call_id: str, tool_name: str, rows: list[dict[str, object]]) -> dict[str, object]:
    result = NewsResearchToolResult(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        status="ok",
        schema_version="news_research_tool_result_v1",
        query_version=f"{tool_name}_v1",
        source_tables=["news_items"],
        input={},
        rows=rows,
        row_count=len(rows),
        truncated=False,
        skipped_reason="",
        result_hash="sha256:test",
        generated_at_ms=1_779_000_000_000,
        latency_ms=1,
        redaction_notes=[],
        evidence_refs=[],
    )
    return result.model_dump(mode="json")
