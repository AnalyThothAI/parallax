from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.domains.pulse_lab.repositories.pulse_admission_repository import PulseAdmissionRepository
from parallax.domains.pulse_lab.repositories.pulse_agent_eval_repository import PulseAgentEvalRepository
from parallax.domains.pulse_lab.repositories.pulse_candidates_repository import PulseCandidatesRepository
from parallax.domains.pulse_lab.repositories.pulse_evidence_repository import PulseEvidenceRepository
from parallax.domains.pulse_lab.repositories.pulse_playbooks_repository import PulsePlaybooksRepository
from parallax.domains.pulse_lab.repositories.pulse_runs_repository import PulseRunsRepository
from parallax.domains.pulse_lab.types import (
    IdentityEvidence,
    MarketEvidence,
    PulseEvidencePacket,
    PulseEvidenceQualityMetrics,
    SocialEvidence,
)

NOW_MS = 1_779_000_000_000


@pytest.mark.parametrize(
    ("operation", "factory", "invoke"),
    [
        (
            "insert_agent_run",
            PulseRunsRepository,
            lambda repo: repo.insert_agent_run(
                run_id="run-1",
                job_id="job-1",
                candidate_id="candidate-1",
                provider="test",
                model="model",
                workflow_name="workflow",
                agent_name="agent",
                artifact_version_hash="sha256:artifact",
                prompt_version="prompt-v1",
                schema_version="schema-v1",
                runtime_version="runtime-v1",
                runtime_hash="sha256:runtime",
                input_hash="sha256:input",
                outcome="running",
            ),
        ),
        (
            "finish_agent_run",
            PulseRunsRepository,
            lambda repo: repo.finish_agent_run("run-1", "done", outcome="completed"),
        ),
        (
            "insert_agent_run_step",
            PulseRunsRepository,
            lambda repo: repo.insert_agent_run_step(
                step_id="step-1",
                run_id="run-1",
                stage="pulse_decision",
                route="meme",
                attempt_index=0,
                provider="test",
                model="model",
                prompt_version="prompt-v1",
                schema_version="schema-v1",
                input_json={},
                prompt_text="prompt",
                response_json={},
            ),
        ),
        (
            "upsert_agent_runtime_version",
            PulseAgentEvalRepository,
            lambda repo: repo.upsert_agent_runtime_version(
                runtime_version="runtime-v1",
                runtime_hash="sha256:runtime",
                strategy="default",
                provider="test",
                model="model",
                prompt_version="prompt-v1",
                schema_version="schema-v1",
                manifest_json={},
            ),
        ),
        (
            "insert_agent_eval_case",
            PulseAgentEvalRepository,
            lambda repo: repo.insert_agent_eval_case(
                eval_case_id="case-1",
                source_run_id="run-1",
                runtime_hash="sha256:runtime",
                eval_type="deterministic",
                route="meme",
                recommendation="trade_candidate",
                input_json={},
                expected_json={},
                rubric_json={},
            ),
        ),
        (
            "upsert_agent_eval_result",
            PulseAgentEvalRepository,
            lambda repo: repo.upsert_agent_eval_result(
                eval_result_id="result-1",
                eval_case_id="case-1",
                runtime_hash="sha256:runtime",
                status="pass",
                score=1.0,
                grader_version="grader-v1",
                details_json={},
            ),
        ),
        (
            "upsert_packet",
            PulseEvidenceRepository,
            lambda repo: repo.upsert_packet(_evidence_packet()),
        ),
        (
            "upsert_candidate",
            PulseCandidatesRepository,
            lambda repo: repo.upsert_candidate(
                candidate_id="candidate-1",
                candidate_type="asset",
                subject_key="solana:abc",
                window="1h",
                scope="default",
                pulse_status="trade_candidate",
                verdict="trade_candidate",
                social_phase="impulse",
                candidate_score=82.0,
                score_band="high_conviction",
                trigger_signature="trigger",
                timeline_signature="timeline",
                pulse_version="pulse-v1",
                gate_version="gate-v1",
                prompt_version="prompt-v1",
                schema_version="schema-v1",
                factor_snapshot_json={},
                gate_json={},
                decision_route="meme",
                decision_recommendation="trade_candidate",
                decision_confidence=0.8,
                decision_stage_count=1,
                decision_json={},
                target_type="asset",
                target_id="asset-1",
            ),
        ),
        (
            "hide_public_candidate_for_low_information",
            PulseCandidatesRepository,
            lambda repo: repo.hide_public_candidate_for_low_information(
                candidate_id="candidate-1",
                candidate_score=12.0,
                trigger_signature="trigger",
                factor_snapshot_json={},
                gate_json={},
            ),
        ),
        (
            "upsert_playbook_snapshot",
            PulsePlaybooksRepository,
            lambda repo: repo.upsert_playbook_snapshot(
                playbook_id="playbook-1",
                candidate_id="candidate-1",
                horizon="1h",
                decision_time_ms=NOW_MS,
                playbook_status="active",
                side="long",
                setup={},
                confirmation={},
                invalidation={},
                risk={},
                playbook_version="playbook-v1",
            ),
        ),
        (
            "upsert_playbook_outcome",
            PulsePlaybooksRepository,
            lambda repo: repo.upsert_playbook_outcome(
                playbook_id="playbook-1",
                settled_at_ms=NOW_MS,
            ),
        ),
        (
            "record_edge_observation",
            PulseAdmissionRepository,
            lambda repo: repo.record_edge_observation(
                candidate_id="candidate-1",
                current_state_json={"score_band": "high_conviction"},
                edge_signature="edge",
                observed_at_ms=NOW_MS,
            ),
        ),
        (
            "claim_edge_budget",
            PulseAdmissionRepository,
            lambda repo: repo.claim_edge_budget(
                candidate_id="candidate-1",
                hour_bucket_ms=NOW_MS,
                now_ms=NOW_MS,
            ),
        ),
        (
            "mark_edge_job_enqueued",
            PulseAdmissionRepository,
            lambda repo: repo.mark_edge_job_enqueued(
                candidate_id="candidate-1",
                processed_state_json={},
                edge_events_json=["rank_score_changed"],
                job_id="job-1",
                processed_at_ms=NOW_MS,
            ),
        ),
        (
            "mark_edge_budget_rejected",
            PulseAdmissionRepository,
            lambda repo: repo.mark_edge_budget_rejected(
                candidate_id="candidate-1",
                edge_events_json=["rank_score_changed"],
                rejected_at_ms=NOW_MS,
            ),
        ),
        (
            "mark_edge_run_finished",
            PulseAdmissionRepository,
            lambda repo: repo.mark_edge_run_finished(
                candidate_id="candidate-1",
                agent_run_id="run-1",
                processed_state_json={},
                edge_events_json=["rank_score_changed"],
                finished_at_ms=NOW_MS,
            ),
        ),
    ],
)
def test_pulse_agent_write_repositories_require_connection_transaction_before_sql_when_committing(
    operation: str,
    factory: Callable[[Any], Any],
    invoke: Callable[[Any], object],
) -> None:
    connection = MissingTransactionConnection(operation)
    repo = factory(connection)

    with pytest.raises(RuntimeError, match="pulse_repository_transaction_required"):
        invoke(repo)

    assert connection.sql == []
    assert connection.commits == 0


