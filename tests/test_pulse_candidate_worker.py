from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.interfaces import PULSE_THESIS_SCHEMA_VERSION
from gmgn_twitter_intel.domains.pulse_lab.runtime.pulse_candidate_worker import (
    PulseCandidateWorker,
    PulseTriggerThresholds,
    _asset_candidate_id,
    _asset_trigger_signature,
    _cooldown_active,
    _cooldown_bypass,
    _is_asset_trigger,
    _score_bucket,
    _source_candidate_id,
    _source_trigger_metrics,
    _source_trigger_signature,
)
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_gate import PulseGateResult
from gmgn_twitter_intel.domains.pulse_lab.types.pulse_thesis import PulseThesisPayload
from gmgn_twitter_intel.integrations.openai_agents.pulse_thesis_agent_client import PulseThesisAgentResult

NOW_MS = 1_800_000


def test_asset_led_enqueue_signatures_and_same_signature_skip() -> None:
    repos = FakeRepos()
    row = _radar_row(heat=84, event_id="event-latest")
    repos.token_radar.rows = [row]
    repos.token_targets.rows = [_timeline_row("event-latest", NOW_MS - 10_000)]
    worker = PulseCandidateWorker(
        repository_session=lambda: _session(repos),
        thesis_client=FakeClient(),
        batch_size=10,
    )

    first = worker.scan_triggers_once(now_ms=NOW_MS)
    second = worker.scan_triggers_once(now_ms=NOW_MS)

    assert first["asset_enqueued"] == 1
    assert second["asset_skipped"] == 1
    assert len(repos.pulse.jobs) == 1
    job = repos.pulse.jobs[0]
    assert job["candidate_id"] == _asset_candidate_id(
        candidate_type="token_target",
        window="1h",
        scope="all",
        target_type="Asset",
        target_id="asset-1",
    )
    assert job["target_type"] == "Asset"
    assert job["target_id"] == "asset-1"
    assert job["trigger_signature"] == _asset_trigger_signature(
        row=row,
        window="1h",
        scope="all",
        candidate_type="token_target",
    )
    assert job["timeline_signature"].startswith("sha256:")


def test_existing_pending_job_blocks_signature_churn_reenqueue() -> None:
    repos = FakeRepos()
    first_row = _radar_row(heat=86, event_id="event-1")
    repos.token_radar.rows = [first_row]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 10_000)]
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), thesis_client=FakeClient())

    first = worker.scan_triggers_once(now_ms=NOW_MS)
    repos.token_radar.rows = [_radar_row(heat=87, event_id="event-2")]
    repos.token_targets.rows = [_timeline_row("event-2", NOW_MS + 10_000)]
    second = worker.scan_triggers_once(now_ms=NOW_MS + 10_000)

    assert first["asset_enqueued"] == 1
    assert second["asset_skipped"] == 1
    assert len(repos.pulse.jobs) == 1
    assert repos.pulse.jobs[0]["attempt_count"] == 0
    assert repos.pulse.jobs[0]["trigger_signature"] == _asset_trigger_signature(
        row=first_row,
        window="1h",
        scope="all",
        candidate_type="token_target",
    )


def test_cooldown_skip_and_watched_confirmation_bypass() -> None:
    repos = FakeRepos()
    base_row = _radar_row(heat=84, event_id="event-1")
    repos.token_radar.rows = [base_row]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 10_000)]
    candidate_id = _asset_candidate_id(
        candidate_type="token_target",
        window="1h",
        scope="all",
        target_type="Asset",
        target_id="asset-1",
    )
    repos.pulse.candidates[candidate_id] = {
        "candidate_id": candidate_id,
        "pulse_status": "token_watch",
        "updated_at_ms": NOW_MS - 60_000,
        "trigger_signature": _asset_trigger_signature(
            row=base_row,
            window="1h",
            scope="all",
            candidate_type="token_target",
        ),
        "timeline_signature": "different-but-no-bypass",
        "radar_score_json": {
            "pulse_trigger_metrics": {
                "heat_bucket": _score_bucket(84),
                "social_phase": "seed",
                "watched_confirmation": False,
                "independent_author_count": 2,
                "market_status": "fresh",
                "hard_risks": [],
            }
        },
    }
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), thesis_client=FakeClient())

    skipped = worker.scan_triggers_once(now_ms=NOW_MS)
    assert skipped["asset_skipped"] == 1
    assert len(repos.pulse.jobs) == 0

    repos.token_radar.rows = [_radar_row(heat=84, event_id="event-2", watched_mentions=1)]
    bypassed = worker.scan_triggers_once(now_ms=NOW_MS)

    assert bypassed["asset_enqueued"] == 1
    assert repos.pulse.jobs[0]["candidate_id"] == candidate_id


