from __future__ import annotations

import asyncio
import hashlib
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.app.runtime import providers_wiring
from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.pulse_lab.providers import (
    DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT,
    PulseAgentRuntimeContract,
    PulseDecisionResult,
)
from parallax.domains.pulse_lab.runtime.pulse_candidate_worker import (
    PulseCandidateWorker,
    _asset_candidate_id,
    _asset_trigger_metrics,
    _terminalize_exhausted_stale_running_jobs,
)
from parallax.domains.pulse_lab.services import pulse_candidate_job_service as job_module
from parallax.domains.pulse_lab.services.claim_evidence_verifier import ClaimEvidenceVerificationResult
from parallax.domains.pulse_lab.services.evidence_completeness_gate import (
    EvidenceCompletenessGateResult,
)
from parallax.domains.pulse_lab.services.pulse_admission_policy import PulseAdmissionPolicy
from parallax.domains.pulse_lab.services.pulse_candidate_gate import PulseGateResult
from parallax.domains.pulse_lab.services.pulse_candidate_job_service import (
    _normalized_failure_reason,
    _run_outcome,
)
from parallax.domains.pulse_lab.types.agent_decision import (
    BullBearView,
    FinalDecision,
    PulseStageFailure,
    StageRunAudit,
    TradePlaybook,
)
from parallax.domains.pulse_lab.types.pulse_candidate_context import PulseCandidateContext
from parallax.platform.agent_execution import (
    AgentCapacityReservation,
    AgentExecutionError,
    AgentExecutionErrorClass,
)
from parallax.platform.config.settings import Settings

NOW_MS = 1_800_000


def test_asset_candidate_id_uses_stable_product_window_identity() -> None:
    expected = "pulse-" + hashlib.sha256(b"token_target|1h|all|Asset|asset-1").hexdigest()[:40]

    assert (
        _asset_candidate_id(
            candidate_type="token_target",
            window="1h",
            scope="all",
            target_type="Asset",
            target_id="asset-1",
        )
        == expected
    )


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
                recommended_decision="discard",
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
                recommended_decision="discard",
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


def test_watched_only_rank_44_is_not_enqueued() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [
        _radar_row(
            factor_snapshot_json=_factor_snapshot(
                rank_score=44,
                recommended_decision="discard",
                watched_mentions=1,
                unique_authors=1,
                independent_authors=1,
                effective_authors=1.0,
                top_author_share=1.0,
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


def test_abstain_decision_maps_to_evidence_insufficient_outcome() -> None:
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

    gate = EvidenceCompletenessGateResult(
        evidence_status="complete",
        hard_blocked=False,
        blocked_reason=None,
        max_decision_status="trade_candidate",
        required_ref_ids=("event:event-1",),
        missing_ref_types=(),
        data_gaps=(),
        public_allowed=True,
        display_status="display_trade_candidate",
    )

    assert _run_outcome(final_decision, evidence_gate=gate, claim_verification=_valid_claim_verification()) == (
        "abstain_insufficient_evidence"
    )


def test_invalid_ref_abstain_maps_to_unknown_evidence_outcome() -> None:
    final_decision = FinalDecision(
        route="meme",
        recommendation="abstain",
        confidence=0.0,
        abstain_reason="invalid_unknown_evidence_ref",
        summary_zh="模型输出引用了证据包外的 ref，本次不发布候选。",
        narrative_archetype="unclear",
        narrative_thesis_zh="模型输出包含证据包以外的引用，违反封闭证据合同；本次仅记录无效输出并等待下一轮有效证据综合。",
        bull_view=BullBearView(strength="absent"),
        bear_view=BullBearView(strength="absent"),
        playbook=TradePlaybook(
            has_playbook=False,
            watch_signals=[],
            exit_triggers=[],
            monitoring_horizon="1h",
        ),
        invalidation_conditions=[],
        residual_risks=["outside allowed_evidence_refs"],
        evidence_event_ids=[],
    )
    gate = EvidenceCompletenessGateResult(
        evidence_status="complete",
        hard_blocked=False,
        blocked_reason=None,
        max_decision_status="trade_candidate",
        required_ref_ids=("event:event-1",),
        missing_ref_types=(),
        data_gaps=(),
        public_allowed=True,
        display_status="display_trade_candidate",
    )

    assert _run_outcome(final_decision, evidence_gate=gate, claim_verification=_valid_claim_verification()) == (
        "invalid_unknown_evidence_ref"
    )


def _valid_claim_verification() -> ClaimEvidenceVerificationResult:
    return ClaimEvidenceVerificationResult(
        valid=True,
        unknown_ref_ids=(),
        unsupported_claims=(),
        missing_required_ref_claims=(),
        decision_status="valid",
        display_status_if_failed=None,
    )


def test_asset_context_uses_factor_snapshot_and_no_legacy_runtime_context() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(
        rank_score=82,
        subject={
            "target_type": "Asset",
            "target_id": "asset-1",
            "target_market_type": "dex",
            "symbol": "SNAP",
            "chain": "solana",
            "address": "So111",
        },
    )
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
    assert job["context_json"]["subject_key"] == "SNAP"
    assert job["context_json"]["symbol"] == "SNAP"
    assert job["context_json"]["factor_snapshot"] == snapshot
    assert job["context_json"]["factor_snapshot"]["subject"]["chain"] == "solana"
    assert job["context_json"]["factor_snapshot"]["subject"]["address"] == "So111"
    assert job["context_json"]["factor_snapshot"]["subject"]["target_market_type"] == "dex"
    assert job["context_json"]["edge_events"] == ["pulse_status_changed"]
    assert job["context_json"]["selected_posts"]
    assert "radar_score" not in job["context_json"]
    assert "market_context" not in job["context_json"]
    assert "timeline_context" not in job["context_json"]


def test_asset_context_without_source_events_does_not_hydrate_target_timeline() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [
        {
            **_radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82)),
            "source_event_ids_json": [],
        }
    ]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 1
    assert result["asset_enqueued"] == 0
    assert result["asset_skipped"] == 1
    assert repos.pulse_jobs.jobs == []
    assert repos.token_targets.event_id_calls == []
    assert repos.token_targets.legacy_timeline_calls == []
    assert repos.pulse_candidates.low_information_hides == []


def test_asset_context_requires_explicit_source_event_ids_json() -> None:
    repos = FakeRepos()
    row = _radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82))
    row.pop("source_event_ids_json", None)
    repos.token_radar.rows = [row]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 1
    assert result["asset_enqueued"] == 0
    assert result["asset_skipped"] == 1
    assert repos.pulse_jobs.jobs == []
    assert repos.token_targets.event_id_calls == []
    assert repos.token_targets.legacy_timeline_calls == []


def test_matched_asset_context_loads_only_source_event_rows_with_watched_filter() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [
        {
            **_radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82)),
            "source_event_ids_json": ["event-2", "event-1"],
        }
    ]
    repos.token_targets.rows = [
        _timeline_row("event-1", NOW_MS - 1_000),
        {**_timeline_row("event-2", NOW_MS - 500), "is_watched": True},
    ]
    worker = _worker(repos, settings=_settings(scopes=("matched",)))

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_enqueued"] == 1
    assert repos.token_targets.legacy_timeline_calls == []
    assert repos.token_targets.event_id_calls == [
        {
            "target_type": "Asset",
            "target_id": "asset-1",
            "event_ids": ["event-2", "event-1"],
            "watched_only": True,
            "limit": 200,
        }
    ]
    job = repos.pulse_jobs.jobs[0]
    assert job["context_json"]["source_event_ids"] == ["event-2", "event-1"]
    assert [post["event_id"] for post in job["context_json"]["selected_posts"]] == ["event-2"]
    assert job["context_json"]["post_clusters"]
    assert job["context_json"]["post_clusters"][0]["event_ids"] == ["event-2"]
    assert job["context_json"]["post_clusters"][0]["watched_author_present"] is True


def test_low_information_gate_does_not_hydrate_source_timeline() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(rank_score=82)
    snapshot["gates"]["eligible_for_high_alert"] = False
    snapshot["gates"]["blocked_reasons"] = []
    snapshot["gates"]["risk_reasons"] = []
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 1
    assert result["asset_enqueued"] == 0
    assert result["asset_skipped"] == 1
    assert repos.pulse_jobs.jobs == []
    assert repos.token_targets.event_id_calls == []
    assert repos.token_targets.legacy_timeline_calls == []


