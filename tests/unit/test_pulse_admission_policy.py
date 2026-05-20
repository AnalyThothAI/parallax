from __future__ import annotations

from gmgn_twitter_intel.domains.pulse_lab.services.pulse_admission_policy import (
    PulseAdmissionPolicy,
)


def test_policy_suppresses_unchanged_state() -> None:
    state = {"pulse_status": "token_watch", "score_band": "70-79"}
    decision = PulseAdmissionPolicy().classify(
        previous_state=state,
        current_state=state,
        existing_job=None,
        edge_events=[],
        pending_score_band=None,
        pending_score_band_count=0,
    )

    assert decision.action == "suppress"
    assert decision.reason == "unchanged"


def test_policy_suppresses_pending_and_running_jobs() -> None:
    policy = PulseAdmissionPolicy()

    pending = policy.classify(
        previous_state={"pulse_status": "token_watch"},
        current_state={"pulse_status": "trade_candidate"},
        existing_job={"status": "pending", "attempt_count": 0, "max_attempts": 3},
        edge_events=["pulse_status_changed"],
        pending_score_band=None,
        pending_score_band_count=0,
    )
    running = policy.classify(
        previous_state={"pulse_status": "token_watch"},
        current_state={"pulse_status": "trade_candidate"},
        existing_job={"status": "running", "attempt_count": 1, "max_attempts": 3},
        edge_events=["pulse_status_changed"],
        pending_score_band=None,
        pending_score_band_count=0,
    )

    assert pending.action == "suppress"
    assert pending.reason == "active_job"
    assert running.action == "suppress"
    assert running.reason == "active_job"


def test_policy_suppresses_retryable_failed_job_with_specific_reason() -> None:
    decision = PulseAdmissionPolicy().classify(
        previous_state={"pulse_status": "token_watch"},
        current_state={"pulse_status": "trade_candidate"},
        existing_job={"status": "failed", "attempt_count": 1, "max_attempts": 3},
        edge_events=["pulse_status_changed"],
        pending_score_band=None,
        pending_score_band_count=0,
    )

    assert decision.action == "suppress"
    assert decision.reason == "retryable_failed_job"


def test_policy_admits_first_observation_as_material_edge() -> None:
    decision = PulseAdmissionPolicy().classify(
        previous_state={},
        current_state={"pulse_status": "token_watch"},
        existing_job=None,
        edge_events=["pulse_status_changed"],
        pending_score_band=None,
        pending_score_band_count=0,
    )

    assert decision.action == "enqueue_agent"
    assert decision.reason == "material_edge"


def test_policy_admits_escalation_edges_with_specific_reason() -> None:
    decision = PulseAdmissionPolicy().classify(
        previous_state={"pulse_status": "token_watch"},
        current_state={"pulse_status": "trade_candidate"},
        existing_job=None,
        edge_events=["pulse_status_changed"],
        pending_score_band=None,
        pending_score_band_count=0,
    )

    assert decision.action == "enqueue_agent"
    assert decision.reason == "escalation"


def test_policy_admits_hard_risk_added_with_specific_reason() -> None:
    decision = PulseAdmissionPolicy().classify(
        previous_state={"hard_risks": []},
        current_state={"hard_risks": ["duplicate_text_share_high"]},
        existing_job=None,
        edge_events=["hard_risk_added"],
        pending_score_band=None,
        pending_score_band_count=0,
    )

    assert decision.action == "enqueue_agent"
    assert decision.reason == "hard_risk_added"


def test_policy_admits_material_evidence_changes_with_specific_reason() -> None:
    decision = PulseAdmissionPolicy().classify(
        previous_state={"timeline_signature": "sha256:old"},
        current_state={"timeline_signature": "sha256:new"},
        existing_job=None,
        edge_events=["timeline_evidence_changed"],
        pending_score_band=None,
        pending_score_band_count=0,
    )

    assert decision.action == "enqueue_agent"
    assert decision.reason == "material_evidence_changed"


def test_policy_failure_circuit_suppresses_material_evidence_changes() -> None:
    decision = PulseAdmissionPolicy().classify(
        previous_state={"timeline_signature": "sha256:old"},
        current_state={"timeline_signature": "sha256:new"},
        existing_job=None,
        edge_events=["timeline_evidence_changed"],
        pending_score_band=None,
        pending_score_band_count=0,
        recent_failure_count=3,
    )

    assert decision.action == "suppress"
    assert decision.reason == "failure_circuit_open"


def test_policy_suppresses_first_score_band_observation() -> None:
    decision = PulseAdmissionPolicy().classify(
        previous_state={"score_band": "60-69", "pulse_status": "token_watch"},
        current_state={"score_band": "70-79", "pulse_status": "token_watch"},
        existing_job=None,
        edge_events=["score_band_crossed"],
        pending_score_band=None,
        pending_score_band_count=0,
    )

    assert decision.action == "suppress"
    assert decision.reason == "score_band_pending"


def test_policy_requires_two_score_band_observations() -> None:
    decision = PulseAdmissionPolicy().classify(
        previous_state={"score_band": "60-69", "pulse_status": "token_watch"},
        current_state={"score_band": "70-79", "pulse_status": "token_watch"},
        existing_job=None,
        edge_events=["score_band_crossed"],
        pending_score_band="70-79",
        pending_score_band_count=1,
    )

    assert decision.action == "enqueue_agent"
    assert decision.reason == "score_band_confirmed"


def test_policy_opens_failure_circuit_for_non_escalation_edges() -> None:
    decision = PulseAdmissionPolicy().classify(
        previous_state={"score_band": "60-69", "pulse_status": "token_watch"},
        current_state={"score_band": "70-79", "pulse_status": "token_watch"},
        existing_job=None,
        edge_events=["score_band_crossed"],
        pending_score_band="70-79",
        pending_score_band_count=1,
        recent_failure_count=3,
    )

    assert decision.action == "suppress"
    assert decision.reason == "failure_circuit_open"
