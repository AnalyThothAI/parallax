"""Integration tests for the pulse-agent-desk redesign migration.

Locked behaviour (see plan §"Task 2 — narrative_type 原子 hard cut +
stage CHECK 改"):

* The new ``pulse_agent_run_steps_stage_check`` constraint accepts only
  ``investigator`` / ``decision_maker`` / ``research_only_gate`` and
  rejects every legacy ``analyst`` / ``critic`` / ``judge`` value on
  new INSERTs.
* The constraint is added ``NOT VALID``; historical rows that violate
  the constraint must remain queryable. The downgrade also re-adds the
  legacy constraint ``NOT VALID`` so an emergency rollback cannot fail
  on freshly written ``investigator`` rows.
* ``pulse_candidates.narrative_type`` is fully removed by the upgrade
  and restored by the downgrade; the upgrade -> downgrade -> upgrade
  cycle must converge without intervention.
"""

from __future__ import annotations

import json

from alembic import command
from psycopg import errors as psycopg_errors

from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_repository import PulseRepository
from gmgn_twitter_intel.platform.db.postgres_migrations import alembic_config
from tests.postgres_test_utils import connect_postgres_test, reset_postgres_schema
from tests.postgres_test_utils import test_postgres_dsn as _test_postgres_dsn

_REVISION = "20260516_0051"
_PREVIOUS_REVISION = "20260516_0050"
_ROLLBACK_REVISION = "20260516_0049"


def _alembic_config_with_dsn():
    config = alembic_config()
    config.attributes["database_url"] = _test_postgres_dsn()
    return config


