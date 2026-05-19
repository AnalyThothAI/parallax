from __future__ import annotations

import asyncio
from typing import Any

import pytest

from gmgn_twitter_intel.domains.pulse_lab.services import pulse_candidate_job_service as job_module
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_gate import PulseGateResult
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_job_service import PulseCandidateJobService
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import PulseStageFailure, StageRunAudit
from tests.unit.test_pulse_candidate_worker import (
    NOW_MS,
    FakeClient,
    FakeDB,
    FakeRepos,
    _factor_snapshot,
    _pulse_context,
    _settings,
)


def test_pre_audit_failure_marks_job_failed() -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    job = _enqueue_context_job(repos, context)

    def gate_func(**_: Any) -> PulseGateResult:
        raise RuntimeError("gate exploded")

    service = _service(repos, gate_func=gate_func)

    with pytest.raises(RuntimeError, match="gate exploded"):
        asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    assert len(repos.pulse_jobs.failures) == 1
    assert repos.pulse_jobs.failures[0]["job"]["job_id"] == job["job_id"]
    assert repos.pulse_jobs.failures[0]["error"] == "gate exploded"
    assert repos.pulse_jobs.failures[0]["failure_reason"] == "unexpected_exception"
    assert repos.pulse_runs.finished_runs == []
    assert repos.pulse_agent_eval.eval_cases == []


def test_provider_stage_failure_records_failed_run_eval_and_job_failure() -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    job = _enqueue_context_job(repos, context)

    class FailingClient(FakeClient):
        async def run_decision_pipeline(self, **kwargs: Any) -> Any:
            failed_audit = StageRunAudit(
                stage="evidence_debate",
                route=kwargs["route"],
                attempt_index=0,
                input_json={"context": kwargs["context"]},
                prompt_text="fake evidence debate prompt",
                response_json={"raw_output": "not valid json"},
                trace_metadata_json={"stage": "evidence_debate"},
                usage_json={"input_tokens": 11},
                latency_ms=42,
                started_at_ms=NOW_MS - 42,
                finished_at_ms=NOW_MS,
                status="failed",
                error="ModelBehaviorError: invalid JSON",
            )
            raise PulseStageFailure("model_validate failed", audits=(failed_audit,))

    service = _service(repos, client=FailingClient())

    with pytest.raises(PulseStageFailure):
        asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    failed_step = next(row for row in repos.pulse_runs.agent_run_steps if row["stage"] == "evidence_debate")
    assert failed_step["status"] == "failed"
    failed_run = next(row for row in repos.pulse_runs.finished_runs if row["status"] == "failed")
    assert failed_run["trace_metadata_json_patch"] == {"failure_reason": "invalid_schema"}
    assert repos.pulse_agent_eval.eval_cases[0]["expected_json"] == {
        "status": "fail",
        "failure_reason": "invalid_schema",
    }
    assert repos.pulse_agent_eval.eval_results[0]["status"] == "pass"
    assert repos.pulse_jobs.failures[0]["failure_reason"] == "invalid_schema"


def test_hard_blocked_success_records_evidence_gate_without_provider_run() -> None:
    repos = FakeRepos()
    repos.pulse_evidence_sources.market_facts = []
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    job = _enqueue_context_job(repos, context)
    client = FakeClient()
    service = _service(repos, client=client)

    asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    assert client.run_calls == 0
    gate_step = next(row for row in repos.pulse_runs.agent_run_steps if row["stage"] == "evidence_completeness_gate")
    assert gate_step["response_json"]["hard_blocked"] is True
    finished_run = next(row for row in repos.pulse_runs.finished_runs if row["status"] == "done")
    assert finished_run["outcome"] == "blocked_market_contract"
    assert repos.pulse_jobs.successes == [job["job_id"]]


def test_normal_success_records_candidate_playbook_eval_and_job_success(monkeypatch: pytest.MonkeyPatch) -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    job = _enqueue_context_job(repos, context)
    client = FakeClient(recommendation="trade_candidate")
    monkeypatch.setattr(job_module, "grade_pulse_deterministic_eval_case", _passing_eval_result)
    service = _service(repos, client=client)

    asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    assert client.run_calls == 1
    assert repos.pulse_runs.finished_runs[0]["status"] == "done"
    assert repos.pulse_runs.finished_runs[0]["outcome"] == "completed"
    assert repos.pulse_agent_eval.eval_cases
    assert repos.pulse_agent_eval.eval_results
    assert repos.pulse_candidates.candidate_upserts[0]["decision_recommendation"] == "trade_candidate"
    assert repos.pulse_playbooks.playbook_upserts
    assert repos.pulse_jobs.successes == [job["job_id"]]


