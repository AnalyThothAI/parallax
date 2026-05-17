from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime import providers_wiring
from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.pulse_lab.providers import (
    DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT,
    PulseAgentRuntimeContract,
    PulseDecisionResult,
)
from gmgn_twitter_intel.domains.pulse_lab.runtime.pulse_candidate_worker import (
    PulseCandidateWorker,
    _asset_candidate_id,
    _asset_trigger_metrics,
)
from gmgn_twitter_intel.domains.pulse_lab.services import pulse_candidate_job_service as job_module
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_gate import PulseGateResult
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_job_service import (
    _investigation_tool_calls_count,
    _normalized_failure_reason,
    _run_outcome,
)
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    BullBearView,
    FinalDecision,
    PulseStageFailure,
    StageRunAudit,
    TradePlaybook,
)
from gmgn_twitter_intel.domains.pulse_lab.types.pulse_candidate_context import PulseCandidateContext
from gmgn_twitter_intel.platform.config.settings import Settings

NOW_MS = 1_800_000


def test_missing_factor_snapshot_is_not_enqueued() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=None)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 1
    assert result["asset_skipped"] == 1
    assert result["asset_enqueued"] == 0
    assert repos.pulse_jobs.jobs == []


def test_malformed_v3_factor_snapshot_is_not_enqueued() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(rank_score=82)
    snapshot["families"]["market_quality"] = {"facts": {"market_status": "fresh"}}
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 1
    assert result["asset_skipped"] == 1
    assert result["asset_enqueued"] == 0
    assert repos.pulse_jobs.jobs == []


def test_default_trigger_floor_enqueues_rank_45_without_decision_or_watched_shortcuts() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [
        _radar_row(
            factor_snapshot_json=_factor_snapshot(
                rank_score=45,
                recommended_decision="low_info",
                watched_mentions=0,
            )
        )
    ]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 1
    assert result["asset_enqueued"] == 1
    assert repos.pulse_jobs.jobs


def test_default_trigger_floor_skips_rank_44_without_decision_or_watched_shortcuts() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [
        _radar_row(
            factor_snapshot_json=_factor_snapshot(
                rank_score=44,
                recommended_decision="low_info",
                watched_mentions=0,
            )
        )
    ]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 1
    assert result["asset_enqueued"] == 0
    assert result["asset_skipped"] == 1
    assert repos.pulse_jobs.jobs == []


def test_critic_veto_abstain_maps_to_generic_abstain_outcome() -> None:
    final_decision = FinalDecision(
        route="meme",
        recommendation="abstain",
        confidence=0.0,
        abstain_reason="critic_veto",
        summary_zh="证据不足,暂不形成交易候选。",
        narrative_archetype="unclear",
        narrative_thesis_zh="当前数据完整度不足，无法形成可靠叙事判断；等待更多事实信号后再评估。",
        bull_view=BullBearView(strength="absent"),
        bear_view=BullBearView(strength="absent"),
        playbook=TradePlaybook(
            has_playbook=False,
            watch_signals=[],
            exit_triggers=[],
            monitoring_horizon="1h",
        ),
        invalidation_conditions=[],
        residual_risks=["critic_veto"],
        evidence_event_ids=[],
    )

    assert _run_outcome(final_decision, completeness_blocked=False) == "abstain"


def test_asset_context_uses_factor_snapshot_and_no_legacy_runtime_context() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(rank_score=82)
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_enqueued"] == 1
    job = repos.pulse_jobs.jobs[0]
    assert job["candidate_id"] == _asset_candidate_id(
        candidate_type="token_target",
        window="1h",
        scope="all",
        target_type="Asset",
        target_id="asset-1",
    )
    assert job["context_json"]["factor_snapshot"] == snapshot
    assert job["context_json"]["edge_events"] == ["pulse_status_changed"]
    assert job["context_json"]["selected_posts"]
    assert "radar_score" not in job["context_json"]
    assert "market_context" not in job["context_json"]
    assert "timeline_context" not in job["context_json"]


def test_worker_gates_before_agent_and_agent_cannot_upgrade_gate_status() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=_factor_snapshot(rank_score=50))]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    client = FakeClient(recommendation="trade_candidate")
    gate_calls: list[dict[str, Any]] = []

    def gate_func(**kwargs: Any) -> PulseGateResult:
        gate_calls.append(kwargs)
        return PulseGateResult(
            pulse_status="token_watch",
            verdict="token_watch",
            candidate_score=50.0,
            score_band="speculative",
            gate_reasons=["factor_snapshot_watch_gate_passed"],
            risk_reasons=[],
            hard_risks=[],
            max_recommendation="watch",
            eligible_for_high_alert=True,
            blocked_reasons=[],
        )

    worker = PulseCandidateWorker(
        name="pulse_candidate",
        settings=_settings(),
        db=FakeDB(repos),
        telemetry=object(),
        decision_client=client,
        gate_func=gate_func,
    )

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 1
    assert gate_calls and client.contexts
    assert client.contexts[0]["gate_result"]["pulse_status"] == "token_watch"
    assert client.contexts[0]["gate_result"]["max_recommendation"] == "watch"
    assert repos.pulse_candidates.candidate_upserts[0]["pulse_status"] == "token_watch"
    assert repos.pulse_candidates.candidate_upserts[0]["candidate_score"] == 50.0
    assert repos.pulse_candidates.candidate_upserts[0]["score_band"] == "speculative"
    candidate_id = repos.pulse_candidates.candidate_upserts[0]["candidate_id"]
    edge = repos.pulse_admission.edge_states[candidate_id]
    assert edge["last_processed_state_json"] == edge["latest_observed_state_json"]


