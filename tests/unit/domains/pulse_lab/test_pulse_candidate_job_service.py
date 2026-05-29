from __future__ import annotations

import asyncio
from typing import Any

import pytest

from gmgn_twitter_intel.domains.pulse_lab.providers import PulseDecisionResult
from gmgn_twitter_intel.domains.pulse_lab.services import pulse_candidate_job_service as job_module
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_gate import PulseGateResult
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_job_service import (
    PulseCandidateJobService,
    _normalized_failure_reason,
)
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    BullBearView,
    FinalDecision,
    PulseStageFailure,
    StageRunAudit,
    TradePlaybook,
)
from gmgn_twitter_intel.platform.agent_execution import AgentExecutionError, AgentExecutionErrorClass
from gmgn_twitter_intel.platform.cancellation import WORKER_HARD_TIMEOUT_CANCEL_REASON
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
                stage="signal_analyst",
                route=kwargs["route"],
                attempt_index=0,
                input_json={"context": kwargs["context"]},
                prompt_text="fake signal analyst prompt",
                response_json={"raw_output": "not valid json"},
                trace_metadata_json={"stage": "signal_analyst"},
                usage_json={"input_tokens": 11},
                latency_ms=42,
                started_at_ms=NOW_MS - 42,
                finished_at_ms=NOW_MS,
                status="failed",
                error="ValidationError: invalid JSON",
            )
            raise PulseStageFailure("model_validate failed", audits=(failed_audit,))

    service = _service(repos, client=FailingClient())

    with pytest.raises(PulseStageFailure):
        asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    failed_step = next(row for row in repos.pulse_runs.agent_run_steps if row["stage"] == "signal_analyst")
    assert failed_step["status"] == "failed"
    failed_run = next(row for row in repos.pulse_runs.finished_runs if row["status"] == "failed")
    assert failed_run["trace_metadata_json_patch"] == {"failure_reason": "invalid_schema"}
    assert repos.pulse_agent_eval.eval_cases[0]["expected_json"] == {
        "status": "fail",
        "failure_reason": "invalid_schema",
    }
    assert repos.pulse_agent_eval.eval_results[0]["status"] == "pass"
    assert repos.pulse_jobs.failures[0]["failure_reason"] == "invalid_schema"


def test_invalid_model_output_abstain_finishes_run_done(monkeypatch: pytest.MonkeyPatch) -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    job = _enqueue_context_job(repos, context)

    class InvalidModelOutputClient(FakeClient):
        async def run_decision_pipeline(self, **kwargs: Any) -> Any:
            self.run_calls += 1
            audit = self.request_audit(
                context=kwargs["context"],
                run_id=kwargs["run_id"],
                job=kwargs["job"],
                route=kwargs["route"],
                completeness=kwargs["completeness"],
                runtime_manifest=kwargs["runtime_manifest"],
            )
            failed_audit = _failed_stage_audit(
                route=kwargs["route"],
                status="failed",
                error="ValidationError: trading execution language is not allowed",
            )
            return PulseDecisionResult(
                final_decision=_invalid_model_output_abstain(route=kwargs["route"]),
                agent_run_audit={**audit, "output_hash": "output-hash"},
                stage_audits=(failed_audit,),
            )

    monkeypatch.setattr(job_module, "grade_pulse_deterministic_eval_case", _passing_eval_result)
    service = _service(repos, client=InvalidModelOutputClient())

    asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    finished_run = next(row for row in repos.pulse_runs.finished_runs if row["status"] == "done")
    assert finished_run["outcome"] == "abstain_insufficient_evidence"
    assert repos.pulse_jobs.successes == [job["job_id"]]
    assert repos.pulse_jobs.failures == []


