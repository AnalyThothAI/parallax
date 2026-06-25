from __future__ import annotations

import pytest

from parallax.domains.pulse_lab.services.pulse_admission_policy import (
    PulseAdmissionPolicy,
)


def _classify(**overrides):
    values = {
        "previous_state": {},
        "current_state": {},
        "existing_job": None,
        "edge_events": [],
        "pending_score_band": None,
        "pending_score_band_count": 0,
        "recent_failure_count": 0,
        "failure_circuit_per_hour": 3,
        "timeline_debounce_seconds": 600,
    }
    values.update(overrides)
    return PulseAdmissionPolicy().classify(**values)


def test_policy_suppresses_unchanged_state() -> None:
    state = {"pulse_status": "token_watch", "score_band": "70-79"}
    decision = _classify(
        previous_state=state,
        current_state=state,
    )

    assert decision.action == "suppress"
    assert decision.reason == "unchanged"


def test_policy_suppresses_pending_and_running_jobs() -> None:
    pending = _classify(
        previous_state={"pulse_status": "token_watch"},
        current_state={"pulse_status": "trade_candidate"},
        existing_job={"status": "pending", "attempt_count": 0, "max_attempts": 3},
        edge_events=["pulse_status_changed"],
    )
    running = _classify(
        previous_state={"pulse_status": "token_watch"},
        current_state={"pulse_status": "trade_candidate"},
        existing_job={"status": "running", "attempt_count": 1, "max_attempts": 3},
        edge_events=["pulse_status_changed"],
    )

    assert pending.action == "suppress"
    assert pending.reason == "active_job"
    assert running.action == "suppress"
    assert running.reason == "active_job"


def test_policy_suppresses_retryable_failed_job_with_specific_reason() -> None:
    decision = _classify(
        previous_state={"pulse_status": "token_watch"},
        current_state={"pulse_status": "trade_candidate"},
        existing_job={"status": "failed", "attempt_count": 1, "max_attempts": 3},
        edge_events=["pulse_status_changed"],
    )

    assert decision.action == "suppress"
    assert decision.reason == "retryable_failed_job"


def test_policy_rejects_failed_job_missing_attempt_contract_without_default() -> None:
    with pytest.raises(RuntimeError, match="pulse_existing_failed_job_attempt_contract_required"):
        _classify(
            previous_state={"pulse_status": "token_watch"},
            current_state={"pulse_status": "trade_candidate"},
            existing_job={"status": "failed", "attempt_count": 1},
            edge_events=["timeline_evidence_changed"],
        )


def test_policy_admits_first_observation_as_material_edge() -> None:
    decision = _classify(
        previous_state={},
        current_state={"pulse_status": "token_watch"},
        edge_events=["pulse_status_changed"],
    )

    assert decision.action == "enqueue_agent"
    assert decision.reason == "material_edge"


def test_policy_admits_escalation_edges_with_specific_reason() -> None:
    decision = _classify(
        previous_state={"pulse_status": "token_watch"},
        current_state={"pulse_status": "trade_candidate"},
        edge_events=["pulse_status_changed"],
    )

    assert decision.action == "enqueue_agent"
    assert decision.reason == "escalation"


def test_policy_admits_hard_risk_added_with_specific_reason() -> None:
    decision = _classify(
        previous_state={"hard_risks": []},
        current_state={"hard_risks": ["duplicate_text_share_high"]},
        edge_events=["hard_risk_added"],
    )

    assert decision.action == "enqueue_agent"
    assert decision.reason == "hard_risk_added"


def test_policy_admits_material_evidence_changes_with_specific_reason() -> None:
    decision = _classify(
        previous_state={"timeline_signature": "sha256:old"},
        current_state={"timeline_signature": "sha256:new"},
        edge_events=["timeline_evidence_changed"],
    )

    assert decision.action == "enqueue_agent"
    assert decision.reason == "material_evidence_changed"


def test_policy_failure_circuit_suppresses_material_evidence_changes() -> None:
    decision = _classify(
        previous_state={"timeline_signature": "sha256:old"},
        current_state={"timeline_signature": "sha256:new"},
        edge_events=["timeline_evidence_changed"],
        recent_failure_count=3,
    )

    assert decision.action == "suppress"
    assert decision.reason == "failure_circuit_open"


@pytest.mark.parametrize("failure_circuit_per_hour", [0, -1, True, "3"])
def test_policy_rejects_malformed_failure_circuit_threshold(failure_circuit_per_hour: object) -> None:
    with pytest.raises(ValueError, match="pulse_failure_circuit_per_hour_required"):
        _classify(
            edge_events=["timeline_evidence_changed"],
            failure_circuit_per_hour=failure_circuit_per_hour,
        )


@pytest.mark.parametrize("timeline_debounce_seconds", [-1, True, "600"])
def test_policy_rejects_malformed_timeline_debounce(timeline_debounce_seconds: object) -> None:
    with pytest.raises(ValueError, match="pulse_timeline_debounce_seconds_required"):
        _classify(
            previous_state={"timeline_signature": "old"},
            current_state={"timeline_signature": "new"},
            edge_events=["timeline_evidence_changed"],
            last_processed_at_ms=1_000,
            now_ms=1_100,
            timeline_debounce_seconds=timeline_debounce_seconds,
        )


def test_policy_suppresses_first_score_band_observation() -> None:
    decision = _classify(
        previous_state={"score_band": "60-69", "pulse_status": "token_watch"},
        current_state={"score_band": "70-79", "pulse_status": "token_watch"},
        edge_events=["score_band_crossed"],
    )

    assert decision.action == "suppress"
    assert decision.reason == "score_band_pending"


def test_policy_requires_two_score_band_observations() -> None:
    decision = _classify(
        previous_state={"score_band": "60-69", "pulse_status": "token_watch"},
        current_state={"score_band": "70-79", "pulse_status": "token_watch"},
        edge_events=["score_band_crossed"],
        pending_score_band="70-79",
        pending_score_band_count=1,
    )

    assert decision.action == "enqueue_agent"
    assert decision.reason == "score_band_confirmed"


def test_policy_opens_failure_circuit_for_non_escalation_edges() -> None:
    decision = _classify(
        previous_state={"score_band": "60-69", "pulse_status": "token_watch"},
        current_state={"score_band": "70-79", "pulse_status": "token_watch"},
        edge_events=["score_band_crossed"],
        pending_score_band="70-79",
        pending_score_band_count=1,
        recent_failure_count=3,
    )

    assert decision.action == "suppress"
    assert decision.reason == "failure_circuit_open"
