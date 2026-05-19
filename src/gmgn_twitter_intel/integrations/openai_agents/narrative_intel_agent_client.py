from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from pydantic import BaseModel, Field

from gmgn_twitter_intel.domains.narrative_intel.types.discussion_digest import (
    DiscussionDigestRequest,
    DiscussionDigestResult,
    TokenDiscussionDigest,
)
from gmgn_twitter_intel.domains.narrative_intel.types.mention_semantics import (
    MentionSemanticLabel,
    MentionSemanticsBatchRequest,
    MentionSemanticsBatchResult,
)
from gmgn_twitter_intel.integrations.openai_agents.agent_execution_types import AgentStageSpec
from gmgn_twitter_intel.integrations.openai_agents.agent_hashing import json_sha256

WORKFLOW_NAME = "gmgn-twitter-intel.narrative_intel"
MENTION_SEMANTICS_AGENT_NAME = "NarrativeMentionSemanticsAgent"
DISCUSSION_DIGEST_AGENT_NAME = "TokenDiscussionDigestAgent"


class MentionSemanticsAgentPayload(BaseModel):
    labels: list[MentionSemanticLabel] = Field(default_factory=list)
    failures: list[dict[str, Any]] = Field(default_factory=list)


class DiscussionDigestAgentPayload(BaseModel):
    digest: TokenDiscussionDigest


class OpenAIAgentsNarrativeIntelClient:
    provider = "openai"

    def __init__(
        self,
        *,
        model: str,
        agent_gateway: Any,
        workflow_name: str = WORKFLOW_NAME,
        max_turns: int = 1,
    ) -> None:
        self.model = str(model or "").strip()
        if not self.model:
            raise ValueError("narrative_intel_model is required")
        if agent_gateway is None:
            raise ValueError("agent_gateway is required")
        self._agent_gateway = agent_gateway
        self.workflow_name = str(workflow_name or "").strip() or WORKFLOW_NAME
        self.max_turns = max(1, int(max_turns))

    @property
    def artifact_version_hash(self) -> str:
        return f"artifact:{self.model}"

    def request_audit_for_label_mentions(
        self,
        *,
        run_id: str,
        request: MentionSemanticsBatchRequest,
    ) -> dict[str, Any]:
        stage = self._label_mentions_stage(run_id=run_id, request=request)
        return self._agent_gateway.request_audit(stage).model_dump(mode="json")

    async def label_mentions(
        self,
        *,
        run_id: str,
        request: MentionSemanticsBatchRequest,
    ) -> MentionSemanticsBatchResult:
        stage = self._label_mentions_stage(run_id=run_id, request=request)
        execution = await self._agent_gateway.execute(stage)
        payload = _coerce_mention_payload(execution.final_output)
        output_json = payload.model_dump(mode="json")
        return MentionSemanticsBatchResult(
            run_id=request.run_id,
            schema_version=request.schema_version,
            prompt_version=request.prompt_version,
            labels=payload.labels,
            failures=payload.failures,
            raw_response=output_json,
            agent_run_audit=_agent_run_audit(execution.audit.model_dump(mode="json"), output_json),
        )

    def request_audit_for_summarize_discussion(
        self,
        *,
        run_id: str,
        request: DiscussionDigestRequest,
    ) -> dict[str, Any]:
        stage = self._summarize_discussion_stage(run_id=run_id, request=request)
        return self._agent_gateway.request_audit(stage).model_dump(mode="json")

    async def summarize_discussion(
        self,
        *,
        run_id: str,
        request: DiscussionDigestRequest,
    ) -> DiscussionDigestResult:
        stage = self._summarize_discussion_stage(run_id=run_id, request=request)
        execution = await self._agent_gateway.execute(stage)
        payload = _coerce_digest_payload(execution.final_output)
        output_json = payload.model_dump(mode="json")
        return DiscussionDigestResult(
            run_id=request.run_id,
            schema_version=request.schema_version,
            prompt_version=request.prompt_version,
            digest=payload.digest,
            raw_response=output_json,
            agent_run_audit=_agent_run_audit(execution.audit.model_dump(mode="json"), output_json),
        )

    async def aclose(self) -> None:
        return None

    def _label_mentions_stage(
        self,
        *,
        run_id: str,
        request: MentionSemanticsBatchRequest,
    ) -> AgentStageSpec:
        payload = request.model_dump(mode="json")
        return AgentStageSpec(
            lane="narrative.mention_semantics",
            stage="mention_semantics",
            model=self.model,
            instructions=_instructions("mention_semantics.md"),
            input_payload=_input_payload(payload),
            output_type=MentionSemanticsAgentPayload,
            prompt_version=request.prompt_version,
            schema_version=request.schema_version,
            workflow_name=self.workflow_name,
            agent_name=MENTION_SEMANTICS_AGENT_NAME,
            group_id=_mention_group_id(request),
            trace_metadata={
                "run_id": run_id,
                "stage": "mention_semantics",
                "schema_version": request.schema_version,
                "prompt_version": request.prompt_version,
                "model": self.model,
                "mention_count": len(request.mentions),
                "target_count": len(_mention_targets(request)),
                "targets": _mention_targets(request),
            },
            max_turns=self.max_turns,
        )

    def _summarize_discussion_stage(
        self,
        *,
        run_id: str,
        request: DiscussionDigestRequest,
    ) -> AgentStageSpec:
        payload = request.model_dump(mode="json")
        return AgentStageSpec(
            lane="narrative.discussion_digest",
            stage="discussion_digest",
            model=self.model,
            instructions=_instructions("discussion_digest.md"),
            input_payload=_input_payload(payload),
            output_type=DiscussionDigestAgentPayload,
            prompt_version=request.prompt_version,
            schema_version=request.schema_version,
            workflow_name=self.workflow_name,
            agent_name=DISCUSSION_DIGEST_AGENT_NAME,
            group_id=request.target_id,
            trace_metadata={
                "run_id": run_id,
                "stage": "discussion_digest",
                "schema_version": request.schema_version,
                "prompt_version": request.prompt_version,
                "model": self.model,
                "target_type": request.target_type,
                "target_id": request.target_id,
                "window": request.window,
                "scope": request.scope,
                "mention_count": len(request.mentions),
            },
            max_turns=self.max_turns,
        )


