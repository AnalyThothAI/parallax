from __future__ import annotations

from typing import Any

import pytest

from gmgn_twitter_intel.domains.equity_event_intel.services.brief_input import (
    build_equity_event_brief_input_packet,
)
from gmgn_twitter_intel.domains.equity_event_intel.services.brief_validation import (
    validate_equity_event_brief_output,
)
from gmgn_twitter_intel.domains.equity_event_intel.types import EquityEventBriefAgentConfig
from gmgn_twitter_intel.platform.agent_hashing import json_sha256


def _packet():
    return build_equity_event_brief_input_packet(
        event={
            "company_event_id": "event-1",
            "company_id": "market_instrument:us_equity:MSFT",
            "ticker": "MSFT",
            "company_name": "Microsoft Corporation",
            "event_type": "quarterly_report",
            "priority": "P0",
            "source_role": "official_regulator",
            "event_time_ms": 1_779_000_000_000,
            "fiscal_period": "2026Q1",
            "summary": "Microsoft reported quarterly revenue growth.",
        },
        story=None,
        story_members=[],
        source_documents=[
            {
                "event_document_id": "doc-1",
                "source_role": "official_regulator",
                "document_type": "sec_filing",
                "form_type": "10-Q",
                "document_url": "https://www.sec.gov/Archives/edgar/data/789019/doc.htm",
                "content_hash": "sha256:doc",
            }
        ],
        source_spans=[
            {
                "span_id": "span-1",
                "event_document_id": "doc-1",
                "span_type": "financial_metric",
                "span_start": 100,
                "span_end": 160,
                "evidence_quote": "Revenue was $63.0 billion.",
                "confidence": 0.98,
            }
        ],
        fact_candidates=[
            {
                "fact_candidate_id": "fact-1",
                "source_span_id": "span-1",
                "fact_type": "revenue_actual",
                "metric_name": "revenue",
                "value_numeric": 63.0,
                "value_unit": "USD_billion",
                "period": "2026Q1",
                "direction": "up",
                "claim": "Revenue was $63.0 billion.",
                "evidence_quote": "Revenue was $63.0 billion.",
                "validation_status": "accepted",
                "source_role": "official_regulator",
            }
        ],
        agent_config=EquityEventBriefAgentConfig(
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
        "summary_zh": "微软季度收入为 630 亿美元，官方申报文件提供了收入证据。",
        "event_read_zh": "该事件的可审计重点是收入事实本身，而不是交易执行。",
        "bull_view": {
            "strength": "moderate",
            "thesis_zh": "收入事实支持基本面关注度提升。",
            "evidence_refs": ["fact:fact-1", "span:span-1"],
        },
        "bear_view": {
            "strength": "weak",
            "thesis_zh": "输入没有提供利润率或指引证据。",
            "evidence_refs": ["event:summary"],
        },
        "company_impacts": [
            {
                "ticker": "MSFT",
                "company_name": "Microsoft Corporation",
                "impact_direction": "bullish",
                "reason_zh": "收入事实来自官方文件。",
                "evidence_refs": ["fact:fact-1"],
            }
        ],
        "watch_triggers": ["后续管理层指引或 10-Q 细节补充"],
        "invalidation_conditions": ["后续文件修正收入数据"],
        "data_gaps": [],
        "evidence_refs": ["event:summary", "doc:doc-1", "span:span-1", "fact:fact-1"],
    }
    payload.update(overrides)
    return payload


def test_valid_ready_payload_is_publishable_and_hashes_normalized_output() -> None:
    packet = _packet()

    result = validate_equity_event_brief_output(payload=_ready_payload(), packet=packet, audit={})

    assert result.publishable is True
    assert result.status == "ready"
    assert result.payload is not None
    assert result.errors == []
    assert result.output_hash == json_sha256(result.payload)


def test_validation_rejects_unknown_evidence_ref() -> None:
    packet = _packet()

    result = validate_equity_event_brief_output(
        payload=_ready_payload(evidence_refs=["fact:fact-1", "span:missing"]),
        packet=packet,
        audit={},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unknown_evidence_ref", "message": "span:missing"} in result.errors


def test_validation_rejects_uncited_material_claims() -> None:
    packet = _packet()

    result = validate_equity_event_brief_output(
        payload=_ready_payload(
            evidence_refs=[],
            bull_view={
                "strength": "moderate",
                "thesis_zh": "收入事实支持基本面关注度提升。",
                "evidence_refs": [],
            },
        ),
        packet=packet,
        audit={},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert any(error["code"] == "uncited_material_claim" for error in result.errors)


def test_validation_rejects_unexpected_tool_or_handoff_audit() -> None:
    packet = _packet()

    result = validate_equity_event_brief_output(
        payload=_ready_payload(),
        packet=packet,
        audit={"tool_calls": [{"name": "web_search"}], "handoffs": [{"target": "trader"}]},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert {"code": "unexpected_agent_action", "message": "tool_calls"} in result.errors
    assert {"code": "unexpected_agent_action", "message": "handoffs"} in result.errors


@pytest.mark.parametrize(
    "phrase",
    ["开仓做多 MSFT", "建议买入 MSFT 股票", "Use a 5% position size", "Set a stop loss at 3%"],
)
def test_validation_rejects_trade_execution_instructions(phrase: str) -> None:
    packet = _packet()

    result = validate_equity_event_brief_output(
        payload=_ready_payload(event_read_zh=phrase),
        packet=packet,
        audit={},
    )

    assert result.publishable is False
    assert result.status == "failed"
    assert any(error["code"] == "forbidden_execution_language" for error in result.errors)


@pytest.mark.parametrize(
    "phrase",
    ["公司计划卖出非核心资产。", "公司公告买入云业务少数股权。", "回购计划包含买入公司股份。"],
)
def test_validation_allows_corporate_action_buy_sell_phrasing(phrase: str) -> None:
    packet = _packet()

    result = validate_equity_event_brief_output(
        payload=_ready_payload(event_read_zh=phrase),
        packet=packet,
        audit={},
    )

    assert result.publishable is True
    assert result.errors == []


def test_ready_requires_useful_summary_and_evidence_while_insufficient_uses_data_gaps() -> None:
    packet = _packet()

    ready = validate_equity_event_brief_output(
        payload=_ready_payload(summary_zh="", event_read_zh="", evidence_refs=[]),
        packet=packet,
        audit={},
    )
    insufficient = validate_equity_event_brief_output(
        payload={
            "status": "insufficient",
            "direction": "neutral",
            "decision_class": "watch",
            "summary_zh": "",
            "event_read_zh": "",
            "bull_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
            "bear_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
            "company_impacts": [],
            "watch_triggers": [],
            "invalidation_conditions": [],
            "data_gaps": [{"description_zh": "缺少足够的官方事实证据。", "severity": "high"}],
            "evidence_refs": ["event:summary"],
        },
        packet=packet,
        audit={},
    )

    assert ready.publishable is False
    assert any(error["code"] == "ready_invariant" for error in ready.errors)
    assert insufficient.publishable is True
    assert insufficient.status == "insufficient"
