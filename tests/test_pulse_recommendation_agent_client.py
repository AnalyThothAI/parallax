from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from agents import ModelBehaviorError

from gmgn_twitter_intel.domains.pulse_lab.interfaces import (
    AGENT_NAME,
    BACKEND,
    PULSE_RECOMMENDATION_PROMPT_VERSION,
    PULSE_RECOMMENDATION_SCHEMA_VERSION,
    WORKFLOW_NAME,
)
from gmgn_twitter_intel.domains.pulse_lab.types.pulse_recommendation import (
    PulseRecommendationPayload,
    collect_factor_keys,
)
from gmgn_twitter_intel.integrations.openai_agents.pulse_recommendation_agent_client import (
    OpenAIAgentsPulseRecommendationClient,
    PulseRecommendationOutputSchema,
)

AVAILABLE_FACTOR_KEYS = [
    "composite",
    "composite.family_scores.semantic_catalyst",
    "composite.family_scores.social_heat",
    "composite.family_scores.social_propagation",
    "composite.family_scores.timing_risk",
    "composite.rank_score",
    "composite.recommended_decision",
    "data_health",
    "data_health.alpha",
    "data_health.identity",
    "data_health.market",
    "data_health.social",
    "gates",
    "gates.blocked_reasons",
    "gates.eligible_for_high_alert",
    "gates.max_decision",
    "normalization",
    "normalization.status",
    "semantic_catalyst",
    "semantic_catalyst.data_health",
    "semantic_catalyst.phase",
    "semantic_catalyst.raw_score",
    "semantic_catalyst.score",
    "semantic_catalyst.weight",
    "social_heat",
    "social_heat.data_health",
    "social_heat.raw_score",
    "social_heat.score",
    "social_heat.unique_authors",
    "social_heat.weight",
    "social_propagation",
    "social_propagation.data_health",
    "social_propagation.duplicate_text_share",
    "social_propagation.independent_authors",
    "social_propagation.raw_score",
    "social_propagation.score",
    "social_propagation.weight",
    "timing_risk",
    "timing_risk.data_health",
    "timing_risk.price_change_status",
    "timing_risk.raw_score",
    "timing_risk.score",
    "timing_risk.weight",
]


class FakeRunner:
    def __init__(self, output: PulseRecommendationPayload | dict[str, object]):
        self.output = output
        self.calls: list[dict[str, object]] = []

    async def run(self, starting_agent, input, *, max_turns, run_config):
        self.calls.append(
            {
                "agent": starting_agent,
                "input": input,
                "max_turns": max_turns,
                "run_config": run_config,
            }
        )
        return SimpleNamespace(final_output=self.output)


def _factor_snapshot() -> dict[str, object]:
    return {
        "schema_version": "token_factor_snapshot_v3_social_attention",
        "subject": {"target_type": "CexToken", "target_id": "cex-token:PEPE", "symbol": "PEPE"},
        "market": {
            "market_status": "anchored",
            "price_change_status": "live_not_persisted",
            "provider": "okx",
            "anchor_price_usd": 0.42,
            "social_signal_start_ms": 1_700_000_000_000,
            "event_price_readiness": {"status": "ready"},
        },
        "gates": {"eligible_for_high_alert": True, "blocked_reasons": [], "max_decision": "high_alert"},
        "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
        "families": {
            "social_heat": _family(76, 0.35, {"unique_authors": 4}, {}),
            "social_propagation": {
                "raw_score": 76,
                "score": 76,
                "weight": 0.3,
                "data_health": "ready",
                "facts": {"independent_authors": 4},
                "factors": {"duplicate_text_share": {"value": 0.12}},
            },
            "semantic_catalyst": _family(76, 0.25, {"phase": "ignition"}, {}),
            "timing_risk": _family(76, 0.1, {"price_change_status": "ready"}, {}),
        },
        "normalization": {"status": "pending_cross_section"},
        "composite": {
            "rank_score": 76,
            "recommended_decision": "watch",
            "family_scores": {
                "social_heat": 76,
                "social_propagation": 76,
                "semantic_catalyst": 76,
                "timing_risk": 76,
            },
        },
        "provenance": {"source_event_ids": ["event-evidence"], "computed_at_ms": 1_700_000_000_000},
    }


