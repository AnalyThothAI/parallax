"""SDK plumbing tests for the packet-only pulse decision client.

Coverage focus:
- ``StrictJsonOutputSchema`` strict + jsonref flattening (qwen3.6 / llama.cpp).
- ``_extract_usage`` reflective object → dict serialization.
- Base URL normalization on construction.
- Pulse public runtime no longer registers critical data-acquisition tools.
"""

from __future__ import annotations

import asyncio
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


class _RawOutputRunner:
    def __init__(self, raw_output: object) -> None:
        self.raw_output = raw_output

    async def run(self, agent, stage_input, *, max_turns, run_config, context):
        return SimpleNamespace(final_output=self.raw_output, usage=SimpleNamespace(total_tokens=3))


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


def test_run_stage_normalizes_raw_dict_before_pydantic_validation_and_records_trace_metadata() -> None:
    raw_output = _final_decision_raw(
        supporting_refs=["event:event-l"],
        playbook={
            "has_playbook": False,
            "watch_signals": ["继续观察链上流动性"],
            "exit_triggers": ["叙事降温"],
            "monitoring_horizon": "4h",
        },
    )
    client = OpenAIAgentsPulseDecisionClient(
        api_key="sk-test",
        model="gpt-test",
        llm_gateway=_FakeGateway(),
        decision_runtime=PulseDecisionRuntimeService(db_pool=object()),
        runner=_RawOutputRunner(raw_output),
    )

    step = asyncio.run(
        client._run_stage(
            stage="decision_maker",
            route="meme",
            agent=object(),  # type: ignore[arg-type]
            output_type=FinalDecision,
            input_payload={
                "evidence_packet": {
                    "candidate_id": "candidate-1",
                    "allowed_evidence_refs": [{"ref_id": "event:event-1", "ref_type": "event"}],
                }
            },
            prompt="decision prompt",
            audit={"trace_metadata": {"run_id": "run-1"}, "sdk_trace_id": "trace-1"},
            max_turns=1,
        )
    )

    assert step.status == "ok"
    assert step.response_json["supporting_evidence_refs"] == ["event:event-1"]
    assert step.response_json["playbook"]["watch_signals"] == []
    assert step.response_json["playbook"]["exit_triggers"] == []
    assert step.trace_metadata_json["schema_normalization"]["repairs"] == [
        {"path": "playbook.watch_signals", "action": "cleared", "reason": "playbook_has_playbook_false"},
        {"path": "playbook.exit_triggers", "action": "cleared", "reason": "playbook_has_playbook_false"},
    ]
    assert step.trace_metadata_json["evidence_ref_canonicalization"]["corrections"] == [
        {
            "path": "supporting_evidence_refs[0]",
            "from": "event:event-l",
            "to": "event:event-1",
            "ref_type": "event",
            "reason": "unique_same_type_edit_distance_1",
        }
    ]


def test_run_stage_normalizes_pydantic_output_instance_before_audit() -> None:
    raw_output = FinalDecision.model_validate(
        _final_decision_raw(
            supporting_refs=["event:event-l"],
            playbook={
                "has_playbook": True,
                "watch_signals": ["成交量继续扩张"],
                "exit_triggers": ["叙事降温"],
                "monitoring_horizon": "4h",
            },
        )
    )
    client = OpenAIAgentsPulseDecisionClient(
        api_key="sk-test",
        model="gpt-test",
        llm_gateway=_FakeGateway(),
        decision_runtime=PulseDecisionRuntimeService(db_pool=object()),
        runner=_RawOutputRunner(raw_output),
    )

    step = asyncio.run(
        client._run_stage(
            stage="decision_maker",
            route="meme",
            agent=object(),  # type: ignore[arg-type]
            output_type=FinalDecision,
            input_payload={
                "evidence_packet": {
                    "candidate_id": "candidate-1",
                    "allowed_evidence_refs": [{"ref_id": "event:event-1", "ref_type": "event"}],
                }
            },
            prompt="decision prompt",
            audit={"trace_metadata": {"run_id": "run-1"}, "sdk_trace_id": "trace-1"},
            max_turns=1,
        )
    )

    assert step.status == "ok"
    assert step.response_json["supporting_evidence_refs"] == ["event:event-1"]
    assert step.trace_metadata_json["evidence_ref_canonicalization"]["corrections"] == [
        {
            "path": "supporting_evidence_refs[0]",
            "from": "event:event-l",
            "to": "event:event-1",
            "ref_type": "event",
            "reason": "unique_same_type_edit_distance_1",
        }
    ]


def _final_decision_raw(*, supporting_refs: list[str], playbook: dict) -> dict:
    return {
        "route": "meme",
        "recommendation": "trade_candidate",
        "confidence": 0.63,
        "abstain_reason": None,
        "summary_zh": "社交与市场证据形成观察。",
        "narrative_archetype": "memetic",
        "narrative_thesis_zh": "社交扩散与市场反馈形成同步观察，但仍需要继续监控证据质量和后续确认。",
        "bull_view": {
            "strength": "moderate",
            "thesis_zh": "社交流量与市场反馈同步增强。",
            "supporting_event_ids": ["event-1"],
        },
        "bear_view": {
            "strength": "weak",
            "thesis_zh": "流动性仍然偏薄，需要观察延续性。",
            "supporting_event_ids": ["event-1"],
        },
        "playbook": playbook,
        "evidence_event_ids": ["event-1"],
        "supporting_evidence_refs": supporting_refs,
        "risk_evidence_refs": [],
        "data_gap_refs": [],
        "invalidation_conditions": [],
        "residual_risks": [],
    }