def test_low_information_gate_hides_existing_public_candidate_without_hydration() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(rank_score=82)
    snapshot["gates"]["eligible_for_high_alert"] = False
    snapshot["gates"]["blocked_reasons"] = []
    snapshot["gates"]["risk_reasons"] = []
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    candidate_id = _asset_candidate_id(
        candidate_type="token_target",
        window="1h",
        scope="all",
        target_type="Asset",
        target_id="asset-1",
    )
    repos.pulse_candidates.candidates[candidate_id] = {
        "candidate_id": candidate_id,
        "display_status": "display_trade_candidate",
        "pulse_status": "trade_candidate",
        "decision_status": "trade_candidate",
        "evidence_status": "complete",
        "updated_at_ms": NOW_MS - 60_000,
    }
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 1
    assert result["asset_enqueued"] == 0
    assert result["asset_skipped"] == 1
    assert repos.pulse_jobs.jobs == []
    assert repos.token_targets.event_id_calls == []
    assert repos.token_targets.legacy_timeline_calls == []
    assert repos.pulse_candidates.candidates[candidate_id]["display_status"] == "hidden_blocked_low_information"
    assert repos.pulse_candidates.candidates[candidate_id]["pulse_status"] == "blocked_low_information"
    assert repos.pulse_candidates.candidates[candidate_id]["source_event_ids_json"] == ["event-1"]
    assert repos.pulse_candidates.low_information_hides == [candidate_id]


def test_low_information_hide_requires_repository_contract() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(rank_score=82)
    snapshot["gates"]["eligible_for_high_alert"] = False
    snapshot["gates"]["blocked_reasons"] = []
    snapshot["gates"]["risk_reasons"] = []
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    repos.pulse_candidates = MissingLowInformationHidePulseCandidates()
    worker = _worker(repos, settings=_settings(trigger_error_retry_ms=12_345))

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["dirty_triggers_failed"] == 1
    assert result["dirty_triggers_done"] == 0
    assert repos.pulse_trigger_dirty_targets.done == []
    assert repos.pulse_trigger_dirty_targets.errors
    assert "hide_public_candidate_for_low_information" in repos.pulse_trigger_dirty_targets.errors[0]["error"]
    assert repos.pulse_trigger_dirty_targets.errors[0]["retry_ms"] == 12_345


def test_low_information_hide_advances_edge_state_so_public_recovery_reenqueues() -> None:
    repos = FakeRepos()
    public_snapshot = _factor_snapshot(rank_score=82)
    public_row = _radar_row(factor_snapshot_json=public_snapshot)
    repos.token_radar.rows = [public_row]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(repos)
    candidate_id = _asset_candidate_id(
        candidate_type="token_target",
        window="1h",
        scope="all",
        target_type="Asset",
        target_id="asset-1",
    )
    public_context = worker._asset_context(repos, public_row, window="1h", scope="all", now_ms=NOW_MS)
    assert public_context is not None
    public_state = _processed_edge_state(
        candidate_id=candidate_id,
        pulse_status="trade_candidate",
        score_band="high_conviction",
    )
    public_state["trigger_signature"] = public_context.trigger_signature
    public_state["timeline_signature"] = public_context.timeline_signature
    repos.pulse_admission.edge_states[candidate_id] = {
        "candidate_id": candidate_id,
        "last_processed_state_json": public_state,
        "latest_observed_state_json": public_state,
    }
    repos.pulse_candidates.candidates[candidate_id] = {
        "candidate_id": candidate_id,
        "display_status": "display_trade_candidate",
        "pulse_status": "trade_candidate",
        "decision_status": "trade_candidate",
        "evidence_status": "complete",
        "updated_at_ms": NOW_MS - 60_000,
    }
    repos.token_targets.event_id_calls.clear()
    repos.token_targets.legacy_timeline_calls.clear()

    low_info_snapshot = _factor_snapshot(rank_score=82)
    low_info_snapshot["gates"]["eligible_for_high_alert"] = False
    low_info_snapshot["gates"]["blocked_reasons"] = []
    low_info_snapshot["gates"]["risk_reasons"] = []
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=low_info_snapshot)]

    low_info_result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert low_info_result["asset_enqueued"] == 0
    assert repos.pulse_jobs.jobs == []
    assert repos.token_targets.event_id_calls == []
    edge_after_hide = repos.pulse_admission.edge_states[candidate_id]
    assert edge_after_hide["last_processed_state_json"]["pulse_status"] == "blocked_low_information"
    assert edge_after_hide["last_processed_state_json"]["timeline_signature"] == "low_information"
    assert edge_after_hide["last_suppressed_reason"] == "blocked_low_information"

    repos.token_radar.rows = [public_row]
    recovery_result = worker.scan_triggers_once(now_ms=NOW_MS + 1_000)

    assert recovery_result["asset_enqueued"] == 1
    assert len(repos.pulse_jobs.jobs) == 1
    assert repos.pulse_admission.admission_claims[-1]["admission_action"] == "enqueue_agent"
    assert "pulse_status_changed" in repos.pulse_admission.admission_claims[-1]["edge_events"]


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
    assert "radar_score" + "_json" not in upsert
    assert "market_context_json" not in upsert
    assert "thesis_json" not in upsert


def test_watched_only_high_score_is_hidden_by_source_quality() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(
        rank_score=82,
        watched_mentions=1,
        unique_authors=1,
        independent_authors=1,
        effective_authors=1.0,
        top_author_share=1.0,
    )
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(repos)

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 1
    upsert = repos.pulse_candidates.candidate_upserts[0]
    assert upsert["display_status"] == "hidden_source_quality"
    assert upsert["gate_json"]["source_quality"]["public_allowed"] is False
    assert "watched_only_source" in upsert["gate_json"]["source_quality"]["reasons"]
    assert repos.pulse_playbooks.playbook_upserts == []


def test_matched_single_author_risk_reject_is_hidden_by_source_quality() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(
        rank_score=82,
        blocked_reasons=["timing_chase_risk"],
        watched_mentions=0,
        unique_authors=1,
        independent_authors=1,
        effective_authors=1.0,
        top_author_share=1.0,
    )
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(repos, settings=_settings(scopes=("matched",)))

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 1
    upsert = repos.pulse_candidates.candidate_upserts[0]
    assert upsert["scope"] == "matched"
    assert upsert["decision_status"] == "risk_rejected_high_info"
    assert upsert["display_status"] == "hidden_source_quality"
    assert "single_author_source" in upsert["gate_json"]["source_quality"]["reasons"]


def test_multi_author_all_scope_remains_public() -> None:
    repos = FakeRepos()
    snapshot = _factor_snapshot(
        rank_score=82,
        watched_mentions=0,
        unique_authors=4,
        independent_authors=4,
        effective_authors=4.0,
        top_author_share=0.4,
    )
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=snapshot)]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(repos)

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 1
    upsert = repos.pulse_candidates.candidate_upserts[0]
    assert upsert["display_status"] == "display_token_watch"
    assert upsert["gate_json"]["source_quality"]["public_allowed"] is True


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
    worker = _worker(repos)
    context = worker._asset_context(repos, repos.token_radar.rows[0], window="1h", scope="all", now_ms=NOW_MS)
    assert context is not None
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
            "trigger_signature": context.trigger_signature,
            "timeline_signature": context.timeline_signature,
        },
    }

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 1
    assert result["asset_enqueued"] == 0
    assert result["asset_skipped"] == 1
    assert repos.pulse_jobs.jobs == []


def test_malformed_failed_existing_job_fails_dirty_trigger_instead_of_defaulting_attempts() -> None:
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
    repos.pulse_jobs.jobs.append(
        {
            "job_id": "job-malformed-failed",
            "candidate_id": candidate_id,
            "status": "failed",
            "attempt_count": 1,
            "window": "1h",
            "scope": "all",
        }
    )
    worker = _worker(repos)

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["dirty_triggers_failed"] == 1
    assert result["dirty_triggers_done"] == 0
    assert repos.pulse_trigger_dirty_targets.done == []
    assert repos.pulse_trigger_dirty_targets.errors
    assert "pulse_existing_failed_job_attempt_contract_required" in repos.pulse_trigger_dirty_targets.errors[0]["error"]