def _family(score: int, weight: float, facts: dict[str, object], factors: dict[str, object]) -> dict[str, object]:
    return {
        "raw_score": score,
        "score": score,
        "weight": weight,
        "data_health": "ready",
        "facts": facts,
        "factors": factors,
    }


def _context(**overrides: object) -> dict[str, object]:
    context: dict[str, object] = {
        "candidate_id": "candidate-1",
        "candidate_type": "token_target",
        "subject_key": "target:CexToken:cex-token:PEPE",
        "target_type": "CexToken",
        "target_id": "cex-token:PEPE",
        "factor_snapshot": _factor_snapshot(),
        "gate_result": {"pulse_status": "token_watch", "max_recommendation": "research"},
        "available_factor_keys": [
            "manual.key_should_not_be_used",
        ],
        "source_event_ids": ["event-top", ""],
        "evidence_event_ids": ["event-evidence"],
        "selected_posts": [
            {"event_id": "event-post-1"},
            {"event_id": "event-post-2"},
            {"event_id": ""},
        ],
        "post_clusters": [
            {"event_ids": ["event-cluster-1", "event-cluster-2", "event-post-1"]},
        ],
        "stage_segments": [
            {"representative_event_ids": ["event-stage-1", "event-cluster-2"]},
        ],
    }
    context.update(overrides)
    return context


def _payload(**overrides: object) -> PulseRecommendationPayload:
    payload: dict[str, object] = {
        "schema_version": PULSE_RECOMMENDATION_SCHEMA_VERSION,
        "recommendation": "research",
        "summary_zh": "PEPE 社交扩散有效，但行情和重复文本风险仍需确认。",
        "primary_reasons": [
            {
                "factor_key": "social_heat.unique_authors",
                "explanation_zh": "独立作者扩散正在增加。",
            }
        ],
        "upgrade_conditions": [
            {
                "factor_key": "social_propagation.independent_authors",
                "operator": ">=",
                "value": 4,
                "description_zh": "继续观察独立作者扩散是否增加。",
            }
        ],
        "invalidation_conditions": [
            {
                "factor_key": "social_propagation.duplicate_text_share",
                "operator": ">=",
                "value": 0.5,
                "description_zh": "重复文本继续升高会削弱信号。",
            }
        ],
        "residual_risks": [
            {
                "factor_key": "social_propagation.duplicate_text_share",
                "description_zh": "重复文本可能放大噪声。",
            }
        ],
        "evidence_event_ids": ["event-post-1", "event-cluster-2", "event-evidence"],
        "confidence": 0.71,
    }
    payload.update(overrides)
    return PulseRecommendationPayload.model_validate(payload)


