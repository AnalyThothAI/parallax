from __future__ import annotations

import pytest
from pydantic import ValidationError

from parallax.domains.news_intel.types.news_item_brief import (
    NewsItemBriefPayload,
    NewsItemResearchPlan,
    NewsResearchToolResult,
    build_news_item_brief_base_packet,
    news_research_tool_material_identity,
)


def test_news_item_brief_key_points_are_bounded_text() -> None:
    with pytest.raises(ValidationError):
        NewsItemBriefPayload(
            status="ready",
            direction="bullish",
            decision_class="watch",
            novelty_status="new",
            confirmation_state="single_source",
            summary_zh="事件摘要",
            market_read_zh="市场解读",
            bull_view={"strength": "moderate", "thesis_zh": "x" * 301, "evidence_refs": ["item:title"]},
            bear_view={"strength": "absent", "thesis_zh": "", "evidence_refs": []},
            affected_assets=[],
            watch_triggers=[],
            invalidation_conditions=[],
            data_gaps=[],
            evidence_refs=["item:title"],
            source_consensus_zh="单一来源",
            retrieval_notes_zh="未检索外部数据",
            retrieval_evidence_refs=[],
            research_todos_zh=[],
            used_tool_call_ids=[],
        )


def test_news_item_brief_payload_rejects_legacy_bull_bear_view_shape() -> None:
    with pytest.raises(ValidationError):
        NewsItemBriefPayload(
            status="ready",
            direction="bullish",
            decision_class="watch",
            novelty_status="new",
            confirmation_state="single_source",
            summary_zh="事件摘要",
            market_read_zh="市场解读",
            bull_bear_view={"bull": "legacy", "bear": "legacy"},
            bull_view={"strength": "moderate", "thesis_zh": "利多叙事", "evidence_refs": ["item:title"]},
            bear_view={"strength": "absent", "thesis_zh": "", "evidence_refs": []},
            affected_assets=[],
            watch_triggers=[],
            invalidation_conditions=[],
            data_gaps=[],
            evidence_refs=["item:title"],
            source_consensus_zh="单一来源",
            retrieval_notes_zh="未检索外部数据",
            retrieval_evidence_refs=[],
            research_todos_zh=[],
            used_tool_call_ids=[],
        )


def test_research_plan_allows_bounded_tool_calls_and_validates_strict_shape() -> None:
    plan = NewsItemResearchPlan.model_validate(
        {
            "status": "ready",
            "research_todos": [
                {"todo_id": "todo-1", "content_zh": "检查历史新闻", "status": "pending"},
            ],
            "tool_calls": [
                {
                    "tool_call_id": "call-1",
                    "tool_name": "search_news_archive",
                    "input": {"query_terms": ["ETF"], "symbols": ["BTC"], "window_hours": 168, "limit": 8},
                    "purpose_zh": "确认数据库中是否已有同类新闻",
                    "expected_evidence": ["similar:item"],
                },
            ],
            "budget": {
                "max_tool_calls": 5,
                "max_total_chars": 3000,
                "hard_max_total_chars": 6000,
                "max_rows_per_tool": 25,
            },
            "policy_notes_zh": "",
            "skip_reason_zh": "",
            "evidence_refs": [],
        }
    )

    assert plan.tool_calls[0].tool_name == "search_news_archive"
    with pytest.raises(ValidationError):
        NewsItemResearchPlan.model_validate({**plan.model_dump(mode="json"), "unexpected": True})


def test_research_tool_result_generated_at_is_not_material_identity() -> None:
    result = _tool_result(generated_at_ms=1_779_000_000_000)
    later = result.model_copy(update={"generated_at_ms": 1_779_000_060_000, "latency_ms": 900})

    assert news_research_tool_material_identity(result) == news_research_tool_material_identity(later)


def test_base_budget_report_records_truncated_fact_lanes() -> None:
    packet = build_news_item_brief_base_packet(
        item=_item(),
        token_mentions=[],
        fact_candidates=[_long_fact(index) for index in range(60)],
        material_budget_chars=12_000,
    )

    assert packet.base_budget_report.original_fact_count == 60
    assert packet.base_budget_report.kept_fact_count < 60
    assert "fact_lanes_budget" in packet.base_budget_report.truncation_reasons


def test_base_packet_exposes_allowed_context_targets_from_resolved_mentions() -> None:
    packet = build_news_item_brief_base_packet(
        item=_item(),
        token_mentions=[
            _mention(
                display_symbol="SOL",
                target_type="CexToken",
                target_id="cex_token:SOL",
                resolution_status="unique_by_context",
            ),
            _mention(
                display_symbol="XYZ-CL",
                target_type=None,
                target_id=None,
                resolution_status="unknown_attention",
            ),
        ],
        fact_candidates=[],
        material_budget_chars=12_000,
    )

    assert packet.allowed_context_targets[0].target_type == "CexToken"
    assert packet.allowed_context_targets[0].target_id == "cex_token:SOL"
    assert all(target.target_id != "XYZ-CL" for target in packet.allowed_context_targets)


def test_v2_news_item_brief_payload_requires_new_research_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        NewsItemBriefPayload(
            status="ready",
            direction="neutral",
            decision_class="context",
            summary_zh="摘要",
            market_read_zh="市场解读",
        )

    missing_fields = {error["loc"][0] for error in exc_info.value.errors() if error["type"] == "missing"}
    assert {
        "novelty_status",
        "confirmation_state",
        "source_consensus_zh",
        "retrieval_notes_zh",
        "retrieval_evidence_refs",
        "research_todos_zh",
        "used_tool_call_ids",
    }.issubset(missing_fields)


def _tool_result(*, generated_at_ms: int) -> NewsResearchToolResult:
    return NewsResearchToolResult(
        tool_call_id="call-1",
        tool_name="search_news_archive",
        status="ok",
        input={"query_terms": ["ETF"], "limit": 8},
        output={"rows": [{"news_item_id": "news-2", "title": "ETF update"}]},
        evidence_refs=["similar:item:news-2"],
        generated_at_ms=generated_at_ms,
        latency_ms=120,
        runtime_metadata={"worker": "unit-test"},
    )


def _item() -> dict[str, object]:
    return {
        "news_item_id": "news-1",
        "title": "SEC is said to approve spot SOL ETF filings",
        "summary": "ETF filing update.",
        "body_text": "Longer source body.",
        "published_at_ms": 1_779_000_000_000,
        "content_hash": "hash-1",
        "source_domain": "example.com",
        "source_name": "Example",
        "source_role": "specialist",
        "trust_tier": "watch",
        "content_class": "etf_fund_flow",
    }


def _mention(
    *,
    display_symbol: str,
    target_type: str | None,
    target_id: str | None,
    resolution_status: str,
) -> dict[str, object]:
    return {
        "mention_id": f"mention-{display_symbol}",
        "observed_symbol": display_symbol,
        "display_symbol": display_symbol,
        "target_type": target_type,
        "target_id": target_id,
        "resolution_status": resolution_status,
        "confidence": 0.91 if target_id else 0.2,
    }


def _long_fact(index: int) -> dict[str, object]:
    return {
        "fact_candidate_id": f"fact-{index}",
        "event_type": "etf",
        "claim": f"Fact claim {index} " + ("x" * 760),
        "realis": "attention",
        "validation_status": "attention",
        "evidence_quote": "quote",
    }
