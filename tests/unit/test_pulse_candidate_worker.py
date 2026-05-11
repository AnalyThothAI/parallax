from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.interfaces import PULSE_RECOMMENDATION_SCHEMA_VERSION
from gmgn_twitter_intel.domains.pulse_lab.providers import PulseRecommendationResult
from gmgn_twitter_intel.domains.pulse_lab.runtime.pulse_candidate_worker import (
    PulseCandidateWorker,
    _asset_candidate_id,
    _asset_trigger_metrics,
    _source_seed_factor_snapshot,
)
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_gate import PulseGateResult
from gmgn_twitter_intel.domains.pulse_lab.types.pulse_recommendation import PulseRecommendationPayload

NOW_MS = 1_800_000


def test_missing_factor_snapshot_is_not_enqueued() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=None)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), recommendation_client=FakeClient())

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 1
    assert result["asset_skipped"] == 1
    assert result["asset_enqueued"] == 0
    assert repos.pulse.jobs == []


def test_malformed_v2_factor_snapshot_is_not_enqueued() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(rank_score=82)
    snapshot["families"]["market_quality"] = {"facts": {"market_status": "fresh"}}
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), recommendation_client=FakeClient())

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
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), recommendation_client=FakeClient())

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
        recommendation_client=client,
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


def test_worker_persists_factor_snapshot_gate_and_recommendation_only() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(rank_score=82)
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), recommendation_client=FakeClient())

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 1
    upsert = repos.pulse.candidate_upserts[0]
    assert upsert["factor_snapshot_json"] == snapshot
    assert upsert["gate_json"]["pulse_status"] == "trade_candidate"
    assert upsert["agent_recommendation_json"]["schema_version"] == "pulse_recommendation_v1"
    assert "radar_score_json" not in upsert
    assert "market_context_json" not in upsert
    assert "thesis_json" not in upsert


def test_source_seed_without_target_is_gated_blocked_after_agent() -> None:
    repos = FakeRepos()
    repos.harness.social_events = [_source_event()]
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), recommendation_client=FakeClient())

    scan = worker.scan_triggers_once(now_ms=NOW_MS)
    run = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert scan["source_enqueued"] == 1
    assert run["processed"] == 1
    upsert = repos.pulse.candidate_upserts[0]
    assert upsert["candidate_type"] == "source_seed"
    assert upsert["pulse_status"] == "blocked_low_information"
    assert upsert["gate_json"]["blocked_reasons"] == ["identity_unresolved"]
    assert upsert["gate_json"]["max_recommendation"] == "ignore"
    assert "hard_gates" not in upsert["factor_snapshot_json"]
    assert upsert["factor_snapshot_json"]["gates"]["blocked_reasons"] == ["identity_unresolved"]


def test_worker_trigger_metrics_use_v2_families_and_gates() -> None:
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


def test_source_seed_factor_snapshot_is_v2_without_legacy_hard_gates() -> None:
    snapshot = _source_seed_factor_snapshot(_source_event())

    assert snapshot["schema_version"] == "token_factor_snapshot_v2_alpha_gated"
    assert set(snapshot) == {
        "schema_version",
        "subject",
        "market",
        "gates",
        "data_health",
        "families",
        "normalization",
        "composite",
        "provenance",
    }
    assert "hard_gates" not in snapshot
    assert snapshot["market"]["market_status"] == "missing"
    assert snapshot["gates"]["blocked_reasons"] == ["identity_unresolved"]
    assert set(snapshot["families"]) == {
        "attention_heat",
        "diffusion_quality",
        "semantic_quality",
        "timing_response",
    }