def test_worker_can_be_woken_by_token_radar_update_before_interval() -> None:
    repos = FakeRepos()
    wake_listener = FakeWakeListener()
    worker = _worker(repos, wake_waiter=wake_listener, settings=_settings(interval_seconds=60.0))

    async def scenario() -> None:
        task = asyncio.create_task(worker.run())
        try:
            await _wait_until(lambda: repos.pulse_trigger_dirty_targets.claim_calls >= 1)
            await _wait_until(lambda: repos.pulse_trigger_dirty_targets.claim_calls >= 2)
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


def test_edge_budget_uses_formal_candidate_limit_setting() -> None:
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
    worker = _worker(repos, settings=_settings(candidate_edge_budget_per_hour=4))

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_enqueued"] == 1
    assert repos.pulse_admission.admission_claims[-1]["candidate_limit"] == 4
    assert repos.pulse_jobs.jobs


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
    worker = _worker(repos)
    context = worker._asset_context(repos, repos.token_radar.rows[0], window="1h", scope="all", now_ms=NOW_MS)
    assert context is not None
    previous["trigger_signature"] = context.trigger_signature
    previous["timeline_signature"] = context.timeline_signature
    repos.pulse_admission.edge_states[candidate_id] = {
        "candidate_id": candidate_id,
        "last_processed_state_json": previous,
    }

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_enqueued"] == 0
    assert repos.pulse_jobs.jobs == []
    edge = repos.pulse_admission.edge_states[candidate_id]
    assert edge["last_suppressed_reason"] == "score_band_pending"
    assert edge["pending_score_band"] == "high_conviction"
    assert edge["pending_score_band_count"] == 1


def test_admission_policy_debounces_timeline_only_edge_inside_window() -> None:
    decision = PulseAdmissionPolicy().classify(
        previous_state={"candidate_id": "candidate-1", "score_band": "watch"},
        current_state={"candidate_id": "candidate-1", "score_band": "watch"},
        existing_job=None,
        edge_events=("timeline_evidence_changed",),
        pending_score_band=None,
        pending_score_band_count=0,
        recent_failure_count=0,
        failure_circuit_per_hour=3,
        last_processed_at_ms=NOW_MS - 120_000,
        now_ms=NOW_MS,
        timeline_debounce_seconds=600,
    )

    assert decision.action == "suppress"
    assert decision.reason == "timeline_debounce"


def test_admission_policy_escalation_and_hard_risk_bypass_timeline_debounce() -> None:
    escalation = PulseAdmissionPolicy().classify(
        previous_state={"candidate_id": "candidate-1", "pulse_status": "token_watch"},
        current_state={"candidate_id": "candidate-1", "pulse_status": "trade_candidate"},
        existing_job=None,
        edge_events=("timeline_evidence_changed", "pulse_status_changed"),
        pending_score_band=None,
        pending_score_band_count=0,
        recent_failure_count=0,
        failure_circuit_per_hour=3,
        last_processed_at_ms=NOW_MS - 120_000,
        now_ms=NOW_MS,
        timeline_debounce_seconds=600,
    )
    hard_risk = PulseAdmissionPolicy().classify(
        previous_state={"candidate_id": "candidate-1", "hard_risks": []},
        current_state={"candidate_id": "candidate-1", "hard_risks": ["timing_chase_risk"]},
        existing_job=None,
        edge_events=("timeline_evidence_changed", "hard_risk_added"),
        pending_score_band=None,
        pending_score_band_count=0,
        recent_failure_count=0,
        failure_circuit_per_hour=3,
        last_processed_at_ms=NOW_MS - 120_000,
        now_ms=NOW_MS,
        timeline_debounce_seconds=600,
    )

    assert escalation.action == "enqueue_agent"
    assert escalation.reason == "escalation"
    assert hard_risk.action == "enqueue_agent"
    assert hard_risk.reason == "hard_risk_added"


def test_admission_policy_score_band_confirmation_still_requires_second_observation() -> None:
    pending = PulseAdmissionPolicy().classify(
        previous_state={"candidate_id": "candidate-1", "score_band": "watch"},
        current_state={"candidate_id": "candidate-1", "score_band": "high_conviction"},
        existing_job=None,
        edge_events=("score_band_crossed",),
        pending_score_band=None,
        pending_score_band_count=0,
        recent_failure_count=0,
        failure_circuit_per_hour=3,
        last_processed_at_ms=NOW_MS - 120_000,
        now_ms=NOW_MS,
        timeline_debounce_seconds=600,
    )
    confirmed = PulseAdmissionPolicy().classify(
        previous_state={"candidate_id": "candidate-1", "score_band": "watch"},
        current_state={"candidate_id": "candidate-1", "score_band": "high_conviction"},
        existing_job=None,
        edge_events=("score_band_crossed",),
        pending_score_band="high_conviction",
        pending_score_band_count=1,
        recent_failure_count=0,
        failure_circuit_per_hour=3,
        last_processed_at_ms=NOW_MS - 120_000,
        now_ms=NOW_MS,
        timeline_debounce_seconds=600,
    )

    assert pending.action == "suppress"
    assert pending.reason == "score_band_pending"
    assert confirmed.action == "enqueue_agent"
    assert confirmed.reason == "score_band_confirmed"


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


def test_recent_schema_failure_circuit_uses_formal_threshold_and_reason_settings() -> None:
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
    worker = _worker(
        repos,
        settings=_settings(
            failure_circuit_per_hour=4,
            failure_circuit_reasons=("schema_validation_failed",),
        ),
    )

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_enqueued"] == 1
    assert repos.pulse_admission.recent_failure_calls[-1]["reasons"] == ("schema_validation_failed",)
    assert repos.pulse_jobs.jobs


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


def test_scan_global_pending_cap_bounds_enqueues_across_windows_and_scopes() -> None:
    repos = FakeRepos()
    repos.token_radar.rows_by_window_scope = {
        ("1h", "all"): [_radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82), target_id="asset-1h-all")],
        ("1h", "matched"): [
            _radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82), target_id="asset-1h-matched")
        ],
        ("4h", "all"): [_radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82), target_id="asset-4h-all")],
        ("4h", "matched"): [
            _radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82), target_id="asset-4h-matched")
        ],
    }
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(
        repos,
        settings=_settings(
            windows=("1h", "4h"),
            scopes=("all", "matched"),
            max_enqueues_per_cycle=10,
            max_pending_jobs_global=2,
            max_pending_jobs_per_window_scope=10,
            trigger_capacity_retry_ms=4_242,
        ),
    )

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 2
    assert result["asset_enqueued"] == 2
    assert result["asset_skipped"] == 2
    assert result["asset_suppressed_pending_global"] == 2
    assert result["dirty_triggers_rescheduled"] == 2
    assert {call["due_at_ms"] for call in repos.pulse_trigger_dirty_targets.rescheduled} == {NOW_MS + 4_242}
    assert len(repos.pulse_jobs.jobs) == 2


def test_scan_window_scope_pending_cap_suppresses_enqueue_without_admission_claim() -> None:
    repos = FakeRepos()
    repos.pulse_jobs.pending_job_counts_by_window_scope[("1h", "all")] = 1
    repos.token_radar.rows = [
        _radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82), target_id="asset-cap-a"),
        _radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82), target_id="asset-cap-b"),
    ]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(
        repos,
        settings=_settings(
            max_enqueues_per_cycle=10,
            max_pending_jobs_global=10,
            max_pending_jobs_per_window_scope=1,
        ),
    )

    result = worker.scan_triggers_once(now_ms=NOW_MS)

    assert result["asset_seen"] == 0
    assert result["asset_enqueued"] == 0
    assert result["asset_skipped"] == 2
    assert result["asset_suppressed_pending_window_scope"] == 2
    assert result["dirty_triggers_rescheduled"] == 2
    assert repos.pulse_admission.admission_claims == []
    assert repos.pulse_jobs.jobs == []


def test_runtime_terminalizes_exhausted_stale_running_jobs() -> None:
    repos = FakeRepos()
    repos.pulse_jobs.jobs.append(
        {
            "job_id": "job-stale-1h",
            "candidate_id": "candidate-stale-1h",
            "status": "running",
            "window": "1h",
            "scope": "all",
            "created_at_ms": NOW_MS - 3_601_000,
            "updated_at_ms": NOW_MS - 3_601_000,
            "attempt_count": 3,
            "max_attempts": 3,
        }
    )
    worker = _worker(repos, settings=_settings(stale_job_ttl_by_window_seconds={"1h": 3600}))

    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["claimed"] == 0
    assert result["terminalized_stale_running"] == 1
    assert repos.pulse_jobs.jobs[0]["status"] == "dead"
    assert repos.pulse_jobs.jobs[0]["last_error"] == "stale_running_timeout"


