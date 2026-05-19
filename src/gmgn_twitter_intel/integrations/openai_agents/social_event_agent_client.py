from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.social_enrichment.types.social_event_extraction import (
    AGENT_NAME,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    WORKFLOW_NAME,
    SocialEventPayload,
    payload_from_output,
    social_event_agent_input,
    social_event_agent_instructions,
    social_event_extraction_from_payload,
)
from gmgn_twitter_intel.integrations.openai_agents.agent_execution_types import RUNTIME_VERSION, AgentStageSpec
from gmgn_twitter_intel.integrations.openai_agents.agent_hashing import artifact_hash_for, json_sha256


class OpenAIAgentsSocialEventClient:
    provider = "openai"

    def __init__(
        self,
        *,
        model: str,
        agent_gateway: Any,
        workflow_name: str = WORKFLOW_NAME,
        max_turns: int = 1,
    ):
        self.model = str(model or "").strip()
        if not self.model:
            raise ValueError("llm.model is required")
        if agent_gateway is None:
            raise ValueError("agent_gateway is required")
        self._agent_gateway = agent_gateway
        self.workflow_name = str(workflow_name or "").strip() or WORKFLOW_NAME
        self.max_turns = max(1, min(2, int(max_turns)))

    @property
    def artifact_version_hash(self) -> str:
        return artifact_hash_for(
            model=self.model,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            runtime_version=RUNTIME_VERSION,
            output_schema_hash=json_sha256(SocialEventPayload.model_json_schema()),
        )

    @property
    def timeout_seconds(self) -> float:
        return 120.0

    def request_audit(self, *, event: dict, entities: list[dict], run_id: str, job: dict) -> dict[str, Any]:
        stage = self._stage(event=event, entities=entities, run_id=run_id, job=job)
        audit = self._agent_gateway.request_audit(stage)
        if hasattr(audit, "model_dump"):
            return audit.model_dump(mode="json")
        return dict(audit)

    async def enrich_event(self, *, event: dict, entities: list[dict], run_id: str, job: dict):
        stage = self._stage(event=event, entities=entities, run_id=run_id, job=job)
        execution = await self._agent_gateway.execute(stage)
        payload = payload_from_output(execution.final_output)
        audit = execution.audit.model_dump(mode="json")
        return social_event_extraction_from_payload(
            payload,
            event_text=_event_text(event),
            agent_run_audit=audit,
        )

    def _stage(
        self,
        *,
        event: dict,
        entities: list[dict],
        run_id: str,
        job: dict,
    ) -> AgentStageSpec:
        return AgentStageSpec(
            lane="social.event_enrichment",
            stage="social_event",
            model=self.model,
            instructions=social_event_agent_instructions(),
            input_payload=social_event_agent_input(event=event, entities=entities),
            output_type=SocialEventPayload,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            workflow_name=self.workflow_name,
            agent_name=AGENT_NAME,
            group_id=str(event.get("event_id") or ""),
            trace_metadata={
                "run_id": run_id,
                "event_id": str(event.get("event_id") or ""),
                "job_id": str(job.get("job_id") or ""),
                "job_type": str(job.get("job_type") or ""),
                "attempt_count": int(job.get("attempt_count") or 0),
            },
            max_turns=self.max_turns,
        )


def _event_text(event: dict) -> str:
    text = event.get("search_text") or event.get("text_clean")
    if isinstance(text, str):
        return text
    content = event.get("content")
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"]
    return ""
