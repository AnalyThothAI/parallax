from __future__ import annotations

from alembic import command

from parallax.platform.db.postgres_migrations import alembic_config, latest_migration_version
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate
from tests.postgres_test_utils import test_postgres_dsn as _test_postgres_dsn

RETIRED_BACKEND_TABLES = {
    "projection_runs",
    "projection_offsets",
    "pulse_agent_eval_results",
    "pulse_agent_eval_cases",
    "pulse_evidence_packets",
    "pulse_agent_run_steps",
    "pulse_playbook_snapshots",
    "pulse_candidates",
    "pulse_agent_runs",
    "pulse_agent_jobs",
    "pulse_agent_runtime_versions",
    "pulse_candidate_edge_state",
    "pulse_candidate_run_budget",
    "pulse_target_run_budget",
    "pulse_trigger_dirty_targets",
    "narrative_admissions",
    "narrative_admission_dirty_targets",
    "macro_daily_briefs",
    "macro_import_runs",
    "cex_oi_radar_publication_state",
    "cex_oi_radar_rows",
    "cex_detail_snapshots",
    "account_profiles",
    "account_token_call_stats",
    "account_quality_snapshots",
    "news_item_agent_briefs",
    "news_item_agent_runs",
    "news_source_quality_rows",
    "token_radar_source_dirty_events",
    "market_tick_current_dirty_targets",
    "token_capture_tier_dirty_targets",
    "token_capture_tier",
}


def test_current_postgres_schema_has_one_kappa_truth_and_compact_read_models(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        tables = {
            row["table_name"]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()
        }
        macro_series_columns = {
            row["column_name"]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'macro_observation_series_rows'
                """
            ).fetchall()
        }
        news_source_columns = {
            row["column_name"]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'news_sources'
                """
            ).fetchall()
        }
        macro_snapshot_columns = {
            row["column_name"]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'macro_view_snapshots'
                """
            ).fetchall()
        }
        market_current_columns = {
            row["column_name"]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'market_tick_current'
                """
            ).fetchall()
        }
        news_fetch_run_fk_index = conn.execute(
            """
            SELECT index_state.indisvalid, index_state.indisready
            FROM pg_index AS index_state
            JOIN pg_class AS index_class ON index_class.oid = index_state.indexrelid
            WHERE index_class.relname = 'idx_news_provider_items_fetch_run_id'
            """
        ).fetchone()
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()["version_num"]
    finally:
        conn.close()

    assert {
        "raw_frames",
        "events",
        "token_intents",
        "token_intent_resolutions",
        "market_ticks",
        "enriched_events",
        "token_radar_current_rows",
        "token_radar_publication_state",
        "account_token_alerts",
    } <= tables
    assert RETIRED_BACKEND_TABLES.isdisjoint(tables)
    assert macro_series_columns == {
        "projection_version",
        "concept_key",
        "observed_at",
        "value_numeric",
        "source_name",
        "series_key",
        "unit",
        "frequency",
        "data_quality",
        "event_metadata_json",
    }
    assert {"config_payload_hash", "terminal_config_payload_hash"} <= news_source_columns
    assert "module_views_json" in macro_snapshot_columns
    assert "assets_brief_json" not in macro_snapshot_columns
    assert {"raw_payload_json", "payload_hash"}.isdisjoint(market_current_columns)
    assert news_fetch_run_fk_index == {"indisvalid": True, "indisready": True}
    assert version == latest_migration_version() == "20260722_0187"


