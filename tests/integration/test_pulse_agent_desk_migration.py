from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from psycopg import errors as psycopg_errors

from parallax.domains.pulse_lab.repositories.pulse_candidates_repository import PulseCandidatesRepository
from parallax.domains.pulse_lab.repositories.pulse_jobs_repository import PulseJobsRepository
from parallax.domains.pulse_lab.repositories.pulse_runs_repository import PulseRunsRepository
from tests.postgres_test_utils import connect_postgres_test, reset_postgres_schema

pytestmark = pytest.mark.integration

_RESEARCH_COMMITTEE_STAGES = (
    "evidence_pack",
    "evidence_completeness_gate",
    "signal_analyst",
    "bear_case",
    "claim_verifier",
    "risk_portfolio_judge",
    "recommendation_clipper",
    "deterministic_eval",
    "write_gate",
)


def _pulse_repos(conn: Any) -> SimpleNamespace:
    return SimpleNamespace(
        candidates=PulseCandidatesRepository(conn),
        jobs=PulseJobsRepository(conn),
        runs=PulseRunsRepository(conn),
    )


def _seed_run_and_job(repo: SimpleNamespace, *, run_id: str) -> None:
    repo.jobs.enqueue_job(
        job_id=f"job-{run_id}",
        candidate_id=f"candidate-{run_id}",
        candidate_type="token_target",
        subject_key="toly",
        window="1h",
        scope="global",
        trigger_signature=f"trigger-{run_id}",
        timeline_signature=f"timeline-{run_id}",
        priority=10,
        next_run_at_ms=1_000,
        now_ms=900,
    )
    repo.runs.insert_agent_run(
        run_id=run_id,
        job_id=f"job-{run_id}",
        candidate_id=f"candidate-{run_id}",
        provider="litellm",
        model="gpt-5-mini",
        workflow_name="signal_lab_pulse",
        agent_name="pulse_decision_pipeline",
        artifact_version_hash="artifact-hash",
        prompt_version="pulse-decision-v3",
        schema_version="pulse_decision_v3",
        runtime_version="pulse-decision-runtime-v3",
        runtime_hash=f"sha256:{run_id}",
        input_hash="input-hash",
        status="running",
        outcome="running",
        decision_route="meme",
        decision_stage_count=0,
        request_json={"target": "asset:sol"},
        started_at_ms=1_100,
    )


def test_stage_check_admits_research_committee_stages_and_rejects_legacy(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        reset_postgres_schema(conn)
        repo = _pulse_repos(conn)
        _seed_run_and_job(repo, run_id="run-stage-check")

        for accepted_stage in _RESEARCH_COMMITTEE_STAGES:
            step = repo.runs.insert_agent_run_step(
                step_id=f"run-stage-check:{accepted_stage}:0",
                run_id="run-stage-check",
                stage=accepted_stage,
                route="meme",
                attempt_index=0,
                provider="litellm",
                model="gpt-5-mini",
                prompt_version=f"pulse-{accepted_stage}-v3",
                schema_version="pulse_decision_v3",
                input_json={"stage": accepted_stage},
                prompt_text=f"{accepted_stage} prompt",
                response_json={"ok": True},
                started_at_ms=1_101,
                finished_at_ms=1_102,
                created_at_ms=1_102,
            )
            assert step["stage"] == accepted_stage

        for legacy_stage in (
            "analyst",
            "critic",
            "judge",
            "investigator",
            "research_only_gate",
            "evidence_debate",
            "decision_maker",
        ):
            with pytest.raises(psycopg_errors.CheckViolation):
                repo.runs.insert_agent_run_step(
                    step_id=f"run-stage-check:{legacy_stage}:0",
                    run_id="run-stage-check",
                    stage=legacy_stage,
                    route="meme",
                    attempt_index=1,
                    provider="litellm",
                    model="gpt-5-mini",
                    prompt_version=f"pulse-{legacy_stage}-v2",
                    schema_version="pulse_decision_v2",
                    input_json={"stage": legacy_stage},
                    prompt_text=f"{legacy_stage} prompt",
                    response_json={"ok": True},
                    started_at_ms=1_103,
                    finished_at_ms=1_104,
                    created_at_ms=1_104,
                )
            conn.rollback()
    finally:
        conn.close()


def test_public_candidate_rows_require_evidence_packet_hash(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        reset_postgres_schema(conn)
        repo = _pulse_repos(conn)

        with pytest.raises(psycopg_errors.CheckViolation):
            repo.candidates.upsert_candidate(
                **_candidate_payload(
                    candidate_id="candidate-public-no-packet",
                    evidence_packet_hash=None,
                    display_status="display_trade_candidate",
                    evidence_status="complete",
                    decision_status="trade_candidate",
                ),
                commit=False,
            )
        conn.rollback()

        hidden = repo.candidates.upsert_candidate(
            **_candidate_payload(
                candidate_id="candidate-hidden-no-packet",
                evidence_packet_hash=None,
                display_status="hidden_insufficient_evidence",
                evidence_status="insufficient",
                decision_status="invalid",
            ),
            commit=False,
        )
        public = repo.candidates.upsert_candidate(
            **_candidate_payload(
                candidate_id="candidate-public-with-packet",
                evidence_packet_hash="sha256:packet",
                display_status="display_trade_candidate",
                evidence_status="complete",
                decision_status="trade_candidate",
            ),
            commit=False,
        )

        assert hidden["display_status"] == "hidden_insufficient_evidence"
        assert public["evidence_packet_hash"] == "sha256:packet"
    finally:
        conn.close()


def test_hidden_source_quality_status_is_allowed_for_non_public_rows(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        reset_postgres_schema(conn)
        repo = _pulse_repos(conn)

        row = repo.candidates.upsert_candidate(
            **_candidate_payload(
                candidate_id="candidate-source-quality",
                evidence_packet_hash="sha256:packet-source-quality",
                display_status="hidden_source_quality",
                evidence_status="complete",
                decision_status="token_watch",
            ),
            commit=False,
        )

        assert row["display_status"] == "hidden_source_quality"
    finally:
        conn.close()


def _candidate_payload(
    *,
    candidate_id: str,
    evidence_packet_hash: str | None,
    display_status: str,
    evidence_status: str,
    decision_status: str,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "candidate_type": "token_target",
        "subject_key": "toly",
        "target_type": "asset",
        "target_id": "asset:sol",
        "symbol": "SOL",
        "window": "1h",
        "scope": "global",
        "pulse_status": "trade_candidate",
        "verdict": "trade_candidate",
        "social_phase": "ignition",
        "candidate_score": 82.0,
        "score_band": "trade",
        "trigger_signature": f"trigger:{candidate_id}",
        "timeline_signature": f"timeline:{candidate_id}",
        "pulse_version": "pulse-v3",
        "gate_version": "gate-v3",
        "prompt_version": "prompt-v3",
        "schema_version": "schema-v3",
        "factor_snapshot_json": {"schema_version": "token_factor_snapshot_v3_social_attention"},
        "gate_json": {"pulse_status": "trade_candidate"},
        "decision_route": "meme",
        "decision_recommendation": "trade_candidate",
        "decision_confidence": 0.72,
        "decision_stage_count": 8,
        "decision_json": {"route": "meme", "recommendation": "trade_candidate"},
        "evidence_packet_hash": evidence_packet_hash,
        "evidence_status": evidence_status,
        "decision_status": decision_status,
        "display_status": display_status,
        "created_at_ms": 1_000,
        "updated_at_ms": 1_000,
    }