def test_worker_persists_factor_snapshot_gate_and_decision_only() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(rank_score=82)
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(repos)

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 1
    upsert = repos.pulse_candidates.candidate_upserts[0]
    assert upsert["factor_snapshot_json"] == snapshot
    assert upsert["gate_json"]["pulse_status"] == "trade_candidate"
    assert upsert["decision_json"]["recommendation"] == "watchlist"
    assert upsert["decision_route"] == "meme"
    assert upsert["decision_recommendation"] == "watchlist"
    assert upsert["last_edge_events_json"] == ["pulse_status_changed"]
    assert "agent_recommendation_json" not in upsert
    assert "radar_score_json" not in upsert
    assert "market_context_json" not in upsert
    assert "thesis_json" not in upsert


def test_worker_trigger_metrics_use_v3_families_and_gates() -> None:
    snapshot = _factor_snapshot(rank_score=82, blocked_reasons=["duplicate_text_share_high"])
    row = _radar_row(factor_snapshot_json=snapshot)

    metrics = _asset_trigger_metrics(row)

    assert metrics == {
        "rank_score": 82,
        "recommended_decision": "high_alert",
        "watched_confirmation": True,
        "independent_author_count": 7,
        "blocked_reasons": ["duplicate_text_share_high"],
        "hard_risks": ["duplicate_text_share_high"],
        "trade_candidate_eligible": False,
    }


def test_worker_suppresses_unchanged_edge_state_without_cooldown_compatibility() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(rank_score=82)
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    candidate_id = _asset_candidate_id(
        candidate_type="token_target",
        window="1h",
        scope="all",
        target_type="Asset",
        target_id="asset-1",
    )
    repos.pulse_admission.edge_states[candidate_id] = {
        "candidate_id": candidate_id,
        "last_processed_state_json": {
            "candidate_id": candidate_id,
            "candidate_type": "token_target",
            "target_type": "Asset",
            "target_id": "asset-1",
            "window": "1h",
            "scope": "all",
            "pulse_version": "signal-pulse-v3-factor-snapshot",
            "gate_version": "pulse-factor-gate-v2-edge-state",
            "pulse_status": "trade_candidate",
            "verdict": "trade_candidate",
            "score_band": "high_conviction",
            "candidate_score_bucket": "80-89",
            "rank_score_bucket": "80-89",
            "recommended_decision": "high_alert",
            "watched_confirmation": True,
            "independent_author_count_bucket": "6-10",
            "hard_risks": [],
            "trigger_signature": "ignored-by-edge",
            "timeline_signature": "ignored-by-edge",
        },
    }
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 1
    assert result["asset_enqueued"] == 0
    assert result["asset_skipped"] == 1
    assert repos.pulse_jobs.jobs == []


def test_worker_can_be_woken_by_token_radar_update_before_interval() -> None:
    repos = FakeRepos()
    wake_listener = FakeWakeListener()
    worker = _worker(repos, wake_waiter=wake_listener, settings=_settings(interval_seconds=60.0))

    async def scenario() -> None:
        task = asyncio.create_task(worker.run())
        try:
            await _wait_until(lambda: repos.token_radar.latest_calls >= 1)
            await _wait_until(lambda: repos.token_radar.latest_calls >= 2)
        finally:
            await worker.stop()
            await task

    asyncio.run(scenario())
    assert wake_listener.listen_calls >= 1