def test_source_led_enqueue_as_source_seed_without_target() -> None:
    repos = FakeRepos()
    repos.harness.social_events = [_source_event()]
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), thesis_client=FakeClient())

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["source_enqueued"] == 1
    job = repos.pulse.jobs[0]
    assert job["candidate_type"] == "source_seed"
    assert job["candidate_id"] == _source_candidate_id(window="1h", scope="matched", source_event_id="source-1")
    assert job["target_type"] is None
    assert job["target_id"] is None
    assert job["subject_key"] == "source:source-1"
    assert job["context_json"]["timeline_context"]["selected_posts"][0]["text"] == "生态发布正在获得关注"
    assert _source_trigger_metrics(_source_event())["impact_bucket"] == "very_high"
    assert _source_trigger_metrics(_source_event())["novelty_bucket"] == "high"
    assert _source_trigger_signature(_source_event()).startswith("sha256:")


def test_asset_trigger_predicate_matrix() -> None:
    base = _radar_row(heat=10, event_id="event-low", decision="discard", propagation=10)

    assert _is_asset_trigger(_radar_row(heat=10, event_id="driver", decision="driver", propagation=10))
    assert _is_asset_trigger(_radar_row(heat=10, event_id="watch", decision="watch", propagation=10))
    assert _is_asset_trigger(_radar_row(heat=80, event_id="heat", decision="discard", propagation=10))
    assert not _is_asset_trigger(_radar_row(heat=70, event_id="heat-default", decision="discard", propagation=10))
    assert _is_asset_trigger(
        _radar_row(heat=70, event_id="heat-configured", decision="discard", propagation=10),
        thresholds=PulseTriggerThresholds(asset_heat_min=70),
    )
    assert _is_asset_trigger(_radar_row(heat=10, event_id="prop", decision="discard", propagation=70))
    assert _is_asset_trigger(
        _radar_row(heat=10, event_id="watched", decision="discard", propagation=10, watched_mentions=1)
    )
    assert not _is_asset_trigger(base)
    assert not _is_asset_trigger({**base, "target_type": None})
    assert not _is_asset_trigger({**base, "target_id": None})


def test_cooldown_bypass_matrix() -> None:
    previous = {
        "heat_bucket": "80-89",
        "social_phase": "seed",
        "watched_confirmation": False,
        "independent_author_count": 2,
        "chase_risk": False,
        "market_status": "stale",
        "hard_risks": ["market_stale"],
    }
    existing = {"pulse_status": "blocked_low_information"}

    assert _cooldown_bypass(existing, previous, {**previous, "trade_candidate_eligible": True})
    assert not _cooldown_bypass({"pulse_status": "risk_rejected_high_info"}, previous, dict(previous))
    assert not _cooldown_bypass({"pulse_status": "blocked_low_information"}, previous, dict(previous))
    assert not _cooldown_bypass({"pulse_status": "token_watch"}, previous, {**previous, "social_phase": "ignition"})
    assert not _cooldown_bypass({"pulse_status": "token_watch"}, previous, {**previous, "heat_bucket": "90-99"})
    assert _cooldown_bypass({"pulse_status": "token_watch"}, previous, {**previous, "watched_confirmation": True})
    assert _cooldown_bypass({"pulse_status": "token_watch"}, previous, {**previous, "independent_author_count": 7})
    assert _cooldown_bypass({"pulse_status": "token_watch"}, previous, {**previous, "chase_risk": True})
    assert not _cooldown_bypass({"pulse_status": "token_watch"}, previous, {**previous, "market_status": "fresh"})
    assert _cooldown_bypass(
        {"pulse_status": "token_watch"},
        previous,
        {**previous, "hard_risks": ["market_stale", "liquidity_missing"]},
    )
    assert not _cooldown_bypass({"pulse_status": "token_watch"}, previous, dict(previous))