def _input_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _mention_group_id(request: MentionSemanticsBatchRequest) -> str:
    for mention in request.mentions:
        event_id = str(mention.get("event_id") or "").strip()
        if event_id:
            return event_id
    return request.run_id


def _mention_targets(request: MentionSemanticsBatchRequest) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    targets: list[dict[str, str]] = []
    for mention in request.mentions:
        target_type = str(mention.get("target_type") or "").strip()
        target_id = str(mention.get("target_id") or "").strip()
        if not target_type or not target_id:
            continue
        key = (target_type, target_id)
        if key in seen:
            continue
        seen.add(key)
        targets.append({"target_type": target_type, "target_id": target_id})
    return targets


def _instructions(filename: str) -> str:
    return (
        files("gmgn_twitter_intel.domains.narrative_intel.prompts")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )


def _agent_run_audit(audit: dict[str, Any], output_json: dict[str, Any]) -> dict[str, Any]:
    if audit.get("output_hash"):
        return audit
    return {**audit, "output_hash": json_sha256(output_json)}


def _coerce_mention_payload(value: Any) -> MentionSemanticsAgentPayload:
    if isinstance(value, MentionSemanticsAgentPayload):
        return value
    if isinstance(value, MentionSemanticsBatchResult):
        return MentionSemanticsAgentPayload(labels=value.labels, failures=value.failures)
    return MentionSemanticsAgentPayload.model_validate(value)


def _coerce_digest_payload(value: Any) -> DiscussionDigestAgentPayload:
    if isinstance(value, DiscussionDigestAgentPayload):
        return value
    if isinstance(value, DiscussionDigestResult):
        return DiscussionDigestAgentPayload(digest=value.digest)
    if isinstance(value, TokenDiscussionDigest):
        return DiscussionDigestAgentPayload(digest=value)
    if isinstance(value, dict) and "digest" not in value:
        return DiscussionDigestAgentPayload(digest=TokenDiscussionDigest.model_validate(value))
    return DiscussionDigestAgentPayload.model_validate(value)


__all__ = [
    "DiscussionDigestAgentPayload",
    "MentionSemanticsAgentPayload",
    "OpenAIAgentsNarrativeIntelClient",
]