def test_edge_budget_caps_candidate_enqueues_per_hour() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(rank_score=82)
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    candidate_id = _asset_candidate_id(
        candidate_type="token_target",
        window="1h",
        scope="all",
        target_type="Asset",
        target_id="asset-1",
    )
    repos.pulse_admission.budget_claims[(candidate_id, NOW_MS // 3_600_000 * 3_600_000)] = 3
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 1
    assert result["asset_enqueued"] == 0
    assert result["asset_skipped"] == 1
    assert repos.pulse_jobs.jobs == []


def test_score_band_only_edge_waits_for_confirmation_without_job() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(rank_score=82)
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    candidate_id = _asset_candidate_id(
        candidate_type="token_target",
        window="1h",
        scope="all",
        target_type="Asset",
        target_id="asset-1",
    )
    previous = {
        "candidate_id": candidate_id,
        "candidate_type": "token_target",
        "target_type": "Asset",
        "target_id": "asset-1",
        "window": "1h",
        "scope": "all",
        "pulse_version": "signal-pulse-v3-factor-snapshot",
        "gate_version": "pulse-factor-gate-v2-edge-state",
        "pulse_status": "trade_candidate",
        "verdict": "trade_candidate",
        "score_band": "watch",
        "candidate_score_bucket": "80-89",
        "rank_score_bucket": "80-89",
        "recommended_decision": "high_alert",
        "watched_confirmation": True,
        "independent_author_count_bucket": "6-10",
        "hard_risks": [],
        "trigger_signature": "ignored-by-edge",
        "timeline_signature": "ignored-by-edge",
    }
    repos.pulse_admission.edge_states[candidate_id] = {
        "candidate_id": candidate_id,
        "last_processed_state_json": previous,
    }
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_enqueued"] == 0
    assert repos.pulse_jobs.jobs == []
    edge = repos.pulse_admission.edge_states[candidate_id]
    assert edge["last_suppressed_reason"] == "score_band_pending"
    assert edge["pending_score_band"] == "high_conviction"
    assert edge["pending_score_band_count"] == 1


def test_recent_schema_failure_circuit_suppresses_non_escalation_edge() -> None:
    repos = FakeRepos()
    repos.pulse_admission.recent_failure_count = 3
    snapshot = _factor_snapshot(rank_score=82)
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    candidate_id = _asset_candidate_id(
        candidate_type="token_target",
        window="1h",
        scope="all",
        target_type="Asset",
        target_id="asset-1",
    )
    repos.pulse_admission.edge_states[candidate_id] = {
        "candidate_id": candidate_id,
        "last_processed_state_json": _processed_edge_state(
            candidate_id=candidate_id,
            pulse_status="trade_candidate",
            score_band="watch",
        ),
        "pending_score_band": "high_conviction",
        "pending_score_band_count": 1,
    }
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_enqueued"] == 0
    assert repos.pulse_jobs.jobs == []
    edge = repos.pulse_admission.edge_states[candidate_id]
    assert edge["last_suppressed_reason"] == "failure_circuit_open"


def test_recent_schema_failure_circuit_does_not_suppress_escalation_edge() -> None:
    repos = FakeRepos()
    repos.pulse_admission.recent_failure_count = 3
    snapshot = _factor_snapshot(rank_score=82)
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    candidate_id = _asset_candidate_id(
        candidate_type="token_target",
        window="1h",
        scope="all",
        target_type="Asset",
        target_id="asset-1",
    )
    repos.pulse_admission.edge_states[candidate_id] = {
        "candidate_id": candidate_id,
        "last_processed_state_json": _processed_edge_state(
            candidate_id=candidate_id,
            pulse_status="token_watch",
            score_band="high_conviction",
        ),
    }
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_enqueued"] == 1
    assert repos.pulse_jobs.jobs
    assert repos.pulse_admission.admission_claims[-1]["admission_reason"] == "escalation"


def test_normalized_failure_reason_maps_unknown_evidence() -> None:
    assert _normalized_failure_reason(ValueError("unknown evidence ids: event-x")) == "unknown_evidence_id"


def test_normalized_failure_reason_maps_schema_validation() -> None:
    assert _normalized_failure_reason(ValueError("model_validate failed")) == "schema_validation_failed"


def test_worker_persists_failed_stage_audits_when_provider_raises_stage_failure() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82))]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]

    class FailingClient(FakeClient):
        async def run_decision_pipeline(self, **kwargs: Any) -> Any:
            self.run_calls += 1
            failed_audit = StageRunAudit(
                stage="investigator",
                route=kwargs["route"],
                attempt_index=0,
                input_json={"context": kwargs["context"]},
                prompt_text="fake investigator prompt",
                response_json={"raw_output": "**Investigation Report:** prose only"},
                trace_metadata_json={"stage": "investigator"},
                usage_json={"input_tokens": 11},
                latency_ms=42,
                started_at_ms=NOW_MS - 42,
                finished_at_ms=NOW_MS,
                status="failed",
                error="ModelBehaviorError: invalid JSON",
            )
            raise PulseStageFailure("model_validate failed", audits=(failed_audit,))

    worker = _worker(repos, client=FailingClient())

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 0
    assert result["failed"] == 1
    assert len(repos.pulse_runs.agent_run_steps) == 1
    step = repos.pulse_runs.agent_run_steps[0]
    assert step["stage"] == "investigator"
    assert step["status"] == "failed"
    assert step["error"] == "ModelBehaviorError: invalid JSON"
    assert step["response_json"] == {"raw_output": "**Investigation Report:** prose only"}
    assert step["started_at_ms"] == NOW_MS - 42
    assert step["finished_at_ms"] == NOW_MS
    assert step["usage_json"] == {"input_tokens": 11}
    failed_run = next(row for row in repos.pulse_runs.finished_runs if row["status"] == "failed")
    assert failed_run["trace_metadata_json_patch"] == {"failure_reason": "schema_validation_failed"}
    assert len(repos.pulse_jobs.failures) == 1
    assert repos.pulse_jobs.failures[0]["failure_reason"] == "schema_validation_failed"
    assert repos.pulse_agent_eval.eval_cases[0]["expected_json"] == {
        "status": "fail",
        "failure_reason": "schema_validation_failed",
    }
    assert repos.pulse_agent_eval.eval_results[0]["status"] == "pass"
    candidate_id = repos.pulse_jobs.jobs[0]["candidate_id"]
    assert repos.pulse_admission.edge_states[candidate_id]["last_processed_state_json"] == {}


def test_hard_blocked_research_only_gate_records_real_step_timing(monkeypatch) -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
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
    now_values = iter([NOW_MS + 10, NOW_MS + 25, NOW_MS + 40])
    monkeypatch.setattr(job_module, "_now_ms", lambda: next(now_values))
    client = FakeClient()
    worker = _worker(repos, client=client)

    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 1
    assert client.run_calls == 0
    step = repos.pulse_runs.agent_run_steps[0]
    assert step["stage"] == "research_only_gate"
    assert step["status"] == "skipped"
    assert step["started_at_ms"] == NOW_MS + 10
    assert step["finished_at_ms"] == NOW_MS + 25
    assert step["started_at_ms"] != step["finished_at_ms"]


def test_hard_blocked_run_marks_edge_state_processed(monkeypatch) -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82))]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
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
    now_values = iter([NOW_MS + 10, NOW_MS + 25, NOW_MS + 40])
    monkeypatch.setattr(job_module, "_now_ms", lambda: next(now_values))
    worker = _worker(repos)

    scan = worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert scan["asset_enqueued"] == 1
    assert result["processed"] == 1
    candidate_id = repos.pulse_jobs.jobs[0]["candidate_id"]
    edge = repos.pulse_admission.edge_states[candidate_id]
    assert edge["last_processed_state_json"] == edge["latest_observed_state_json"]
    assert edge["last_processed_at_ms"] == NOW_MS + 40


