from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.providers import PulseDecisionResult
from gmgn_twitter_intel.domains.pulse_lab.runtime.pulse_candidate_worker import (
    PulseCandidateWorker,
    _asset_candidate_id,
    _asset_trigger_metrics,
)
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_gate import PulseGateResult
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import FinalDecision, PulseStageFailure, StageRunAudit

NOW_MS = 1_800_000


def test_missing_factor_snapshot_is_not_enqueued() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=None)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), decision_client=FakeClient())

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 1
    assert result["asset_skipped"] == 1
    assert result["asset_enqueued"] == 0
    assert repos.pulse.jobs == []


def test_malformed_v3_factor_snapshot_is_not_enqueued() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(rank_score=82)
    snapshot["families"]["market_quality"] = {"facts": {"market_status": "fresh"}}
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), decision_client=FakeClient())

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 1
    assert result["asset_skipped"] == 1
    assert result["asset_enqueued"] == 0
    assert repos.pulse.jobs == []


def test_asset_context_uses_factor_snapshot_and_no_legacy_runtime_context() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(rank_score=82)
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), decision_client=FakeClient())

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_enqueued"] == 1
    job = repos.pulse.jobs[0]
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
        repository_session=lambda: _session(repos),
        decision_client=client,
        gate_func=gate_func,
    )

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 1
    assert gate_calls and client.contexts
    assert client.contexts[0]["gate_result"]["pulse_status"] == "token_watch"
    assert client.contexts[0]["gate_result"]["max_recommendation"] == "watch"
    assert repos.pulse.candidate_upserts[0]["pulse_status"] == "token_watch"
    assert repos.pulse.candidate_upserts[0]["candidate_score"] == 50.0
    assert repos.pulse.candidate_upserts[0]["score_band"] == "speculative"


def test_worker_persists_factor_snapshot_gate_and_decision_only() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(rank_score=82)
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), decision_client=FakeClient())

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 1
    upsert = repos.pulse.candidate_upserts[0]
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


def test_worker_does_not_scan_unresolved_social_events() -> None:
    repos = FakeRepos()
    repos.harness.social_events = [_source_event()]
    client = FakeClient()
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), decision_client=client)

    scan = worker.scan_triggers_once(now_ms=NOW_MS)
    run = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert scan["source_seen"] == 0
    assert scan["source_enqueued"] == 0
    assert run["processed"] == 0
    assert repos.pulse.jobs == []
    assert repos.pulse.candidate_upserts == []
    assert client.run_calls == 0


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
    repos.pulse.edge_states[candidate_id] = {
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
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), decision_client=FakeClient())

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 1
    assert result["asset_enqueued"] == 0
    assert result["asset_skipped"] == 1
    assert repos.pulse.jobs == []


def test_worker_can_be_woken_by_token_radar_update_before_interval() -> None:
    repos = FakeRepos()
    wake_listener = FakeWakeListener()
    worker = PulseCandidateWorker(
        repository_session=lambda: _session(repos),
        decision_client=FakeClient(),
        poll_interval=60.0,
        wake_listener=wake_listener,
    )

    async def scenario() -> None:
        task = asyncio.create_task(worker.run())
        try:
            await _wait_until(lambda: repos.token_radar.latest_calls >= 1)
            await _wait_until(lambda: repos.token_radar.latest_calls >= 2)
        finally:
            worker.stop()
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
    repos.pulse.budget_claims[(candidate_id, NOW_MS // 3_600_000 * 3_600_000)] = 3
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), decision_client=FakeClient())

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 1
    assert result["asset_enqueued"] == 0
    assert result["asset_skipped"] == 1
    assert repos.pulse.jobs == []


def test_worker_persists_failed_stage_audits_when_provider_raises_stage_failure() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82))]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]

    class FailingClient(FakeClient):
        async def run_decision_pipeline(self, **kwargs: Any) -> Any:
            self.run_calls += 1
            failed_audit = StageRunAudit(
                stage="analyst",
                route=kwargs["route"],
                attempt_index=0,
                input_json={"context": kwargs["context"]},
                prompt_text="fake analyst prompt",
                response_json={"raw_output": "**Analyst Report:** prose only"},
                trace_metadata_json={"stage": "analyst"},
                usage_json={},
                latency_ms=42,
                status="failed",
                error="ModelBehaviorError: invalid JSON",
            )
            raise PulseStageFailure("analyst stage failed", audits=(failed_audit,))

    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), decision_client=FailingClient())

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 0
    assert result["failed"] == 1
    assert len(repos.pulse.agent_run_steps) == 1
    step = repos.pulse.agent_run_steps[0]
    assert step["stage"] == "analyst"
    assert step["status"] == "failed"
    assert step["error"] == "ModelBehaviorError: invalid JSON"
    assert step["response_json"] == {"raw_output": "**Analyst Report:** prose only"}
    assert any(row["status"] == "failed" for row in repos.pulse.finished_runs)
    assert len(repos.pulse.failures) == 1


@contextmanager
def _session(repos: FakeRepos):
    yield repos