def test_cooldown_active_uses_bypass_matrix() -> None:
    context = _candidate_context(
        {
            "heat_bucket": "80-89",
            "social_phase": "seed",
            "watched_confirmation": False,
            "independent_author_count": 2,
            "chase_risk": False,
            "market_status": "stale",
            "hard_risks": [],
        }
    )
    existing = {
        "pulse_status": "token_watch",
        "updated_at_ms": NOW_MS - 60_000,
        "radar_score_json": {
            "pulse_trigger_metrics": {
                "heat_bucket": "80-89",
                "social_phase": "seed",
                "watched_confirmation": False,
                "independent_author_count": 2,
                "chase_risk": False,
                "market_status": "stale",
                "hard_risks": [],
            }
        },
    }

    assert _cooldown_active(existing, context, now_ms=NOW_MS)
    fresh_context = _candidate_context({**context.radar_score["pulse_trigger_metrics"], "market_status": "fresh"})
    assert _cooldown_active(existing, fresh_context, now_ms=NOW_MS)
    confirmed_context = _candidate_context(
        {**context.radar_score["pulse_trigger_metrics"], "watched_confirmation": True}
    )
    assert not _cooldown_active(existing, confirmed_context, now_ms=NOW_MS)


def test_cooldown_does_not_bypass_for_inferred_token_watch_status_rank() -> None:
    context = _candidate_context(
        {
            "heat_bucket": "80-89",
            "propagation_bucket": "70-79",
            "social_phase": "ignition",
            "watched_confirmation": False,
            "independent_author_count": 2,
            "chase_risk": False,
            "market_status": "fresh",
            "hard_risks": ["market_stale"],
            "trade_candidate_eligible": False,
        }
    )
    existing = {
        "pulse_status": "risk_rejected_high_info",
        "updated_at_ms": NOW_MS - 60_000,
        "radar_score_json": {
            "pulse_trigger_metrics": {
                "heat_bucket": "80-89",
                "propagation_bucket": "70-79",
                "social_phase": "ignition",
                "watched_confirmation": False,
                "independent_author_count": 2,
                "chase_risk": False,
                "market_status": "fresh",
                "hard_risks": ["market_stale"],
                "trade_candidate_eligible": False,
            }
        },
    }

    assert _cooldown_active(existing, context, now_ms=NOW_MS)


def test_recent_dead_job_blocks_reenqueue_without_candidate() -> None:
    repos = FakeRepos()
    stale_row = _radar_row(heat=86, event_id="event-old")
    fresh_row = _radar_row(heat=87, event_id="event-new")
    candidate_id = _asset_candidate_id(
        candidate_type="token_target",
        window="1h",
        scope="all",
        target_type="Asset",
        target_id="asset-1",
    )
    repos.pulse.jobs.append(
        {
            "job_id": "job-dead",
            "candidate_id": candidate_id,
            "candidate_type": "token_target",
            "subject_key": "TEST",
            "target_type": "Asset",
            "target_id": "asset-1",
            "window": "1h",
            "scope": "all",
            "trigger_signature": _asset_trigger_signature(
                row=stale_row,
                window="1h",
                scope="all",
                candidate_type="token_target",
            ),
            "timeline_signature": "sha256:old",
            "context_json": {},
            "priority": 86,
            "status": "dead",
            "attempt_count": 3,
            "max_attempts": 3,
            "updated_at_ms": NOW_MS - 60_000,
        }
    )
    repos.token_radar.rows = [fresh_row]
    repos.token_targets.rows = [_timeline_row("event-new", NOW_MS - 1_000)]
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), thesis_client=FakeClient())

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_skipped"] == 1
    assert len(repos.pulse.jobs) == 1
    assert repos.pulse.jobs[0]["trigger_signature"] == _asset_trigger_signature(
        row=stale_row,
        window="1h",
        scope="all",
        candidate_type="token_target",
    )


def test_claim_run_gate_upserts_candidate_audit_playbook_and_marks_success() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [_radar_row(heat=86, event_id="event-1")]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 10_000)]
    client = FakeClient()
    gate_result = PulseGateResult(
        pulse_status="token_watch",
        verdict="token_watch",
        candidate_score=72.0,
        score_band="watch",
        gate_reasons=["trade_gate_incomplete"],
        risk_reasons=[],
        hard_risks=[],
    )
    worker = PulseCandidateWorker(
        repository_session=lambda: _session(repos),
        thesis_client=client,
        gate_func=lambda **_: gate_result,
    )

    scan_result = worker.scan_triggers_once(now_ms=NOW_MS)
    run_result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert scan_result["asset_enqueued"] == 1
    assert run_result["processed"] == 1
    assert repos.pulse.agent_runs[0]["status"] == "running"
    assert repos.pulse.finished_runs[0]["status"] == "done"
    assert repos.pulse.candidate_upserts[0]["pulse_status"] == "token_watch"
    assert repos.pulse.candidate_upserts[0]["agent_run_id"].startswith("pulse-run:")
    assert repos.pulse.playbook_upserts[0]["side"] == "OBSERVE_ONLY"
    assert repos.pulse.successes == [repos.pulse.jobs[0]["job_id"]]