def test_worker_runtime_manifest_uses_decision_client_runtime_contract() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82))]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]

    class ContractClient(FakeClient):
        runtime_contract = PulseAgentRuntimeContract(
            stage_names=("investigator", "decision_maker"),
            tool_names_by_stage={
                "investigator": ("custom_tool",),
                "decision_maker": (),
            },
            route_tool_budgets={"cex": 1, "meme": 2, "research_only": 1},
            max_turns_per_stage={"investigator": 4, "decision_maker": 2},
            safety_net_enabled=False,
            validators_enabled=("runtime_evidence_id_subset",),
            failure_taxonomy_version="pulse-failure-taxonomy-test",
        )

    worker = _worker(repos, client=ContractClient())

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 1
    manifest = repos.pulse_agent_eval.runtime_versions[0]["manifest_json"]
    assert manifest["runtime"]["tool_names_by_stage"] == {"investigator": ["custom_tool"], "decision_maker": []}
    assert manifest["runtime"]["route_tool_budgets"] == {"cex": 1, "meme": 2, "research_only": 1}
    assert manifest["runtime"]["max_turns_per_stage"] == {"investigator": 4, "decision_maker": 2}
    assert manifest["runtime"]["safety_net_enabled"] is False
    assert manifest["contracts"]["validators_enabled"] == ["runtime_evidence_id_subset"]
    assert manifest["failure_taxonomy"]["version"] == "pulse-failure-taxonomy-test"


def test_worker_runtime_manifest_uses_wired_provider_custom_tool_budgets(monkeypatch) -> None:
    settings = Settings(
        ws_token="secret",
        llm={
            "api_key": "sk-test",
            "model": "gpt-enrich",
            "pulse_agent_model": "gpt-pulse",
            "watchlist_handle_summary_model": "gpt-summary",
        },
    )
    settings.workers.pulse_candidate.investigator_max_tool_calls = {
        "cex": 2,
        "meme": 4,
        "research_only": 1,
    }
    wired = providers_wiring.wire_providers(
        settings,
        start_collector=True,
        llm_gateway=FakeGateway(),
        db_pool=object(),
    )
    repos = FakeRepos()
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82))]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
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
    assert wired.pulse_lab.decision_provider is not None
    worker = _worker(repos, client=wired.pulse_lab.decision_provider)

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 1
    manifest = repos.pulse_agent_eval.runtime_versions[0]["manifest_json"]
    assert manifest["runtime"]["route_tool_budgets"] == {
        "cex": 2,
        "meme": 4,
        "research_only": 1,
    }
    assert manifest["runtime"]["tool_names_by_stage"]["decision_maker"] == ["get_target_recent_tweets"]
    assert manifest["runtime"]["safety_net_enabled"] is True


def test_pulse_worker_run_once_returns_worker_result() -> None:
    repos = FakeRepos()
    worker = _worker(repos)

    result = asyncio.run(worker.run_once(now_ms=NOW_MS))

    assert isinstance(worker, WorkerBase)
    assert worker.SINGLE_WRITER_KEY == 2026051502
    assert isinstance(result, WorkerResult)
    assert result.processed == 0
    assert result.notes["scan"]["asset_seen"] == 0
    assert result.notes["process"]["claimed"] == 0
    assert repos.db_worker_sessions[0] == {"name": "pulse_candidate", "statement_timeout_seconds": 30.0}


def test_pulse_worker_aclose_keeps_base_cleanup_owner() -> None:
    repos = FakeRepos()
    lock = TrackingAdvisoryLock()
    client = ClosingFakeClient()
    worker = _worker(repos, client=client)
    worker._advisory_lock_connection = lock

    asyncio.run(worker.aclose())

    assert client.closed is True
    assert lock.released is True
    assert worker._advisory_lock_connection is None
    assert worker._closed is True


def _worker(
    repos: FakeRepos,
    *,
    client: Any | None = None,
    settings: Any | None = None,
    wake_waiter: Any | None = None,
) -> PulseCandidateWorker:
    return PulseCandidateWorker(
        name="pulse_candidate",
        settings=settings or _settings(),
        db=FakeDB(repos),
        telemetry=object(),
        decision_client=client or FakeClient(),
        wake_waiter=wake_waiter,
    )


