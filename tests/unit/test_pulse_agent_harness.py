from __future__ import annotations

from gmgn_twitter_intel.domains.pulse_lab.services.agent_harness import (
    PULSE_AGENT_HARNESS_VERSION,
    build_pulse_harness_manifest,
    pulse_harness_hash,
)
from gmgn_twitter_intel.domains.pulse_lab.services.agent_harness_eval import (
    build_pulse_deterministic_eval_case,
    grade_pulse_deterministic_eval_case,
)
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    AnalystOpinion,
    CritiqueReport,
    FinalDecision,
    StageRunAudit,
)


def test_pulse_harness_manifest_hash_is_stable_and_model_sensitive() -> None:
    first = build_pulse_harness_manifest(
        provider="openai",
        model="gpt-5-mini",
        artifact_version_hash="artifact:gpt-5-mini",
        timeout_seconds=20.0,
    )
    same = build_pulse_harness_manifest(
        provider="openai",
        model="gpt-5-mini",
        artifact_version_hash="artifact:gpt-5-mini",
        timeout_seconds=20.0,
    )
    other_model = build_pulse_harness_manifest(
        provider="openai",
        model="gpt-5.5",
        artifact_version_hash="artifact:gpt-5.5",
        timeout_seconds=20.0,
    )

    assert first["harness_version"] == PULSE_AGENT_HARNESS_VERSION
    assert first["strategy"] == "signal_pulse_decision"
    assert first["runtime"]["stages"] == ["analyst", "critic", "judge"]
    assert first["runtime"]["max_turns_per_stage"] == 1
    assert first["contracts"]["decision_routes"] == ["cex", "meme", "research_only"]
    assert first["eval_metadata"]["deterministic_grader_version"] == "pulse-deterministic-harness-v1"
    assert pulse_harness_hash(first).startswith("sha256:")
    assert pulse_harness_hash(first) == pulse_harness_hash(same)
    assert pulse_harness_hash(first) != pulse_harness_hash(other_model)


def test_deterministic_eval_passes_valid_three_stage_decision() -> None:
    final = _final_decision(confidence=0.58)
    case = build_pulse_deterministic_eval_case(
        run_id="run-valid",
        harness_hash="sha256:harness",
        context={"candidate_id": "candidate-1", "candidate_type": "token_target"},
        route="meme",
        completeness={"hard_blocked": False},
        final_decision=final,
        stage_audits=_stage_audits(final=final, critic_ceiling=0.6),
    )

    result = grade_pulse_deterministic_eval_case(case)

    assert result["status"] == "pass"
    assert result["score"] == 1.0
    assert result["details_json"]["violations"] == []


def test_deterministic_eval_flags_critic_ceiling_violation() -> None:
    final = _final_decision(confidence=0.72)
    case = build_pulse_deterministic_eval_case(
        run_id="run-ceiling",
        harness_hash="sha256:harness",
        context={"candidate_id": "candidate-1", "candidate_type": "token_target"},
        route="meme",
        completeness={"hard_blocked": False},
        final_decision=final,
        stage_audits=_stage_audits(final=final, critic_ceiling=0.6),
    )

    result = grade_pulse_deterministic_eval_case(case)

    assert result["status"] == "fail"
    assert result["score"] == 0.0
    assert "critic_confidence_ceiling_exceeded" in result["details_json"]["violations"]


def _stage_audits(*, final: FinalDecision, critic_ceiling: float) -> tuple[StageRunAudit, ...]:
    analyst = AnalystOpinion(
        route="meme",
        recommendation="watchlist",
        confidence=0.55,
        summary_zh="社交流量开始扩散。",
        evidence=["event-1"],
    )
    critic = CritiqueReport(
        route="meme",
        weaknesses=["流动性仍需确认"],
        missing_fact_impacts=[],
        confidence_ceiling=critic_ceiling,
        should_abstain=False,
    )
    return (
        StageRunAudit(
            stage="analyst",
            route="meme",
            attempt_index=0,
            input_json={},
            prompt_text="analyst prompt",
            response_json=analyst.model_dump(mode="json"),
            trace_metadata_json={},
            usage_json={},
            latency_ms=1,
            status="ok",
            error=None,
        ),
        StageRunAudit(
            stage="critic",
            route="meme",
            attempt_index=0,
            input_json={},
            prompt_text="critic prompt",
            response_json=critic.model_dump(mode="json"),
            trace_metadata_json={},
            usage_json={},
            latency_ms=1,
            status="ok",
            error=None,
        ),
        StageRunAudit(
            stage="judge",
            route="meme",
            attempt_index=0,
            input_json={},
            prompt_text="judge prompt",
            response_json=final.model_dump(mode="json"),
            trace_metadata_json={},
            usage_json={},
            latency_ms=1,
            status="ok",
            error=None,
        ),
    )


def _final_decision(*, confidence: float) -> FinalDecision:
    return FinalDecision(
        route="meme",
        recommendation="trade_candidate",
        confidence=confidence,
        abstain_reason=None,
        summary_zh="社交扩散与市场事实共振。",
        invalidation_conditions=["独立作者数回落。"],
        residual_risks=["流动性仍可能变薄。"],
        evidence_event_ids=["event-1"],
    )
