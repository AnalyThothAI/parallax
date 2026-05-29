from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import litellm
from pydantic import ValidationError

from gmgn_twitter_intel.integrations.model_execution.output_schema import StrictJsonOutputSchema
from gmgn_twitter_intel.integrations.model_execution.usage import extract_model_usage
from gmgn_twitter_intel.platform.agent_capabilities import AgentCapabilityProfile, AgentRequestOptions
from gmgn_twitter_intel.platform.agent_execution import AgentStageSpec


@dataclass(frozen=True, slots=True)
class StructuredOutputContext:
    stage: AgentStageSpec
    model_name: str
    timeout_seconds: float
    capability_profile: AgentCapabilityProfile


@dataclass(frozen=True, slots=True)
class StructuredOutputOutcome:
    final_output: Any
    raw_result: Any | None
    audit_extra: dict[str, Any]


class StructuredOutputStrategy(Protocol):
    async def run(self, context: StructuredOutputContext) -> StructuredOutputOutcome: ...


class ChatJsonObjectStrategy:
    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self._api_key = str(api_key or "")
        self._base_url = str(base_url or "").strip().rstrip("/")

    async def run(self, context: StructuredOutputContext) -> StructuredOutputOutcome:
        output_schema = StrictJsonOutputSchema(context.stage.output_type)
        schema = output_schema.json_schema()
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
            raw_response = await litellm.acompletion(
                model=_litellm_model_name(context.model_name, base_url=self._base_url),
                messages=messages,
                response_format={"type": "json_object"},
                api_key=self._api_key or None,
                base_url=self._base_url or None,
                timeout=float(context.timeout_seconds),
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
                        "usage": extract_model_usage(raw_response),
                    },
                )
            except (ValidationError, ValueError) as exc:
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
    choices = _response_get(response, "choices") or []
    if not choices:
        return ""
    message = _response_get(choices[0], "message")
    content = _response_get(message, "content")
    return str(content or "")


def _response_get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


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


def _litellm_model_name(model_name: str, *, base_url: str) -> str:
    normalized = str(model_name or "").strip()
    if "/" in normalized or not str(base_url or "").strip():
        return normalized
    return f"openai/{normalized}"


__all__ = [
    "ChatJsonObjectStrategy",
    "StructuredOutputContext",
    "StructuredOutputOutcome",
    "StructuredOutputStrategy",
    "runner_input_payload",
]