def _seed_run_and_job(repo: PulseRepository, *, run_id: str) -> None:
    repo.enqueue_job(
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
    repo.insert_agent_run(
        run_id=run_id,
        job_id=f"job-{run_id}",
        candidate_id=f"candidate-{run_id}",
        provider="openai",
        model="gpt-5-mini",
        workflow_name="signal_lab_pulse",
        agent_name="pulse_decision_pipeline",
        artifact_version_hash="artifact-hash",
        prompt_version="pulse-decision-v2",
        schema_version="pulse_decision_v2",
        harness_version="pulse-decision-harness-v2",
        harness_hash=f"sha256:{run_id}",
        input_hash="input-hash",
        status="running",
        outcome="running",
        decision_route="meme",
        decision_stage_count=0,
        request_json={"target": "asset:sol"},
        started_at_ms=1_100,
    )


def test_stage_check_admits_new_stages_and_rejects_legacy(tmp_path) -> None:
    """After upgrade, only investigator / decision_maker / research_only_gate are accepted."""

    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        reset_postgres_schema(conn)
        repo = PulseRepository(conn)
        _seed_run_and_job(repo, run_id="run-stage-check")

        for accepted_stage in ("investigator", "decision_maker", "research_only_gate"):
            step = repo.insert_agent_run_step(
                step_id=f"run-stage-check:{accepted_stage}:0",
                run_id="run-stage-check",
                stage=accepted_stage,
                route="meme",
                attempt_index=0,
                provider="openai",
                model="gpt-5-mini",
                prompt_version=f"pulse-{accepted_stage}-v1",
                schema_version="pulse_decision_v2",
                input_json={"stage": accepted_stage},
                prompt_text=f"{accepted_stage} prompt",
                response_json={"ok": True},
                started_at_ms=1_101,
                finished_at_ms=1_102,
                created_at_ms=1_102,
            )
            assert step["stage"] == accepted_stage

        for legacy_stage in ("analyst", "critic", "judge"):
            try:
                repo.insert_agent_run_step(
                    step_id=f"run-stage-check:{legacy_stage}:0",
                    run_id="run-stage-check",
                    stage=legacy_stage,
                    route="meme",
                    attempt_index=1,
                    provider="openai",
                    model="gpt-5-mini",
                    prompt_version=f"pulse-{legacy_stage}-v1",
                    schema_version="pulse_decision_v2",
                    input_json={"stage": legacy_stage},
                    prompt_text=f"{legacy_stage} prompt",
                    response_json={"ok": True},
                    started_at_ms=1_103,
                    finished_at_ms=1_104,
                    created_at_ms=1_104,
                )
            except psycopg_errors.CheckViolation:
                # Required behaviour: the new CHECK rejects legacy stage names.
                conn.rollback()
                continue
            raise AssertionError(f"INSERT with legacy stage {legacy_stage!r} should have failed the CHECK constraint")
    finally:
        conn.close()


def test_not_valid_preserves_legacy_rows_and_blocks_new_writes(tmp_path) -> None:
    """``NOT VALID`` keeps historical rows queryable while constraining new writes.

    The upgrade must add the new CHECK constraint without validating
    existing rows. We simulate that by downgrading first (legacy CHECK),
    inserting a legacy ``analyst`` row, then upgrading again. The row
    must remain readable but a fresh INSERT of ``analyst`` must fail.
    """

    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        reset_postgres_schema(conn)
        config = _alembic_config_with_dsn()

        command.downgrade(config, _PREVIOUS_REVISION)
        conn.commit()

        repo = PulseRepository(conn)
        _seed_run_and_job(repo, run_id="run-legacy")
        legacy_step = repo.insert_agent_run_step(
            step_id="run-legacy:analyst:0",
            run_id="run-legacy",
            stage="analyst",
            route="meme",
            attempt_index=0,
            provider="openai",
            model="gpt-5-mini",
            prompt_version="meme-analyst-v1",
            schema_version="pulse_decision_v1",
            input_json={"stage": "analyst"},
            prompt_text="analyst prompt",
            response_json={"recommendation": "watchlist"},
            started_at_ms=1_101,
            finished_at_ms=1_102,
            created_at_ms=1_102,
        )
        assert legacy_step["stage"] == "analyst"

        command.upgrade(config, _REVISION)
        conn.commit()

        legacy_rows = repo.list_agent_run_steps("run-legacy")
        assert [row["stage"] for row in legacy_rows] == ["analyst"]

        try:
            repo.insert_agent_run_step(
                step_id="run-legacy:analyst:1",
                run_id="run-legacy",
                stage="analyst",
                route="meme",
                attempt_index=1,
                provider="openai",
                model="gpt-5-mini",
                prompt_version="meme-analyst-v1",
                schema_version="pulse_decision_v1",
                input_json={"stage": "analyst"},
                prompt_text="analyst prompt",
                response_json={"recommendation": "watchlist"},
                started_at_ms=1_103,
                finished_at_ms=1_104,
                created_at_ms=1_104,
            )
        except psycopg_errors.CheckViolation:
            conn.rollback()
        else:
            raise AssertionError("New INSERT with stage='analyst' should have violated the CHECK constraint")

        # Sanity: the new CHECK still admits the new stage names after the upgrade.
        new_step = repo.insert_agent_run_step(
            step_id="run-legacy:investigator:0",
            run_id="run-legacy",
            stage="investigator",
            route="meme",
            attempt_index=2,
            provider="openai",
            model="gpt-5-mini",
            prompt_version="pulse-investigator-v1",
            schema_version="pulse_decision_v2",
            input_json={"stage": "investigator"},
            prompt_text="investigator prompt",
            response_json={"recommendation": "watchlist"},
            started_at_ms=1_105,
            finished_at_ms=1_106,
            created_at_ms=1_106,
        )
        assert new_step["stage"] == "investigator"
    finally:
        conn.close()


def test_upgrade_downgrade_upgrade_cycle_drops_and_restores_narrative_type(tmp_path) -> None:
    """The full migration cycle must round-trip without losing pulse_candidates rows."""

    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        reset_postgres_schema(conn)
        config = _alembic_config_with_dsn()

        columns = {
            row["column_name"]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'pulse_candidates'"
            ).fetchall()
        }
        assert "narrative_type" not in columns

        command.downgrade(config, _PREVIOUS_REVISION)
        conn.commit()

        columns_after_down = {
            row["column_name"]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'pulse_candidates'"
            ).fetchall()
        }
        assert "narrative_type" in columns_after_down

        # Insert a legacy row carrying narrative_type so we can confirm survival across the next upgrade.
        conn.execute(
            """
            INSERT INTO pulse_candidates(
              candidate_id, candidate_type, subject_key, target_type, target_id, symbol,
              "window", scope, pulse_status, verdict, social_phase, narrative_type,
              candidate_score, score_band, trigger_signature, timeline_signature,
              factor_snapshot_json, gate_json, decision_route, decision_recommendation,
              decision_confidence, decision_abstain_reason, decision_stage_count, decision_json,
              gate_reasons_json, risk_reasons_json, evidence_event_ids_json, source_event_ids_json,
              last_edge_events_json, agent_run_id, pulse_version, gate_version, prompt_version, schema_version,
              created_at_ms, updated_at_ms
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s
            )
            """,
            (
                "candidate-cycle",
                "token_target",
                "toly",
                "asset",
                "asset:sol",
                "SOL",
                "1h",
                "global",
                "token_watch",
                "token_watch",
                "ignition",
                "direct_token",
                0.82,
                "watch",
                "trigger-cycle",
                "timeline-cycle",
                json.dumps({"schema_version": "token_factor_snapshot_v3_social_attention"}),
                json.dumps({"pulse_status": "token_watch"}),
                "meme",
                "watchlist",
                0.72,
                None,
                3,
                json.dumps({"route": "meme"}),
                json.dumps([]),
                json.dumps([]),
                json.dumps([]),
                json.dumps([]),
                json.dumps([]),
                None,
                "pulse-v1",
                "gate-v1",
                "prompt-v1",
                "schema-v1",
                1_000,
                2_000,
            ),
        )
        conn.commit()

        command.upgrade(config, _REVISION)
        conn.commit()

        columns_after_up = {
            row["column_name"]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'pulse_candidates'"
            ).fetchall()
        }
        assert "narrative_type" not in columns_after_up

        rows = conn.execute(
            "SELECT candidate_id, social_phase FROM pulse_candidates WHERE candidate_id = %s",
            ("candidate-cycle",),
        ).fetchall()
        assert [(row["candidate_id"], row["social_phase"]) for row in rows] == [
            ("candidate-cycle", "ignition")
        ]
    finally:
        conn.close()