@pytest.mark.parametrize(
    ("error_class", "expected"),
    [
        (AgentExecutionErrorClass.TRANSPORT_ERROR, "provider_unavailable"),
        (AgentExecutionErrorClass.PROVIDER_ERROR, "provider_unavailable"),
        (AgentExecutionErrorClass.RATE_LIMITED, "provider_rate_limited"),
        (AgentExecutionErrorClass.TIMEOUT, "timeout"),
        (AgentExecutionErrorClass.SCHEMA_INVALID, "invalid_schema"),
        (AgentExecutionErrorClass.DOMAIN_VALIDATION_FAILED, "invalid_schema"),
    ],
)
def test_stage_failure_reason_uses_stage_trace_error_class(
    error_class: AgentExecutionErrorClass,
    expected: str,
) -> None:
    failure = PulseStageFailure(
        "agent stage failed",
        audits=(
            _failed_stage_audit(
                route="meme",
                status="timeout" if error_class is AgentExecutionErrorClass.TIMEOUT else "failed",
                error="connection reset by provider",
                error_class=error_class,
            ),
        ),
    )

    assert _normalized_failure_reason(failure) == expected


def test_provider_transport_stage_failure_records_provider_unavailable() -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    job = _enqueue_context_job(repos, context)

    class TransportFailingClient(FakeClient):
        async def run_decision_pipeline(self, **kwargs: Any) -> Any:
            failed_audit = _failed_stage_audit(
                route=kwargs["route"],
                status="failed",
                error="connection reset by provider",
                error_class=AgentExecutionErrorClass.TRANSPORT_ERROR,
            )
            raise PulseStageFailure("agent stage failed", audits=(failed_audit,))

    service = _service(repos, client=TransportFailingClient())

    with pytest.raises(PulseStageFailure):
        asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    failed_run = next(row for row in repos.pulse_runs.finished_runs if row["status"] == "failed")
    assert failed_run["trace_metadata_json_patch"] == {"failure_reason": "provider_unavailable"}
    assert repos.pulse_jobs.failures[0]["failure_reason"] == "provider_unavailable"


def test_worker_timeout_before_execution_releases_job_and_finishes_run() -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    job = _enqueue_context_job(repos, context)

    class BeforeExecutionTimeout(asyncio.CancelledError):
        execution_started = False

    class CancellingClient(FakeClient):
        async def run_decision_pipeline(self, **_: Any) -> Any:
            self.run_calls += 1
            raise BeforeExecutionTimeout(WORKER_HARD_TIMEOUT_CANCEL_REASON)

    service = _service(repos, client=CancellingClient())

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    finished_run = next(row for row in repos.pulse_runs.finished_runs if row["status"] == "failed")
    assert finished_run["outcome"] == "worker_timeout"
    assert finished_run["trace_metadata_json_patch"] == {"failure_reason": "worker_timeout_cancelled"}
    cancellation = repos.pulse_jobs.timeout_cancellations[0]
    assert cancellation["job_id"] == job["job_id"]
    assert cancellation["execution_started"] is False
    assert cancellation["now_ms"] >= NOW_MS
    stored_job = repos.pulse_jobs.jobs[0]
    assert stored_job["status"] == "pending"
    assert stored_job["attempt_count"] == 0
    assert stored_job["last_error"] == "worker_timeout_before_execution"
    assert stored_job["next_run_at_ms"] == cancellation["now_ms"] + 5_000


def test_worker_timeout_after_execution_marks_job_failed_or_dead_and_finishes_run() -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    _enqueue_context_job(repos, context)
    repos.pulse_jobs.jobs[0]["max_attempts"] = 1
    job = dict(repos.pulse_jobs.jobs[0])

    class AfterExecutionTimeout(asyncio.CancelledError):
        execution_started = True

    class CancellingClient(FakeClient):
        async def run_decision_pipeline(self, **_: Any) -> Any:
            self.run_calls += 1
            raise AfterExecutionTimeout(WORKER_HARD_TIMEOUT_CANCEL_REASON)

    service = _service(repos, client=CancellingClient())

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    finished_run = next(row for row in repos.pulse_runs.finished_runs if row["status"] == "failed")
    assert finished_run["outcome"] == "worker_timeout"
    assert finished_run["trace_metadata_json_patch"] == {"failure_reason": "worker_timeout_cancelled"}
    cancellation = repos.pulse_jobs.timeout_cancellations[0]
    assert cancellation["job_id"] == job["job_id"]
    assert cancellation["execution_started"] is True
    assert cancellation["now_ms"] >= NOW_MS
    stored_job = repos.pulse_jobs.jobs[0]
    assert stored_job["status"] == "dead"
    assert stored_job["last_error"] == "worker_timeout_after_execution"


