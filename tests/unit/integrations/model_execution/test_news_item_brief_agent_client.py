from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from parallax.domains.news_intel.types.news_item_brief import (
    NEWS_ITEM_BRIEF_AGENT_NAME,
    NEWS_ITEM_BRIEF_LANE,
    NEWS_ITEM_BRIEF_PROMPT_VERSION,
    NEWS_ITEM_BRIEF_SCHEMA_VERSION,
    NEWS_ITEM_BRIEF_WORKFLOW_NAME,
    NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION,
    NewsItemBriefBasePacket,
    NewsItemBriefBudgetReport,
    NewsItemBriefNewsItem,
    NewsItemBriefPayload,
    NewsItemBriefSynthesisPacket,
    NewsItemResearchBudget,
    NewsItemResearchPlan,
    NewsItemResearchToolCall,
    NewsResearchToolResult,
)
from parallax.integrations.model_execution.news_item_brief_agent_client import (
    LiteLLMNewsItemBriefClient,
)
from parallax.integrations.model_execution.output_schema import StrictJsonOutputSchema
from parallax.platform.agent_execution import RUNTIME_VERSION
from parallax.platform.agent_hashing import artifact_hash_for, json_sha256


def test_news_item_brief_client_builds_stage_and_delegates_reservation() -> None:
    gateway = FakeGateway()
    client = LiteLLMNewsItemBriefClient(agent_gateway=gateway)
    packet = _synthesis_packet()

    reservation = client.try_reserve_execution(NEWS_ITEM_BRIEF_LANE)
    audit = client.request_audit(run_id="run-1", packet=packet)

    assert reservation is gateway.reservation
    assert gateway.reserved_lanes == [NEWS_ITEM_BRIEF_LANE]
    assert audit["lane"] == NEWS_ITEM_BRIEF_LANE
    assert audit["trace_metadata"]["research_packet_hash"].startswith("sha256:")
    assert audit["trace_metadata"]["tool_catalog_version"] == NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION
    assert client.artifact_version_hash == audit["artifact_version_hash"]
    stage = gateway.audit_stages[0]
    assert stage.lane == NEWS_ITEM_BRIEF_LANE
    assert stage.stage == "news_item_brief_synthesis"
    assert stage.workflow_name == NEWS_ITEM_BRIEF_WORKFLOW_NAME
    assert stage.agent_name == NEWS_ITEM_BRIEF_AGENT_NAME
    assert client.model == "gpt-news"
    assert stage.output_type is NewsItemBriefPayload
    assert stage.trace_metadata["phase"] == "synthesis"
    assert stage.trace_metadata["research_packet_hash"].startswith("sha256:")
    assert stage.trace_metadata["tool_catalog_version"] == NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION


def test_news_item_brief_client_executes_strict_payload_with_caller_reservation() -> None:
    gateway = FakeGateway()
    client = LiteLLMNewsItemBriefClient(agent_gateway=gateway)
    packet = _synthesis_packet()
    reservation = object()

    result = asyncio.run(client.brief_item(run_id="run-1", packet=packet, reservation=reservation))

    assert gateway.executions[0].reservation is reservation
    stage = gateway.executions[0].stage
    assert stage.lane == NEWS_ITEM_BRIEF_LANE
    assert stage.stage == "news_item_brief_synthesis"
    assert stage.workflow_name == NEWS_ITEM_BRIEF_WORKFLOW_NAME
    assert stage.agent_name == NEWS_ITEM_BRIEF_AGENT_NAME
    assert stage.output_type is NewsItemBriefPayload
    assert stage.input_payload["research_packet"]["research_packet_hash"].startswith("sha256:")
    assert stage.trace_metadata["synthesis_input_hash"].startswith("sha256:")
    assert result == {
        "payload": gateway.payload.model_dump(mode="json"),
        "agent_run_audit": {"status": "done", "lane": NEWS_ITEM_BRIEF_LANE},
    }