def test_fresh_worker_processes_durable_job_context_after_restart() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [_radar_row(heat=86, event_id="event-1")]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 10_000)]
    worker_a = PulseCandidateWorker(repository_session=lambda: _session(repos), thesis_client=FakeClient())

    scan_result = worker_a.scan_triggers_once(now_ms=NOW_MS)
    repos.token_radar.rows = []
    repos.token_targets.rows = []
    worker_b = PulseCandidateWorker(repository_session=lambda: _session(repos), thesis_client=FakeClient())
    run_result = worker_b.process_due_jobs_once(now_ms=NOW_MS + 1_000)

    assert scan_result["asset_enqueued"] == 1
    assert repos.pulse.jobs[0]["context_json"]["candidate_id"] == repos.pulse.jobs[0]["candidate_id"]
    assert run_result["processed"] == 1
    assert run_result["missing_context"] == 0
    assert repos.pulse.candidate_upserts[0]["candidate_id"] == repos.pulse.jobs[0]["candidate_id"]


def test_reenqueue_changed_signature_creates_distinct_run_ids() -> None:
    repos = FakeRepos(enforce_unique_run_ids=True)
    repos.token_radar.rows = [_radar_row(heat=86, event_id="event-1")]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 10_000)]
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), thesis_client=FakeClient())

    worker.scan_triggers_once(now_ms=NOW_MS)
    first = worker.process_due_jobs_once(now_ms=NOW_MS + 1_000)
    repos.token_radar.rows = [_radar_row(heat=87, event_id="event-churn")]
    repos.token_targets.rows = [_timeline_row("event-churn", NOW_MS + 1_500)]
    skipped = worker.scan_triggers_once(now_ms=NOW_MS + 1_500)
    repos.token_radar.rows = [_radar_row(heat=96, event_id="event-2", watched_mentions=1)]
    repos.token_targets.rows = [_timeline_row("event-2", NOW_MS + 2_000)]
    worker.scan_triggers_once(now_ms=NOW_MS + 2_000)
    second = worker.process_due_jobs_once(now_ms=NOW_MS + 3_000)

    run_ids = [row["run_id"] for row in repos.pulse.agent_runs]
    assert first["processed"] == 1
    assert skipped["asset_skipped"] == 1
    assert second["processed"] == 1
    assert len(run_ids) == 2
    assert len(set(run_ids)) == 2


def test_failure_path_marks_job_failed_and_finishes_failed_run_when_audit_exists() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [_radar_row(heat=86, event_id="event-1")]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 10_000)]
    client = FakeClient(error=RuntimeError("agent unavailable"))
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), thesis_client=client)

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["failed"] == 1
    assert repos.pulse.agent_runs[0]["status"] == "running"
    assert repos.pulse.finished_runs[0]["status"] == "failed"
    assert repos.pulse.finished_runs[0]["error"] == "agent unavailable"
    assert repos.pulse.failures[0]["error"] == "agent unavailable"


