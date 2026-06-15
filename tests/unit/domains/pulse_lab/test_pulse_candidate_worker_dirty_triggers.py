from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.domains.pulse_lab.runtime.pulse_candidate_worker import PulseCandidateWorker
from tests.unit.test_pulse_candidate_worker import _factor_snapshot, _radar_row, _timeline_row

NOW_MS = 1_800_000


def test_empty_dirty_queue_does_not_scan_token_radar_rows() -> None:
    repos = _FakeRepos()
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["reason"] == "no_due_pulse_triggers"
    assert result["claimed"] == 0
    assert result["source_rows_scanned"] == 0
    assert result["targets_loaded"] == 0
    assert result["queue_depth"] == 0
    assert repos.token_radar.latest_calls == 0
    assert repos.pulse_trigger_dirty_targets.claim_calls == 1


def test_worker_requires_repository_session_transaction_before_claiming_dirty_targets() -> None:
    repos = _FakeRepos()
    session_without_transaction = SimpleNamespace(
        conn=repos.conn,
        pulse_trigger_dirty_targets=repos.pulse_trigger_dirty_targets,
        token_radar=repos.token_radar,
        token_targets=repos.token_targets,
        pulse_jobs=repos.pulse_jobs,
        pulse_admission=repos.pulse_admission,
    )
    worker = _worker(session_without_transaction)

    with pytest.raises(AttributeError, match="transaction"):
        worker.scan_triggers_once(now_ms=NOW_MS)

    assert repos.pulse_trigger_dirty_targets.claim_calls == 0


def test_claimed_dirty_trigger_loads_exact_target_context_and_marks_done() -> None:
    claim = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "window": "1h",
        "scope": "all",
        "payload_hash": "pulse-trigger-1",
        "lease_owner": "pulse-candidate",
        "attempt_count": 1,
        "dirty_reason": "token_radar_changed",
        "source_watermark_ms": NOW_MS - 1_000,
    }
    row = _radar_row(factor_snapshot_json=_factor_snapshot(rank_score=80))
    repos = _FakeRepos(claims=[claim], exact_rows={("Asset", "asset-1", "1h", "all"): row})
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _RecordingWorker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["claimed"] == 1
    assert result["targets_loaded"] == 1
    assert result["asset_enqueued"] == 1
    assert result["source_rows_scanned"] == 0
    assert repos.token_radar.latest_calls == 0
    assert repos.token_radar.exact_calls == [
        {
            "projection_version": "token-radar-v13-social-attention",
            "target_type": "Asset",
            "target_id": "asset-1",
            "window": "1h",
            "scope": "all",
            "venue": "all",
        }
    ]
    assert repos.pulse_trigger_dirty_targets.done == [claim]
    assert worker.recorded_contexts[0].target_id == "asset-1"
    assert worker.recorded_contexts[0].window == "1h"


@pytest.mark.parametrize(
    ("claim_overrides", "error_token"),
    (
        ({"scope": "typo"}, "pulse_trigger_dirty_target_invalid_scope:typo"),
        ({"window": "24h"}, "pulse_trigger_dirty_target_invalid_window:24h"),
    ),
)
def test_dirty_trigger_rejects_unconfigured_dimensions_before_payload_reads(
    claim_overrides: dict[str, str],
    error_token: str,
) -> None:
    claim = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "window": "1h",
        "scope": "all",
        "payload_hash": "pulse-trigger-bad-dimension",
        "lease_owner": "pulse-candidate",
        "attempt_count": 1,
        "dirty_reason": "token_radar_changed",
        "source_watermark_ms": NOW_MS - 1_000,
    }
    claim.update(claim_overrides)
    row = _radar_row(factor_snapshot_json=_factor_snapshot(rank_score=80))
    repos = _FakeRepos(claims=[claim], exact_rows={("Asset", "asset-1", "1h", "all"): row})
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(repos, settings=_settings(trigger_error_retry_ms=7_000))

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["claimed"] == 1
    assert result["dirty_triggers_failed"] == 1
    assert result["dirty_triggers_done"] == 0
    assert result["targets_loaded"] == 0
    assert repos.token_radar.exact_calls == []
    assert repos.pulse_trigger_dirty_targets.done == []
    assert repos.pulse_trigger_dirty_targets.errors[0]["claims"] == [claim]
    assert error_token in repos.pulse_trigger_dirty_targets.errors[0]["error"]
    assert repos.pulse_trigger_dirty_targets.errors[0]["retry_ms"] == 7_000


