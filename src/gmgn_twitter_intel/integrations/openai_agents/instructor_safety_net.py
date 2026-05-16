"""Instructor-backed safety net for openai-agents-python SDK call failures.

Design:
- Does NOT participate in the success path. If Runner.run returns, we return.
- Only triggers on ModelBehaviorError or Pydantic ValidationError.
- Uses an independent AsyncOpenAI instance so instructor.from_openai patching
  cannot affect the SDK's main client.
"""

from __future__ import annotations

import logging
from typing import Any

import instructor
from agents import Agent, Runner
from agents.exceptions import ModelBehaviorError
from agents.run import RunConfig
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

_logger = logging.getLogger(__name__)


class InstructorSafetyNet:
    """Wraps Runner.run with an Instructor-based reask fallback.

    Returned tuple is (final_output, audit_extra). audit_extra always contains
    safety_net_used / safety_net_retries / parse_mode fields suitable to merge
    into StageRunAudit.
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
    ) -> tuple[Any, dict[str, Any]]:
        """Primary path is SDK Runner.run. Fallback is Instructor reask.

        ``pydantic_output_type`` is the underlying Pydantic class the agent expects.
        Pass it explicitly because Agent.output_type may be wrapped (e.g. _JsonOutputSchema).
        """
        try:
            result = await Runner.run(
                agent,
                input_payload,
                run_config=run_config,
                max_turns=1,
            )
            return result.final_output, {
                "safety_net_used": False,
                "safety_net_retries": 0,
                "parse_mode": "strict",
            }
        except (ModelBehaviorError, ValidationError) as exc:
            if not self._enabled:
                raise
            if pydantic_output_type is None:
                # Safety net needs a Pydantic class for response_model. If callers wrap
                # output_type opaquely (e.g. _JsonOutputSchema), they must pass the bare class.
                _logger.warning(
                    "agent_output_invalid_no_pydantic_class agent=%s err=%s",
                    getattr(agent, "name", "?"),
                    str(exc)[:200],
                )
                raise
            _logger.warning(
                "agent_output_invalid_falling_back_to_instructor agent=%s err=%s",
                getattr(agent, "name", "?"),
                str(exc)[:200],
            )
            messages = self._rebuild_messages(agent, input_payload, str(exc))
            inst = self._ensure_instructor()
            obj = await inst.chat.completions.create(
                model=self._model,
                messages=messages,
                response_model=pydantic_output_type,
                max_retries=self._max_retries,
            )
            return obj, {
                "safety_net_used": True,
                "safety_net_retries": self._max_retries,
                "parse_mode": "instructor_reask",
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


__all__ = ["InstructorSafetyNet"]
