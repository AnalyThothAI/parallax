"""Instructor-backed safety net for openai-agents-python SDK call failures.

Design:
- Does NOT participate in the success path. If Runner.run returns, we return
  the SDK output and forward the SDK's usage payload through audit_extra.
- Triggers on ModelBehaviorError or Pydantic ValidationError, runs an Instructor
  reask up to max_retries times; if all retries fail it raises SafetyNetExhausted
  carrying audit_extra so callers can persist a truthful audit row.
- Uses an independent AsyncOpenAI instance so instructor.from_openai patching
  cannot affect the SDK's main client.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, cast

import instructor
from agents import Agent, Runner
from agents.exceptions import ModelBehaviorError
from agents.run import RunConfig
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

_logger = logging.getLogger(__name__)


def _json_safe(value: Any, depth: int = 0) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if depth > 6:
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v, depth + 1) for k, v in value.items() if v is not None}
    if isinstance(value, list | tuple):
        return [_json_safe(item, depth + 1) for item in value]
    # Pydantic models
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        data = dump(mode="json")
        if isinstance(data, dict):
            return _json_safe(data, depth + 1)
    # agents.usage.Usage and similar dataclasses
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _json_safe(dataclasses.asdict(value), depth + 1)
    return str(value)


def _extract_sdk_usage(result: Any) -> dict[str, Any]:
    """Pull a JSON-safe usage dict out of an Agents SDK RunResult, if any."""
    if result is None:
        return {}
    candidates: list[Any] = [
        getattr(result, "usage", None),
        getattr(getattr(result, "context_wrapper", None), "usage", None),
    ]
    for attr in ("raw_response", "response", "final_response"):
        response = getattr(result, attr, None)
        if response is not None:
            candidates.append(getattr(response, "usage", None))
    responses = getattr(result, "raw_responses", None) or getattr(result, "responses", None)
    if isinstance(responses, list | tuple):
        candidates.extend(getattr(response, "usage", None) for response in responses)
    for candidate in candidates:
        if candidate is None:
            continue
        data = _json_safe(candidate)
        if isinstance(data, dict) and data:
            return cast(dict[str, Any], data)
    return {}


def _extract_instructor_usage(obj: Any) -> dict[str, Any]:
    """Instructor v1.15 attaches the raw OpenAI response on _raw_response."""
    raw = getattr(obj, "_raw_response", None)
    if raw is None:
        return {}
    return _extract_sdk_usage(raw)


class SafetyNetExhausted(Exception):
    """Raised when SafetyNet exhausted its Instructor reask retries.

    Carries audit_extra so callers can persist a truthful StageRunAudit row
    (parse_mode='instructor_failed', safety_net_used=True, retries=N)
    before re-raising the underlying ModelBehaviorError / ValidationError.
    """

    def __init__(self, message: str, *, audit_extra: dict[str, Any], original: BaseException) -> None:
        super().__init__(message)
        self.audit_extra = dict(audit_extra)
        self.original = original


class InstructorSafetyNet:
    """Wraps Runner.run with an Instructor-based reask fallback.

    ``run_with_safety_net`` returns ``(final_output, audit_extra)``. ``audit_extra``
    always contains:
      - ``safety_net_used`` (bool)
      - ``safety_net_retries`` (int)
      - ``parse_mode`` (str: 'strict' | 'instructor_reask' | 'instructor_failed')
      - ``usage`` (dict, possibly empty)
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        max_retries: int = 2,
        enabled: bool = True,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._max_retries = max(0, int(max_retries))
        self._enabled = bool(enabled)
        # Independent AsyncOpenAI: instructor.from_openai patches chat.completions.create
        # on the client object, so we MUST NOT share with the SDK's client.
        self._inst_client: AsyncOpenAI | None = None
        self._inst: Any | None = None

    def _ensure_instructor(self) -> Any:
        if self._inst is None:
            self._inst_client = AsyncOpenAI(base_url=self._base_url, api_key=self._api_key)
            # Mode.JSON_SCHEMA matches the response_format strategy SDK already uses on the
            # primary path, so the underlying llama.cpp backend handles both calls the same way.
            self._inst = instructor.from_openai(self._inst_client, mode=instructor.Mode.JSON_SCHEMA)
        return self._inst

    async def aclose(self) -> None:
        if self._inst_client is not None:
            await self._inst_client.close()
            self._inst_client = None
            self._inst = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def run_with_safety_net(
        self,
        *,
        agent: Agent,
        input_payload: Any,
        run_config: RunConfig | None = None,
        pydantic_output_type: type[BaseModel] | None = None,
        context: Any = None,
        max_turns: int = 1,
    ) -> tuple[Any, dict[str, Any]]:
        run_kwargs: dict[str, Any] = {
            "run_config": run_config,
            "max_turns": int(max_turns) if max_turns and int(max_turns) >= 1 else 1,
        }
        if context is not None:
            run_kwargs["context"] = context
        try:
            result = await Runner.run(
                agent,
                input_payload,
                **run_kwargs,
            )
            return result.final_output, {
                "safety_net_used": False,
                "safety_net_retries": 0,
                "parse_mode": "strict",
                "usage": _extract_sdk_usage(result),
            }
        except (ModelBehaviorError, ValidationError) as exc:
            if not self._enabled or pydantic_output_type is None:
                raise
            _logger.warning(
                "agent_output_invalid_falling_back_to_instructor agent=%s err=%s",
                getattr(agent, "name", "?"),
                str(exc)[:200],
            )
            messages = self._rebuild_messages(agent, input_payload, str(exc))
            inst = self._ensure_instructor()
            try:
                obj = await inst.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    response_model=pydantic_output_type,
                    max_retries=self._max_retries,
                )
            except Exception as reask_exc:
                raise SafetyNetExhausted(
                    f"safety_net exhausted after {self._max_retries} retries: {reask_exc}",
                    audit_extra={
                        "safety_net_used": True,
                        "safety_net_retries": self._max_retries,
                        "parse_mode": "instructor_failed",
                        "usage": {},
                    },
                    original=reask_exc,
                ) from reask_exc
            return obj, {
                "safety_net_used": True,
                "safety_net_retries": self._max_retries,
                "parse_mode": "instructor_reask",
                "usage": _extract_instructor_usage(obj),
            }

    @staticmethod
    def _rebuild_messages(agent: Agent, input_payload: Any, error_text: str) -> list[dict[str, str]]:
        instructions = str(getattr(agent, "instructions", "") or "")
        if isinstance(input_payload, str):
            user_content = input_payload
        else:
            try:
                import json as _json

                user_content = _json.dumps(input_payload, ensure_ascii=False)
            except Exception:
                user_content = str(input_payload)
        return [
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_content},
            {
                "role": "user",
                "content": (
                    "Your previous response failed schema validation: "
                    f"{error_text[:500]}. Return JSON that matches the schema exactly. "
                    "Output raw JSON only - no markdown fences, no <think> tags."
                ),
            },
        ]


__all__ = ["InstructorSafetyNet", "SafetyNetExhausted"]