def test_openai_agents_pulse_client_uses_recommendation_output_and_trace_metadata() -> None:
    runner = FakeRunner(_payload())
    client = OpenAIAgentsPulseRecommendationClient(
        api_key="sk-test",
        model="gpt-test",
        runner=runner,
        trace_enabled=True,
        trace_include_sensitive_data=False,
        max_turns=9,
    )

    result = asyncio.run(
        client.write_recommendation(
            context=_context(),
            run_id="run-123",
            job={"job_id": "job-1", "job_type": "pulse_recommendation", "attempt_count": 2},
        )
    )

    call = runner.calls[0]
    agent = call["agent"]
    run_config = call["run_config"]
    decoded_input = json.loads(call["input"])
    assert agent.name == AGENT_NAME
    assert agent.tools == []
    assert isinstance(agent.output_type, PulseRecommendationOutputSchema)
    assert agent.output_type.name() == "PulseRecommendationPayload"
    assert agent.model_settings.retry is not None
    assert agent.model_settings.retry.max_retries == 2
    assert agent.model_settings.retry.policy is not None
    assert agent.model is None
    assert call["max_turns"] == 3
    assert decoded_input["task"] == "write_pulse_recommendation_v1"
    assert set(decoded_input) == {
        "task",
        "factor_snapshot",
        "gate_result",
        "available_factor_keys",
        "selected_posts",
    }
    assert decoded_input["available_factor_keys"] == AVAILABLE_FACTOR_KEYS
    assert run_config.workflow_name == WORKFLOW_NAME
    assert run_config.group_id == "candidate-1"
    assert run_config.trace_id.startswith("trace_")
    assert run_config.trace_include_sensitive_data is False
    assert run_config.tracing_disabled is False
    assert "Do not invent facts" in agent.instructions
    assert (
        "Every primary reason, upgrade condition, invalidation condition, and residual risk must cite a factor_key "
        "present in available_factor_keys"
    ) in agent.instructions
    assert "Recommendation cannot upgrade beyond gate_result.max_recommendation" in agent.instructions
    assert run_config.trace_metadata == {
        "backend": BACKEND,
        "run_id": "run-123",
        "job_id": "job-1",
        "job_type": "pulse_recommendation",
        "attempt_count": 2,
        "prompt_version": PULSE_RECOMMENDATION_PROMPT_VERSION,
        "schema_version": PULSE_RECOMMENDATION_SCHEMA_VERSION,
        "model": "gpt-test",
        "artifact_version_hash": "artifact:gpt-test",
        "input_hash": result.agent_run_audit["input_hash"],
        "candidate_id": "candidate-1",
        "candidate_type": "token_target",
        "subject_key": "target:CexToken:cex-token:PEPE",
        "target_type": "CexToken",
        "target_id": "cex-token:PEPE",
    }
    assert result.payload.recommendation == "research"
    assert result.agent_run_audit["workflow_name"] == WORKFLOW_NAME
    assert result.agent_run_audit["agent_name"] == AGENT_NAME
    assert result.agent_run_audit["prompt_version"] == PULSE_RECOMMENDATION_PROMPT_VERSION
    assert result.agent_run_audit["schema_version"] == PULSE_RECOMMENDATION_SCHEMA_VERSION
    assert result.agent_run_audit["sdk_trace_id"] == run_config.trace_id
    assert result.agent_run_audit["output_hash"].startswith("sha256:")


def test_pulse_recommendation_output_schema_accepts_single_json_fence() -> None:
    schema = PulseRecommendationOutputSchema()
    payload_json = _payload().model_dump_json()

    parsed = schema.validate_json(f"```json\n{payload_json}\n```")

    assert isinstance(parsed, PulseRecommendationPayload)
    assert parsed.recommendation == "research"


def test_pulse_recommendation_output_schema_rejects_prose_wrapped_json_fence() -> None:
    schema = PulseRecommendationOutputSchema()
    payload_json = _payload().model_dump_json()

    with pytest.raises(ModelBehaviorError):
        schema.validate_json(f"Here is the JSON:\n```json\n{payload_json}\n```")


def test_openai_agents_pulse_client_uses_subject_key_group_without_candidate_id() -> None:
    runner = FakeRunner(_payload(recommendation="ignore"))
    client = OpenAIAgentsPulseRecommendationClient(api_key="sk-test", model="gpt-test", runner=runner)

    asyncio.run(
        client.write_recommendation(
            context=_context(candidate_id=None, candidate_type="source_seed", target_type=None, target_id=None),
            run_id="run-123",
            job={},
        )
    )

    assert runner.calls[0]["run_config"].group_id == "target:CexToken:cex-token:PEPE"


def test_openai_agents_pulse_client_sanitizes_event_ids_before_return() -> None:
    runner = FakeRunner(
        _payload(
            evidence_event_ids=["event-outside"],
        )
    )
    client = OpenAIAgentsPulseRecommendationClient(api_key="sk-test", model="gpt-test", runner=runner)

    result = asyncio.run(client.write_recommendation(context=_context(), run_id="run-123", job={}))

    assert result.payload.evidence_event_ids == ["event-top"]