def test_eval_failure_blocks_public_candidate_write(monkeypatch: pytest.MonkeyPatch) -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    job = _enqueue_context_job(repos, context)

    monkeypatch.setattr(
        job_module,
        "grade_pulse_deterministic_eval_case",
        lambda _case: {
            "eval_result_id": "eval-result-fail",
            "eval_case_id": "eval-case-fail",
            "runtime_hash": "sha256:test",
            "status": "fail",
            "score": 0.0,
            "grader_version": "test",
            "details_json": {"violations": ["unsupported_claim"]},
        },
    )
    service = _service(repos, client=FakeClient(recommendation="trade_candidate"))

    asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    assert repos.pulse_candidates.candidate_upserts[0]["display_status"] == "hidden_invalid_output"
    assert repos.pulse_playbooks.playbook_upserts == []
    assert repos.pulse_agent_eval.eval_results[0]["status"] == "fail"
    assert repos.pulse_agent_eval.eval_results[0]["details_json"]["write_gate"] == {
        "write_allowed": True,
        "public_write_allowed": False,
        "playbook_write_allowed": False,
        "decision_status": "invalid",
        "display_status": "hidden_invalid_output",
        "reason": "deterministic_eval_failed",
    }
    assert repos.pulse_jobs.successes == [job["job_id"]]


def test_risk_rejected_high_info_clips_recommendation_and_playbook(monkeypatch: pytest.MonkeyPatch) -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    job = _enqueue_context_job(repos, context)
    monkeypatch.setattr(job_module, "grade_pulse_deterministic_eval_case", _passing_eval_result)

    def gate_func(**_: Any) -> PulseGateResult:
        return PulseGateResult(
            pulse_status="risk_rejected_high_info",
            verdict="risk_rejected_high_info",
            candidate_score=82.0,
            score_band="watch",
            gate_reasons=["risk_rejected_high_info"],
            risk_reasons=["timing_chase_risk"],
            hard_risks=["timing_chase_risk"],
            max_recommendation="ignore",
            eligible_for_high_alert=False,
            blocked_reasons=[],
        )

    service = _service(repos, client=FakeClient(recommendation="trade_candidate"), gate_func=gate_func)

    asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    upsert = repos.pulse_candidates.candidate_upserts[0]
    assert upsert["pulse_status"] == "risk_rejected_high_info"
    assert upsert["decision_recommendation"] == "ignore"
    assert upsert["decision_status"] == "risk_rejected_high_info"
    assert upsert["display_status"] == "display_risk_rejected_high_info"
    assert upsert["decision_json"]["playbook"]["has_playbook"] is False
    assert repos.pulse_playbooks.playbook_upserts == []


def _service(
    repos: FakeRepos,
    *,
    client: Any | None = None,
    gate_func: Any | None = None,
) -> PulseCandidateJobService:
    return PulseCandidateJobService(
        name="pulse_candidate",
        settings=_settings(),
        db=FakeDB(repos),
        decision_client=client or FakeClient(),
        gate_func=gate_func or _passing_gate,
        gate_thresholds=object(),
    )


def _passing_gate(**_: Any) -> PulseGateResult:
    return PulseGateResult(
        pulse_status="trade_candidate",
        verdict="trade_candidate",
        candidate_score=82.0,
        score_band="high_conviction",
        gate_reasons=["factor_snapshot_trade_gate_passed"],
        risk_reasons=[],
        hard_risks=[],
        max_recommendation="trade_candidate",
        eligible_for_high_alert=True,
        blocked_reasons=[],
    )


def _passing_eval_result(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "eval_result_id": "eval-result-pass",
        "eval_case_id": str(case.get("eval_case_id") or "eval-case-pass"),
        "runtime_hash": str(case.get("runtime_hash") or "sha256:test"),
        "status": "pass",
        "score": 1.0,
        "grader_version": "test",
        "details_json": {"violations": []},
    }


def _enqueue_context_job(repos: FakeRepos, context: Any) -> dict[str, Any]:
    repos.pulse_jobs.enqueue_job(
        candidate_id=context.candidate_id,
        candidate_type=context.candidate_type,
        subject_key=context.subject_key,
        window=context.window,
        scope=context.scope,
        trigger_signature=context.trigger_signature,
        timeline_signature=context.timeline_signature,
        priority=context.priority,
        target_type=context.target_type,
        target_id=context.target_id,
        context_json=context.agent_context(),
        max_attempts=3,
        next_run_at_ms=NOW_MS,
        now_ms=NOW_MS,
    )
    claimed = repos.pulse_jobs.claim_due_job(now_ms=NOW_MS)
    assert claimed is not None
    return claimed