def test_normalized_failure_reason_maps_unknown_evidence() -> None:
    assert _normalized_failure_reason(ValueError("unknown evidence ids: event-x")) == "invalid_unknown_evidence_ref"
    assert _normalized_failure_reason(ValueError("bull_view.supporting_event_ids contains unknown event ids")) == (
        "invalid_unknown_evidence_ref"
    )


def test_normalized_failure_reason_maps_schema_validation() -> None:
    assert _normalized_failure_reason(ValueError("model_validate failed")) == "invalid_schema"


def test_worker_persists_failed_stage_audits_when_provider_raises_stage_failure() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82))]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]

    class FailingClient(FakeClient):
        async def run_decision_pipeline(self, **kwargs: Any) -> Any:
            self.run_calls += 1
            failed_audit = StageRunAudit(
                stage="pulse_decision",
                route=kwargs["route"],
                attempt_index=0,
                input_json={"context": kwargs["context"]},
                prompt_text="fake pulse decision prompt",
                response_json={"raw_output": "**Investigation Report:** prose only"},
                trace_metadata_json={"stage": "pulse_decision"},
                usage_json={"input_tokens": 11},
                latency_ms=42,
                started_at_ms=NOW_MS - 42,
                finished_at_ms=NOW_MS,
                status="failed",
                error="ValidationError: invalid JSON",
            )
            raise PulseStageFailure("model_validate failed", audits=(failed_audit,))

    worker = _worker(repos, client=FailingClient())

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 0
    assert result["failed"] == 1
    step = next(row for row in repos.pulse_runs.agent_run_steps if row["stage"] == "pulse_decision")
    assert step["status"] == "failed"
    assert step["error"] == "ValidationError: invalid JSON"
    assert step["response_json"] == {"raw_output": "**Investigation Report:** prose only"}
    assert step["started_at_ms"] == NOW_MS - 42
    assert step["finished_at_ms"] == NOW_MS
    assert step["usage_json"] == {"input_tokens": 11}
    failed_run = next(row for row in repos.pulse_runs.finished_runs if row["status"] == "failed")
    assert failed_run["trace_metadata_json_patch"] == {"failure_reason": "invalid_schema"}
    assert len(repos.pulse_jobs.failures) == 1
    assert repos.pulse_jobs.failures[0]["failure_reason"] == "invalid_schema"
    assert repos.pulse_agent_eval.eval_cases[0]["expected_json"] == {
        "status": "fail",
        "failure_reason": "invalid_schema",
    }
    assert repos.pulse_agent_eval.eval_results[0]["status"] == "pass"
    candidate_id = repos.pulse_jobs.jobs[0]["candidate_id"]
    assert repos.pulse_admission.edge_states[candidate_id]["last_processed_state_json"] == {}


def test_hard_blocked_evidence_gate_does_not_call_agent() -> None:
    repos = FakeRepos()
    repos.pulse_evidence_sources.market_facts = []
    context = _pulse_context(
        factor_snapshot=_factor_snapshot(rank_score=82, blocked_reasons=["duplicate_text_share_high"])
    )
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
    client = FakeClient()
    worker = _worker(repos, client=client)

    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 1
    assert client.run_calls == 0
    gate_step = next(row for row in repos.pulse_runs.agent_run_steps if row["stage"] == "evidence_completeness_gate")
    assert gate_step["status"] == "ok"
    assert gate_step["response_json"]["hard_blocked"] is True
    assert gate_step["response_json"]["blocked_reason"] == "blocked_market_contract"
    assert not any(row["stage"] == "pulse_decision" for row in repos.pulse_runs.agent_run_steps)


def test_hard_blocked_run_marks_edge_state_processed(monkeypatch) -> None:
    repos = FakeRepos()
    repos.pulse_evidence_sources.market_facts = []
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82))]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    now_values = iter([NOW_MS + 40])
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
            stage_names=("pulse_decision",),
            validators_enabled=("runtime_evidence_id_subset",),
            failure_taxonomy_version="pulse-failure-taxonomy-test",
        )

    worker = _worker(repos, client=ContractClient())

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 1
    manifest = repos.pulse_agent_eval.runtime_versions[0]["manifest_json"]
    assert "tool_names_by_stage" not in manifest["runtime"]
    assert "max_turns_per_stage" not in manifest["runtime"]
    assert "safety_net_enabled" not in manifest["runtime"]
    assert manifest["contracts"]["validators_enabled"] == ["runtime_evidence_id_subset"]
    assert manifest["failure_taxonomy"]["version"] == "pulse-failure-taxonomy-test"


def test_worker_runtime_manifest_uses_wired_provider_evidence_first_contract(monkeypatch) -> None:
    settings = Settings(
        ws_token="secret",
        llm={
            "api_key": "sk-test",
        },
        workers={
            "agent_runtime": {
                "defaults": {"model": "gpt-enrich"},
                "lanes": {
                    "pulse.decision": {"model": "gpt-pulse"},
                },
            },
        },
    )
    wired = providers_wiring.wire_providers(
        settings,
        start_collector=True,
        agent_execution_gateway=FakeAgentExecutionGateway(),
        db_pool=object(),
    )
    repos = FakeRepos()
    repos.pulse_evidence_sources.market_facts = []
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82))]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    assert wired.pulse_lab.decision_provider is not None
    worker = _worker(repos, client=wired.pulse_lab.decision_provider)

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 1
    manifest = repos.pulse_agent_eval.runtime_versions[0]["manifest_json"]
    assert manifest["runtime"]["stages"] == ["pulse_decision"]
    assert "tool_names_by_stage" not in manifest["runtime"]
    assert "safety_net_enabled" not in manifest["runtime"]


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


def test_pulse_worker_requires_formal_settings_db_and_client_contract() -> None:
    repos = FakeRepos()
    settings = _settings()

    with pytest.raises(RuntimeError, match="pulse_candidate_settings_required"):
        PulseCandidateWorker(
            name="pulse_candidate",
            settings=None,
            db=FakeDB(repos),
            telemetry=object(),
            decision_client=FakeClient(),
        )
    with pytest.raises(RuntimeError, match="pulse_candidate_db_required"):
        PulseCandidateWorker(
            name="pulse_candidate",
            settings=settings,
            db=None,
            telemetry=object(),
            decision_client=FakeClient(),
        )
    with pytest.raises(RuntimeError, match="pulse_candidate_decision_client_required"):
        PulseCandidateWorker(
            name="pulse_candidate",
            settings=settings,
            db=FakeDB(repos),
            telemetry=object(),
            decision_client=None,
        )


def test_pulse_worker_uses_formal_settings_fields_and_session_timeout() -> None:
    repos = FakeRepos()
    settings = _settings(
        windows=("4h",),
        scopes=("matched",),
        batch_size=3,
        max_agent_jobs_per_cycle=4,
        max_attempts=5,
        max_enqueues_per_cycle=6,
        max_pending_jobs_global=7,
        max_pending_jobs_per_window_scope=8,
        stale_running_terminalization_batch_size=16,
        trigger_lease_ms=9,
        trigger_capacity_retry_ms=10,
        trigger_error_retry_ms=11,
        target_edge_budget_per_hour=12,
        candidate_edge_budget_per_hour=13,
        failure_circuit_per_hour=14,
        timeline_debounce_seconds=15,
        failure_circuit_reasons=("schema_validation_failed",),
        statement_timeout_seconds=13.0,
        trigger_thresholds=SimpleNamespace(min_rank_score=64),
        gate_thresholds=SimpleNamespace(
            trade_candidate_min=73,
            token_watch_min=46,
            high_info_rejection_min=31,
            high_conviction_min=79,
        ),
    )

    worker = _worker(repos, settings=settings)

    assert worker.windows == ("4h",)
    assert worker.scopes == ("matched",)
    assert worker.batch_size == 3
    assert worker.max_agent_jobs_per_cycle == 4
    assert worker.max_attempts == 5
    assert worker.max_enqueues_per_cycle == 6
    assert worker.max_pending_jobs_global == 7
    assert worker.max_pending_jobs_per_window_scope == 8
    assert worker.stale_running_terminalization_batch_size == 16
    assert worker.trigger_lease_ms == 9
    assert worker.trigger_capacity_retry_ms == 10
    assert worker.trigger_error_retry_ms == 11
    assert worker.target_edge_budget_per_hour == 12
    assert worker.candidate_edge_budget_per_hour == 13
    assert worker.failure_circuit_per_hour == 14
    assert worker.timeline_debounce_seconds == 15
    assert worker.failure_circuit_reasons == ("schema_validation_failed",)
    assert worker.trigger_thresholds.min_rank_score == 64
    assert worker.gate_thresholds.trade_candidate_min == 73
    assert worker.gate_thresholds.token_watch_min == 46
    assert worker.gate_thresholds.high_info_rejection_min == 31
    assert worker.gate_thresholds.high_conviction_min == 79

    result = asyncio.run(worker.run_once(now_ms=NOW_MS))

    assert result.processed == 0
    assert repos.pulse_trigger_dirty_targets.claim_due_calls[0]["lease_ms"] == 9
    assert repos.db_worker_sessions[0] == {"name": "pulse_candidate", "statement_timeout_seconds": 13.0}