def _settings(**overrides: Any) -> SimpleNamespace:
    values = {
        "enabled": True,
        "interval_seconds": 60.0,
        "timeout_seconds": 120.0,
        "batch_size": 10,
        "max_attempts": 3,
        "statement_timeout_seconds": 30.0,
        "advisory_lock_key": 2026051502,
        "wakes_on": ("token_radar_updated",),
        "windows": ("1h",),
        "scopes": ("all",),
        "trigger_thresholds": SimpleNamespace(min_rank_score=45),
        "gate_thresholds": SimpleNamespace(
            trade_candidate_min=72,
            token_watch_min=45,
            high_info_rejection_min=30,
            high_conviction_min=78,
        ),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _pulse_context(*, factor_snapshot: dict[str, Any]) -> Any:
    return PulseCandidateContext(
        candidate_id="pulse-test-hard-blocked",
        candidate_type="token_target",
        subject_key="TEST",
        window="1h",
        scope="all",
        trigger_signature="trigger-hard-blocked",
        timeline_signature="timeline-hard-blocked",
        priority=80,
        target_type="Asset",
        target_id="asset-1",
        symbol="TEST",
        factor_snapshot=factor_snapshot,
        selected_posts=[_timeline_row("event-1", NOW_MS - 1_000)],
        gate_result=None,
        edge_state=None,
        edge_events=("pulse_status_changed",),
        source_event_ids=["event-1"],
        evidence_event_ids=["event-1"],
    )


def _processed_edge_state(
    *,
    candidate_id: str,
    pulse_status: str,
    score_band: str,
    recommended_decision: str = "high_alert",
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "candidate_type": "token_target",
        "target_type": "Asset",
        "target_id": "asset-1",
        "window": "1h",
        "scope": "all",
        "pulse_version": "signal-pulse-v3-factor-snapshot",
        "gate_version": "pulse-factor-gate-v2-edge-state",
        "pulse_status": pulse_status,
        "verdict": pulse_status,
        "score_band": score_band,
        "candidate_score_bucket": "80-89",
        "rank_score_bucket": "80-89",
        "recommended_decision": recommended_decision,
        "watched_confirmation": True,
        "independent_author_count_bucket": "6-10",
        "hard_risks": [],
        "trigger_signature": "ignored-by-edge",
        "timeline_signature": "ignored-by-edge",
    }


@contextmanager
def _session(repos: FakeRepos):
    yield repos


class FakeDB:
    def __init__(self, repos: FakeRepos) -> None:
        self.repos = repos

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        self.repos.db_worker_sessions.append({"name": name, "statement_timeout_seconds": statement_timeout_seconds})
        yield self.repos

    def acquire_advisory_lock_connection(self, worker_name: str, key: int):
        return FakeAdvisoryLock()


class FakeGateway:
    trace_export_enabled = True

    async def run_with_limits(self, worker_name, stage, timeout_s, coro_factory):
        return await coro_factory()

    def openai_client(self, *, model, base_url, timeout_s):
        return object()


class FakeAdvisoryLock:
    def release(self) -> None:
        return None


class TrackingAdvisoryLock:
    def __init__(self) -> None:
        self.released = False

    def release(self) -> None:
        self.released = True


class FakeRepos:
    def __init__(self) -> None:
        self.conn = FakeConn()
        self.token_radar = FakeTokenRadar()
        self.token_targets = FakeTokenTargets()
        pulse_state = FakePulseStore()
        self.pulse_jobs = pulse_state
        self.pulse_admission = pulse_state
        self.pulse_candidates = pulse_state
        self.pulse_runs = pulse_state
        self.pulse_agent_eval = pulse_state
        self.pulse_playbooks = pulse_state
        self.db_worker_sessions: list[dict[str, Any]] = []


class FakeConn:
    @contextmanager
    def transaction(self):
        yield


class FakeTokenRadar:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.latest_calls = 0

    def latest_rows(self, **_: Any) -> list[dict[str, Any]]:
        self.latest_calls += 1
        return list(self.rows)


class FakeTokenTargets:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def timeline_rows(self, **_: Any) -> list[dict[str, Any]]:
        return list(self.rows)


class FakePulseStore:
    def __init__(self) -> None:
        self.jobs: list[dict[str, Any]] = []
        self.candidates: dict[str, dict[str, Any]] = {}
        self.edge_states: dict[str, dict[str, Any]] = {}
        self.budget_claims: dict[tuple[str, int], int] = {}
        self.target_budget_claims: dict[tuple[str, str, int], int] = {}
        self.recent_failure_count = 0
        self.agent_runs: list[dict[str, Any]] = []
        self.agent_run_steps: list[dict[str, Any]] = []
        self.finished_runs: list[dict[str, Any]] = []
        self.runtime_versions: list[dict[str, Any]] = []
        self.eval_cases: list[dict[str, Any]] = []
        self.eval_results: list[dict[str, Any]] = []
        self.candidate_upserts: list[dict[str, Any]] = []
        self.playbook_upserts: list[dict[str, Any]] = []
        self.successes: list[str] = []
        self.failures: list[dict[str, Any]] = []
        self.admission_claims: list[dict[str, Any]] = []

    def candidate_by_id(self, candidate_id: str) -> dict[str, Any] | None:
        return self.candidates.get(candidate_id)

    def job_for_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        for job in reversed(self.jobs):
            if job["candidate_id"] == candidate_id:
                return job
        return None

    def edge_state_by_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        return self.edge_states.get(candidate_id)

    def record_edge_observation(self, **kwargs: Any) -> dict[str, Any]:
        candidate_id = kwargs["candidate_id"]
        row = self.edge_states.get(candidate_id, {"candidate_id": candidate_id, "last_processed_state_json": {}})
        row = {
            **row,
            "latest_observed_state_json": kwargs["current_state_json"],
            "last_edge_signature": kwargs["edge_signature"],
            "observed_at_ms": kwargs["observed_at_ms"],
        }
        self.edge_states[candidate_id] = row
        return row

    def claim_edge_budget(self, **kwargs: Any) -> bool:
        key = (kwargs["candidate_id"], kwargs["hour_bucket_ms"])
        count = self.budget_claims.get(key, 0)
        if count >= kwargs.get("max_enqueues", 3):
            return False
        self.budget_claims[key] = count + 1
        return True

    def mark_edge_job_enqueued(self, **kwargs: Any) -> dict[str, Any]:
        candidate_id = kwargs["candidate_id"]
        row = self.edge_states.get(candidate_id, {"candidate_id": candidate_id})
        row = {
            **row,
            "latest_observed_state_json": row.get("latest_observed_state_json") or kwargs["processed_state_json"],
            "last_processed_state_json": row.get("last_processed_state_json") or {},
            "last_edge_events_json": kwargs["edge_events_json"],
            "last_job_id": kwargs["job_id"],
            "last_processed_at_ms": kwargs["processed_at_ms"],
            "pending_score_band": None,
            "pending_score_band_count": 0,
            "last_suppressed_reason": None,
            "last_suppressed_at_ms": None,
        }
        self.edge_states[candidate_id] = row
        return row

    def mark_edge_budget_rejected(self, **kwargs: Any) -> dict[str, Any]:
        candidate_id = kwargs["candidate_id"]
        row = self.edge_states.get(candidate_id, {"candidate_id": candidate_id})
        row = {**row, "last_edge_events_json": kwargs["edge_events_json"], "updated_at_ms": kwargs["rejected_at_ms"]}
        self.edge_states[candidate_id] = row
        return row

    def claim_pulse_admission(self, **kwargs: Any) -> SimpleNamespace:
        self.admission_claims.append(kwargs)
        candidate_id = kwargs["candidate_id"]
        now_ms = kwargs["now_ms"]
        edge_state = kwargs["edge_state"]
        edge_events = list(kwargs["edge_events"])
        row = self.record_edge_observation(
            candidate_id=candidate_id,
            current_state_json=edge_state,
            edge_signature="sha256:test",
            observed_at_ms=now_ms,
        )
        if kwargs.get("admission_action") != "enqueue_agent":
            score_band = edge_state.get("score_band")
            pending_count = int(row.get("pending_score_band_count") or 0)
            if kwargs.get("admission_reason") == "score_band_pending":
                pending_count = pending_count + 1 if row.get("pending_score_band") == score_band else 1
                row["pending_score_band"] = score_band
                row["pending_score_band_count"] = pending_count
            row["last_edge_events_json"] = edge_events
            row["last_suppressed_reason"] = kwargs.get("admission_reason")
            row["last_suppressed_at_ms"] = now_ms
            self.edge_states[candidate_id] = row
            return SimpleNamespace(accepted=False, reason=kwargs.get("admission_reason"), job=None)
        hour_bucket_ms = kwargs["hour_bucket_ms"]
        target_key = (kwargs["target_type"], kwargs["target_id"], hour_bucket_ms)
        candidate_key = (candidate_id, hour_bucket_ms)
        if self.target_budget_claims.get(target_key, 0) >= kwargs["target_limit"]:
            return SimpleNamespace(accepted=False, reason="target_budget_exhausted", job=None)
        if self.budget_claims.get(candidate_key, 0) >= kwargs["candidate_limit"]:
            return SimpleNamespace(accepted=False, reason="candidate_budget_exhausted", job=None)
        self.target_budget_claims[target_key] = self.target_budget_claims.get(target_key, 0) + 1
        self.budget_claims[candidate_key] = self.budget_claims.get(candidate_key, 0) + 1
        return SimpleNamespace(accepted=True, reason=kwargs.get("admission_reason"), job=None)

    def mark_edge_run_finished(self, **kwargs: Any) -> dict[str, Any]:
        candidate_id = kwargs["candidate_id"]
        row = self.edge_states.get(candidate_id, {"candidate_id": candidate_id})
        row = {
            **row,
            "last_agent_run_id": kwargs["agent_run_id"],
            "last_processed_state_json": kwargs["processed_state_json"],
            "last_edge_events_json": kwargs["edge_events_json"],
            "last_processed_at_ms": kwargs["finished_at_ms"],
            "updated_at_ms": kwargs["finished_at_ms"],
        }
        self.edge_states[candidate_id] = row
        return row

    def recent_target_failure_count(self, **_: Any) -> int:
        return self.recent_failure_count

    def enqueue_job(self, **kwargs: Any) -> dict[str, Any]:
        job = {
            **kwargs,
            "job_id": f"job-{len(self.jobs) + 1}",
            "status": "pending",
            "attempt_count": 0,
            "max_attempts": kwargs.get("max_attempts", 3),
        }
        self.jobs.append(job)
        return job

    def claim_due_job(self, now_ms: int | None = None) -> dict[str, Any] | None:
        for job in self.jobs:
            if job["status"] == "pending":
                job["status"] = "running"
                job["attempt_count"] += 1
                job["updated_at_ms"] = now_ms
                return dict(job)
        return None

    def insert_agent_run(self, **kwargs: Any) -> dict[str, Any]:
        self.agent_runs.append(kwargs)
        return kwargs

    def finish_agent_run(self, run_id: str, status: str, **kwargs: Any) -> dict[str, Any]:
        row = {"run_id": run_id, "status": status, **kwargs}
        self.finished_runs.append(row)
        return row

    def insert_agent_run_step(self, **kwargs: Any) -> dict[str, Any]:
        self.agent_run_steps.append(kwargs)
        return kwargs

    def upsert_agent_runtime_version(self, **kwargs: Any) -> dict[str, Any]:
        self.runtime_versions.append(kwargs)
        return kwargs

    def insert_agent_eval_case(self, **kwargs: Any) -> dict[str, Any]:
        self.eval_cases.append(kwargs)
        return kwargs

    def upsert_agent_eval_result(self, **kwargs: Any) -> dict[str, Any]:
        self.eval_results.append(kwargs)
        return kwargs

    def upsert_candidate(self, **kwargs: Any) -> dict[str, Any]:
        self.candidate_upserts.append(kwargs)
        self.candidates[kwargs["candidate_id"]] = kwargs
        return kwargs

    def upsert_playbook_snapshot(self, **kwargs: Any) -> dict[str, Any]:
        self.playbook_upserts.append(kwargs)
        return kwargs

    def mark_job_succeeded(self, job_id: str, **_: Any) -> dict[str, Any]:
        for job in self.jobs:
            if job["job_id"] == job_id:
                job["status"] = "done"
        self.successes.append(job_id)
        return {"job_id": job_id, "status": "done"}

    def mark_job_failed(self, job: dict[str, Any], error: str, **kwargs: Any) -> dict[str, Any]:
        self.failures.append({"job": job, "error": error, "failure_reason": kwargs.get("failure_reason")})
        return {"job_id": job["job_id"], "status": "failed"}


class FakeClient:
    provider = "fake"
    model = "fake-pulse"
    timeout_seconds = 1.0
    artifact_version_hash = "artifact:fake"
    runtime_contract = DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT

    def __init__(self, *, recommendation: str = "watchlist") -> None:
        self.recommendation = recommendation
        self.contexts: list[dict[str, Any]] = []
        self.run_calls = 0

    def request_audit(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: str,
        completeness: dict[str, Any],
        runtime_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        self.contexts.append(context)
        return {
            "backend": "fake",
            "sdk_trace_id": f"trace-{run_id}",
            "workflow_name": "test-flow",
            "agent_name": "test-agent",
            "prompt_version": "prompt-v1",
            "schema_version": "pulse_decision_v1",
            "artifact_version_hash": self.artifact_version_hash,
            "runtime_version": runtime_manifest["runtime_version"],
            "runtime_hash": "sha256:fake-runtime",
            "trace_metadata": {
                "candidate_id": context["candidate_id"],
                "route": route,
                "completeness": completeness,
                "runtime_version": runtime_manifest["runtime_version"],
                "runtime_hash": "sha256:fake-runtime",
            },
            "input_hash": "input-hash",
        }

    async def run_decision_pipeline(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: str,
        completeness: dict[str, Any],
        runtime_manifest: dict[str, Any],
    ) -> PulseDecisionResult:
        self.run_calls += 1
        evidence_ids = context.get("source_event_ids") or ["event-1"]
        final_decision = FinalDecision(
            route=route,  # type: ignore[arg-type]
            recommendation=self.recommendation,
            confidence=0.7,
            abstain_reason=None,
            summary_zh="因子快照显示信号值得继续观察。",
            narrative_archetype="社交扩散",
            narrative_thesis_zh="当前独立作者与社交热度同步抬升，链上质量尚可，适合继续观察扩散是否持续。",
            bull_view=BullBearView(
                strength="moderate",
                thesis_zh="独立作者扩散和关注账号确认提供了继续观察的积极证据。",
                supporting_event_ids=list(evidence_ids),
            ),
            bear_view=BullBearView(
                strength="weak",
                thesis_zh="价格响应和流动性确认仍不足，热度可能快速降温。",
                supporting_event_ids=list(evidence_ids),
            ),
            playbook=TradePlaybook(
                has_playbook=True,
                watch_signals=["关注独立作者是否继续扩散"],
                exit_triggers=["独立作者讨论快速降温"],
                monitoring_horizon="4h",
            ),
            invalidation_conditions=["独立作者数回落。"],
            residual_risks=["价格响应仍可能变化。"],
            evidence_event_ids=list(evidence_ids),
        )
        investigator_audit = StageRunAudit(
            stage="investigator",
            route=route,  # type: ignore[arg-type]
            attempt_index=0,
            input_json={
                "context": context,
                "completeness": completeness,
                "tool_calls": [{"tool_name": "get_target_recent_tweets", "event_ids": list(evidence_ids)}],
            },
            prompt_text="fake investigator prompt",
            response_json={
                "narrative_archetype_candidate": "社交扩散",
                "narrative_observation_zh": "当前社交扩散和关注账号确认构成继续观察的主要事实。",
                "bull_observation": {
                    "strength": "moderate",
                    "thesis_zh": "独立作者扩散和关注账号确认提供了继续观察的积极证据。",
                    "supporting_event_ids": list(evidence_ids),
                },
                "bear_observation": {
                    "strength": "weak",
                    "thesis_zh": "价格响应和流动性确认仍不足，热度可能快速降温。",
                    "supporting_event_ids": list(evidence_ids),
                },
                "data_gaps": [],
            },
            trace_metadata_json={},
            usage_json={},
            latency_ms=1,
            status="ok",
            error=None,
        )
        stage_audit = StageRunAudit(
            stage="decision_maker",
            route=route,  # type: ignore[arg-type]
            attempt_index=0,
            input_json={"context": context, "completeness": completeness},
            prompt_text="fake prompt",
            response_json=final_decision.model_dump(mode="json"),
            trace_metadata_json={},
            usage_json={},
            latency_ms=1,
            status="ok",
            error=None,
        )
        audit = self.request_audit(
            context=context,
            run_id=run_id,
            job=job,
            route=route,
            completeness=completeness,
            runtime_manifest=runtime_manifest,
        )
        return PulseDecisionResult(
            final_decision=final_decision,
            agent_run_audit={**audit, "output_hash": "output-hash"},
            stage_audits=(investigator_audit, stage_audit),
        )


class ClosingFakeClient(FakeClient):
    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeWakeListener:
    def __init__(self) -> None:
        self.listen_calls = 0
        self.emitted = False

    def listen_pulse_wakes(self, *, on_wake, should_stop, interval_seconds):
        self.listen_calls += 1
        if not self.emitted:
            self.emitted = True
            on_wake()

    async def async_wait(self, timeout: float) -> bool:
        self.listen_calls += 1
        return True

    def wake(self) -> None:
        return None


async def _wait_until(predicate, *, timeout_seconds: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("timed out waiting for condition")
        await asyncio.sleep(0.01)


def _radar_row(*, factor_snapshot_json: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "row_id": "row-1",
        "window": "1h",
        "scope": "all",
        "computed_at_ms": NOW_MS - 1_000,
        "event_id": "event-1",
        "target_type": "Asset",
        "target_id": "asset-1",
        "target_json": {"target_type": "Asset", "target_id": "asset-1", "symbol": "TEST"},
        "asset_json": {"target_type": "Asset", "target_id": "asset-1", "symbol": "TEST"},
        "factor_snapshot_json": factor_snapshot_json,
        "source_event_ids_json": ["event-1"],
    }


def _factor_snapshot(
    *,
    rank_score: int,
    blocked_reasons: list[str] | None = None,
    recommended_decision: str | None = None,
    watched_mentions: int = 1,
) -> dict[str, Any]:
    decision = recommended_decision or ("high_alert" if rank_score >= 72 else "watch")
    return {
        "schema_version": "token_factor_snapshot_v3_social_attention",
        "subject": {
            "target_type": "Asset",
            "target_id": "asset-1",
            "target_market_type": "dex",
            "symbol": "TEST",
        },
        "market": {
            "event_anchor": None,
            "decision_latest": {
                "target_type": "Asset",
                "target_id": "asset-1",
                "observed_at_ms": NOW_MS - 1_000,
                "received_at_ms": NOW_MS - 1_000,
                "source": "decision_latest",
                "provider": "okx",
                "pricefeed_id": "pf-test",
                "price_usd": 0.42,
                "price_quote": None,
                "quote_symbol": "USD",
                "price_basis": "usd",
                "market_cap_usd": 1_000_000,
                "liquidity_usd": 250_000,
                "holders": 1_000,
                "volume_24h_usd": 12_000,
                "open_interest_usd": None,
                "raw_payload_hash": None,
            },
            "readiness": {
                "anchor_status": "ready",
                "latest_status": "live",
                "dex_floor_status": "ready",
                "missing_fields": [],
                "stale_fields": [],
            },
        },
        "gates": {
            "eligible_for_high_alert": not blocked_reasons,
            "blocked_reasons": blocked_reasons or [],
            "risk_reasons": blocked_reasons or [],
            "max_decision": "watch" if blocked_reasons else "high_alert",
        },
        "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
        "families": {
            "social_heat": {
                "raw_score": rank_score,
                "score": rank_score,
                "weight": 0.35,
                "data_health": "ready",
                "facts": {"mentions_1h": 8, "unique_authors": 7, "watched_mentions": watched_mentions},
                "factors": {
                    "watched_mentions": {
                        "family": "social_heat",
                        "key": "watched_mentions",
                        "risk_flags": [],
                    }
                },
            },
            "social_propagation": {
                "raw_score": rank_score,
                "score": rank_score,
                "weight": 0.3,
                "data_health": "ready",
                "facts": {"independent_authors": 7},
                "factors": {
                    "independent_authors": {
                        "family": "social_propagation",
                        "key": "independent_authors",
                        "risk_flags": blocked_reasons or [],
                    }
                },
            },
            "semantic_catalyst": {
                "raw_score": rank_score,
                "score": rank_score,
                "weight": 0.25,
                "data_health": "ready",
                "facts": {"phase": "ignition"},
                "factors": {},
            },
            "timing_risk": {
                "raw_score": rank_score,
                "score": rank_score,
                "weight": 0.1,
                "data_health": "ready",
                "facts": {"price_change_status": "ready"},
                "factors": {"price_change_status": {"family": "timing_risk", "key": "price_change_status"}},
            },
        },
        "normalization": {
            "status": "ranked",
            "cohort_status": "ready",
            "cohort": {"size": 12, "in_cohort": True},
            "factor_ranks": {},
            "alpha_rank": 0.82,
        },
        "composite": {
            "family_scores": {
                "social_heat": rank_score,
                "social_propagation": rank_score,
                "semantic_catalyst": rank_score,
                "timing_risk": rank_score,
            },
            "rank_score": rank_score,
            "recommended_decision": decision,
        },
        "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": NOW_MS - 1_000},
    }


def _timeline_row(event_id: str, received_at_ms: int) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "author_handle": "toly",
        "text": "$TEST is getting more attention",
        "is_watched": False,
        "received_at_ms": received_at_ms,
        "target_type": "Asset",
        "target_id": "asset-1",
        "symbol": "TEST",
    }


def _source_event() -> dict[str, Any]:
    return {
        "event_id": "source-1",
        "extraction_id": "extract-1",
        "author_handle": "toly",
        "received_at_ms": NOW_MS - 20_000,
        "event_type": "product_catalyst",
        "subject": "ecosystem launch",
        "subject_key": "ecosystem launch",
        "is_signal_event": True,
        "direction_hint": "positive",
        "impact_hint": 0.82,
        "semantic_novelty_hint": 0.67,
        "summary_zh": "生态发布正在获得关注",
    }


# ---------------------------------------------------------------------------
# _investigation_tool_calls_count helper
# ---------------------------------------------------------------------------


def _stage_audit(stage: str, *, tool_calls: Any | None = None) -> StageRunAudit:
    payload: dict[str, Any] = {"context": {}, "completeness": {}}
    if tool_calls is not None:
        payload["tool_calls"] = tool_calls
    return StageRunAudit(
        stage=stage,  # type: ignore[arg-type]
        route="meme",
        attempt_index=0,
        input_json=payload,
        prompt_text="prompt",
        response_json={},
        trace_metadata_json={},
        usage_json={},
        latency_ms=1,
        status="ok",
        error=None,
    )


def test_investigation_tool_calls_count_returns_zero_when_no_audits() -> None:
    assert _investigation_tool_calls_count(()) == 0


def test_investigation_tool_calls_count_reads_stage_zero_input_json() -> None:
    audit = _stage_audit("investigator", tool_calls=[{"name": "fetch"}, {"name": "lookup"}])
    decision = _stage_audit("decision_maker")
    assert _investigation_tool_calls_count((audit, decision)) == 2


def test_investigation_tool_calls_count_zero_when_tool_calls_missing() -> None:
    audit = _stage_audit("investigator")
    assert _investigation_tool_calls_count((audit,)) == 0


def test_investigation_tool_calls_count_zero_when_tool_calls_not_list() -> None:
    audit = _stage_audit("investigator", tool_calls="not-a-list")
    assert _investigation_tool_calls_count((audit,)) == 0


def test_investigation_tool_calls_count_zero_when_stage_zero_is_not_investigator() -> None:
    # research_only_gate path (completeness hard-blocked) puts gate audit at index 0
    audit = _stage_audit("research_only_gate", tool_calls=[{"name": "noop"}])
    assert _investigation_tool_calls_count((audit,)) == 0