def test_openai_agents_pulse_client_validates_factor_keys_before_return() -> None:
    runner = FakeRunner(
        _payload(
            primary_reasons=[
                {
                    "factor_key": "unknown.factor",
                    "explanation_zh": "未知因子不应通过。",
                }
            ]
        )
    )
    client = OpenAIAgentsPulseRecommendationClient(api_key="sk-test", model="gpt-test", runner=runner)

    with pytest.raises(ValueError, match="factor_key"):
        asyncio.run(client.write_recommendation(context=_context(), run_id="run-123", job={}))


def test_openai_agents_pulse_client_collects_factor_keys_from_snapshot() -> None:
    client = OpenAIAgentsPulseRecommendationClient(api_key="sk-test", model="gpt-test", runner=FakeRunner(_payload()))

    audit = client.request_audit(context=_context(), run_id="run-123", job={})

    assert audit["available_factor_keys"] == sorted(collect_factor_keys(_context()["factor_snapshot"]))


def test_openai_agents_pulse_client_validates_max_recommendation_before_return() -> None:
    runner = FakeRunner(_payload(recommendation="alert"))
    client = OpenAIAgentsPulseRecommendationClient(api_key="sk-test", model="gpt-test", runner=runner)

    with pytest.raises(ValueError, match="max_recommendation"):
        asyncio.run(client.write_recommendation(context=_context(), run_id="run-123", job={}))


def test_openai_agents_pulse_client_can_build_request_audit_before_model_returns() -> None:
    client = OpenAIAgentsPulseRecommendationClient(
        api_key="sk-test",
        model="gpt-test",
        runner=FakeRunner(_payload()),
        max_turns=0,
    )

    audit = client.request_audit(
        context=_context(),
        run_id="run-fail",
        job={"job_id": "job-fail", "job_type": "pulse_recommendation", "attempt_count": 4},
    )

    assert audit["backend"] == BACKEND
    assert audit["sdk_trace_id"].startswith("trace_")
    assert audit["workflow_name"] == WORKFLOW_NAME
    assert audit["agent_name"] == AGENT_NAME
    assert audit["input_hash"].startswith("sha256:")
    assert "output_hash" not in audit
    assert audit["input_source_event_ids"] == [
        "event-top",
        "event-evidence",
        "event-post-1",
        "event-post-2",
        "event-cluster-1",
        "event-cluster-2",
        "event-stage-1",
    ]
    assert audit["available_factor_keys"] == AVAILABLE_FACTOR_KEYS
    assert audit["max_recommendation"] == "research"
    assert audit["trace_metadata"]["attempt_count"] == 4


def test_openai_agents_pulse_client_sets_configured_trace_export_key(monkeypatch) -> None:
    exported_keys: list[str] = []
    monkeypatch.setattr(
        "gmgn_twitter_intel.integrations.openai_agents.pulse_recommendation_agent_client.set_tracing_export_api_key",
        exported_keys.append,
    )

    client = OpenAIAgentsPulseRecommendationClient(
        api_key="sk-configured",
        model="gpt-test",
        runner=FakeRunner(_payload()),
        trace_enabled=True,
    )

    assert client.max_turns == 3
    assert exported_keys == ["sk-configured"]


def test_openai_agents_pulse_client_does_not_export_custom_provider_key(monkeypatch) -> None:
    exported_keys: list[str] = []
    monkeypatch.setattr(
        "gmgn_twitter_intel.integrations.openai_agents.pulse_recommendation_agent_client.set_tracing_export_api_key",
        exported_keys.append,
    )

    client = OpenAIAgentsPulseRecommendationClient(
        api_key="custom-provider-key",
        model="qwen3.6",
        base_url="https://big9er.com/v1",
        runner=FakeRunner(_payload()),
        trace_enabled=True,
    )

    assert exported_keys == []
    assert client.trace_enabled is False