def test_terminalize_exhausted_stale_running_jobs_uses_formal_batch_limit() -> None:
    class PulseJobs:
        def __init__(self) -> None:
            self.calls: list[dict[str, int]] = []

        def terminalize_exhausted_stale_running_jobs(self, *, now_ms: int, stale_after_ms: int, limit: int) -> int:
            self.calls.append({"now_ms": now_ms, "stale_after_ms": stale_after_ms, "limit": limit})
            return 2

    pulse_jobs = PulseJobs()

    result = _terminalize_exhausted_stale_running_jobs(
        pulse_jobs,
        now_ms=NOW_MS,
        running_timeout_ms=300_000,
        limit=7,
    )

    assert result == 2
    assert pulse_jobs.calls == [{"now_ms": NOW_MS, "stale_after_ms": 300_000, "limit": 7}]


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


def test_pulse_worker_aclose_requires_decision_client_aclose_contract_without_close_fallback() -> None:
    repos = FakeRepos()
    client = CloseOnlyFakeClient()
    worker = _worker(repos, client=client)

    try:
        asyncio.run(worker.aclose())
    except RuntimeError as exc:
        assert "pulse_candidate_decision_client_aclose_required" in str(exc)
    else:
        raise AssertionError("expected Pulse candidate provider cleanup to require decision_client.aclose()")

    assert client.close_calls == 0


def test_process_due_jobs_does_not_claim_when_agent_capacity_denied() -> None:
    repos = FakeRepos()
    repos.pulse_jobs.jobs.append(
        {
            "job_id": "job-1",
            "status": "pending",
            "attempt_count": 0,
            "context_json": _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82)).__dict__,
        }
    )
    worker = _worker(repos, client=CapacityDeniedFakeClient())

    result = asyncio.run(worker.process_due_jobs_once_async(now_ms=NOW_MS))

    assert result["claimed"] == 0
    assert result["agent_backpressure_capacity_denied"] == 1
    assert repos.pulse_jobs.claim_due_job_calls == 0
    assert repos.pulse_jobs.jobs[0]["attempt_count"] == 0


def test_process_due_jobs_uses_agent_execution_budget_separate_from_scan_batch() -> None:
    repos = FakeRepos()
    context = _pulse_context(factor_snapshot=_factor_snapshot(rank_score=82))
    for index in range(3):
        repos.pulse_jobs.jobs.append(
            {
                "job_id": f"job-{index}",
                "candidate_id": f"candidate-{index}",
                "candidate_type": context.candidate_type,
                "subject_key": context.subject_key,
                "target_type": context.target_type,
                "target_id": context.target_id,
                "window": context.window,
                "scope": context.scope,
                "trigger_signature": f"trigger-{index}",
                "timeline_signature": f"timeline-{index}",
                "priority": context.priority,
                "status": "pending",
                "attempt_count": 0,
                "max_attempts": 3,
                "context_json": context.agent_context(),
            }
        )
    worker = _worker(repos, settings=_settings(batch_size=10, max_agent_jobs_per_cycle=2))

    result = asyncio.run(worker.process_due_jobs_once_async(now_ms=NOW_MS))

    assert result["claimed"] == 2
    assert result["processed"] == 2
    assert repos.pulse_jobs.claim_due_job_calls == 2
    assert sum(1 for job in repos.pulse_jobs.jobs if job["status"] == "pending") == 1


def test_pulse_pipeline_parent_reservation_is_passed_to_stage_execution() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82))]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    client = TrackingParentReservationClient()
    worker = _worker(repos, client=client)

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 1
    assert client.reserve_calls
    assert all(
        call
        == {
            "lane": "pulse.decision",
            "child_lanes": ("pulse.decision",),
            "scope": "parent",
        }
        for call in client.reserve_calls
    )
    assert client.parent_reservations == [client.reservation]


def test_no_start_agent_backpressure_reschedules_job_without_provider_failure() -> None:
    repos = FakeRepos()
    repos.token_radar.rows = [_radar_row(factor_snapshot_json=_factor_snapshot(rank_score=82))]
    repos.token_targets.rows = [_timeline_row("event-1", NOW_MS - 1_000)]
    worker = _worker(repos, client=NoStartBackpressureClient())

    worker.scan_triggers_once(now_ms=NOW_MS)
    result = worker.process_due_jobs_once(now_ms=NOW_MS)

    assert result["processed"] == 0
    assert result["failed"] == 0
    assert repos.pulse_jobs.failures == []
    assert repos.pulse_jobs.backpressure_releases == []
    assert len(repos.pulse_jobs.provider_cooldown_releases) == 1
    released = repos.pulse_jobs.provider_cooldown_releases[0]
    assert released["reason"] == "provider_cooldown:capacity_denied"
    job = repos.pulse_jobs.jobs[0]
    assert job["status"] == "pending"
    assert job["attempt_count"] == 0
    assert job["next_run_at_ms"] == NOW_MS + 120_000
    skipped_run = next(row for row in repos.pulse_runs.finished_runs if row["status"] == "skipped")
    assert skipped_run["outcome"] == "backpressure_capacity_denied"
    assert skipped_run["trace_metadata_json_patch"] == {
        "agent_backpressure": True,
        "agent_error_class": "capacity_denied",
    }