def test_downgrade_to_0049_preserves_historical_v2_stage_rows(tmp_path) -> None:
    """Rollback to 0049 must not validate away rows written by the v2 stage taxonomy."""

    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        reset_postgres_schema(conn)
        config = _alembic_config_with_dsn()

        # Head includes 0052; step back to 0049, then explicitly exercise the 0051 upgrade.
        command.downgrade(config, _ROLLBACK_REVISION)
        conn.commit()
        command.upgrade(config, _REVISION)
        conn.commit()

        repo = PulseRepository(conn)
        _seed_run_and_job(repo, run_id="run-v2-rollback")
        for offset, stage in enumerate(("investigator", "decision_maker")):
            repo.insert_agent_run_step(
                step_id=f"run-v2-rollback:{stage}:0",
                run_id="run-v2-rollback",
                stage=stage,
                route="meme",
                attempt_index=0,
                provider="openai",
                model="gpt-5-mini",
                prompt_version=f"pulse-{stage}-v2",
                schema_version="pulse_decision_v2",
                input_json={"stage": stage, "tool_calls": [{"tool_name": "get_target_recent_tweets"}]}
                if stage == "investigator"
                else {"stage": stage},
                prompt_text=f"{stage} prompt",
                response_json={"stage": stage, "ok": True},
                started_at_ms=1_200 + offset,
                finished_at_ms=1_210 + offset,
                created_at_ms=1_210 + offset,
            )

        command.downgrade(config, _ROLLBACK_REVISION)
        conn.commit()

        rows = repo.list_agent_run_steps("run-v2-rollback")
        assert [row["stage"] for row in rows] == ["investigator", "decision_maker"]

        try:
            repo.insert_agent_run_step(
                step_id="run-v2-rollback:investigator:1",
                run_id="run-v2-rollback",
                stage="investigator",
                route="meme",
                attempt_index=1,
                provider="openai",
                model="gpt-5-mini",
                prompt_version="pulse-investigator-v2",
                schema_version="pulse_decision_v2",
                input_json={"stage": "investigator"},
                prompt_text="investigator prompt",
                response_json={"stage": "investigator", "ok": True},
                started_at_ms=1_300,
                finished_at_ms=1_301,
                created_at_ms=1_301,
            )
        except psycopg_errors.CheckViolation:
            conn.rollback()
        else:
            raise AssertionError("New INSERT with stage='investigator' should violate the restored legacy CHECK")
    finally:
        conn.close()
