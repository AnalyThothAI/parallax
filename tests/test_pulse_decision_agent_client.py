from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    AnalystOpinion,
    CritiqueReport,
    FinalDecision,
)
from gmgn_twitter_intel.integrations.openai_agents.pulse_decision_agent_client import (
    OpenAIAgentsPulseDecisionClient,
)


class FakeRunner:
    def __init__(self, outputs: list[object]):
        self.outputs = list(outputs)
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
        return SimpleNamespace(final_output=self.outputs.pop(0))


def test_stage_runner_calls_analyst_critic_judge_in_order() -> None:
    runner = FakeRunner(
        [
            _analyst(),
            _critic(),
            _judge(),
        ]
    )
    client = OpenAIAgentsPulseDecisionClient(api_key="sk-test", model="gpt-test", runner=runner)

    result = asyncio.run(
        client.run_decision_pipeline(
            context=_context(),
            run_id="run-1",
            job={"job_id": "job-1", "attempt_count": 2},
            route="meme",
            completeness={"score": 1.0, "missing_fields": []},
            harness=_harness(),
        )
    )

    assert [call["agent"].name for call in runner.calls] == ["MemeAnalyst", "MemeCritic", "MemeJudge"]
    assert result.final_decision.recommendation == "trade_candidate"
    assert [audit.stage for audit in result.stage_audits] == ["analyst", "critic", "judge"]
    assert result.run_audit["agent_name"] == "PulseDecisionPipeline"
    assert result.run_audit["prompt_version"] == "pulse-decision-v1"
    assert result.run_audit["schema_version"] == "pulse_decision_v1"


def test_each_stage_uses_max_turns_one_and_no_tools() -> None:
    runner = FakeRunner([_analyst(route="cex"), _critic(route="cex"), _judge(route="cex")])
    client = OpenAIAgentsPulseDecisionClient(api_key="sk-test", model="gpt-test", runner=runner)

    asyncio.run(
        client.run_decision_pipeline(
            context=_context(),
            run_id="run-1",
            job={},
            route="cex",
            completeness={"score": 1.0, "missing_fields": []},
            harness=_harness(model="gpt-test"),
        )
    )

    assert [call["max_turns"] for call in runner.calls] == [1, 1, 1]
    assert all(call["agent"].tools == [] for call in runner.calls)
    assert [call["agent"].name for call in runner.calls] == ["CexAnalyst", "CexCritic", "CexJudge"]


def test_critic_veto_returns_abstain_final_decision_without_judge() -> None:
    runner = FakeRunner(
        [
            _analyst(),
            _critic(should_abstain=True, confidence_ceiling=0.2),
        ]
    )
    client = OpenAIAgentsPulseDecisionClient(api_key="sk-test", model="gpt-test", runner=runner)

    result = asyncio.run(
        client.run_decision_pipeline(
            context=_context(),
            run_id="run-1",
            job={},
            route="meme",
            completeness={"score": 0.7, "missing_fields": ["holders"]},
            harness=_harness(),
        )
    )

    assert len(runner.calls) == 2
    assert result.final_decision.recommendation == "abstain"
    assert result.final_decision.confidence == 0.2
    assert result.final_decision.abstain_reason == "critic_veto"
    assert [audit.stage for audit in result.stage_audits] == ["analyst", "critic"]


def test_stage_audit_contains_prompt_input_output_and_latency() -> None:
    runner = FakeRunner([_analyst(), _critic(), _judge()])
    client = OpenAIAgentsPulseDecisionClient(api_key="sk-test", model="gpt-test", runner=runner)

    result = asyncio.run(
        client.run_decision_pipeline(
            context=_context(),
            run_id="run-1",
            job={},
            route="meme",
            completeness={"score": 1.0, "missing_fields": []},
            harness=_harness(),
        )
    )

    first = result.stage_audits[0]
    assert first.input_json["route"] == "meme"
    assert first.prompt_text
    assert first.response_json["recommendation"] == "watchlist"
    assert first.latency_ms >= 0
    assert first.status == "ok"


def test_runner_rejects_execution_language_in_final_output() -> None:
    runner = FakeRunner(
        [
            _analyst(),
            _critic(),
            {
                **_judge().model_dump(mode="json"),
                "summary_zh": "可以买入并设置止损。",
            },
        ]
    )
    client = OpenAIAgentsPulseDecisionClient(api_key="sk-test", model="gpt-test", runner=runner)

    with pytest.raises(ValueError, match="trading execution"):
        asyncio.run(
            client.run_decision_pipeline(
                context=_context(),
                run_id="run-1",
                job={},
                route="meme",
                completeness={"score": 1.0, "missing_fields": []},
                harness=_harness(),
            )
        )


def _context() -> dict[str, object]:
    return {
        "candidate_id": "candidate-1",
        "candidate_type": "token_target",
        "subject_key": "asset:pepe",
        "target_type": "Asset",
        "target_id": "asset:pepe",
        "factor_snapshot": {"schema_version": "token_factor_snapshot_v3_social_attention"},
        "selected_posts": [{"event_id": "event-1", "text": "PEPE volume rising"}],
    }


def _harness(*, model: str = "gpt-test") -> dict[str, object]:
    return {
        "harness_version": "pulse-decision-harness-v1",
        "strategy": "signal_pulse_decision",
        "runtime": {"stages": ["analyst", "critic", "judge"], "max_turns_per_stage": 1},
        "model": {"provider": "openai", "model": model, "artifact_version_hash": f"artifact:{model}"},
        "contracts": {"prompt_version": "pulse-decision-v1", "schema_version": "pulse_decision_v1"},
        "eval_metadata": {"deterministic_grader_version": "pulse-deterministic-harness-v1"},
    }


def _analyst(*, route: str = "meme") -> AnalystOpinion:
    return AnalystOpinion(
        route=route,
        recommendation="watchlist",
        confidence=0.62,
        summary_zh="社交热度有效。",
        evidence=["event-1"],
    )


def _critic(*, route: str = "meme", should_abstain: bool = False, confidence_ceiling: float = 0.55) -> CritiqueReport:
    return CritiqueReport(
        route=route,
        weaknesses=["liquidity thin"],
        missing_fact_impacts=[],
        confidence_ceiling=confidence_ceiling,
        should_abstain=should_abstain,
    )


def _judge(*, route: str = "meme") -> FinalDecision:
    return FinalDecision(
        route=route,
        recommendation="trade_candidate",
        confidence=0.55,
        abstain_reason=None,
        summary_zh="社交与市场事实共振。",
        invalidation_conditions=["attention fades"],
        residual_risks=["liquidity thin"],
        evidence_event_ids=["event-1"],
    )
