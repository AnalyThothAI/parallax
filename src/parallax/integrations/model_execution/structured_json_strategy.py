from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import litellm

from parallax.integrations.model_execution.output_schema import StrictJsonOutputSchema
from parallax.integrations.model_execution.usage import extract_model_usage
from parallax.platform.agent_capabilities import AgentCapabilityProfile, AgentRequestOptions
from parallax.platform.agent_execution import AgentStageSpec


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
        request_options = _chat_completion_request_options(context.capability_profile.request_options)
        raw_response = await litellm.acompletion(
            model=_litellm_model_name(context.model_name, base_url=self._base_url),
            messages=messages,
            response_format={"type": "json_object"},
            api_key=self._api_key or None,
            base_url=self._base_url or None,
            timeout=float(context.timeout_seconds),
            **request_options,
        )
        parsed = output_schema.validate_json(_first_message_content(raw_response))
        return StructuredOutputOutcome(
            parsed,
            raw_response,
            {
                "parse_mode": "json_object_client_validate",
                "schema_enforcement": "client_validate",
                "usage": extract_model_usage(raw_response),
            },
        )


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
    "runner_input_payload",
]
