from __future__ import annotations

import pytest
from alembic import command
from psycopg.errors import RaiseException

from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import test_postgres_dsn as _test_postgres_dsn
from tracefold.platform.postgres.postgres_migrations import alembic_config


def test_0194_preserves_macro_truth_and_hard_cuts_old_derived_state(
    tmp_path,
) -> None:
    conn = connect_postgres_test(
        tmp_path / "postgres_test_db",
        read_only=False,
    )
    try:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO public")
        conn.commit()
        config = alembic_config()
        config.attributes["database_url"] = _test_postgres_dsn()
        command.upgrade(config, "20260723_0193")
        conn.execute(
            """
            INSERT INTO macro_observations(
              observation_id,
              source_name,
              series_key,
              observed_at,
              value_numeric,
              unit,
              frequency,
              data_quality,
              source_ts,
              raw_payload_json,
              ingested_at_ms,
              concept_key,
              source_priority,
              fact_payload_hash
            )
            VALUES (
              'macro-observation:kept',
              'official',
              'official:spy',
              '2026-07-23',
              635.25,
              'price',
              'daily',
              'ok',
              '2026-07-23',
              '{}'::jsonb,
              100,
              'asset:spy',
              1,
              'sha256:kept'
            );
            INSERT INTO macro_view_snapshots(
              snapshot_key,
              projection_version,
              fact_watermark,
              market_cutoff,
              computed_at_ms,
              overview_json,
              cross_asset_json,
              rates_inflation_json,
              growth_labor_json,
              liquidity_funding_json,
              credit_json,
              payload_hash
            )
            VALUES (
              'current',
              'macro_decision_v2',
              '2026-07-23',
              '2026-07-23',
              100,
              '{}'::jsonb,
              '{}'::jsonb,
              '{}'::jsonb,
              '{}'::jsonb,
              '{}'::jsonb,
              '{}'::jsonb,
              'retired-snapshot'
            );
            INSERT INTO macro_judgment_jobs(
              session_date,
              market_cutoff_ms,
              status,
              evidence_pack_json,
              evidence_pack_hash,
              compiler_version,
              selection_policy_version,
              sealed_at_ms,
              max_attempts,
              due_at_ms,
              created_at_ms,
              updated_at_ms
            )
            VALUES (
              '2026-07-23',
              100,
              'pending',
              '{}'::jsonb,
              'retired-pack',
              'compiler-v1',
              'selection-v1',
              110,
              3,
              110,
              110,
              110
            )
            """
        )
        conn.commit()

        command.upgrade(config, "20260724_0194")

        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()["version_num"]
        material_count = conn.execute("SELECT COUNT(*)::int AS count FROM macro_observations").fetchone()["count"]
        retired = {
            name: conn.execute(
                "SELECT to_regclass(%s) AS relation",
                (f"public.{name}",),
            ).fetchone()["relation"]
            for name in (
                "macro_projection_dirty_targets",
                "macro_observation_series_rows",
                "macro_observation_series_publication_state",
                "macro_view_snapshots",
                "macro_judgment_jobs",
                "macro_judgment_publications",
                "macro_judgment_outcomes",
            )
        }
        checkpoint_versions = [
            row["v"] for row in conn.execute("SELECT v FROM checkpoint_migrations ORDER BY v").fetchall()
        ]
        checkpoint_write_columns = {
            row["column_name"]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'checkpoint_writes'
                """
            ).fetchall()
        }
        _insert_research_publication(conn)
        conn.commit()

        with pytest.raises(RaiseException, match="publication_immutable"):
            conn.execute(
                """
                UPDATE macro_research_publications
                SET report_markdown = 'rewritten'
                WHERE session_date = '2026-07-23'
                """
            )
        conn.rollback()
        with pytest.raises(RaiseException, match="run_delete_forbidden"):
            conn.execute(
                """
                DELETE FROM macro_research_runs
                WHERE session_date = '2026-07-23'
                """
            )
        conn.rollback()
        with pytest.raises(RuntimeError, match="irreversible"):
            command.downgrade(config, "20260723_0193")
    finally:
        conn.close()

    assert version == "20260724_0194"
    assert material_count == 1
    assert set(retired.values()) == {None}
    assert checkpoint_versions == list(range(10))
    assert "task_path" in checkpoint_write_columns


def _insert_research_publication(conn) -> None:
    conn.execute(
        """
        INSERT INTO macro_research_runs(
          session_date,
          market_cutoff_ms,
          status,
          sealed_at_ms,
          max_attempts,
          due_at_ms,
          created_at_ms,
          updated_at_ms
        )
        VALUES (
          '2026-07-23',
          100,
          'pending',
          110,
          3,
          110,
          110,
          110
        );
        UPDATE macro_research_runs
        SET status = 'running',
            attempt_count = 1,
            leased_until_ms = 200,
            lease_owner = 'migration-test',
            updated_at_ms = 120
        WHERE session_date = '2026-07-23';
        INSERT INTO macro_research_publications(
          session_date,
          market_cutoff_ms,
          artifact_json,
          report_markdown,
          audit_json,
          model_name,
          prompt_version,
          workflow_version,
          artifact_hash,
          published_at_ms
        )
        VALUES (
          '2026-07-23',
          100,
          '{}'::jsonb,
          '# 宏观研究',
          '{}'::jsonb,
          'fake-model',
          'prompt-v1',
          'workflow-v1',
          'sha256:artifact',
          130
        );
        UPDATE macro_research_runs
        SET status = 'published',
            leased_until_ms = NULL,
            lease_owner = NULL,
            updated_at_ms = 130
        WHERE session_date = '2026-07-23'
        """
    )
