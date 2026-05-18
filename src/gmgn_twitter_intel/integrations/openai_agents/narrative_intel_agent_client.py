from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from typing import Any

from agents import Agent, RunConfig, Runner
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
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
from gmgn_twitter_intel.integrations.openai_agents.agent_model_settings import (
    default_agent_model_settings,
)
from gmgn_twitter_intel.integrations.openai_agents.agent_output_schema import StrictJsonOutputSchema
from gmgn_twitter_intel.integrations.openai_agents.instructor_safety_net import InstructorSafetyNet

BACKEND = "openai_agents_sdk"
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
        api_key: str,
        model: str,
        llm_gateway: Any,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 120.0,
        runner: Any | None = None,
        safety_net: InstructorSafetyNet | None = None,
        trace_enabled: bool = True,
        trace_include_sensitive_data: bool = False,
        workflow_name: str = WORKFLOW_NAME,
        max_turns: int = 1,
    ) -> None:
        self.api_key = api_key
        self.model = str(model or "").strip()
        if not self.model:
            raise ValueError("narrative_intel_model is required")
        if llm_gateway is None:
            raise ValueError("llm_gateway is required")
        self._llm_gateway = llm_gateway
        self.base_url = _api_base(base_url)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.workflow_name = str(workflow_name or "").strip() or WORKFLOW_NAME
        self.trace_enabled = bool(trace_enabled and getattr(self._llm_gateway, "trace_export_enabled", False))
        self.trace_include_sensitive_data = bool(trace_include_sensitive_data)
        self.max_turns = max(1, min(2, int(max_turns)))
        self._runner = runner or Runner
        self._safety_net = safety_net
        self._model = None if runner is not None else self._build_model()

    @property
    def artifact_version_hash(self) -> str:
        return f"artifact:{self.model}"

    async def label_mentions(
        self,
        *,
        run_id: str,
        request: MentionSemanticsBatchRequest,
    ) -> MentionSemanticsBatchResult:
        input_payload, audit = self._request_context(
            run_id=run_id,
            stage="mention_semantics",
            agent_name=MENTION_SEMANTICS_AGENT_NAME,
            group_id=_mention_group_id(request),
            prompt_version=request.prompt_version,
            schema_version=request.schema_version,
            payload=request.model_dump(mode="json"),
            trace_extra={"mention_count": len(request.mentions)},
        )
        agent = Agent(
            name=MENTION_SEMANTICS_AGENT_NAME,
            instructions=_instructions("mention_semantics.md"),
            output_type=StrictJsonOutputSchema(MentionSemanticsAgentPayload),
            tools=[],
            model=self._model,
            model_settings=default_agent_model_settings(),
        )
        final_output, audit_extra = await self._run_agent(
            stage="mention_semantics",
            agent=agent,
            input_payload=input_payload,
            audit=audit,
            pydantic_output_type=MentionSemanticsAgentPayload,
        )
        payload = _coerce_mention_payload(final_output)
        output_json = payload.model_dump(mode="json")
        return MentionSemanticsBatchResult(
            run_id=request.run_id,
            schema_version=request.schema_version,
            prompt_version=request.prompt_version,
            labels=payload.labels,
            failures=payload.failures,
            raw_response=output_json,
            agent_run_audit=_agent_run_audit(audit, audit_extra, output_json),
        )

    async def summarize_discussion(
        self,
        *,
        run_id: str,
        request: DiscussionDigestRequest,
    ) -> DiscussionDigestResult:
        input_payload, audit = self._request_context(
            run_id=run_id,
            stage="discussion_digest",
            agent_name=DISCUSSION_DIGEST_AGENT_NAME,
            group_id=request.target_id,
            prompt_version=request.prompt_version,
            schema_version=request.schema_version,
            payload=request.model_dump(mode="json"),
            trace_extra={
                "target_type": request.target_type,
                "target_id": request.target_id,
                "window": request.window,
                "scope": request.scope,
                "mention_count": len(request.mentions),
            },
        )
        agent = Agent(
            name=DISCUSSION_DIGEST_AGENT_NAME,
            instructions=_instructions("discussion_digest.md"),
            output_type=StrictJsonOutputSchema(DiscussionDigestAgentPayload),
            tools=[],
            model=self._model,
            model_settings=default_agent_model_settings(),
        )
        final_output, audit_extra = await self._run_agent(
            stage="discussion_digest",
            agent=agent,
            input_payload=input_payload,
            audit=audit,
            pydantic_output_type=DiscussionDigestAgentPayload,
        )
        payload = _coerce_digest_payload(final_output)
        output_json = payload.model_dump(mode="json")
        return DiscussionDigestResult(
            run_id=request.run_id,
            schema_version=request.schema_version,
            prompt_version=request.prompt_version,
            digest=payload.digest,
            raw_response=output_json,
            agent_run_audit=_agent_run_audit(audit, audit_extra, output_json),
        )

    async def aclose(self) -> None:
        return None

    async def _run_agent(
        self,
        *,
        stage: str,
        agent: Agent,
        input_payload: str,
        audit: dict[str, Any],
        pydantic_output_type: type[BaseModel],
    ) -> tuple[Any, dict[str, Any]]:
        run_config = RunConfig(
            workflow_name=self.workflow_name,
            trace_id=audit["sdk_trace_id"],
            group_id=audit["group_id"],
            trace_include_sensitive_data=self.trace_include_sensitive_data,
            tracing_disabled=not self.trace_enabled,
            trace_metadata=audit["trace_metadata"],
        )
        audit_extra: dict[str, Any] = {
            "safety_net_used": False,
            "safety_net_retries": 0,
            "parse_mode": "strict",
        }
        if self._safety_net is not None:
            return await self._llm_gateway.run_with_limits(
                "narrative_intel",
                stage,
                self.timeout_seconds,
                lambda: self._safety_net.run_with_safety_net(
                    agent=agent,
                    input_payload=input_payload,
                    run_config=run_config,
                    pydantic_output_type=pydantic_output_type,
                ),
            )

        result = await self._llm_gateway.run_with_limits(
            "narrative_intel",
            stage,
            self.timeout_seconds,
            lambda: self._runner.run(
                agent,
                input_payload,
                max_turns=self.max_turns,
                run_config=run_config,
            ),
        )
        return result.final_output, audit_extra

    def _request_context(
        self,
        *,
        run_id: str,
        stage: str,
        agent_name: str,
        group_id: str,
        prompt_version: str,
        schema_version: str,
        payload: dict[str, Any],
        trace_extra: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        input_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        input_hash = _sha256(payload)
        trace_metadata = {
            "backend": BACKEND,
            "run_id": run_id,
            "stage": stage,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "model": self.model,
            "artifact_version_hash": self.artifact_version_hash,
            "input_hash": input_hash,
            **trace_extra,
        }
        audit = {
            "backend": BACKEND,
            "sdk_trace_id": _trace_id(run_id),
            "workflow_name": self.workflow_name,
            "agent_name": agent_name,
            "stage": stage,
            "group_id": group_id,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "artifact_version_hash": self.artifact_version_hash,
            "trace_metadata": trace_metadata,
            "input_hash": input_hash,
        }
        return input_payload, audit

    def _build_model(self):
        return OpenAIChatCompletionsModel(
            model=self.model,
            openai_client=self._llm_gateway.openai_client(
                model=self.model,
                base_url=self.base_url,
                timeout_s=self.timeout_seconds,
            ),
        )


def _mention_group_id(request: MentionSemanticsBatchRequest) -> str:
    for mention in request.mentions:
        event_id = str(mention.get("event_id") or "").strip()
        if event_id:
            return event_id
    return request.run_id


def _instructions(filename: str) -> str:
    return (
        files("gmgn_twitter_intel.domains.narrative_intel.prompts")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )


def _agent_run_audit(
    audit: dict[str, Any],
    audit_extra: dict[str, Any],
    output_json: dict[str, Any],
) -> dict[str, Any]:
    return {
        **audit,
        "output_hash": _sha256(output_json),
        "trace_metadata": {**audit["trace_metadata"], **audit_extra},
        "safety_net_used": bool(audit_extra.get("safety_net_used", False)),
        "safety_net_retries": int(audit_extra.get("safety_net_retries") or 0),
        "parse_mode": str(audit_extra.get("parse_mode") or "strict"),
    }


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


def _api_base(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    if not value:
        return "https://api.openai.com/v1"
    return value if value.endswith("/v1") else f"{value}/v1"


def _trace_id(run_id: str) -> str:
    return "trace_" + hashlib.sha256(str(run_id or "").encode("utf-8")).hexdigest()[:32]


def _sha256(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


__all__ = [
    "DiscussionDigestAgentPayload",
    "MentionSemanticsAgentPayload",
    "OpenAIAgentsNarrativeIntelClient",
]