def _worker(
    repos: FakeRepos,
    *,
    client: Any | None = None,
    settings: Any | None = None,
    wake_waiter: Any | None = None,
) -> PulseCandidateWorker:
    resolved_settings = settings or _settings()
    repos.pulse_trigger_dirty_targets.configure(
        windows=tuple(getattr(resolved_settings, "windows", ("1h",)) or ("1h",)),
        scopes=tuple(getattr(resolved_settings, "scopes", ("all",)) or ("all",)),
    )
    return PulseCandidateWorker(
        name="pulse_candidate",
        settings=resolved_settings,
        db=FakeDB(repos),
        telemetry=object(),
        decision_client=client or FakeClient(),
        wake_waiter=wake_waiter,
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
        "wakes_on": ("token_radar_updated",),
        "windows": ("1h",),
        "scopes": ("all",),
        "max_enqueues_per_cycle": 10,
        "max_pending_jobs_global": 100,
        "max_pending_jobs_per_window_scope": 25,
        "job_running_timeout_ms": 300_000,
        "stale_running_terminalization_batch_size": 100,
        "trigger_lease_ms": 60_000,
        "trigger_capacity_retry_ms": 30_000,
        "trigger_error_retry_ms": 60_000,
        "target_edge_budget_per_hour": 3,
        "candidate_edge_budget_per_hour": 3,
        "failure_circuit_per_hour": 3,
        "failure_circuit_reasons": ("schema_validation_failed", "unknown_evidence_id"),
        "timeline_debounce_seconds": 600,
        "evidence_market_freshness_ms": 3_600_000,
        "stale_job_ttl_by_window_seconds": {},
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
        post_clusters=[],
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


class FakeAgentExecutionGateway:
    def model_for_lane(self, lane: str) -> str:
        if lane == "pulse.decision":
            return "gpt-pulse"
        if lane == "watchlist.handle_summary":
            return "gpt-summary"
        return "gpt-enrich"

    def try_reserve(self, lane: str, **_: Any) -> AgentCapacityReservation:
        return AgentCapacityReservation(lane=lane, acquired=True)

    async def execute(self, stage, **_: Any):
        allowed_refs = [
            str(ref.get("ref_id"))
            for ref in stage.input_payload.get("allowed_evidence_refs", [])
            if isinstance(ref, dict) and ref.get("ref_id")
        ]
        supporting_refs = tuple(ref for ref in allowed_refs if ref.startswith("event:"))[:1] or tuple(allowed_refs[:1])
        risk_refs = tuple(ref for ref in allowed_refs if ref.startswith("market:"))[:1]
        evidence_packet = stage.input_payload.get("evidence_packet") or {}
        evidence_ids = evidence_packet.get("source_event_ids") or ["event-1"]
        final_output = FinalDecision(
            route=stage.input_payload.get("route") or "meme",
            recommendation="watchlist",
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
            supporting_evidence_refs=supporting_refs,
            risk_evidence_refs=risk_refs,
        )
        return SimpleNamespace(
            final_output=final_output,
            audit=SimpleNamespace(
                trace_metadata={"stage": stage.stage},
                input_hash=stage.input_hash,
                output_hash=f"sha256:{stage.stage}",
                safety_net={"safety_net_used": False, "safety_net_retries": 0},
                usage={},
                latency_ms=1,
                parse_mode="strict",
                error_class=None,
            ),
        )


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
        self.pulse_trigger_dirty_targets = FakePulseTriggerDirtyTargets(self.token_radar)
        self.token_targets = FakeTokenTargets()
        pulse_state = FakePulseStore()
        self.pulse_jobs = pulse_state
        self.pulse_admission = pulse_state
        self.pulse_candidates = pulse_state
        self.pulse_runs = pulse_state
        self.pulse_agent_eval = pulse_state
        self.pulse_playbooks = pulse_state
        self.pulse_evidence = pulse_state
        self.pulse_evidence_sources = pulse_state
        self.db_worker_sessions: list[dict[str, Any]] = []

    @contextmanager
    def transaction(self):
        with self.conn.transaction():
            yield


class FakeConn:
    @contextmanager
    def transaction(self):
        yield

    def execute(self, *_: Any, **__: Any) -> Any:
        return FakeCursor(
            {
                "latest_packet_created_at_ms": NOW_MS,
                "latest_agent_run_finished_at_ms": NOW_MS,
                "latest_public_candidate_updated_at_ms": NOW_MS,
                "due_jobs": 0,
                "claimed_jobs": 0,
                "failed_jobs_4h": 0,
                "dead_jobs": 0,
                "agent_runs_4h": 0,
                "agent_failed_4h": 0,
                "unknown_ref_failures_4h": 0,
                "unsupported_claim_failures_4h": 0,
                "hidden_abstain_4h": 0,
                "hidden_hold_publish_4h": 0,
                "hidden_insufficient_evidence_4h": 0,
                "public_candidates_4h": 0,
            }
        )


class FakeCursor:
    def __init__(self, row: dict[str, Any] | None = None, rows: list[dict[str, Any]] | None = None) -> None:
        self.row = row
        self.rows = rows or ([] if row is None else [row])

    def fetchone(self) -> dict[str, Any] | None:
        return self.row

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self.rows)