class FakeGateway:
    def __init__(self) -> None:
        self.reservation = object()
        self.reserved_lanes: list[str] = []
        self.audit_stages: list[Any] = []
        self.executions: list[Any] = []
        self.payload = NewsItemBriefPayload(
            status="ready",
            direction="neutral",
            decision_class="context",
            novelty_status="unclear",
            confirmation_state="single_source",
            title_zh="中性新闻摘要",
            summary_zh="摘要",
            market_read_zh="市场解读",
            source_consensus_zh="单一来源。",
            retrieval_notes_zh="检索完成。",
            retrieval_evidence_refs=[],
            research_todos_zh=[],
            used_tool_call_ids=[],
        )

    def try_reserve(self, lane: str, *, rate_units: int = 1) -> object:
        assert rate_units == 1
        self.reserved_lanes.append(lane)
        return self.reservation

    def model_for_lane(self, lane: str) -> str:
        assert lane == NEWS_ITEM_BRIEF_LANE
        return "gpt-news"

    def request_audit(self, stage: Any) -> Any:
        self.audit_stages.append(stage)
        output_schema = StrictJsonOutputSchema(stage.output_type)
        artifact_version_hash = artifact_hash_for(
            model=self.model_for_lane(stage.lane),
            prompt_version=stage.prompt_version,
            schema_version=stage.schema_version,
            runtime_version=RUNTIME_VERSION,
            output_schema_hash=json_sha256(output_schema.json_schema()),
        )
        return SimpleNamespace(
            model_dump=lambda mode="json": {
                "lane": stage.lane,
                "mode": mode,
                "artifact_version_hash": artifact_version_hash,
                "trace_metadata": stage.trace_metadata,
            }
        )

    async def execute(self, stage: Any, *, reservation: object | None = None) -> Any:
        self.executions.append(SimpleNamespace(stage=stage, reservation=reservation))
        return SimpleNamespace(
            final_output=self.payload,
            audit=SimpleNamespace(
                model_dump=lambda mode="json": {"status": "done", "lane": stage.lane},
            ),
        )


def _synthesis_packet() -> NewsItemBriefSynthesisPacket:
    return NewsItemBriefSynthesisPacket(
        packet_id="synthesis-packet-1",
        base_packet=NewsItemBriefBasePacket(
            packet_id="base-packet-1",
            news_item=NewsItemBriefNewsItem(
                news_item_id="news-1",
                title="Fed says crypto supervision remains active",
                summary="A short source summary.",
            ),
            base_budget_report=NewsItemBriefBudgetReport(
                material_budget_chars=12_000,
                material_chars=2400,
                original_token_count=2,
                kept_token_count=1,
                original_fact_count=0,
                kept_fact_count=0,
            ),
            prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
            schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
            input_hash="sha256:base",
        ),
        research_plan=NewsItemResearchPlan(
            status="ready",
            tool_calls=[
                NewsItemResearchToolCall(
                    tool_call_id="call-1",
                    tool_name="search_news_archive",
                    input={"query": "Fed crypto supervision"},
                    purpose_zh="补充监管背景",
                )
            ],
            budget=NewsItemResearchBudget(max_tool_calls=1, max_total_chars=2000),
            policy_notes_zh="需要监管背景。",
        ),
        tool_results=[
            NewsResearchToolResult(
                tool_call_id="call-1",
                tool_name="search_news_archive",
                status="ok",
                schema_version="news_research_tool_result_v1",
                query_version="search_news_archive_v1",
                source_tables=["news_items"],
                input={"query": "Fed crypto supervision"},
                rows=[{"news_item_id": "news-0", "title": "Fed supervision context"}],
                row_count=1,
                result_hash="sha256:runtime-only",
                generated_at_ms=1_779_000_010_000,
                latency_ms=123,
                evidence_refs=["archive:news-0"],
            )
        ],
    )