def test_timed_out_agent_job_is_failed_and_next_job_continues() -> None:
    repos = FakeRepos()
    context = _candidate_context(
        {
            "heat_bucket": "80-89",
            "social_phase": "ignition",
            "watched_confirmation": False,
            "independent_author_count": 3,
            "market_status": "fresh",
            "hard_risks": [],
        }
    )
    first_context = context.agent_context()
    second_context = {**first_context, "candidate_id": "candidate-2", "subject_key": "target:Asset:asset-2"}
    repos.pulse.enqueue_job(
        candidate_id="candidate-1",
        candidate_type="token_target",
        subject_key="target:Asset:asset-1",
        target_type="Asset",
        target_id="asset-1",
        window="1h",
        scope="all",
        trigger_signature="trigger-1",
        timeline_signature="timeline-1",
        context_json=first_context,
        priority=80,
        max_attempts=3,
        next_run_at_ms=NOW_MS,
        now_ms=NOW_MS,
    )
    repos.pulse.enqueue_job(
        candidate_id="candidate-2",
        candidate_type="token_target",
        subject_key="target:Asset:asset-2",
        target_type="Asset",
        target_id="asset-2",
        window="1h",
        scope="all",
        trigger_signature="trigger-2",
        timeline_signature="timeline-2",
        context_json=second_context,
        priority=79,
        max_attempts=3,
        next_run_at_ms=NOW_MS,
        now_ms=NOW_MS,
    )
    client = SlowThenSuccessClient()
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), thesis_client=client)

    result = asyncio.run(worker.process_due_jobs_once_async(now_ms=NOW_MS))

    assert result["failed"] == 1
    assert result["processed"] == 1
    assert client.calls == 2
    assert repos.pulse.finished_runs[0]["status"] == "failed"
    assert repos.pulse.finished_runs[0]["error"] == "Agents SDK request timed out after 0.1s"
    assert repos.pulse.failures[0]["error"] == "Agents SDK request timed out after 0.1s"
    assert repos.pulse.finished_runs[1]["status"] == "done"
    assert repos.pulse.successes == ["job-2"]


@contextmanager
def _session(repos: FakeRepos):
    yield repos


class FakeRepos:
    def __init__(self, *, enforce_unique_run_ids: bool = False) -> None:
        self.conn = FakeConn()
        self.token_radar = FakeTokenRadar()
        self.token_targets = FakeTokenTargets()
        self.harness = FakeHarness()
        self.pulse = FakePulse(enforce_unique_run_ids=enforce_unique_run_ids)


class FakeConn:
    @contextmanager
    def transaction(self):
        yield