def test_plain_cancellation_does_not_persist_worker_timeout_cleanup() -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    job = _enqueue_context_job(repos, context)

    class CancellingClient(FakeClient):
        async def run_decision_pipeline(self, **_: Any) -> Any:
            self.run_calls += 1
            raise asyncio.CancelledError()

    service = _service(repos, client=CancellingClient())

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    assert repos.pulse_jobs.timeout_cancellations == []
    assert repos.pulse_runs.finished_runs == []
    assert repos.pulse_jobs.jobs[0]["status"] == "running"


def test_worker_timeout_cleanup_does_not_mutate_newer_claim_attempt() -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    job = _enqueue_context_job(repos, context)
    repos.pulse_jobs.jobs[0]["attempt_count"] = int(job["attempt_count"]) + 1
    repos.pulse_jobs.jobs[0]["updated_at_ms"] = int(job["updated_at_ms"]) + 1

    result = repos.pulse_jobs.mark_job_cancelled_by_worker_timeout(
        job,
        now_ms=NOW_MS + 10_000,
        execution_started=True,
    )

    assert result is None
    assert repos.pulse_jobs.jobs[0]["status"] == "running"
    assert repos.pulse_jobs.jobs[0].get("last_error") is None


def test_no_start_circuit_open_releases_job_to_cooldown() -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    job = _enqueue_context_job(repos, context)

    class CircuitOpenClient(FakeClient):
        async def run_decision_pipeline(self, **_: Any) -> Any:
            self.run_calls += 1
            raise AgentExecutionError(
                AgentExecutionErrorClass.CIRCUIT_OPEN,
                "agent lane circuit is open",
                audit=None,
                execution_started=False,
            )

    service = _service(repos, client=CircuitOpenClient())

    with pytest.raises(job_module.PulseAgentBackpressureReleased):
        asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    assert repos.pulse_jobs.failures == []
    assert repos.pulse_jobs.provider_cooldown_releases
    released = repos.pulse_jobs.provider_cooldown_releases[0]
    assert released["reason"] == "provider_cooldown:circuit_open"
    assert released["cooldown_until_ms"] == NOW_MS + 120_000
    stored_job = repos.pulse_jobs.jobs[0]
    assert stored_job["status"] == "pending"
    assert stored_job["attempt_count"] == 0
    assert stored_job["next_run_at_ms"] == NOW_MS + 120_000


def test_hard_blocked_success_records_evidence_gate_without_provider_run() -> None:
    repos = FakeRepos()
    repos.pulse_evidence_sources.market_facts = []
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    job = _enqueue_context_job(repos, context)
    client = FakeClient()
    service = _service(repos, client=client)

    asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    assert client.run_calls == 0
    stored_run = repos.pulse_runs.agent_runs[0]
    assert stored_run["request_json"]["cost_guard"]["decision"]["action"] == "no_llm_finalize"
    gate_step = next(row for row in repos.pulse_runs.agent_run_steps if row["stage"] == "evidence_completeness_gate")
    assert gate_step["response_json"]["hard_blocked"] is True
    assert not any(row["stage"] == "signal_analyst" for row in repos.pulse_runs.agent_run_steps)
    assert not any(row["stage"] == "bear_case" for row in repos.pulse_runs.agent_run_steps)
    assert not any(row["stage"] == "risk_portfolio_judge" for row in repos.pulse_runs.agent_run_steps)
    finished_run = next(row for row in repos.pulse_runs.finished_runs if row["status"] == "done")
    assert finished_run["outcome"] == "blocked_market_contract"
    assert repos.pulse_jobs.successes == [job["job_id"]]


