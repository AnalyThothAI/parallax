from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from gmgn_twitter_intel.domains.equity_event_intel.types import (
    EQUITY_EVENT_BRIEF_AGENT_NAME,
    EQUITY_EVENT_BRIEF_LANE,
    EQUITY_EVENT_BRIEF_WORKFLOW_NAME,
    EquityEventBriefInputPacket,
    EquityEventBriefPayload,
)
from gmgn_twitter_intel.platform.agent_execution import AgentStageSpec


@lru_cache(maxsize=1)
def equity_event_brief_instructions() -> str:
    return (Path(__file__).resolve().parents[1] / "prompts" / "equity_event_brief.md").read_text(encoding="utf-8")


def build_equity_event_brief_stage(*, packet: EquityEventBriefInputPacket, run_id: str) -> AgentStageSpec:
    story_or_event_id = (
        packet.story_context.story_id if packet.story_context is not None else packet.current_event.company_event_id
    )
    return AgentStageSpec(
        lane=EQUITY_EVENT_BRIEF_LANE,
        stage="equity_event_brief",
        instructions=equity_event_brief_instructions(),
        input_payload=packet.model_dump(mode="json", exclude={"input_hash"}),
        output_type=EquityEventBriefPayload,
        prompt_version=packet.prompt_version,
        schema_version=packet.schema_version,
        workflow_name=EQUITY_EVENT_BRIEF_WORKFLOW_NAME,
        agent_name=EQUITY_EVENT_BRIEF_AGENT_NAME,
        group_id=f"equity_event:{story_or_event_id}",
        trace_metadata={
            "company_event_id": packet.current_event.company_event_id,
            "story_id": packet.story_context.story_id if packet.story_context is not None else None,
            "run_id": str(run_id),
            "input_hash": packet.input_hash,
            "prompt_version": packet.prompt_version,
            "schema_version": packet.schema_version,
        },
        max_turns=1,
        tools=[],
    )


__all__ = ["build_equity_event_brief_stage", "equity_event_brief_instructions"]