def _evidence_packet() -> PulseEvidencePacket:
    return PulseEvidencePacket(
        evidence_packet_id="packet-1",
        run_id="run-1",
        evidence_packet_hash="sha256:packet",
        schema_version="schema-v1",
        candidate_id="candidate-1",
        target_type="asset",
        target_id="asset-1",
        symbol="ABC",
        window="1h",
        scope="default",
        snapshot_at_ms=NOW_MS,
        source_event_ids=("event-1",),
        allowed_evidence_refs=(),
        social_evidence=SocialEvidence(status="complete"),
        market_evidence=MarketEvidence(status="complete", route="dex", target_market_type="spot"),
        identity_evidence=IdentityEvidence(status="complete"),
        quality_metrics=PulseEvidenceQualityMetrics(
            ref_count=0,
            high_quality_ref_count=0,
            fresh_ref_count=0,
        ),
    )


class MissingTransactionConnection:
    def __init__(self, operation: str) -> None:
        self.operation = operation
        self.sql: list[str] = []
        self.commits = 0

    def execute(self, sql: str, params: Any = None) -> object:
        del params
        self.sql.append(sql)
        raise AssertionError(f"{self.operation} must require transaction before SQL")

    def commit(self) -> None:
        self.commits += 1
        raise AssertionError(f"{self.operation} must not manually commit without transaction")
