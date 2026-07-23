from __future__ import annotations

import pytest
from alembic import command

from parallax.platform.db.postgres_migrations import alembic_config
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import test_postgres_dsn as _test_postgres_dsn


def test_macro_decision_workbench_hard_cut_migrates_nonempty_0191_state(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO public")
        conn.commit()
        config = alembic_config()
        config.attributes["database_url"] = _test_postgres_dsn()
        command.upgrade(config, "20260723_0191")

        conn.execute(
            """
            INSERT INTO macro_observations(
              observation_id, source_name, series_key, observed_at, value_numeric,
              unit, frequency, data_quality, raw_payload_json, ingested_at_ms,
              concept_key, source_priority, fact_payload_hash
            ) VALUES (
              'macro-decision-fact', 'fred', 'fred:DGS10', '2026-07-22', 4.25,
              'percent', 'daily', 'ok', '{}'::jsonb, 100,
              'rates:dgs10', 100, 'macro-decision-fact-hash'
            );
            INSERT INTO macro_observation_series_rows(
              projection_version, concept_key, observed_at, value_numeric,
              source_name, series_key, unit, frequency, data_quality,
              event_metadata_json
            ) VALUES (
              'macro_evidence_v1', 'rates:dgs10', '2026-07-22', 4.25,
              'fred', 'fred:DGS10', 'percent', 'daily', 'ok', '{}'::jsonb
            );
            INSERT INTO macro_observation_series_publication_state(
              projection_version, source_signature, row_count,
              latest_attempt_status, latest_attempt_started_at_ms,
              latest_attempt_finished_at_ms, updated_at_ms
            ) VALUES (
              'macro_evidence_v1', 'old-signature', 1,
              'published', 100, 100, 100
            );
            INSERT INTO macro_view_snapshots(
              snapshot_key, projection_version, fact_watermark, market_cutoff,
              computed_at_ms, overview_json, cross_asset_json,
              rates_inflation_json, growth_labor_json, liquidity_funding_json,
              credit_json, payload_hash
            ) VALUES (
              'current', 'macro_evidence_v1', '2026-07-22', '2026-07-22',
              100, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
              '{}'::jsonb, '{}'::jsonb, 'old-snapshot-hash'
            )
            """
        )
        conn.commit()

        fact_before = conn.execute(
            """
            SELECT observation_id, concept_key, observed_at, value_numeric,
                   fact_payload_hash
            FROM macro_observations
            WHERE observation_id = 'macro-decision-fact'
            """
        ).fetchone()

        command.upgrade(config, "20260723_0192")

        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()["version_num"]
        fact_after = conn.execute(
            """
            SELECT observation_id, concept_key, observed_at, value_numeric,
                   fact_payload_hash
            FROM macro_observations
            WHERE observation_id = 'macro-decision-fact'
            """
        ).fetchone()
        derived_counts = {
            table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in (
                "macro_observation_series_rows",
                "macro_observation_series_publication_state",
                "macro_view_snapshots",
            )
        }
        dirty = conn.execute(
            """
            SELECT projection_name, projection_version, target_kind, target_id,
                   dirty_reason, source_watermark_ms, leased_until_ms,
                   lease_owner, attempt_count, last_error,
                   min_observed_at, max_observed_at
            FROM macro_projection_dirty_targets
            """
        ).fetchall()

        with pytest.raises(RuntimeError, match="irreversible derived-state hard cut"):
            command.downgrade(config, "20260723_0191")
    finally:
        conn.close()

    assert version == "20260723_0192"
    assert fact_after == fact_before
    assert derived_counts == {
        "macro_observation_series_rows": 0,
        "macro_observation_series_publication_state": 0,
        "macro_view_snapshots": 0,
    }
    assert dirty == [
        {
            "projection_name": "macro_evidence",
            "projection_version": "macro_decision_v2",
            "target_kind": "current",
            "target_id": "current",
            "dirty_reason": "schema_hard_cut_0192",
            "source_watermark_ms": 100,
            "leased_until_ms": None,
            "lease_owner": None,
            "attempt_count": 0,
            "last_error": None,
            "min_observed_at": fact_before["observed_at"],
            "max_observed_at": fact_before["observed_at"],
        }
    ]
