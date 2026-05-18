"""SDK plumbing tests for the packet-only pulse decision client.

Coverage focus:
- ``StrictJsonOutputSchema`` strict + jsonref flattening (qwen3.6 / llama.cpp).
- ``_extract_usage`` reflective object → dict serialization.
- Base URL normalization on construction.
- Pulse public runtime no longer registers critical data-acquisition tools.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from gmgn_twitter_intel.domains.pulse_lab.providers import EvidenceDebateMemo
from gmgn_twitter_intel.domains.pulse_lab.services.agent_runtime import build_pulse_runtime_manifest
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_decision_runtime import (
    PulseDecisionRuntimeService,
)
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    FinalDecision,
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
    schema = StrictJsonOutputSchema(EvidenceDebateMemo)
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
    assert schema.output_type is EvidenceDebateMemo


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
        decision_runtime=PulseDecisionRuntimeService(db_pool=object()),
        base_url="https://api.openai.com",
    )

    assert gateway.openai_client_calls == [
        {"model": "gpt-test", "base_url": "https://api.openai.com/v1", "timeout_s": 20.0}
    ]


def test_pulse_client_requires_decision_runtime_only() -> None:
    import pytest

    with pytest.raises(ValueError, match="decision_runtime is required"):
        OpenAIAgentsPulseDecisionClient(
            api_key="sk-test",
            model="gpt-test",
            llm_gateway=_FakeGateway(),
            decision_runtime=None,  # type: ignore[arg-type]
        )


def test_pulse_client_runtime_contract_is_packet_only_without_tools() -> None:
    client = OpenAIAgentsPulseDecisionClient(
        api_key="sk-test",
        model="gpt-test",
        llm_gateway=_FakeGateway(),
        decision_runtime=PulseDecisionRuntimeService(db_pool=object()),
        runner=object(),
    )

    contract = client.runtime_contract

    assert contract.stage_names == ("evidence_debate", "decision_maker")
    assert contract.tool_names_by_stage == {"evidence_debate": (), "decision_maker": ()}
    assert contract.manifest_kwargs()["tool_names_by_stage"] == {
        "evidence_debate": (),
        "decision_maker": (),
    }
    assert "route_tool_budgets" not in contract.manifest_kwargs()


def test_pulse_runtime_manifest_declares_packet_schema_and_no_tools() -> None:
    manifest = build_pulse_runtime_manifest(
        provider="openai",
        model="gpt-test",
        artifact_version_hash="artifact:gpt-test",
        timeout_seconds=20.0,
    )

    assert manifest["runtime"]["stages"] == ["evidence_debate", "decision_maker"]
    assert manifest["runtime"]["tool_names_by_stage"] == {
        "evidence_debate": [],
        "decision_maker": [],
    }
    assert "route_tool_budgets" not in manifest["runtime"]
    assert manifest["contracts"]["evidence_packet_schema_version"]


def test_evidence_debate_stage_input_contains_packet_hash_and_allowed_refs() -> None:
    runtime = PulseDecisionRuntimeService(db_pool=object())
    packet = {
        "evidence_packet_id": "pkt-1",
        "evidence_packet_hash": "sha256:packet",
        "schema_version": "pulse-evidence-packet-v1",
        "candidate_id": "candidate-1",
        "target_id": "asset:pepe",
        "allowed_evidence_refs": [
            {"ref_id": "event:evt-1", "summary_zh": "高粉账号提及"},
            {"ref_id": "metric:market:price_usd", "summary_zh": "价格快照"},
        ],
    }

    spec = runtime.evidence_debate_stage_spec(
        route="meme",
        evidence_packet=packet,
        evidence_gate={"status": "complete"},
    )

    assert spec.stage == "evidence_debate"
    assert spec.input_payload["evidence_packet_hash"] == "sha256:packet"
    assert spec.input_payload["allowed_evidence_ref_ids"] == [
        "event:evt-1",
        "metric:market:price_usd",
    ]