def test_backend_kiss_hard_cut_migrates_nonempty_0184_state(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO public")
        conn.commit()
        config = alembic_config()
        config.attributes["database_url"] = _test_postgres_dsn()
        command.upgrade(config, "20260721_0184")

        conn.execute(
            """
            INSERT INTO projection_runs(
              run_id, projection_name, projection_version, mode, status, started_at_ms
            ) VALUES ('run-old', 'token_radar', 'v1', 'incremental', 'ready', 1);
            INSERT INTO projection_offsets(
              projection_name, projection_version, source_table, status, created_at_ms, updated_at_ms
            ) VALUES ('token_radar', 'v1', 'events', 'ready', 1, 1);

            INSERT INTO news_sources(
              source_id, provider_type, feed_url, source_domain, source_name,
              created_at_ms, updated_at_ms
            ) VALUES (
              'source-1', 'rss', 'https://example.test/feed', 'example.test', 'Example', 1, 1
            );
            INSERT INTO news_fetch_runs(
              fetch_run_id, source_id, started_at_ms, finished_at_ms, status
            ) VALUES ('fetch-old', 'source-1', 1, 2, 'success');
            INSERT INTO news_provider_items(
              provider_item_id, source_id, fetch_run_id, source_item_key, canonical_url,
              payload_hash, raw_payload_json, fetched_at_ms
            ) VALUES (
              'provider-item-old', 'source-1', 'fetch-old', 'source-item-old',
              'https://example.test/item-old', 'payload-old', '{}'::jsonb, 2
            );

            INSERT INTO token_radar_dirty_targets(
              target_type_key, identity_id, dirty_reason, payload_hash, due_at_ms,
              first_dirty_at_ms, updated_at_ms, market_dirty, repair_dirty
            ) VALUES (
              'Asset', 'asset-1', 'market_tick_written', 'target-hash', 200,
              100, 200, true, false
            );
            INSERT INTO token_radar_source_dirty_events(
              projection_version, source_event_id, target_type_key, identity_id,
              dirty_reason, payload_hash, due_at_ms, first_dirty_at_ms, updated_at_ms
            ) VALUES (
              'token-radar-v13-social-attention', 'event-1', 'Asset', 'asset-1',
              'resolution_updated', 'source-hash', 150, 50, 250
            );
            INSERT INTO worker_queue_terminal_events(
              terminal_id, worker_name, source_table, target_key, source_row_json,
              source_row_hash, final_status, final_reason, terminalized_at_ms
            ) VALUES (
              'terminal-source-queue', 'token_radar_projection',
              'token_radar_source_dirty_events', 'event-1:Asset:asset-1',
              '{}'::jsonb, 'source-row-hash', 'failed', 'retry_budget_exhausted', 1
            );

            INSERT INTO macro_observation_series_rows(
              projection_version, concept_key, observed_at, series_rank, value_numeric,
              source_name, series_key, source_priority, unit, frequency, data_quality,
              source_ts, raw_payload_json, ingested_at_ms, projected_at_ms, payload_hash
            ) VALUES (
              'macro_regime_v4', 'event:fed_fomc_statement', '2026-07-21', 1, NULL,
              'official_fed_text', 'fomc_statement_latest', 80, NULL, 'event', 'ok',
              '2026-07-21',
              '{"value":"FOMC statement","series_key":"official_fed_text:fomc_statement_latest","provenance":[{"source_url":"https://fed.example/statement","speaker":"Powell"}]}'::jsonb,
              1, 1, 'old-series-hash'
            );
            INSERT INTO macro_view_snapshots(
              projection_version, asof_date, status, regime, computed_at_ms, payload_hash
            ) VALUES (
              'macro_regime_v4', '2026-07-21', 'ready', 'risk_on', 1, 'old-snapshot-hash'
            );
            INSERT INTO macro_daily_briefs(
              brief_key, projection_version, brief_date, asof_date, status, headline,
              payload_json, computed_at_ms, updated_at_ms, payload_hash
            ) VALUES (
              'assets_today', 'macro_regime_v4', '2026-07-21', '2026-07-21', 'ready',
              'Assets today', '{"headline":"Assets today"}'::jsonb, 1, 1, 'old-brief-hash'
            );
            """
        )
        conn.commit()

        command.upgrade(config, "head")

        tables = {
            row["table_name"]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()
        }
        queue_row = conn.execute(
            """
            SELECT dirty_reason, due_at_ms, first_dirty_at_ms, updated_at_ms,
                   leased_until_ms, attempt_count, last_error, market_dirty, repair_dirty
            FROM token_radar_dirty_targets
            WHERE target_type_key = 'Asset' AND identity_id = 'asset-1'
            """
        ).fetchone()
        terminal_row = conn.execute(
            """
            SELECT operator_action, operator_reason
            FROM worker_queue_terminal_events
            WHERE terminal_id = 'terminal-source-queue'
            """
        ).fetchone()
        news_source = conn.execute(
            """
            SELECT config_payload_hash, terminal_config_payload_hash
            FROM news_sources WHERE source_id = 'source-1'
            """
        ).fetchone()
        macro_series = conn.execute(
            """
            SELECT event_metadata_json
            FROM macro_observation_series_rows
            WHERE concept_key = 'event:fed_fomc_statement'
            """
        ).fetchone()
        macro_snapshot = conn.execute(
            """
            SELECT module_views_json, payload_hash
            FROM macro_view_snapshots
            WHERE projection_version = 'macro_regime_v4'
            """
        ).fetchone()
        macro_rebuild = conn.execute(
            """
            SELECT payload_hash, dirty_reason, leased_until_ms, attempt_count
            FROM macro_projection_dirty_targets
            WHERE projection_name = 'macro_view'
              AND projection_version = 'macro_regime_v4'
              AND target_kind = 'current'
              AND target_id = 'current'
            """
        ).fetchone()
        old_fetch = conn.execute("SELECT fetch_run_id FROM news_fetch_runs WHERE fetch_run_id = 'fetch-old'").fetchone()
        retained_provider_item = conn.execute(
            """
            SELECT fetch_run_id
            FROM news_provider_items
            WHERE provider_item_id = 'provider-item-old'
            """
        ).fetchone()
    finally:
        conn.close()

    assert RETIRED_BACKEND_TABLES.isdisjoint(tables)
    assert queue_row["dirty_reason"] == "mixed"
    assert tuple(queue_row[key] for key in ("due_at_ms", "first_dirty_at_ms", "updated_at_ms")) == (150, 50, 250)
    assert queue_row["leased_until_ms"] is None
    assert queue_row["attempt_count"] == 0
    assert queue_row["last_error"] is None
    assert queue_row["market_dirty"] is True
    assert queue_row["repair_dirty"] is False
    assert tuple(terminal_row.values()) == ("archive", "queue_retired_by_0185")
    assert news_source["config_payload_hash"].startswith("sha256:")
    assert news_source["terminal_config_payload_hash"] is None
    assert macro_series["event_metadata_json"] == {
        "event_code": "official_fed_text:fomc_statement_latest",
        "source_url": "https://fed.example/statement",
        "speaker": "Powell",
        "text_value": "FOMC statement",
    }
    assert macro_snapshot is None
    assert macro_rebuild == {
        "payload_hash": "migration:20260722_0186:module_views_only",
        "dirty_reason": "migration_module_views_only_rebuild",
        "leased_until_ms": None,
        "attempt_count": 0,
    }
    assert old_fetch is None
    assert retained_provider_item == {"fetch_run_id": None}


def test_runtime_hard_cut_reconciles_nonempty_0185_backlog(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO public")
        conn.commit()
        config = alembic_config()
        config.attributes["database_url"] = _test_postgres_dsn()
        command.upgrade(config, "20260721_0185")

        conn.execute(
            """
            INSERT INTO registry_assets(
              asset_id, chain_id, token_standard, address, status, first_seen_at_ms, updated_at_ms
            ) VALUES
              (
                'asset-market-backlog', 'eip155:1', 'erc20', '0xabc',
                'canonical', 100, 100
              ),
              (
                'asset-terminal-backlog', 'eip155:1', 'erc20', '0xdef',
                'canonical', 100, 100
              ),
              (
                'asset-quarantined-backlog', 'eip155:1', 'erc20', '0xbad',
                'canonical', 100, 100
              );

            INSERT INTO market_ticks(
              observed_at_ms, tick_id, target_type, target_id, chain, token_address,
              source_tier, source_provider, received_at_ms, price_usd, raw_payload_json,
              payload_hash, created_at_ms
            ) VALUES
              (
                100, 'tick-old', 'chain_token', 'eip155:1:0xabc', 'eip155:1', '0xabc',
                'tier2_poll', 'okx_dex_rest', 110, 1.00, '{"version":"old"}'::jsonb,
                'hash-old', 111
              ),
              (
                200, 'tick-new', 'chain_token', 'eip155:1:0xabc', 'eip155:1', '0xabc',
                'tier2_poll', 'okx_dex_rest', 210, 2.00, '{"version":"new"}'::jsonb,
                'hash-new', 211
              ),
              (
                300, 'tick-terminal-only', 'chain_token', 'eip155:1:0xdef', 'eip155:1', '0xdef',
                'tier2_poll', 'okx_dex_rest', 310, 3.00, '{"version":"terminal"}'::jsonb,
                'hash-terminal', 311
              ),
              (
                400, 'tick-quarantined', 'chain_token', 'eip155:1:0xbad', 'eip155:1', '0xbad',
                'tier2_poll', 'okx_dex_rest', 410, 4.00, '{"version":"quarantined"}'::jsonb,
                'hash-quarantined', 411
              );

            INSERT INTO market_tick_current(
              target_type, target_id, tick_observed_at_ms, tick_id, source_tier,
              source_provider, chain, token_address, price_usd, raw_payload_json,
              payload_hash, updated_at_ms, created_at_ms
            ) VALUES (
              'chain_token', 'eip155:1:0xabc', 200, 'tick-new', 'tier2_poll',
              'okx_dex_rest', 'eip155:1', '0xabc', 999.00, '{"version":"corrupt"}'::jsonb,
              'hash-corrupt', 210, 211
            );

            INSERT INTO market_tick_current_dirty_targets(
              target_type, target_id, dirty_reason, payload_hash, due_at_ms,
              source_watermark_ms, priority, first_dirty_at_ms, updated_at_ms
            ) VALUES (
              'chain_token', 'eip155:1:0xabc', 'market_tick_written', 'dirty-new',
              200, 210, 0, 200, 210
            );

            INSERT INTO token_radar_dirty_targets(
              target_type_key, identity_id, dirty_reason, market_dirty, repair_dirty,
              payload_hash, due_at_ms, first_dirty_at_ms, updated_at_ms
            ) VALUES (
              'Asset', 'asset-market-backlog', 'ingest_resolution', false, false,
              'social-dirty-before-market', 150, 150, 150
            );

            INSERT INTO worker_queue_terminal_events(
              terminal_id, worker_name, source_table, target_key, source_row_json,
              source_row_hash, final_status, final_reason, attempt_count,
              payload_hash, terminalized_at_ms
            ) VALUES (
              'terminal-market-current-only', 'market_tick_current_projection',
              'market_tick_current_dirty_targets', 'chain_token:eip155:1:0xdef',
              '{"target_type":"chain_token","target_id":"eip155:1:0xdef"}'::jsonb,
              'terminal-source-hash', 'terminal', 'retry_budget_exhausted', 5,
              'dirty-terminal', 320
            );

            INSERT INTO worker_queue_terminal_events(
              terminal_id, worker_name, source_table, target_key, source_row_json,
              source_row_hash, final_status, final_reason, attempt_count,
              payload_hash, terminalized_at_ms, operator_action, operator_reason,
              operator_action_at_ms
            ) VALUES (
              'terminal-market-current-quarantined', 'market_tick_current_projection',
              'market_tick_current_dirty_targets', 'chain_token:eip155:1:0xbad',
              '{"target_type":"chain_token","target_id":"eip155:1:0xbad"}'::jsonb,
              'quarantined-source-hash', 'terminal', 'malformed_source', 5,
              'dirty-quarantined', 420, 'quarantine', 'operator_known_bad', 421
            );

            DELETE FROM macro_projection_dirty_targets
            WHERE projection_name = 'macro_view'
              AND projection_version = 'macro_regime_v4'
              AND target_kind = 'current'
              AND target_id = 'current';
            INSERT INTO macro_view_snapshots(
              projection_version, asof_date, status, regime, computed_at_ms, payload_hash,
              assets_brief_json, module_views_json
            ) VALUES (
              'macro_regime_v4', '2026-07-21', 'ready', 'risk_on', 100, 'snapshot-old',
              '{"headline":"legacy"}'::jsonb, '{"assets":{"status":"ready"}}'::jsonb
            );
            """
        )
        conn.commit()

        command.upgrade(config, "head")

        current = conn.execute(
            """
            SELECT tick_id, tick_observed_at_ms, updated_at_ms, price_usd
            FROM market_tick_current
            WHERE target_type = 'chain_token' AND target_id = 'eip155:1:0xabc'
            """
        ).fetchone()
        radar_dirty = conn.execute(
            """
            SELECT dirty_reason, market_dirty, repair_dirty, leased_until_ms, attempt_count
            FROM token_radar_dirty_targets
            WHERE target_type_key = 'Asset' AND identity_id = 'asset-market-backlog'
            """
        ).fetchone()
        terminal_current = conn.execute(
            """
            SELECT tick_id, tick_observed_at_ms, updated_at_ms, price_usd
            FROM market_tick_current
            WHERE target_type = 'chain_token' AND target_id = 'eip155:1:0xdef'
            """
        ).fetchone()
        terminal_radar_dirty = conn.execute(
            """
            SELECT dirty_reason, market_dirty, repair_dirty, leased_until_ms, attempt_count
            FROM token_radar_dirty_targets
            WHERE target_type_key = 'Asset' AND identity_id = 'asset-terminal-backlog'
            """
        ).fetchone()
        terminal_evidence = conn.execute(
            """
            SELECT operator_action, operator_reason
            FROM worker_queue_terminal_events
            WHERE terminal_id = 'terminal-market-current-only'
            """
        ).fetchone()
        quarantined_current = conn.execute(
            """
            SELECT tick_id
            FROM market_tick_current
            WHERE target_type = 'chain_token' AND target_id = 'eip155:1:0xbad'
            """
        ).fetchone()
        quarantined_radar_dirty = conn.execute(
            """
            SELECT identity_id
            FROM token_radar_dirty_targets
            WHERE target_type_key = 'Asset' AND identity_id = 'asset-quarantined-backlog'
            """
        ).fetchone()
        quarantined_evidence = conn.execute(
            """
            SELECT operator_action, operator_reason
            FROM worker_queue_terminal_events
            WHERE terminal_id = 'terminal-market-current-quarantined'
            """
        ).fetchone()
        retired_queue = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'market_tick_current_dirty_targets'
            """
        ).fetchone()
        macro_snapshot = conn.execute(
            "SELECT projection_version FROM macro_view_snapshots WHERE projection_version = 'macro_regime_v4'"
        ).fetchone()
        macro_rebuild = conn.execute(
            """
            SELECT payload_hash, dirty_reason, leased_until_ms, attempt_count
            FROM macro_projection_dirty_targets
            WHERE projection_name = 'macro_view'
              AND projection_version = 'macro_regime_v4'
              AND target_kind = 'current'
              AND target_id = 'current'
            """
        ).fetchone()
    finally:
        conn.close()

    assert current == {
        "tick_id": "tick-new",
        "tick_observed_at_ms": 200,
        "updated_at_ms": 210,
        "price_usd": 2,
    }
    assert radar_dirty == {
        "dirty_reason": "mixed",
        "market_dirty": True,
        "repair_dirty": False,
        "leased_until_ms": None,
        "attempt_count": 0,
    }
    assert terminal_current == {
        "tick_id": "tick-terminal-only",
        "tick_observed_at_ms": 300,
        "updated_at_ms": 310,
        "price_usd": 3,
    }
    assert terminal_radar_dirty == {
        "dirty_reason": "market_tick_current_changed",
        "market_dirty": True,
        "repair_dirty": False,
        "leased_until_ms": None,
        "attempt_count": 0,
    }
    assert terminal_evidence == {
        "operator_action": "archive",
        "operator_reason": "queue_retired_by_0186",
    }
    assert quarantined_current is None
    assert quarantined_radar_dirty is None
    assert quarantined_evidence == {
        "operator_action": "quarantine",
        "operator_reason": "operator_known_bad",
    }
    assert retired_queue is None
    assert macro_snapshot is None
    assert macro_rebuild == {
        "payload_hash": "migration:20260722_0186:module_views_only",
        "dirty_reason": "migration_module_views_only_rebuild",
        "leased_until_ms": None,
        "attempt_count": 0,
    }


def test_postgres_migrations_are_idempotent_at_current_head(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        migrate(conn)
        rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
    finally:
        conn.close()

    assert [row["version_num"] for row in rows] == [latest_migration_version()]
