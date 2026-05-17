from __future__ import annotations

import asyncio
from types import SimpleNamespace
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
    assert repos.pulse_harness.eval_cases == []


def test_provider_stage_failure_records_failed_run_eval_and_job_failure() -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    job = _enqueue_context_job(repos, context)

    class FailingClient(FakeClient):
        async def run_decision_pipeline(self, **kwargs: Any) -> Any:
            failed_audit = StageRunAudit(
                stage="investigator",
                route=kwargs["route"],
                attempt_index=0,
                input_json={"context": kwargs["context"]},
                prompt_text="fake investigator prompt",
                response_json={"raw_output": "not valid json"},
                trace_metadata_json={"stage": "investigator"},
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

    assert len(repos.pulse_runs.agent_run_steps) == 1
    assert repos.pulse_runs.agent_run_steps[0]["stage"] == "investigator"
    failed_run = next(row for row in repos.pulse_runs.finished_runs if row["status"] == "failed")
    assert failed_run["trace_metadata_json_patch"] == {"failure_reason": "schema_validation_failed"}
    assert repos.pulse_harness.eval_cases[0]["expected_json"] == {
        "status": "fail",
        "failure_reason": "schema_validation_failed",
    }
    assert repos.pulse_harness.eval_results[0]["status"] == "pass"
    assert repos.pulse_jobs.failures[0]["failure_reason"] == "schema_validation_failed"


def test_hard_blocked_success_records_gate_step_without_provider_run(monkeypatch: pytest.MonkeyPatch) -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    job = _enqueue_context_job(repos, context)
    client = FakeClient()
    monkeypatch.setattr(job_module, "route_decision_context", lambda context: "research_only")
    monkeypatch.setattr(
        job_module,
        "compute_completeness",
        lambda factor_snapshot, route: SimpleNamespace(
            route=route,
            score=0.2,
            hard_blocked=True,
            missing_fields=("liquidity_usd",),
            stale_fields=(),
            blockers=("missing_liquidity",),
        ),
    )
    service = _service(repos, client=client)

    asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    assert client.run_calls == 0
    assert repos.pulse_runs.agent_run_steps[0]["stage"] == "research_only_gate"
    assert repos.pulse_runs.finished_runs[0]["status"] == "done"
    assert repos.pulse_runs.finished_runs[0]["outcome"] == "abstain_insufficient_data"
    assert repos.pulse_jobs.successes == [job["job_id"]]


def test_normal_success_records_candidate_playbook_eval_and_job_success() -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    job = _enqueue_context_job(repos, context)
    client = FakeClient(recommendation="trade_candidate")
    service = _service(repos, client=client)

    asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    assert client.run_calls == 1
    assert repos.pulse_runs.finished_runs[0]["status"] == "done"
    assert repos.pulse_runs.finished_runs[0]["outcome"] == "completed"
    assert repos.pulse_harness.eval_cases
    assert repos.pulse_harness.eval_results
    assert repos.pulse_candidates.candidate_upserts[0]["decision_recommendation"] == "trade_candidate"
    assert repos.pulse_playbooks.playbook_upserts
    assert repos.pulse_jobs.successes == [job["job_id"]]


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
        gate_thresholds=SimpleNamespace(),
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