class FakeRepos:
    def __init__(self) -> None:
        self.conn = FakeConn()
        self.token_radar = FakeTokenRadar()
        self.token_targets = FakeTokenTargets()
        self.harness = FakeHarness()
        self.pulse = FakePulse()


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


class FakeHarness:
    def __init__(self) -> None:
        self.social_events: list[dict[str, Any]] = []

    def list_social_events(self, **_: Any) -> list[dict[str, Any]]:
        return list(self.social_events)


class FakePulse:
    def __init__(self) -> None:
        self.jobs: list[dict[str, Any]] = []
        self.candidates: dict[str, dict[str, Any]] = {}
        self.edge_states: dict[str, dict[str, Any]] = {}
        self.budget_claims: dict[tuple[str, int], int] = {}
        self.agent_runs: list[dict[str, Any]] = []
        self.agent_run_steps: list[dict[str, Any]] = []
        self.finished_runs: list[dict[str, Any]] = []
        self.harness_versions: list[dict[str, Any]] = []
        self.eval_cases: list[dict[str, Any]] = []
        self.eval_results: list[dict[str, Any]] = []
        self.candidate_upserts: list[dict[str, Any]] = []
        self.playbook_upserts: list[dict[str, Any]] = []
        self.successes: list[str] = []
        self.failures: list[dict[str, Any]] = []

    def candidate_by_id(self, candidate_id: str) -> dict[str, Any] | None:
        return self.candidates.get(candidate_id)

    def job_for_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        for job in reversed(self.jobs):
            if job["candidate_id"] == candidate_id:
                return job
        return None

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
            "last_processed_state_json": kwargs["processed_state_json"],
            "last_edge_events_json": kwargs["edge_events_json"],
            "last_job_id": kwargs["job_id"],
            "last_processed_at_ms": kwargs["processed_at_ms"],
        }
        self.edge_states[candidate_id] = row
        return row

    def mark_edge_budget_rejected(self, **kwargs: Any) -> dict[str, Any]:
        candidate_id = kwargs["candidate_id"]
        row = self.edge_states.get(candidate_id, {"candidate_id": candidate_id})
        row = {**row, "last_edge_events_json": kwargs["edge_events_json"], "updated_at_ms": kwargs["rejected_at_ms"]}
        self.edge_states[candidate_id] = row
        return row

    def mark_edge_run_finished(self, **kwargs: Any) -> dict[str, Any]:
        candidate_id = kwargs["candidate_id"]
        row = self.edge_states.get(candidate_id, {"candidate_id": candidate_id})
        row = {**row, "last_agent_run_id": kwargs["agent_run_id"], "updated_at_ms": kwargs["finished_at_ms"]}
        self.edge_states[candidate_id] = row
        return row

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

    def upsert_agent_harness_version(self, **kwargs: Any) -> dict[str, Any]:
        self.harness_versions.append(kwargs)
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

    def mark_job_failed(self, job: dict[str, Any], error: str, **_: Any) -> dict[str, Any]:
        self.failures.append({"job": job, "error": error})
        return {"job_id": job["job_id"], "status": "failed"}


class FakeClient:
    provider = "fake"
    model = "fake-pulse"
    timeout_seconds = 1.0
    artifact_version_hash = "artifact:fake"

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
        harness: dict[str, Any],
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
            "harness_version": harness["harness_version"],
            "harness_hash": "sha256:fake-harness",
            "trace_metadata": {
                "candidate_id": context["candidate_id"],
                "route": route,
                "completeness": completeness,
                "harness_version": harness["harness_version"],
                "harness_hash": "sha256:fake-harness",
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
        harness: dict[str, Any],
    ) -> PulseDecisionResult:
        self.run_calls += 1
        final_decision = FinalDecision(
            route=route,  # type: ignore[arg-type]
            recommendation=self.recommendation,
            confidence=0.7,
            abstain_reason=None,
            summary_zh="因子快照显示信号值得继续观察。",
            invalidation_conditions=["独立作者数回落。"],
            residual_risks=["价格响应仍可能变化。"],
            evidence_event_ids=context.get("source_event_ids") or ["event-1"],
        )
        stage_audit = StageRunAudit(
            stage="judge",
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
            harness=harness,
        )
        return PulseDecisionResult(
            final_decision=final_decision,
            agent_run_audit={**audit, "output_hash": "output-hash"},
            stage_audits=(stage_audit,),
        )


class FakeWakeListener:
    def __init__(self) -> None:
        self.listen_calls = 0
        self.emitted = False

    def listen_pulse_wakes(self, *, on_wake, should_stop, interval_seconds):
        self.listen_calls += 1
        if not self.emitted:
            self.emitted = True
            on_wake()


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


def _factor_snapshot(*, rank_score: int, blocked_reasons: list[str] | None = None) -> dict[str, Any]:
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
                "facts": {"mentions_1h": 8, "unique_authors": 7, "watched_mentions": 1},
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
            "recommended_decision": "high_alert" if rank_score >= 72 else "watch",
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
