from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from agents import Agent, RunConfig, Runner
from agents.exceptions import ModelBehaviorError
from pydantic import ValidationError

from gmgn_twitter_intel.integrations.openai_agents.agent_model_settings import (
    default_agent_model_settings,
)
from gmgn_twitter_intel.integrations.openai_agents.agent_output_schema import StrictJsonOutputSchema
from gmgn_twitter_intel.integrations.openai_agents.instructor_safety_net import (
    InstructorSafetyNet,
    extract_sdk_usage,
)
from gmgn_twitter_intel.platform.agent_capabilities import AgentCapabilityProfile, AgentRequestOptions
from gmgn_twitter_intel.platform.agent_execution import AgentRuntimeDefaultsPolicy, AgentStageSpec


@dataclass(frozen=True, slots=True)
class StructuredOutputContext:
    stage: AgentStageSpec
    model_name: str
    timeout_seconds: float
    defaults: AgentRuntimeDefaultsPolicy
    capability_profile: AgentCapabilityProfile
    trace_metadata: dict[str, Any]
    trace_id: str = ""
    group_id: str = ""
    trace_enabled: bool = False
    trace_include_sensitive_data: bool = False


@dataclass(frozen=True, slots=True)
class StructuredOutputOutcome:
    final_output: Any
    raw_result: Any | None
    audit_extra: dict[str, Any]


class StructuredOutputStrategy(Protocol):
    async def run(self, context: StructuredOutputContext) -> StructuredOutputOutcome: ...


class AgentsJsonSchemaStrategy:
    def __init__(
        self,
        *,
        model_factory: Callable[[str, float], Any],
        runner: Any | None = None,
        safety_net: InstructorSafetyNet | None = None,
    ) -> None:
        self._model_factory = model_factory
        self._runner = runner or Runner
        self._safety_net = safety_net

    async def run(self, context: StructuredOutputContext) -> StructuredOutputOutcome:
        output_schema = StrictJsonOutputSchema(context.stage.output_type)
        model = self._model_factory(context.model_name, context.timeout_seconds)
        agent = Agent(
            name=context.stage.agent_name,
            instructions=context.stage.instructions,
            output_type=output_schema,
            tools=context.stage.tools,
            model=model,
            model_settings=default_agent_model_settings(
                disable_thinking=context.defaults.disable_thinking,
                include_usage=context.defaults.include_usage,
            ),
        )
        run_config = RunConfig(
            workflow_name=context.stage.workflow_name,
            trace_id=context.trace_id,
            group_id=context.group_id,
            trace_include_sensitive_data=context.trace_include_sensitive_data,
            tracing_disabled=not context.trace_enabled,
            trace_metadata=context.trace_metadata,
        )
        runner_input = runner_input_payload(context.stage.input_payload)
        if self._safety_net is not None:
            final_output, audit_extra, raw_result = await self._safety_net.run_with_safety_net(
                agent=agent,
                input_payload=runner_input,
                run_config=run_config,
                pydantic_output_type=getattr(output_schema, "output_type", context.stage.output_type),
                context=None,
                max_turns=context.stage.max_turns,
                return_result=True,
            )
            return StructuredOutputOutcome(final_output, raw_result, dict(audit_extra))
        raw_result = await self._runner.run(
            agent,
            runner_input,
            max_turns=context.stage.max_turns,
            run_config=run_config,
        )
        return StructuredOutputOutcome(
            getattr(raw_result, "final_output", None),
            raw_result,
            {
                "safety_net_used": False,
                "safety_net_retries": 0,
                "parse_mode": "strict",
                "usage": extract_sdk_usage(raw_result),
            },
        )


class ChatJsonObjectStrategy:
    def __init__(self, *, openai_client_factory: Callable[..., Any]) -> None:
        self._openai_client_factory = openai_client_factory

    async def run(self, context: StructuredOutputContext) -> StructuredOutputOutcome:
        if context.stage.max_turns != 1:
            raise ValueError("json_object strategy supports max_turns=1 only")
        output_schema = StrictJsonOutputSchema(context.stage.output_type)
        schema = output_schema.json_schema()
        client = self._openai_client_factory(
            model=context.model_name,
            timeout_s=context.timeout_seconds,
        )
        messages = _json_object_messages(
            instructions=context.stage.instructions,
            input_payload=context.stage.input_payload,
            schema=schema,
        )
        attempts = max(1, int(context.capability_profile.client_validation_retries) + 1)
        last_error: Exception | None = None
        raw_response: Any | None = None
        request_options = _chat_completion_request_options(context.capability_profile.request_options)
        for attempt_index in range(attempts):
            raw_response = await client.chat.completions.create(
                model=context.model_name,
                messages=messages,
                response_format={"type": "json_object"},
                **request_options,
            )
            text = _first_message_content(raw_response)
            try:
                parsed = output_schema.validate_json(text)
                return StructuredOutputOutcome(
                    parsed,
                    raw_response,
                    {
                        "safety_net_used": attempt_index > 0,
                        "safety_net_retries": attempt_index,
                        "parse_mode": "json_object_client_validate",
                        "schema_enforcement": "client_validate",
                        "usage": extract_sdk_usage(raw_response),
                    },
                )
            except (ModelBehaviorError, ValidationError, ValueError) as exc:
                last_error = exc
                messages = _append_validation_reask(messages, error=str(exc), schema=schema)
        raise last_error or ValueError("json_object response validation failed")


def runner_input_payload(input_payload: Any) -> Any:
    if isinstance(input_payload, str | list):
        return input_payload
    try:
        return json.dumps(input_payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        return str(input_payload)


def _json_object_messages(*, instructions: str, input_payload: Any, schema: dict[str, Any]) -> list[dict[str, str]]:
    system = (
        f"{instructions.strip()}\n\n"
        "Return exactly one valid JSON object. Do not include markdown. "
        "The JSON object must match this JSON schema after application-side validation:\n"
        f"{json.dumps(schema, ensure_ascii=False, sort_keys=True)}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": runner_input_payload(input_payload)},
    ]


def _first_message_content(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    return str(content or "")


def _append_validation_reask(
    messages: list[dict[str, str]],
    *,
    error: str,
    schema: dict[str, Any],
) -> list[dict[str, str]]:
    return [
        *messages,
        {
            "role": "user",
            "content": (
                "The previous JSON object failed application validation. "
                f"Validation error: {error[:1000]}\n"
                "Return one corrected JSON object only for this schema:\n"
                f"{json.dumps(schema, ensure_ascii=False, sort_keys=True)}"
            ),
        },
    ]


def _chat_completion_request_options(request_options: AgentRequestOptions) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if request_options.extra_body:
        kwargs["extra_body"] = dict(request_options.extra_body)
    if request_options.max_tokens is not None:
        kwargs["max_tokens"] = request_options.max_tokens
    return kwargs


__all__ = [
    "AgentsJsonSchemaStrategy",
    "ChatJsonObjectStrategy",
    "StructuredOutputContext",
    "StructuredOutputOutcome",
    "StructuredOutputStrategy",
    "runner_input_payload",
]
