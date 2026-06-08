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
    NewsItemBriefInputPacket,
    NewsItemBriefNewsItem,
    NewsItemBriefPayload,
)
from parallax.integrations.model_execution.news_item_brief_agent_client import (
    LiteLLMNewsItemBriefClient,
)
from parallax.integrations.model_execution.output_schema import StrictJsonOutputSchema
from parallax.platform.agent_execution import RUNTIME_VERSION
from parallax.platform.agent_hashing import artifact_hash_for, json_sha256, text_sha256


def test_news_item_brief_client_builds_stage_and_delegates_reservation() -> None:
    gateway = FakeGateway()
    client = LiteLLMNewsItemBriefClient(agent_gateway=gateway)
    packet = _packet()

    reservation = client.try_reserve_execution(NEWS_ITEM_BRIEF_LANE)
    audit = client.request_audit(run_id="run-1", packet=packet)

    assert reservation is gateway.reservation
    assert gateway.reserved_lanes == [NEWS_ITEM_BRIEF_LANE]
    assert audit["lane"] == NEWS_ITEM_BRIEF_LANE
    assert client.artifact_version_hash == audit["artifact_version_hash"]
    stage = gateway.audit_stages[0]
    assert stage.lane == NEWS_ITEM_BRIEF_LANE
    assert stage.workflow_name == NEWS_ITEM_BRIEF_WORKFLOW_NAME
    assert stage.agent_name == NEWS_ITEM_BRIEF_AGENT_NAME
    assert client.model == "gpt-news"
    assert stage.output_type is NewsItemBriefPayload
    expected_artifact_hash = artifact_hash_for(
        model=client.model,
        prompt_version=stage.prompt_version,
        schema_version=stage.schema_version,
        runtime_version=RUNTIME_VERSION,
        output_schema_hash=json_sha256(StrictJsonOutputSchema(stage.output_type).json_schema()),
        prompt_text_hash=text_sha256(stage.instructions),
    )
    assert client.artifact_version_hash == expected_artifact_hash


def test_news_item_brief_client_executes_strict_payload_with_caller_reservation() -> None:
    gateway = FakeGateway()
    client = LiteLLMNewsItemBriefClient(agent_gateway=gateway)
    packet = _packet()
    reservation = object()

    result = asyncio.run(client.brief_item(run_id="run-1", packet=packet, reservation=reservation))

    assert gateway.executions[0].reservation is reservation
    stage = gateway.executions[0].stage
    assert stage.lane == NEWS_ITEM_BRIEF_LANE
    assert stage.workflow_name == NEWS_ITEM_BRIEF_WORKFLOW_NAME
    assert stage.agent_name == NEWS_ITEM_BRIEF_AGENT_NAME
    assert stage.output_type is NewsItemBriefPayload
    assert result == {
        "payload": gateway.payload.model_dump(mode="json"),
        "agent_run_audit": {"status": "done", "lane": NEWS_ITEM_BRIEF_LANE},
    }
    assert "affected_entities" in result["payload"]
    assert "affected_assets" not in result["payload"]


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
            event_type="macro_context",
            title_zh="中性新闻摘要",
            summary_zh="摘要",
            market_read_zh="市场解读",
            market_domains=["macro_rates"],
            affected_entities=[
                {
                    "label": "Federal Reserve",
                    "entity_type": "regulator",
                    "market_domain": "macro_rates",
                    "impact_direction": "neutral",
                    "reason_zh": "摘要提到监管或央行背景。",
                    "evidence_refs": ["item:title"],
                }
            ],
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
            prompt_text_hash=text_sha256(stage.instructions),
        )
        return SimpleNamespace(
            model_dump=lambda mode="json": {
                "lane": stage.lane,
                "mode": mode,
                "artifact_version_hash": artifact_version_hash,
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


def _packet() -> NewsItemBriefInputPacket:
    return NewsItemBriefInputPacket(
        packet_id="packet-1",
        news_item=NewsItemBriefNewsItem(
            news_item_id="news-1",
            title="Fed says crypto supervision remains active",
            summary="A short source summary.",
        ),
        entity_lanes=[],
        market_scope=["crypto", "macro_rates"],
        agent_admission={"status": "eligible", "reason": "provider_score_high"},
        similarity={},
        material_delta={},
        prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
        schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
        input_hash="input-hash",
    )