class FakeTokenRadar:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []

    def latest_rows(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(kwargs)
        return list(self.rows)


class FakeTokenTargets:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []

    def timeline_rows(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(kwargs)
        return list(self.rows)


class FakeHarness:
    def __init__(self) -> None:
        self.social_events: list[dict[str, Any]] = []

    def list_social_events(self, **_: Any) -> list[dict[str, Any]]:
        return list(self.social_events)


class FakePulse:
    def __init__(self, *, enforce_unique_run_ids: bool = False) -> None:
        self.jobs: list[dict[str, Any]] = []
        self.candidates: dict[str, dict[str, Any]] = {}
        self.agent_runs: list[dict[str, Any]] = []
        self.finished_runs: list[dict[str, Any]] = []
        self.candidate_upserts: list[dict[str, Any]] = []
        self.playbook_upserts: list[dict[str, Any]] = []
        self.successes: list[str] = []
        self.failures: list[dict[str, Any]] = []
        self.enforce_unique_run_ids = enforce_unique_run_ids

    def candidate_by_id(self, candidate_id: str) -> dict[str, Any] | None:
        return self.candidates.get(candidate_id)

    def job_for_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        for job in reversed(self.jobs):
            if job["candidate_id"] == candidate_id:
                return job
        return None

    def enqueue_job(self, **kwargs: Any) -> dict[str, Any]:
        job = {
            **kwargs,
            "context_json": kwargs.get("context_json") or {},
            "job_id": kwargs.get("job_id") or f"job-{len(self.jobs) + 1}",
            "status": kwargs.get("status", "pending"),
            "attempt_count": kwargs.get("attempt_count", 0),
            "max_attempts": kwargs.get("max_attempts", 3),
        }
        for index, existing in enumerate(self.jobs):
            if existing["candidate_id"] == job["candidate_id"]:
                self.jobs[index] = job
                return job
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
        if self.enforce_unique_run_ids and any(row["run_id"] == kwargs["run_id"] for row in self.agent_runs):
            raise AssertionError(f"duplicate run_id: {kwargs['run_id']}")
        self.agent_runs.append(kwargs)
        return kwargs

    def finish_agent_run(self, run_id: str, status: str, **kwargs: Any) -> dict[str, Any]:
        row = {"run_id": run_id, "status": status, **kwargs}
        self.finished_runs.append(row)
        return row

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
        for stored_job in self.jobs:
            if stored_job["job_id"] == job["job_id"]:
                stored_job["status"] = "failed"
                stored_job["last_error"] = error
        self.failures.append({"job": job, "error": error})
        return {"job_id": job["job_id"], "status": "failed", "last_error": error}


class FakeClient:
    provider = "fake"
    model = "fake-pulse"
    timeout_seconds = 1.0
    artifact_version_hash = "artifact:fake"

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def request_audit(self, *, context: dict[str, Any], run_id: str, job: dict[str, Any]) -> dict[str, Any]:
        return {
            "backend": "fake",
            "sdk_trace_id": f"trace-{run_id}",
            "workflow_name": "test-flow",
            "agent_name": "test-agent",
            "prompt_version": "prompt-v1",
            "schema_version": PULSE_THESIS_SCHEMA_VERSION,
            "artifact_version_hash": self.artifact_version_hash,
            "trace_metadata": {"candidate_id": context["candidate_id"]},
            "input_hash": "input-hash",
            "input_source_event_ids": context.get("source_event_ids", []),
        }

    async def write_thesis(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
    ) -> PulseThesisAgentResult:
        if self.error is not None:
            raise self.error
        payload = PulseThesisPayload(
            schema_version=PULSE_THESIS_SCHEMA_VERSION,
            candidate_type=context["candidate_type"],
            subject_key=context["subject_key"],
            target_type=context.get("target_type"),
            target_id=context.get("target_id"),
            symbol=context.get("symbol"),
            verdict="token_watch" if context["candidate_type"] == "token_target" else "theme_watch",
            social_phase="ignition",
            narrative_type="direct_token" if context["candidate_type"] == "token_target" else "product_catalyst",
            summary_zh="社交热度正在升温，适合继续观察。",
            why_now_zh="多源讨论和时间线证据出现同步。",
            bull_case_zh=["讨论扩散质量改善。"],
            bear_case_zh=["市场确认仍需观察。"],
            confirmation_triggers_zh=["更多独立账号确认。"],
            invalidation_triggers_zh=["讨论迅速降温。"],
            top_risks=[],
            evidence_event_ids=context.get("evidence_event_ids") or context.get("source_event_ids") or ["event-1"],
            source_event_ids=context.get("source_event_ids") or ["event-1"],
            confidence=0.7,
        )
        audit = self.request_audit(context=context, run_id=run_id, job=job)
        return PulseThesisAgentResult(payload=payload, agent_run_audit={**audit, "output_hash": "output-hash"})


class SlowThenSuccessClient(FakeClient):
    timeout_seconds = 0.01

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def write_thesis(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
    ) -> PulseThesisAgentResult:
        self.calls += 1
        if self.calls == 1:
            await asyncio.sleep(5)
        return await super().write_thesis(context=context, run_id=run_id, job=job)


def _candidate_context(metrics: dict[str, Any]):
    row = _radar_row(heat=84, event_id="event-context")
    context = PulseCandidateWorker(
        repository_session=lambda: _session(FakeRepos()),
        thesis_client=FakeClient(),
    )._asset_context(
        FakeRepos(),
        row,
        window="1h",
        scope="all",
        now_ms=NOW_MS,
    )
    context.radar_score["pulse_trigger_metrics"] = metrics
    return context


def _radar_row(
    *,
    heat: int,
    event_id: str,
    watched_mentions: int = 0,
    decision: str = "watch",
    propagation: int = 72,
) -> dict[str, Any]:
    return {
        "row_id": "row-1",
        "window": "1h",
        "scope": "all",
        "computed_at_ms": NOW_MS - 1_000,
        "event_id": event_id,
        "target_type": "Asset",
        "target_id": "asset-1",
        "target_json": {"target_type": "Asset", "target_id": "asset-1", "symbol": "TEST"},
        "asset_json": {"target_type": "Asset", "target_id": "asset-1", "symbol": "TEST"},
        "attention_json": {
            "latest_seen_ms": NOW_MS - 1_000,
            "watched_mentions": watched_mentions,
            "unique_authors": 2,
        },
        "market_json": {"market_status": "fresh"},
        "price_json": {"market_status": "fresh"},
        "score_json": {
            "heat": {"score": heat},
            "quality": {"score": 64},
            "propagation": {"score": propagation, "phase": "ignition"},
            "tradeability": {"score": 73, "market_status": "fresh"},
            "timing": {"score": 56, "chase_risk": False},
            "opportunity": {"decision": decision, "score": 71},
        },
        "decision": decision,
        "source_event_ids_json": ["event-seed", event_id],
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
