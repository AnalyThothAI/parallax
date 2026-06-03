from __future__ import annotations

import pytest
from pydantic import ValidationError

from parallax.domains.news_intel.types.news_item_brief import (
    NewsContextTargetRef,
    NewsItemBriefBasePacket,
    NewsItemBriefBudgetReport,
    NewsItemBriefNewsItem,
    NewsItemBriefPayload,
    NewsItemResearchPlan,
    NewsResearchToolResult,
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


def test_research_plan_uses_skip_status_for_empty_plan_path() -> None:
    plan = NewsItemResearchPlan.model_validate(
        {
            "status": "skip",
            "research_todos": [],
            "tool_calls": [],
            "budget": {
                "max_tool_calls": 0,
                "max_total_chars": 0,
                "hard_max_total_chars": 0,
                "max_rows_per_tool": 0,
            },
            "policy_notes_zh": "",
            "skip_reason_zh": "自包含新闻，无需检索",
            "evidence_refs": [],
        }
    )

    assert plan.status == "skip"
    with pytest.raises(ValidationError):
        NewsItemResearchPlan.model_validate({**plan.model_dump(mode="json"), "status": "skipped"})


def test_research_tool_result_generated_at_is_not_material_identity() -> None:
    result = _tool_result(generated_at_ms=1_779_000_000_000)
    later = result.model_copy(update={"generated_at_ms": 1_779_000_060_000, "latency_ms": 900})

    assert news_research_tool_material_identity(result) == news_research_tool_material_identity(later)
    assert "generated_at_ms" not in news_research_tool_material_identity(result)
    assert "latency_ms" not in news_research_tool_material_identity(result)
    assert "result_hash" not in news_research_tool_material_identity(result)


def test_research_tool_result_uses_typed_top_level_rows_not_generic_output() -> None:
    result = _tool_result(generated_at_ms=1_779_000_000_000)

    assert result.schema_version == "news_research_tool_result_v1"
    assert result.query_version == "search_news_archive_v1"
    assert result.source_tables == ["news_items"]
    assert result.rows == [{"news_item_id": "news-2", "title": "ETF update"}]
    assert result.row_count == 1
    assert result.truncated is False
    with pytest.raises(ValidationError):
        NewsResearchToolResult.model_validate({**result.model_dump(mode="json"), "output": {"rows": []}})


def test_base_budget_report_records_truncated_fact_lanes() -> None:
    report = NewsItemBriefBudgetReport.model_validate(
        {
            "material_budget_chars": 12_000,
            "material_chars": 11_400,
            "original_token_count": 0,
            "kept_token_count": 0,
            "original_fact_count": 60,
            "kept_fact_count": 18,
            "truncation_reasons": ["fact_lanes_budget"],
        }
    )

    assert report.original_fact_count == 60
    assert report.kept_fact_count < 60
    assert "fact_lanes_budget" in report.truncation_reasons


def test_base_packet_exposes_allowed_context_targets_from_resolved_mentions() -> None:
    packet = _base_packet(
        allowed_context_targets=[
            {
                "target_type": "CexToken",
                "target_id": "cex_token:SOL",
                "display_symbol": "SOL",
                "resolution_status": "unique_by_context",
                "confidence": 0.91,
                "target_scope": "crypto",
            },
        ],
    )

    assert packet.allowed_context_targets[0].target_type == "CexToken"
    assert packet.allowed_context_targets[0].target_id == "cex_token:SOL"
    assert all(target.target_id != "XYZ-CL" for target in packet.allowed_context_targets)
    with pytest.raises(ValidationError):
        NewsContextTargetRef.model_validate(
            {
                "target_type": "CexToken",
                "target_id": "cex_token:SOL",
                "display_symbol": "SOL",
                "resolution_status": "unique_by_context",
                "confidence": 0.91,
                "target_scope": "market",
            }
        )


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
        schema_version="news_research_tool_result_v1",
        query_version="search_news_archive_v1",
        source_tables=["news_items"],
        input={"query_terms": ["ETF"], "limit": 8},
        rows=[{"news_item_id": "news-2", "title": "ETF update"}],
        row_count=1,
        truncated=False,
        skipped_reason="",
        result_hash="sha256:old",
        evidence_refs=["similar:item:news-2"],
        generated_at_ms=generated_at_ms,
        latency_ms=120,
        redaction_notes=["raw_payload_removed"],
    )


def _base_packet(*, allowed_context_targets: list[dict[str, object]]) -> NewsItemBriefBasePacket:
    return NewsItemBriefBasePacket(
        packet_id="packet-1",
        news_item=NewsItemBriefNewsItem(
            news_item_id="news-1",
            title="SEC is said to approve spot SOL ETF filings",
            summary="ETF filing update.",
        ),
        allowed_context_targets=allowed_context_targets,
        content_class="etf_fund_flow",
        base_budget_report=NewsItemBriefBudgetReport(
            material_budget_chars=12_000,
            material_chars=2400,
            original_token_count=2,
            kept_token_count=1,
            original_fact_count=0,
            kept_fact_count=0,
            truncation_reasons=["unresolved_mentions_excluded"],
        ),
        prompt_version="news-item-brief-synthesizer-v1",
        schema_version="news_item_brief_v2",
    )