class FakeTokenRadar:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.rows_by_window_scope: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.latest_calls = 0

    def latest_current_rows(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.latest_calls += 1
        key = (kwargs.get("window"), kwargs.get("scope"))
        if key in self.rows_by_window_scope:
            return list(self.rows_by_window_scope[key])
        return list(self.rows)

    def current_row_for_target(self, **kwargs: Any) -> dict[str, Any] | None:
        key = (kwargs.get("window"), kwargs.get("scope"))
        rows = self.rows_by_window_scope.get(key, self.rows)
        target_type = kwargs.get("target_type")
        target_id = kwargs.get("target_id")
        for row in rows:
            if row.get("target_type") == target_type and row.get("target_id") == target_id:
                return dict(row)
        return None


class FakePulseTriggerDirtyTargets:
    def __init__(self, token_radar: FakeTokenRadar) -> None:
        self.token_radar = token_radar
        self.windows = ("1h",)
        self.scopes = ("all",)
        self.claim_calls = 0
        self.claim_due_calls: list[dict[str, Any]] = []
        self.done: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.rescheduled: list[dict[str, Any]] = []

    def configure(self, *, windows: tuple[str, ...], scopes: tuple[str, ...]) -> None:
        self.windows = windows
        self.scopes = scopes

    def queue_depth(self, **_: Any) -> int:
        return len(self._claim_candidates())

    def claim_due(self, *, limit: int, **kwargs: Any) -> list[dict[str, Any]]:
        self.claim_calls += 1
        self.claim_due_calls.append({"limit": limit, **kwargs})
        return self._claim_candidates()[: max(0, int(limit))]

    def mark_done(self, claims: list[dict[str, Any]], **_: Any) -> int:
        self.done.extend(claims)
        return len(claims)

    def mark_error(self, claims: list[dict[str, Any]], **kwargs: Any) -> int:
        self.errors.append({"claims": list(claims), **kwargs})
        return len(claims)

    def reschedule(self, claims: list[dict[str, Any]], **kwargs: Any) -> int:
        self.rescheduled.append({"claims": list(claims), **kwargs})
        return len(claims)

    def _claim_candidates(self) -> list[dict[str, Any]]:
        claims: list[dict[str, Any]] = []
        if self.token_radar.rows_by_window_scope:
            row_sets = self.token_radar.rows_by_window_scope.items()
        else:
            row_sets = [((window, scope), self.token_radar.rows) for window in self.windows for scope in self.scopes]
        for (window, scope), rows in row_sets:
            for row in rows:
                target_type = str(row.get("target_type") or "")
                target_id = str(row.get("target_id") or "")
                if not target_type or not target_id:
                    continue
                claims.append(
                    {
                        "target_type": target_type,
                        "target_id": target_id,
                        "window": str(window),
                        "scope": str(scope),
                        "payload_hash": f"pulse-trigger:{window}:{scope}:{target_type}:{target_id}",
                        "dirty_reason": "token_radar_changed",
                        "source_watermark_ms": int(
                            row.get("source_max_received_at_ms") or row.get("computed_at_ms") or NOW_MS
                        ),
                        "lease_owner": "pulse_candidate",
                        "attempt_count": 1,
                    }
                )
        return claims


class FakeTokenTargets:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.legacy_timeline_calls: list[dict[str, Any]] = []
        self.event_id_calls: list[dict[str, Any]] = []

    def timeline_rows(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.legacy_timeline_calls.append(dict(kwargs))
        return list(self.rows)

    def timeline_rows_for_event_ids(self, **kwargs: Any) -> list[dict[str, Any]]:
        call = {
            **dict(kwargs),
            "event_ids": list(kwargs.get("event_ids") or []),
        }
        self.event_id_calls.append(call)
        event_ids = {str(event_id) for event_id in call["event_ids"]}
        rows = [row for row in self.rows if str(row.get("event_id") or "") in event_ids]
        if call.get("watched_only"):
            rows = [row for row in rows if row.get("is_watched")]
        return rows[: int(call.get("limit") or len(rows))]


class MissingLowInformationHidePulseCandidates:
    pass


class FakePulseStore:
    def __init__(self) -> None:
        self.jobs: list[dict[str, Any]] = []
        self.candidates: dict[str, dict[str, Any]] = {}
        self.edge_states: dict[str, dict[str, Any]] = {}
        self.budget_claims: dict[tuple[str, int], int] = {}
        self.target_budget_claims: dict[tuple[str, str, int], int] = {}
        self.recent_failure_count = 0
        self.recent_failure_calls: list[dict[str, Any]] = []
        self.agent_runs: list[dict[str, Any]] = []
        self.agent_run_steps: list[dict[str, Any]] = []
        self.finished_runs: list[dict[str, Any]] = []
        self.runtime_versions: list[dict[str, Any]] = []
        self.eval_cases: list[dict[str, Any]] = []
        self.eval_results: list[dict[str, Any]] = []
        self.candidate_upserts: list[dict[str, Any]] = []
        self.low_information_hides: list[str] = []
        self.playbook_upserts: list[dict[str, Any]] = []
        self.packets: list[Any] = []
        self.successes: list[str] = []
        self.failures: list[dict[str, Any]] = []
        self.backpressure_releases: list[dict[str, Any]] = []
        self.provider_cooldown_releases: list[dict[str, Any]] = []
        self.timeout_cancellations: list[dict[str, Any]] = []
        self.claim_due_job_calls = 0
        self.admission_claims: list[dict[str, Any]] = []
        self.pending_job_counts_by_window_scope: dict[tuple[str, str], int] = {}
        self.market_facts: list[dict[str, Any]] = [
            {
                "ref_id": "market:pf-test",
                "route": "meme",
                "target_market_type": "dex",
                "price_usd": Decimal("0.42"),
                "liquidity_usd": Decimal("250000"),
                "market_cap_usd": Decimal("1000000"),
                "volume_24h_usd": Decimal("12000"),
                "pricefeed_id": "pf-test",
                "instrument_ref": "pf-test",
                "source_provider": "okx",
                "observed_at_ms": NOW_MS - 1_000,
                "freshness_status": "fresh",
                "source_table": "market_ticks",
            }
        ]
        self.identity_facts: list[dict[str, Any]] = [
            {
                "source_id": "identity:asset-1",
                "target_id": "asset-1",
                "symbol": "TEST",
                "summary_zh": "TEST 目标身份已解析",
                "quality": "high",
                "observed_at_ms": NOW_MS - 1_000,
                "source_table": "asset_identity_current",
            }
        ]
        self.discussion_digest: dict[str, Any] | None = None

    def candidate_by_id(self, candidate_id: str) -> dict[str, Any] | None:
        return self.candidates.get(candidate_id)

    def hide_public_candidate_for_low_information(self, **kwargs: Any) -> dict[str, Any] | None:
        candidate_id = str(kwargs.get("candidate_id") or "")
        row = self.candidates.get(candidate_id)
        if row is None or row.get("display_status") not in {
            "display_trade_candidate",
            "display_token_watch",
            "display_risk_rejected_high_info",
        }:
            return None
        row.update(
            {
                "display_status": "hidden_blocked_low_information",
                "pulse_status": "blocked_low_information",
                "verdict": "blocked_low_information",
                "score_band": "blocked",
                "decision_status": "invalid",
                "evidence_status": "insufficient",
                "factor_snapshot_json": kwargs.get("factor_snapshot_json") or {},
                "gate_json": kwargs.get("gate_json") or {},
                "source_event_ids_json": list(kwargs.get("source_event_ids_json") or []),
                "updated_at_ms": kwargs.get("updated_at_ms"),
            }
        )
        self.low_information_hides.append(candidate_id)
        return dict(row)

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
            if kwargs.get("admission_reason") == "blocked_low_information":
                row["last_processed_state_json"] = edge_state
                row["last_processed_at_ms"] = now_ms
                row["pending_score_band"] = None
                row["pending_score_band_count"] = 0
            elif kwargs.get("admission_reason") == "score_band_pending":
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

    def recent_target_failure_count(self, **kwargs: Any) -> int:
        self.recent_failure_calls.append(dict(kwargs))
        return self.recent_failure_count

    def pending_agent_job_count(self) -> int:
        return sum(1 for job in self.jobs if job.get("status") in {"pending", "failed", "running"})

    def pending_agent_job_count_for_window_scope(self, *, window: str, scope: str) -> int:
        seeded = self.pending_job_counts_by_window_scope.get((window, scope), 0)
        active = sum(
            1
            for job in self.jobs
            if job.get("status") in {"pending", "failed", "running"}
            and job.get("window") == window
            and job.get("scope") == scope
        )
        return seeded + active

    def terminalize_stale_jobs_by_window(self, *, now_ms: int, ttl_by_window_seconds: dict[str, int]) -> int:
        count = 0
        for job in self.jobs:
            ttl_seconds = ttl_by_window_seconds.get(str(job.get("window") or ""))
            if ttl_seconds is None or job.get("status") not in {"pending", "failed", "running"}:
                continue
            created_at_ms = int(job.get("created_at_ms") or job.get("updated_at_ms") or now_ms)
            if created_at_ms >= now_ms - int(ttl_seconds) * 1000:
                continue
            job["status"] = "dead"
            job["last_error"] = "stale_window_ttl"
            job["updated_at_ms"] = now_ms
            count += 1
        return count

    def terminalize_exhausted_stale_running_jobs(
        self,
        *,
        now_ms: int,
        stale_after_ms: int,
        limit: int,
        **_: Any,
    ) -> int:
        count = 0
        stale_before_ms = int(now_ms) - int(stale_after_ms)
        for job in sorted(
            self.jobs, key=lambda row: (int(row.get("updated_at_ms") or 0), str(row.get("job_id") or ""))
        ):
            if count >= max(1, int(limit)):
                break
            if job.get("status") != "running":
                continue
            if int(job.get("attempt_count") or 0) < int(job.get("max_attempts") or 0):
                continue
            if int(job.get("updated_at_ms") or 0) >= stale_before_ms:
                continue
            job["status"] = "dead"
            job["last_error"] = "stale_running_timeout"
            job["updated_at_ms"] = now_ms
            count += 1
        return count

    def enqueue_job(self, **kwargs: Any) -> dict[str, Any]:
        job = {
            **kwargs,
            "job_id": f"job-{len(self.jobs) + 1}",
            "status": "pending",
            "attempt_count": 0,
            "max_attempts": kwargs["max_attempts"],
            "created_at_ms": kwargs.get("now_ms"),
            "updated_at_ms": kwargs.get("now_ms"),
        }
        self.jobs.append(job)
        return job

    def claim_due_job(self, now_ms: int | None = None) -> dict[str, Any] | None:
        self.claim_due_job_calls += 1
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

    def upsert_packet(self, packet: Any, *, commit: bool = True) -> None:
        self.packets.append(packet)

    def list_source_events(self, event_ids: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
        return [
            {
                "event_id": event_id,
                "observed_at_ms": NOW_MS - 1_000,
                "created_at_ms": NOW_MS - 1_000,
                "summary_zh": f"{event_id} 社交事件正在扩散",
                "source_table": "events",
                "quality": "high",
            }
            for event_id in event_ids
        ]

    def list_enriched_events(self, event_ids: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
        return []

    def list_market_facts(self, context: Any, *, max_age_ms: int, now_ms: int) -> list[dict[str, Any]]:
        return list(self.market_facts)

    def list_identity_facts(self, context: Any) -> list[dict[str, Any]]:
        return list(self.identity_facts)

    def get_current_discussion_digest(
        self,
        *,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        schema_version: str,
    ) -> dict[str, Any] | None:
        return self.discussion_digest

    def mark_job_succeeded(self, job_id: str, **_: Any) -> dict[str, Any]:
        for job in self.jobs:
            if job["job_id"] == job_id:
                job["status"] = "done"
        self.successes.append(job_id)
        return {"job_id": job_id, "status": "done"}

    def mark_job_failed(self, job: dict[str, Any], error: str, **kwargs: Any) -> dict[str, Any]:
        self.failures.append({"job": job, "error": error, "failure_reason": kwargs.get("failure_reason")})
        return {"job_id": job["job_id"], "status": "failed"}

    def mark_job_cancelled_by_worker_timeout(
        self,
        job: dict[str, Any],
        *,
        now_ms: int,
        execution_started: bool,
        **_: Any,
    ) -> dict[str, Any] | None:
        self.timeout_cancellations.append(
            {"job_id": job["job_id"], "execution_started": execution_started, "now_ms": now_ms}
        )
        for stored in self.jobs:
            if stored["job_id"] != job["job_id"] or stored.get("status") != "running":
                continue
            if int(stored.get("attempt_count") or 0) != int(job.get("attempt_count") or 0):
                continue
            if int(stored.get("updated_at_ms") or 0) != int(job.get("updated_at_ms") or 0):
                continue
            if execution_started:
                attempts = int(stored.get("attempt_count") or 0)
                max_attempts = int(stored.get("max_attempts") or 3)
                stored["status"] = "dead" if attempts >= max_attempts else "failed"
                stored["next_run_at_ms"] = now_ms if stored["status"] == "dead" else now_ms + 5_000 * max(1, attempts)
                stored["last_error"] = "worker_timeout_after_execution"
            else:
                stored["status"] = "pending"
                stored["attempt_count"] = max(0, int(stored.get("attempt_count") or 0) - 1)
                stored["next_run_at_ms"] = now_ms + 5_000
                stored["last_error"] = "worker_timeout_before_execution"
            stored["updated_at_ms"] = now_ms
            return dict(stored)
        return None

    def release_running_job_for_backpressure(
        self,
        job: dict[str, Any],
        *,
        reason: str,
        now_ms: int,
        delay_ms: int = 30_000,
        **_: Any,
    ) -> dict[str, Any]:
        self.backpressure_releases.append(
            {
                "job": job,
                "reason": reason,
                "now_ms": now_ms,
                "delay_ms": delay_ms,
            }
        )
        for stored in self.jobs:
            if stored["job_id"] == job["job_id"] and stored.get("status") == "running":
                stored["status"] = "pending"
                stored["attempt_count"] = max(0, int(stored.get("attempt_count") or 0) - 1)
                stored["next_run_at_ms"] = int(now_ms) + int(delay_ms)
                stored["last_error"] = reason
                stored["updated_at_ms"] = now_ms
                return dict(stored)
        return {"job_id": job["job_id"], "status": "pending"}

    def release_running_job_for_provider_cooldown(
        self,
        job: dict[str, Any],
        *,
        reason: str,
        now_ms: int,
        cooldown_until_ms: int,
        decrement_attempt: bool = True,
        **_: Any,
    ) -> dict[str, Any]:
        self.provider_cooldown_releases.append(
            {
                "job": job,
                "reason": reason,
                "now_ms": now_ms,
                "cooldown_until_ms": cooldown_until_ms,
                "decrement_attempt": decrement_attempt,
            }
        )
        for stored in self.jobs:
            if stored["job_id"] == job["job_id"] and stored.get("status") == "running":
                stored["status"] = "pending"
                if decrement_attempt:
                    stored["attempt_count"] = max(0, int(stored.get("attempt_count") or 0) - 1)
                stored["next_run_at_ms"] = int(cooldown_until_ms)
                stored["last_error"] = reason
                stored["updated_at_ms"] = now_ms
                return dict(stored)
        return {"job_id": job["job_id"], "status": "pending"}


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

    def try_reserve_execution(self, lane: str, **_: Any) -> AgentCapacityReservation:
        return AgentCapacityReservation(lane=lane, acquired=True)

    def model_for_lane(self, lane: str) -> str:
        if lane == "pulse.decision":
            return "fake-pulse"
        return ""

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
        runtime_hash = job_module.pulse_runtime_hash(runtime_manifest)
        return {
            "backend": "fake",
            "execution_trace_id": f"trace-{run_id}",
            "workflow_name": "test-flow",
            "agent_name": "test-agent",
            "prompt_version": "prompt-v1",
            "schema_version": "pulse_decision_v1",
            "artifact_version_hash": self.artifact_version_hash,
            "runtime_version": runtime_manifest["runtime_version"],
            "runtime_hash": runtime_hash,
            "trace_metadata": {
                "candidate_id": context["candidate_id"],
                "route": route,
                "completeness": completeness,
                "runtime_version": runtime_manifest["runtime_version"],
                "runtime_hash": runtime_hash,
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
        parent_reservation: AgentCapacityReservation | None = None,
    ) -> PulseDecisionResult:
        self.run_calls += 1
        allowed_refs = [
            str(ref.get("ref_id"))
            for ref in context.get("evidence_packet", {}).get("allowed_evidence_refs", [])
            if isinstance(ref, dict) and ref.get("ref_id")
        ]
        supporting_refs = tuple(ref for ref in allowed_refs if ref.startswith("event:"))[:1] or tuple(allowed_refs[:1])
        risk_refs = tuple(ref for ref in allowed_refs if ref.startswith("market:"))[:1]
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
            supporting_evidence_refs=supporting_refs,
            risk_evidence_refs=risk_refs,
        )
        if _decision_allowed_from_context(context) is False:
            final_decision = FinalDecision(
                route=route,  # type: ignore[arg-type]
                recommendation="abstain",
                confidence=0.0,
                abstain_reason="cost_guard_decision_skipped",
                summary_zh="成本门控跳过单阶段决策，本次不发布候选。",
                narrative_archetype="unclear",
                narrative_thesis_zh=(
                    "确定性成本门控判定该样本不需要运行 Pulse 决策；系统保留审计并等待下一轮公开资格确认。"
                ),
                bull_view=BullBearView(strength="absent"),
                bear_view=BullBearView(strength="absent"),
                playbook=TradePlaybook(
                    has_playbook=False,
                    watch_signals=[],
                    exit_triggers=[],
                    monitoring_horizon="1h",
                ),
                invalidation_conditions=[],
                residual_risks=["cost_guard_decision_skipped"],
                evidence_event_ids=list(evidence_ids),
                supporting_evidence_refs=tuple(),
                risk_evidence_refs=tuple(),
                data_gap_refs=tuple(),
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
                stage_audits=(),
            )
        stage_audit = StageRunAudit(
            stage="pulse_decision",
            route=route,  # type: ignore[arg-type]
            attempt_index=0,
            input_json={
                "context": context,
                "completeness": completeness,
            },
            prompt_text="fake pulse decision prompt",
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
            stage_audits=(stage_audit,),
        )


class CapacityDeniedFakeClient(FakeClient):
    def try_reserve_execution(self, lane: str, **_: Any) -> AgentCapacityReservation:
        return AgentCapacityReservation(
            lane=lane,
            acquired=False,
            reason=AgentExecutionErrorClass.CAPACITY_DENIED,
        )


def _decision_allowed_from_context(context: dict[str, Any]) -> bool:
    cost_guard = context.get("cost_guard")
    if not isinstance(cost_guard, dict):
        return True
    decision = cost_guard.get("decision")
    if not isinstance(decision, dict):
        return True
    return bool(decision.get("decision_allowed", True))


class TrackingParentReservationClient(FakeClient):
    def __init__(self) -> None:
        super().__init__()
        self.reservation = AgentCapacityReservation(lane="pulse.decision", acquired=True)
        self.reserve_calls: list[dict[str, Any]] = []
        self.parent_reservations: list[AgentCapacityReservation | None] = []

    def try_reserve_execution(
        self,
        lane: str,
        *,
        child_lanes: tuple[str, ...] = (),
        scope: str = "execution",
    ) -> AgentCapacityReservation:
        self.reserve_calls.append({"lane": lane, "child_lanes": child_lanes, "scope": scope})
        return self.reservation

    async def run_decision_pipeline(self, **kwargs: Any) -> PulseDecisionResult:
        self.parent_reservations.append(kwargs.get("parent_reservation"))
        return await super().run_decision_pipeline(**kwargs)


class NoStartBackpressureClient(FakeClient):
    async def run_decision_pipeline(self, **kwargs: Any) -> PulseDecisionResult:
        self.run_calls += 1
        raise AgentExecutionError(
            AgentExecutionErrorClass.CAPACITY_DENIED,
            "agent lane unavailable: pulse.decision",
            audit=None,
            execution_started=False,
        )


class ClosingFakeClient(FakeClient):
    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class CloseOnlyFakeClient(FakeClient):
    def __init__(self) -> None:
        super().__init__()
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


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


def _radar_row(*, factor_snapshot_json: dict[str, Any] | None, target_id: str = "asset-1") -> dict[str, Any]:
    if factor_snapshot_json is not None:
        factor_snapshot_json = {
            **factor_snapshot_json,
            "subject": {
                **dict(factor_snapshot_json.get("subject") or {}),
                "target_id": target_id,
            },
        }
    return {
        "row_id": "row-1",
        "window": "1h",
        "scope": "all",
        "computed_at_ms": NOW_MS - 1_000,
        "event_id": "event-1",
        "target_type": "Asset",
        "target_id": target_id,
        "factor_snapshot_json": factor_snapshot_json,
        "source_event_ids_json": ["event-1"],
    }


def _factor_snapshot(
    *,
    rank_score: int,
    subject: dict[str, Any] | None = None,
    blocked_reasons: list[str] | None = None,
    recommended_decision: str | None = None,
    watched_mentions: int = 1,
    unique_authors: int = 7,
    independent_authors: int = 7,
    effective_authors: float | None = None,
    source_weighted_effective_authors: float | None = None,
    top_author_share: float = 0.2,
    duplicate_text_share: float = 0.0,
) -> dict[str, Any]:
    decision = recommended_decision or ("high_alert" if rank_score >= 72 else "watch")
    return {
        "schema_version": "token_factor_snapshot_v3_social_attention",
        "subject": subject
        or {
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
                "facts": {
                    "mentions_1h": 8,
                    "unique_authors": unique_authors,
                    "watched_mentions": watched_mentions,
                },
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
                "facts": {
                    "independent_authors": independent_authors,
                    "effective_authors": effective_authors if effective_authors is not None else independent_authors,
                    "source_weighted_effective_authors": (
                        source_weighted_effective_authors
                        if source_weighted_effective_authors is not None
                        else independent_authors
                    ),
                    "top_author_share": top_author_share,
                    "duplicate_text_share": duplicate_text_share,
                },
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