def test_capacity_budget_reschedules_claim_without_job_enqueue_or_mark_done() -> None:
    claim = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "window": "1h",
        "scope": "all",
        "payload_hash": "pulse-trigger-1",
        "lease_owner": "pulse-candidate",
        "attempt_count": 1,
    }
    row = _radar_row(factor_snapshot_json=_factor_snapshot(rank_score=80))
    repos = _FakeRepos(claims=[claim], exact_rows={("Asset", "asset-1", "1h", "all"): row})
    repos.pulse_jobs.pending_global = 100
    worker = _worker(repos, settings=_settings(max_pending_jobs_global=100))

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["claimed"] == 1
    assert result["asset_enqueued"] == 0
    assert result["asset_suppressed_pending_global"] == 1
    assert repos.pulse_trigger_dirty_targets.done == []
    assert repos.pulse_trigger_dirty_targets.rescheduled[0]["claims"] == [claim]
    assert "reason" not in repos.pulse_trigger_dirty_targets.rescheduled[0]
    assert repos.pulse_jobs.jobs == []


def test_exit_trigger_without_current_row_records_target_scoped_suppression_and_marks_done() -> None:
    claim = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "window": "1h",
        "scope": "all",
        "payload_hash": "pulse-trigger-exit",
        "lease_owner": "pulse-candidate",
        "attempt_count": 1,
        "dirty_reason": "token_radar_exited",
    }
    repos = _FakeRepos(claims=[claim], exact_rows={})
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["claimed"] == 1
    assert result["missing_current_rows"] == 1
    assert result["target_exits_suppressed"] == 1
    assert repos.pulse_trigger_dirty_targets.done == [claim]
    assert repos.pulse_admission.admission_claims[0]["admission_reason"] == "token_radar_exited"
    assert repos.pulse_admission.admission_claims[0]["edge_events"] == ("token_radar_exited",)


def test_exit_trigger_requires_claim_payload_hash_before_suppression_admission() -> None:
    claim = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "window": "1h",
        "scope": "all",
        "lease_owner": "pulse-candidate",
        "attempt_count": 1,
        "dirty_reason": "token_radar_exited",
    }
    repos = _FakeRepos(claims=[claim], exact_rows={})
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["claimed"] == 1
    assert result["target_exits_suppressed"] == 0
    assert result["dirty_triggers_done"] == 0
    assert result["dirty_triggers_failed"] == 1
    assert repos.pulse_admission.admission_claims == []
    assert repos.pulse_trigger_dirty_targets.done == []
    assert repos.pulse_trigger_dirty_targets.errors[0]["claims"] == [claim]
    assert "pulse_trigger_dirty_claim_payload_hash_required" in repos.pulse_trigger_dirty_targets.errors[0]["error"]


def test_missing_pulse_job_state_contract_fails_dirty_trigger_instead_of_marking_done() -> None:
    claim = {
        "target_type": "Asset",
        "target_id": "asset-1",
        "window": "1h",
        "scope": "all",
        "payload_hash": "pulse-trigger-1",
        "lease_owner": "pulse-candidate",
        "attempt_count": 1,
        "dirty_reason": "token_radar_changed",
        "source_watermark_ms": NOW_MS - 1_000,
    }
    row = _radar_row(factor_snapshot_json=_factor_snapshot(rank_score=80))
    repos = _FakeRepos(claims=[claim], exact_rows={("Asset", "asset-1", "1h", "all"): row})
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["claimed"] == 1
    assert result["dirty_triggers_failed"] == 1
    assert result["dirty_triggers_done"] == 0
    assert repos.pulse_trigger_dirty_targets.done == []
    assert repos.pulse_trigger_dirty_targets.errors[0]["claims"] == [claim]
    assert "job_for_candidate" in repos.pulse_trigger_dirty_targets.errors[0]["error"]


class _RecordingWorker(PulseCandidateWorker):
    def __init__(self, repos: _FakeRepos) -> None:
        super().__init__(
            name="pulse_candidate",
            settings=_settings(),
            db=_FakeDB(repos),
            telemetry=object(),
            decision_client=_FakeClient(),
        )
        self.recorded_contexts: list[Any] = []

    def _enqueue_if_due(self, repos: Any, context: Any, *, now_ms: int) -> bool:
        self.recorded_contexts.append(context)
        repos.pulse_jobs.jobs.append({"candidate_id": context.candidate_id, "next_run_at_ms": now_ms})
        return True


def _worker(repos: _FakeRepos, *, settings: Any | None = None) -> PulseCandidateWorker:
    return PulseCandidateWorker(
        name="pulse_candidate",
        settings=settings or _settings(),
        db=_FakeDB(repos),
        telemetry=object(),
        decision_client=_FakeClient(),
    )