def test_legacy_previous_candidate_gate_json_does_not_bypass_cooldown() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(rank_score=50)
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
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
        "verdict": "token_watch",
        "trigger_signature": "old-trigger",
        "timeline_signature": "old-timeline",
        "updated_at_ms": NOW_MS - 1_000,
        "factor_snapshot_json": {
            "schema_version": "token_factor_snapshot_v1",
            "hard_gates": {"eligible_for_high_alert": True, "blocked_reasons": []},
            "composite": {"rank_score": 45},
        },
        "gate_json": {
            "watched_confirmation": False,
            "independent_author_count": 0,
            "hard_risks": [],
            "trade_candidate_eligible": False,
        },
    }
    worker = PulseCandidateWorker(repository_session=lambda: _session(repos), recommendation_client=FakeClient())

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 1
    assert result["asset_enqueued"] == 0
    assert result["asset_skipped"] == 1
    assert repos.pulse.jobs == []


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

    def latest_rows(self, **_: Any) -> list[dict[str, Any]]:
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
        self.agent_runs: list[dict[str, Any]] = []
        self.finished_runs: list[dict[str, Any]] = []
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

    def __init__(self, *, recommendation: str = "watch") -> None:
        self.recommendation = recommendation
        self.contexts: list[dict[str, Any]] = []

    def request_audit(self, *, context: dict[str, Any], run_id: str, job: dict[str, Any]) -> dict[str, Any]:
        self.contexts.append(context)
        return {
            "backend": "fake",
            "sdk_trace_id": f"trace-{run_id}",
            "workflow_name": "test-flow",
            "agent_name": "test-agent",
            "prompt_version": "prompt-v1",
            "schema_version": PULSE_RECOMMENDATION_SCHEMA_VERSION,
            "artifact_version_hash": self.artifact_version_hash,
            "trace_metadata": {"candidate_id": context["candidate_id"]},
            "input_hash": "input-hash",
        }

    async def write_recommendation(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
    ) -> PulseRecommendationResult:
        payload = PulseRecommendationPayload(
            schema_version=PULSE_RECOMMENDATION_SCHEMA_VERSION,
            recommendation=self.recommendation,
            summary_zh="因子快照显示信号值得继续观察。",
            primary_reasons=[
                {"factor_key": "diffusion_quality.independent_authors", "explanation_zh": "独立作者数上升。"}
            ],
            upgrade_conditions=[
                {
                    "factor_key": "attention_heat.watched_mentions",
                    "operator": ">=",
                    "value": 1,
                    "description_zh": "关注账号确认继续出现。",
                }
            ],
            invalidation_conditions=[
                {
                    "factor_key": "diffusion_quality.independent_authors",
                    "operator": "<",
                    "value": 3,
                    "description_zh": "独立作者数回落。",
                }
            ],
            residual_risks=[
                {"factor_key": "timing_response.price_change_status", "description_zh": "价格响应仍可能变化。"}
            ],
            evidence_event_ids=context.get("source_event_ids") or ["event-1"],
            confidence=0.7,
        )
        audit = self.request_audit(context=context, run_id=run_id, job=job)
        return PulseRecommendationResult(payload=payload, agent_run_audit={**audit, "output_hash": "output-hash"})


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
        "schema_version": "token_factor_snapshot_v2_alpha_gated",
        "subject": {
            "target_type": "Asset",
            "target_id": "asset-1",
            "target_market_type": "dex",
            "symbol": "TEST",
        },
        "market": {
            "market_status": "anchored",
            "price_change_status": "live_not_persisted",
            "provider": "okx",
            "anchor_price_usd": 0.42,
            "social_signal_start_ms": NOW_MS - 20_000,
            "event_price_readiness": {"status": "ready"},
        },
        "gates": {
            "eligible_for_high_alert": not blocked_reasons,
            "blocked_reasons": blocked_reasons or [],
            "risk_reasons": blocked_reasons or [],
            "max_decision": "watch" if blocked_reasons else "high_alert",
        },
        "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
        "families": {
            "attention_heat": {
                "raw_score": rank_score,
                "score": rank_score,
                "weight": 0.35,
                "data_health": "ready",
                "facts": {"mentions_1h": 8, "unique_authors": 7, "watched_mentions": 1},
                "factors": {
                    "watched_mentions": {
                        "family": "attention_heat",
                        "key": "watched_mentions",
                        "risk_flags": [],
                    }
                },
            },
            "diffusion_quality": {
                "raw_score": rank_score,
                "score": rank_score,
                "weight": 0.3,
                "data_health": "ready",
                "facts": {"independent_authors": 7},
                "factors": {
                    "independent_authors": {
                        "family": "diffusion_quality",
                        "key": "independent_authors",
                        "risk_flags": blocked_reasons or [],
                    }
                },
            },
            "semantic_quality": {
                "raw_score": rank_score,
                "score": rank_score,
                "weight": 0.25,
                "data_health": "ready",
                "facts": {"phase": "ignition"},
                "factors": {},
            },
            "timing_response": {
                "raw_score": rank_score,
                "score": rank_score,
                "weight": 0.1,
                "data_health": "ready",
                "facts": {"price_change_status": "ready"},
                "factors": {"price_change_status": {"family": "timing_response", "key": "price_change_status"}},
            },
        },
        "normalization": {"status": "pending_cross_section"},
        "composite": {
            "family_scores": {
                "attention_heat": rank_score,
                "diffusion_quality": rank_score,
                "semantic_quality": rank_score,
                "timing_response": rank_score,
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