def test_run_job_reuses_terminal_fingerprint_without_model_call() -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    job = _enqueue_context_job(repos, context)
    repos.pulse_runs.terminal_fingerprint_result = {
        "run_id": "run-existing-terminal",
        "response_json": _invalid_model_output_abstain(route="meme").model_dump(mode="json"),
        "output_hash": "sha256:existing-output",
        "usage_json": {"input_tokens": 999, "output_tokens": 999},
    }
    client = FakeClient()
    service = _service(repos, client=client)

    asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    assert client.run_calls == 0
    assert repos.pulse_runs.terminal_fingerprint_lookups
    stored_run = repos.pulse_runs.agent_runs[0]
    assert stored_run["request_json"]["cost_guard"]["decision"]["action"] == "reuse_terminal_run"
    assert stored_run["request_json"]["cost_guard"]["reused_run_id"] == "run-existing-terminal"
    assert not any(row["stage"] == "signal_analyst" for row in repos.pulse_runs.agent_run_steps)
    finished_run = next(row for row in repos.pulse_runs.finished_runs if row["status"] == "done")
    assert finished_run["usage_json"] == {}
    assert repos.pulse_jobs.successes == [job["job_id"]]


def test_source_quality_hidden_path_does_not_call_deepseek() -> None:
    repos = FakeRepos()
    context = _pulse_context(
        factor_snapshot=_factor_snapshot(
            rank_score=82,
            watched_mentions=1,
            unique_authors=1,
            independent_authors=1,
            effective_authors=1.0,
            top_author_share=1.0,
        )
    )
    job = _enqueue_context_job(repos, context)
    client = FakeClient()
    service = _service(repos, client=client)

    asyncio.run(service.run_job(job, context, now_ms=NOW_MS))

    assert client.run_calls == 1
    assert client.stage_plans
    assert client.stage_plans[0].run_signal_analyst is True
    assert client.stage_plans[0].run_bear_case is True
    assert client.stage_plans[0].run_risk_portfolio_judge is False
    stored_run = repos.pulse_runs.agent_runs[0]
    assert stored_run["request_json"]["cost_guard"]["decision"]["action"] == "research_only"
    assert stored_run["request_json"]["cost_guard"]["decision"]["public_judge_allowed"] is False
    assert any(row["stage"] == "signal_analyst" for row in repos.pulse_runs.agent_run_steps)
    assert any(row["stage"] == "bear_case" for row in repos.pulse_runs.agent_run_steps)
    assert not any(row["stage"] == "risk_portfolio_judge" for row in repos.pulse_runs.agent_run_steps)
    assert repos.pulse_candidates.candidate_upserts[0]["display_status"] == "hidden_source_quality"


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


def _failed_stage_audit(
    *,
    route: str,
    status: str,
    error: str,
    error_class: AgentExecutionErrorClass | None = None,
) -> StageRunAudit:
    trace_metadata_json = {"stage": "signal_analyst"}
    if error_class is not None:
        trace_metadata_json["error_class"] = str(error_class.value)
    return StageRunAudit(
        stage="signal_analyst",
        route=route,  # type: ignore[arg-type]
        attempt_index=0,
        input_json={"context": "test"},
        prompt_text="fake signal analyst prompt",
        response_json=None,
        trace_metadata_json=trace_metadata_json,
        usage_json={"input_tokens": 11},
        latency_ms=42,
        started_at_ms=NOW_MS - 42,
        finished_at_ms=NOW_MS,
        status=status,  # type: ignore[arg-type]
        error=error,
    )


def _invalid_model_output_abstain(*, route: str) -> FinalDecision:
    return FinalDecision(
        route=route,  # type: ignore[arg-type]
        recommendation="abstain",
        confidence=0.0,
        abstain_reason="invalid_model_output",
        summary_zh="模型输出不符合结构化合同，本次不发布候选。",
        narrative_archetype="unclear",
        narrative_thesis_zh="模型输出未通过结构化合同校验，无法形成可靠结论；本次仅记录无效输出并等待下一轮有效证据综合。",
        bull_view=BullBearView(strength="absent"),
        bear_view=BullBearView(strength="absent"),
        playbook=TradePlaybook(
            has_playbook=False,
            watch_signals=[],
            exit_triggers=[],
            monitoring_horizon="1h",
        ),
        invalidation_conditions=[],
        residual_risks=["invalid_model_output"],
        evidence_event_ids=[],
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
