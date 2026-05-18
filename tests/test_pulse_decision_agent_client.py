"""SDK plumbing tests for the rewritten two-stage pulse decision client.

Coverage focus:
- ``StrictJsonOutputSchema`` strict + jsonref flattening (qwen3.6 / llama.cpp).
- ``_extract_usage`` reflective object → dict serialization.
- Base URL normalization on construction.

The full Investigator → DecisionMaker pipeline (happy path, failure modes,
hallucination guard, tool budget, evidence URL enrichment, runtime manifest)
is covered in
``tests/unit/integrations/openai_agents/test_pulse_decision_two_stage.py``.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from gmgn_twitter_intel.domains.pulse_lab.services.agent_tool_runtime import AgentToolRuntime
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_decision_runtime import (
    PulseDecisionRuntimeService,
)
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    FinalDecision,
    InvestigationReport,
)
from gmgn_twitter_intel.integrations.openai_agents.agent_output_schema import StrictJsonOutputSchema
from gmgn_twitter_intel.integrations.openai_agents.pulse_decision_agent_client import (
    OpenAIAgentsPulseDecisionClient,
    _extract_usage,
)


class _FakeGateway:
    trace_export_enabled = True

    def __init__(self) -> None:
        self.openai_client_calls: list[dict[str, object]] = []

    async def run_with_limits(self, worker_name, stage, timeout_s, coro_factory):
        return await coro_factory()

    def openai_client(self, *, model, base_url, timeout_s):
        self.openai_client_calls.append({"model": model, "base_url": base_url, "timeout_s": timeout_s})
        return object()


def _tool_runtime_factory(*, investigator_max_tool_calls: int):
    return AgentToolRuntime(db_pool=object(), investigator_max_tool_calls=investigator_max_tool_calls)


def test_extract_usage_recursively_returns_json_safe_payload() -> None:
    class InputTokensDetails:
        cached_tokens = 4

    class OutputTokensDetails:
        def __init__(self) -> None:
            self.reasoning_tokens = 7

    class Usage:
        def __init__(self) -> None:
            self.input_tokens = 10
            self.output_tokens = 3
            self.total_tokens = 13
            self.input_tokens_details = InputTokensDetails()
            self.output_tokens_details = OutputTokensDetails()

    payload = _extract_usage(SimpleNamespace(usage=Usage()))

    json.dumps(payload, ensure_ascii=False)
    assert payload == {
        "input_tokens": 10,
        "output_tokens": 3,
        "total_tokens": 13,
        "input_tokens_details": {"cached_tokens": 4},
        "output_tokens_details": {"reasoning_tokens": 7},
    }


def test_extract_usage_serializes_pure_slotted_usage_objects() -> None:
    class Details:
        __slots__ = ("cached_tokens",)

        def __init__(self) -> None:
            self.cached_tokens = 4

    class Usage:
        __slots__ = ("input_tokens", "input_tokens_details", "total_tokens")

        def __init__(self) -> None:
            self.input_tokens = 10
            self.input_tokens_details = Details()
            self.total_tokens = 10

    payload = _extract_usage(SimpleNamespace(usage=Usage()))

    json.dumps(payload, ensure_ascii=False)
    assert payload == {
        "input_tokens": 10,
        "input_tokens_details": {"cached_tokens": 4},
        "total_tokens": 10,
    }


def test_json_output_schema_enables_strict_and_flattens_refs() -> None:
    schema = StrictJsonOutputSchema(InvestigationReport)
    assert schema.is_strict_json_schema() is True
    assert schema.is_plain_text() is False
    flat = schema.json_schema()
    assert "type" in flat
    # jsonref.replace_refs must strip $ref/$defs so llama.cpp grammar conversion
    # does not silent-fail-open (llama.cpp issue #21228).
    serialized = json.dumps(flat)
    assert "$ref" not in serialized
    assert "$defs" not in serialized
    # Expose underlying Pydantic class for InstructorSafetyNet fallback path.
    assert schema.output_type is InvestigationReport


def test_json_output_schema_final_decision_also_flattens_refs() -> None:
    schema = StrictJsonOutputSchema(FinalDecision)
    serialized = json.dumps(schema.json_schema())
    assert "$ref" not in serialized
    assert "$defs" not in serialized


def test_pulse_client_normalizes_openai_root_base_url_before_building_model() -> None:
    gateway = _FakeGateway()

    OpenAIAgentsPulseDecisionClient(
        api_key="sk-test",
        model="gpt-test",
        llm_gateway=gateway,
        tool_runtime_factory=_tool_runtime_factory,
        decision_runtime=PulseDecisionRuntimeService(db_pool=object()),
        base_url="https://api.openai.com",
    )

    assert gateway.openai_client_calls == [
        {"model": "gpt-test", "base_url": "https://api.openai.com/v1", "timeout_s": 20.0}
    ]


def test_pulse_client_requires_injected_runtimes() -> None:
    import pytest

    with pytest.raises(ValueError, match="tool_runtime_factory is required"):
        OpenAIAgentsPulseDecisionClient(
            api_key="sk-test",
            model="gpt-test",
            llm_gateway=_FakeGateway(),
            tool_runtime_factory=None,  # type: ignore[arg-type]
            decision_runtime=PulseDecisionRuntimeService(db_pool=object()),
        )

    with pytest.raises(ValueError, match="decision_runtime is required"):
        OpenAIAgentsPulseDecisionClient(
            api_key="sk-test",
            model="gpt-test",
            llm_gateway=_FakeGateway(),
            tool_runtime_factory=_tool_runtime_factory,
            decision_runtime=None,  # type: ignore[arg-type]
        )
