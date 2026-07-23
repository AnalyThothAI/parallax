from __future__ import annotations

import pytest
from alembic import command
from psycopg.errors import RaiseException

from parallax.platform.db.postgres_migrations import alembic_config
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import test_postgres_dsn as _test_postgres_dsn


def test_migration_preserves_existing_macro_and_news_truth_and_creates_immutable_history(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO public")
        conn.commit()
        config = alembic_config()
        config.attributes["database_url"] = _test_postgres_dsn()
        command.upgrade(config, "20260723_0192")
        conn.execute(
            """
            INSERT INTO macro_observations(
              observation_id, source_name, series_key, observed_at, value_numeric,
              unit, frequency, data_quality, source_ts, raw_payload_json, ingested_at_ms,
              concept_key, source_priority, fact_payload_hash
            ) VALUES (
              'judgment-macro-fact', 'test', 'test:SPY', '2026-07-22', 625.10,
              'price', 'daily', 'ok', '2026-07-22', '{}'::jsonb, 100,
              'asset:spy', 1, 'judgment-macro-hash'
            );
            INSERT INTO macro_view_snapshots(
              snapshot_key, projection_version, fact_watermark, market_cutoff,
              computed_at_ms, overview_json, cross_asset_json,
              rates_inflation_json, growth_labor_json, liquidity_funding_json,
              credit_json, payload_hash
            ) VALUES (
              'current', 'macro_decision_v2', '2026-07-22', '2026-07-22',
              100, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
              '{}'::jsonb, '{}'::jsonb, 'existing-snapshot'
            );
            INSERT INTO news_sources(
              source_id, provider_type, feed_url, source_domain, source_name,
              trust_tier, source_quality_status, config_payload_hash, created_at_ms, updated_at_ms
            ) VALUES (
              'judgment-fed', 'rss', 'https://example.test/feed', 'example.test',
              'Federal Reserve', 'official', 'healthy',
              'sha256:0000000000000000000000000000000000000000000000000000000000000000',
              10, 10
            );
            INSERT INTO news_fetch_runs(fetch_run_id, source_id, started_at_ms, status)
            VALUES ('judgment-fetch', 'judgment-fed', 10, 'success');
            INSERT INTO news_provider_items(
              provider_item_id, source_id, fetch_run_id, source_item_key,
              canonical_url, payload_hash, raw_payload_json, fetched_at_ms
            ) VALUES (
              'judgment-provider', 'judgment-fed', 'judgment-fetch', 'statement',
              'https://example.test/statement', 'provider-hash', '{}'::jsonb, 20
            );
            INSERT INTO news_items(
              news_item_id, provider_item_id, source_id, source_domain, canonical_url,
              title, published_at_ms, fetched_at_ms, content_hash, title_fingerprint,
              lifecycle_status, story_key, story_identity_version, created_at_ms, updated_at_ms
            ) VALUES (
              'judgment-news', 'judgment-provider', 'judgment-fed', 'example.test',
              'https://example.test/statement', 'Policy statement', 20, 20,
              'news-hash', 'title-hash', 'processed', 'judgment-story', 'story-v2', 20, 20
            )
            """
        )
        conn.commit()
        before = {
            "macro": conn.execute("SELECT COUNT(*) AS count FROM macro_observations").fetchone()["count"],
            "news": conn.execute("SELECT COUNT(*) AS count FROM news_items").fetchone()["count"],
            "snapshots": conn.execute("SELECT COUNT(*) AS count FROM macro_view_snapshots").fetchone()["count"],
        }

        command.upgrade(config, "20260723_0193")
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()["version_num"]
        after = {
            "macro": conn.execute("SELECT COUNT(*) AS count FROM macro_observations").fetchone()["count"],
            "news": conn.execute("SELECT COUNT(*) AS count FROM news_items").fetchone()["count"],
            "snapshots": conn.execute("SELECT COUNT(*) AS count FROM macro_view_snapshots").fetchone()["count"],
        }
        retired = conn.execute("SELECT to_regclass('public.macro_daily_briefs') AS name").fetchone()["name"]

        _insert_job_and_publication(conn)
        conn.commit()
        with pytest.raises(RaiseException, match="immutable"):
            conn.execute(
                "UPDATE macro_judgment_publications SET memo_text = 'rewritten' WHERE session_date = '2026-07-22'"
            )
        conn.rollback()
        with pytest.raises(RaiseException, match="delete_forbidden"):
            conn.execute("DELETE FROM macro_judgment_jobs WHERE session_date = '2026-07-22'")
        conn.rollback()
        with pytest.raises(RuntimeError, match="cannot be downgraded"):
            command.downgrade(config, "20260723_0192")
    finally:
        conn.close()

    assert version == "20260723_0193"
    assert after == before
    assert retired is None


def _insert_job_and_publication(conn) -> None:
    conn.execute(
        """
        INSERT INTO macro_judgment_jobs(
          session_date, market_cutoff_ms, status, evidence_pack_json,
          evidence_pack_hash, compiler_version, selection_policy_version,
          sealed_at_ms, max_attempts, due_at_ms, created_at_ms, updated_at_ms
        ) VALUES (
          '2026-07-22', 100, 'published', '{}'::jsonb,
          'pack-hash', 'compiler-v1', 'selection-v1',
          110, 3, 110, 110, 110
        );
        INSERT INTO macro_judgment_publications(
          session_date, market_cutoff_ms, evidence_pack_hash, judgment_json,
          memo_text, review_json, agent_audit_json, model_name, prompt_version,
          schema_version, workflow_version, renderer_version, published_at_ms
        ) VALUES (
          '2026-07-22', 100, 'pack-hash', '{}'::jsonb,
          'memo', '{}'::jsonb, '{}'::jsonb, 'fake-model', 'prompt-v1',
          'schema-v1', 'workflow-v1', 'renderer-v1', 120
        )
        """
    )