def _settings(**overrides: Any) -> SimpleNamespace:
    values = {
        "enabled": True,
        "interval_seconds": 60.0,
        "soft_timeout_seconds": 120.0,
        "hard_timeout_seconds": 180.0,
        "batch_size": 10,
        "max_agent_jobs_per_cycle": 2,
        "max_attempts": 3,
        "statement_timeout_seconds": 30.0,
        "advisory_lock_key": 2026051502,
        "windows": ("1h",),
        "scopes": ("all",),
        "max_enqueues_per_cycle": 10,
        "max_pending_jobs_global": 100,
        "max_pending_jobs_per_window_scope": 25,
        "job_running_timeout_ms": 300_000,
        "stale_running_terminalization_batch_size": 100,
        "stale_job_ttl_by_window_seconds": {},
        "trigger_lease_ms": 600_000,
        "trigger_capacity_retry_ms": 120_000,
        "trigger_error_retry_ms": 300_000,
        "target_edge_budget_per_hour": 3,
        "candidate_edge_budget_per_hour": 4,
        "failure_circuit_per_hour": 3,
        "failure_circuit_reasons": ("schema_failure", "provider_error"),
        "timeline_debounce_seconds": 600,
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


class _FakeDB:
    def __init__(self, repos: _FakeRepos) -> None:
        self.repos = repos

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        yield self.repos


class _FakeClient:
    pass


class _FakeRepos:
    def __init__(
        self,
        *,
        claims: list[dict[str, Any]] | None = None,
        exact_rows: dict[tuple[str, str, str, str], dict[str, Any]] | None = None,
    ) -> None:
        self.conn = _FakeConn()
        self.pulse_trigger_dirty_targets = _FakePulseTriggerDirtyTargets(claims or [])
        self.token_radar = _FakeTokenRadar(exact_rows or {})
        self.token_targets = _FakeTokenTargets()
        pulse_store = _FakePulseStore()
        self.pulse_jobs = pulse_store
        self.pulse_admission = pulse_store

    @contextmanager
    def transaction(self):
        with self.conn.transaction():
            yield


class _FakeConn:
    @contextmanager
    def transaction(self):
        yield


class _FakePulseTriggerDirtyTargets:
    def __init__(self, claims: list[dict[str, Any]]) -> None:
        self.claims = list(claims)
        self.claim_calls = 0
        self.done: list[dict[str, Any]] = []
        self.rescheduled: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []

    def claim_due(self, **_: Any) -> list[dict[str, Any]]:
        self.claim_calls += 1
        claims = self.claims
        self.claims = []
        return claims

    def mark_done(self, claims: list[dict[str, Any]], **_: Any) -> int:
        self.done.extend(claims)
        return len(claims)

    def reschedule(self, claims: list[dict[str, Any]], **kwargs: Any) -> int:
        self.rescheduled.append({"claims": list(claims), **kwargs})
        return len(claims)

    def mark_error(self, claims: list[dict[str, Any]], **kwargs: Any) -> int:
        self.errors.append({"claims": list(claims), **kwargs})
        return len(claims)

    def queue_depth(self, **_: Any) -> int:
        return len(self.claims)


class _FakeTokenRadar:
    def __init__(self, exact_rows: dict[tuple[str, str, str, str], dict[str, Any]]) -> None:
        self.exact_rows = dict(exact_rows)
        self.latest_calls = 0
        self.exact_calls: list[dict[str, Any]] = []

    def latest_current_rows(self, **_: Any) -> list[dict[str, Any]]:
        self.latest_calls += 1
        raise AssertionError("worker must not broad-scan token radar current rows")

    def current_row_for_target(self, **kwargs: Any) -> dict[str, Any] | None:
        self.exact_calls.append(dict(kwargs))
        key = (
            str(kwargs["target_type"]),
            str(kwargs["target_id"]),
            str(kwargs["window"]),
            str(kwargs["scope"]),
        )
        return self.exact_rows.get(key)


class _FakeTokenTargets:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def timeline_rows_for_event_ids(self, **_: Any) -> list[dict[str, Any]]:
        return list(self.rows)


class _FakePulseStore:
    def __init__(self) -> None:
        self.jobs: list[dict[str, Any]] = []
        self.pending_global = 0
        self.pending_by_window_scope: dict[tuple[str, str], int] = {}
        self.admission_claims: list[dict[str, Any]] = []

    def pending_agent_job_count(self) -> int:
        return self.pending_global

    def pending_agent_job_count_for_window_scope(self, *, window: str, scope: str) -> int:
        return self.pending_by_window_scope.get((window, scope), 0)

    def claim_pulse_admission(self, **kwargs: Any) -> SimpleNamespace:
        self.admission_claims.append(dict(kwargs))
        return SimpleNamespace(accepted=False, reason=kwargs.get("admission_reason"))
