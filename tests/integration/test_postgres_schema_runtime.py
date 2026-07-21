from __future__ import annotations

from alembic import command

from parallax.domains.evidence.repositories.evidence_repository import EvidenceRepository
from parallax.platform.db.postgres_migrations import alembic_config, latest_migration_version
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate
from tests.postgres_test_utils import test_postgres_dsn as _test_postgres_dsn

_SIGNAL_PULSE_TABLES = (
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
)


def test_postgres_schema_bootstraps_core_tables(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        names = {
            row["name"]
            for row in conn.execute(
                "SELECT table_name AS name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()
        }
        hard_cut_columns = {
            (row["table_name"], row["column_name"])
            for row in conn.execute(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'projection_runs',
                    'narrative_admissions',
                    'cex_detail_snapshots',
                    'macro_view_snapshots',
                    'account_quality_snapshots',
                    'registry_assets',
                    'cex_tokens',
                    'price_feeds'
                  )
                """
            ).fetchall()
        }
        hard_cut_primary_keys = {
            row["table_name"]: _postgres_array_text(row["columns"])
            for row in conn.execute(
                """
                SELECT tc.table_name,
                       array_agg(kcu.column_name ORDER BY kcu.ordinal_position) AS columns
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                 AND tc.table_name = kcu.table_name
                WHERE tc.table_schema = 'public'
                  AND tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_name IN (
                    'narrative_admissions',
                    'cex_detail_snapshots',
                    'macro_view_snapshots',
                    'account_quality_snapshots'
                  )
                GROUP BY tc.table_name
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert "alembic_version" in names
    assert "raw_frames" in names
    assert "events" in names
    assert "event_fts" not in names
    assert "event_entities" in names
    assert "notifications" in names
    assert "projection_offsets" in names
    assert "projection_runs" in names
    assert "token_evidence" in names
    assert "token_intents" in names
    assert "token_intent_evidence" in names
    assert "token_intent_resolutions" in names
    assert "token_radar_current_rows" in names
    assert "token_radar_publication_state" in names
    for legacy_table in (
        "cex_derivative_series",
        "projection_dirty_ranges",
        "token_radar_storage_maintenance_runs",
        "token_radar_publications",
        "token_flow_window_snapshots",
        "token_social_bucket_authors",
        "token_social_buckets",
        "model_runs",
        "discussion_digest_dirty_targets",
        "narrative_model_runs",
        "token_mention_semantics",
        "token_discussion_digests",
        "registry_aliases",
        "registry_versions",
        "schema_migrations",
        "token_aliases",
        "projects",
        "pulse_agent_eval_cases",
        "pulse_agent_eval_results",
        "pulse_agent_jobs",
        "pulse_agent_run_steps",
        "pulse_agent_runs",
        "pulse_agent_runtime_versions",
        "pulse_candidate_edge_state",
        "pulse_candidate_run_budget",
        "pulse_candidates",
        "pulse_evidence_packets",
        "pulse_playbook_snapshots",
        "pulse_target_run_budget",
        "pulse_trigger_dirty_targets",
        "token_radar_projection_coverage",
        "token_radar_snapshot_audit",
        "token_radar_rank_history",
        "token_radar_rows",
        "token_radar_retention_runs",
        "asset_mentions",
        "asset_attributions",
        "asset_resolution_jobs",
        "event_token_mentions",
        "event_token_attributions",
        "token_market_snapshots",
        "token_market_observations",
        "token_signal_snapshots",
        "assets",
        "asset_aliases",
        "asset_venues",
        "asset_market_snapshots",
        "asset_signal_snapshots",
        "asset_signal_outcomes",
        "token_intent_resolution_candidates",
        "market_provider_observations",
        "current_market_field_facts",
        "token_market_price_baselines",
        "attention_seeds",
        "event_clusters",
        "harness_snapshots",
        "harness_decisions",
        "harness_outcomes",
        "harness_credits",
        "harness_weights",
    ):
        assert legacy_table not in names
    assert hard_cut_primary_keys == {
        "narrative_admissions": ["target_type", "target_id", "window", "scope"],
        "cex_detail_snapshots": ["exchange", "native_market_id"],
        "macro_view_snapshots": ["projection_version"],
        "account_quality_snapshots": ["handle", "window"],
    }
    assert {
        ("projection_runs", "dirty_ranges_written"),
        ("narrative_admissions", "admission_id"),
        ("narrative_admissions", "next_semantics_due_at_ms"),
        ("narrative_admissions", "next_digest_due_at_ms"),
        ("narrative_admissions", "suppressed_at_ms"),
        ("cex_detail_snapshots", "snapshot_id"),
        ("macro_view_snapshots", "snapshot_id"),
        ("account_quality_snapshots", "snapshot_id"),
        ("registry_assets", "project_id"),
        ("cex_tokens", "project_id"),
        ("price_feeds", "base_project_id"),
    }.isdisjoint(hard_cut_columns)


def test_backend_kappa_hard_cut_migrates_nonempty_0182_state(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO public")
        conn.commit()
        config = alembic_config()
        config.attributes["database_url"] = _test_postgres_dsn()
        command.upgrade(config, "20260623_0182")

        conn.execute(
            """
            INSERT INTO projects(project_id, status, evidence_level, primary_source, first_seen_at_ms, updated_at_ms)
            VALUES ('project-1', 'active', 'verified', 'seed', 1, 2);
            INSERT INTO registry_assets(
              asset_id, project_id, chain_id, token_standard, address, status, first_seen_at_ms, updated_at_ms
            ) VALUES ('asset-1', 'project-1', 'solana', 'spl', 'address-1', 'active', 1, 2);
            INSERT INTO cex_tokens(
              cex_token_id, project_id, base_symbol, status, evidence_level, first_seen_at_ms, updated_at_ms
            ) VALUES ('cex-1', 'project-1', 'AAA', 'active', 'verified', 1, 2);
            INSERT INTO price_feeds(
              pricefeed_id, feed_type, provider, subject_type, subject_id,
              base_asset_id, base_cex_token_id, base_project_id,
              status, evidence_level, first_seen_at_ms, updated_at_ms
            ) VALUES (
              'feed-1', 'cex', 'seed', 'Asset', 'asset-1', 'asset-1', 'cex-1', 'project-1',
              'active', 'verified', 1, 2
            );
            INSERT INTO asset_profiles(
              asset_id, provider, status, observed_at_ms, next_refresh_at_ms, created_at_ms, updated_at_ms
            ) VALUES ('asset-1', 'gmgn', 'ready', 777, 999, 1, 2);
            INSERT INTO token_profile_current_dirty_targets(
              target_type, target_id, dirty_reason, payload_hash, source_watermark_ms,
              priority, due_at_ms, leased_until_ms, lease_owner, attempt_count,
              last_error, first_dirty_at_ms, updated_at_ms
            ) VALUES
              ('Asset', 'asset-1', 'old', 'old', 0, 100, 999999, 888, 'worker', 4, 'boom', 1, 2),
              ('Asset', 'orphan', 'old', 'old', 0, 100, 999999, NULL, NULL, 0, NULL, 1, 2);
            INSERT INTO token_radar_target_features(
              projection_version, "window", scope, lane, target_type_key, identity_id,
              target_type, target_id, latest_event_received_at_ms,
              payload_hash, last_scored_at_ms, created_at_ms, updated_at_ms
            ) VALUES (
              'token-radar-v13-social-attention', '1h', 'all', 'resolved',
              'Asset', 'asset-feature', 'Asset', 'asset-feature', 555, 'feature-hash', 555, 1, 2
            );
            INSERT INTO token_radar_current_rows(
              row_id, projection_version, "window", scope, lane, target_type_key, identity_id,
              computed_at_ms, source_max_received_at_ms, rank, rank_score,
              factor_version, decision, payload_hash, listed_at_ms, created_at_ms,
              generation_id, published_at_ms, source_frontier_ms, quality_status
            ) VALUES (
              'row-1', 'token-radar-v13-social-attention', '1h', 'all', 'resolved',
              'Asset', 'asset-current', 600, 600, 1, 1.0,
              'factor-v1', 'observe', 'row-hash', 1, 1, 'generation-1', 600, 600, 'ready'
            );
            INSERT INTO token_radar_dirty_targets(
              target_type_key, identity_id, dirty_reason, payload_hash, due_at_ms,
              leased_until_ms, lease_owner, attempt_count, last_error,
              first_dirty_at_ms, updated_at_ms, market_dirty, repair_dirty
            ) VALUES (
              'Asset', 'asset-feature', 'market', 'market-hash', 999999,
              888, 'worker', 3, 'boom', 1, 2, true, false
            );
            INSERT INTO narrative_admissions(
              admission_id, target_type, target_id, "window", scope, schema_version,
              status, reason, priority, source_max_received_at_ms,
              admitted_at_ms, last_seen_at_ms, updated_at_ms, projection_computed_at_ms,
              source_event_count, independent_author_count, payload_hash
            ) VALUES
              ('admission-current', 'Asset', 'narrative-1', '1h', 'all', 'narrative_intel_v1',
               'admitted', 'seed', 1, 100, 1, 100, 100, 100, 1, 1, 'current'),
              ('admission-legacy-newer', 'Asset', 'narrative-1', '1h', 'all', 'legacy_v0',
               'admitted', 'seed', 1, 900, 1, 900, 900, 900, 1, 1, 'legacy-newer'),
              ('admission-legacy-only', 'Asset', 'narrative-2', '1h', 'all', 'legacy_v0',
               'admitted', 'seed', 1, 700, 1, 700, 700, 700, 1, 1, 'legacy-only');
            INSERT INTO narrative_admission_dirty_targets(
              target_type, target_id, "window", scope, projection_version, schema_version,
              dirty_reason, payload_hash, source_watermark_ms, priority, due_at_ms,
              leased_until_ms, lease_owner, attempt_count, last_error, first_dirty_at_ms, updated_at_ms
            ) VALUES (
              'Asset', 'narrative-1', '1h', 'all', 'old-projection', 'legacy_v0',
              'old', 'old', 50, 100, 999999, 888, 'worker', 3, 'boom', 1, 2
            );
            INSERT INTO cex_detail_snapshots(
              snapshot_id, target_id, exchange, native_market_id, base_symbol,
              status, baseline_status, coinglass_status, computed_at_ms, payload_hash
            ) VALUES (
              'cex-snapshot', 'cex-1', 'binance', 'AAAUSDT', 'AAA',
              'ready', 'ready', 'ready', 101, 'cex-hash'
            );
            INSERT INTO macro_view_snapshots(
              snapshot_id, projection_version, asof_date, status, regime, computed_at_ms, payload_hash
            ) VALUES ('macro-snapshot', 'macro-v1', '2026-07-13', 'ready', 'risk_on', 102, 'macro-hash');
            INSERT INTO account_quality_snapshots(snapshot_id, handle, "window", sample_size, updated_at_ms)
            VALUES ('account-quality:alice:30d:current', 'alice', '30d', 12, 103)
            """
        )
        conn.commit()

        command.upgrade(config, "head")

        narratives = conn.execute(
            """
            SELECT target_id, schema_version, source_max_received_at_ms
            FROM narrative_admissions
            ORDER BY target_id
            """
        ).fetchall()
        narrative_queue = conn.execute(
            """
            SELECT target_id, schema_version, source_watermark_ms,
                   leased_until_ms, lease_owner, attempt_count, last_error
            FROM narrative_admission_dirty_targets
            ORDER BY target_id
            """
        ).fetchall()
        radar_queue = conn.execute(
            """
            SELECT identity_id, dirty_reason, leased_until_ms, lease_owner,
                   attempt_count, last_error, market_dirty, repair_dirty
            FROM token_radar_dirty_targets
            ORDER BY identity_id
            """
        ).fetchall()
        profile_queue = conn.execute(
            """
            SELECT target_id, source_watermark_ms, leased_until_ms,
                   lease_owner, attempt_count, last_error
            FROM token_profile_current_dirty_targets
            ORDER BY target_id
            """
        ).fetchall()
        target_feature_count = conn.execute("SELECT count(*) AS count FROM token_radar_target_features").fetchone()[
            "count"
        ]
        retained_snapshots = (
            conn.execute("SELECT exchange, native_market_id FROM cex_detail_snapshots").fetchall(),
            conn.execute("SELECT projection_version FROM macro_view_snapshots").fetchall(),
            conn.execute('SELECT handle, "window" FROM account_quality_snapshots').fetchall(),
        )
        retained_registry_rows = (
            conn.execute("SELECT asset_id FROM registry_assets").fetchall(),
            conn.execute("SELECT cex_token_id FROM cex_tokens").fetchall(),
            conn.execute("SELECT pricefeed_id, base_asset_id, base_cex_token_id FROM price_feeds").fetchall(),
        )
        tables = {
            row["table_name"]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert [tuple(row.values()) for row in narratives] == [("narrative-1", "narrative_intel_v1", 100)]
    assert [tuple(row.values()) for row in narrative_queue] == [
        ("narrative-1", "narrative_intel_v1", 900, None, None, 0, None),
        ("narrative-2", "narrative_intel_v1", 700, None, None, 0, None),
    ]
    assert [tuple(row.values()) for row in radar_queue] == [
        ("asset-current", "schema_hard_cut_0183", None, None, 0, None, False, True),
        ("asset-feature", "mixed", None, None, 0, None, True, True),
    ]
    assert [tuple(row.values()) for row in profile_queue] == [("asset-1", 777, None, None, 0, None)]
    assert target_feature_count == 0
    assert [tuple(row.values()) for row in retained_snapshots[0]] == [("binance", "AAAUSDT")]
    assert [tuple(row.values()) for row in retained_snapshots[1]] == [("macro-v1",)]
    assert [tuple(row.values()) for row in retained_snapshots[2]] == [("alice", "30d")]
    assert [tuple(row.values()) for row in retained_registry_rows[0]] == [("asset-1",)]
    assert [tuple(row.values()) for row in retained_registry_rows[1]] == [("cex-1",)]
    assert [tuple(row.values()) for row in retained_registry_rows[2]] == [("feed-1", "asset-1", "cex-1")]
    assert "projects" not in tables


def test_signal_pulse_hard_delete_migrates_nonempty_fk_graph_and_preserves_kappa_state(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        # Test-harness reset only. The 0184 upgrade below must drop the populated
        # FK graph itself and is separately guarded against DROP ... CASCADE.
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO public")
        conn.commit()
        config = alembic_config()
        config.attributes["database_url"] = _test_postgres_dsn()
        command.upgrade(config, "20260713_0183")

        EvidenceRepository(conn).insert_event(
            make_event(
                "event-kappa-retained",
                text="$KEEP material fact survives the Signal Pulse hard cut",
                received_at_ms=1_000,
            ),
            is_watched=True,
        )
        conn.execute(
            """
            INSERT INTO token_radar_current_rows(
              row_id, projection_version, "window", scope, lane, target_type_key, identity_id,
              computed_at_ms, source_max_received_at_ms, rank, rank_score,
              event_id, factor_version, decision, source_event_ids_json, payload_hash,
              listed_at_ms, created_at_ms, generation_id, published_at_ms,
              source_frontier_ms, quality_status
            ) VALUES (
              'radar-kappa-retained', 'token-radar-v13-social-attention', '1h', 'all', 'resolved',
              'Asset', 'asset-kappa-retained', 1000, 1000, 1, 1.0,
              'event-kappa-retained', 'factor-v1', 'observe', '["event-kappa-retained"]'::jsonb,
              'radar-kappa-hash', 1000, 1000, 'generation-kappa', 1000, 1000, 'ready'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO pulse_agent_runtime_versions(
              runtime_hash, runtime_version, strategy, provider, model,
              prompt_version, schema_version, manifest_json, created_at_ms
            ) VALUES (
              'runtime-hash', 'runtime-v1', 'single_decision', 'test', 'test-model',
              'prompt-v1', 'schema-v1', '{}'::jsonb, 1000
            );
            INSERT INTO pulse_agent_jobs(
              job_id, candidate_id, candidate_type, subject_key, "window", scope,
              trigger_signature, timeline_signature, priority, status,
              next_run_at_ms, created_at_ms, updated_at_ms
            ) VALUES (
              'job-1', 'candidate-1', 'token_target', 'Asset:asset-1', '1h', 'all',
              'trigger-1', 'timeline-1', 1, 'done', 1000, 1000, 1000
            );
            INSERT INTO pulse_agent_runs(
              run_id, job_id, candidate_id, provider, model, workflow_name, agent_name,
              artifact_version_hash, prompt_version, schema_version, input_hash,
              status, request_json, started_at_ms, finished_at_ms, outcome,
              runtime_version, runtime_hash
            ) VALUES (
              'run-1', 'job-1', 'candidate-1', 'test', 'test-model', 'pulse', 'pulse-agent',
              'artifact-hash', 'prompt-v1', 'schema-v1', 'input-hash',
              'done', '{}'::jsonb, 1000, 1001, 'completed', 'runtime-v1', 'runtime-hash'
            );
            INSERT INTO pulse_candidates(
              candidate_id, candidate_type, subject_key, target_type, target_id,
              "window", scope, pulse_status, verdict, social_phase,
              candidate_score, score_band, trigger_signature, timeline_signature,
              pulse_version, gate_version, prompt_version, schema_version,
              created_at_ms, updated_at_ms
            ) VALUES (
              'candidate-1', 'token_target', 'Asset:asset-1', 'Asset', 'asset-1',
              '1h', 'all', 'token_watch', 'watch', 'attention',
              0.75, 'high', 'trigger-1', 'timeline-1',
              'pulse-v1', 'gate-v1', 'prompt-v1', 'schema-v1', 1000, 1000
            );
            INSERT INTO pulse_playbook_snapshots(
              playbook_id, candidate_id, target_type, target_id, horizon,
              decision_time_ms, playbook_status, side, setup_json,
              confirmation_json, invalidation_json, risk_json,
              playbook_version, created_at_ms
            ) VALUES (
              'playbook-1', 'candidate-1', 'Asset', 'asset-1', '4h',
              1000, 'watch', 'long', '{}'::jsonb,
              '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, 'playbook-v1', 1000
            );
            INSERT INTO pulse_agent_run_steps(
              step_id, run_id, stage, route, provider, model,
              prompt_version, schema_version, status,
              started_at_ms, finished_at_ms, created_at_ms
            ) VALUES (
              'step-1', 'run-1', 'pulse_decision', 'research_only', 'test', 'test-model',
              'prompt-v1', 'schema-v1', 'ok', 1000, 1001, 1000
            );
            INSERT INTO pulse_evidence_packets(
              evidence_packet_id, run_id, candidate_id, target_type, target_id,
              "window", scope, schema_version, evidence_packet_hash,
              packet_json, created_at_ms
            ) VALUES (
              'packet-1', 'run-1', 'candidate-1', 'Asset', 'asset-1',
              '1h', 'all', 'schema-v1', 'packet-hash', '{}'::jsonb, 1000
            );
            INSERT INTO pulse_agent_eval_cases(
              eval_case_id, source_run_id, runtime_hash, eval_type, route,
              recommendation, status, created_at_ms
            ) VALUES (
              'eval-case-1', 'run-1', 'runtime-hash', 'deterministic', 'research_only',
              'watchlist', 'active', 1000
            );
            INSERT INTO pulse_agent_eval_results(
              eval_result_id, eval_case_id, runtime_hash, status,
              score, grader_version, created_at_ms
            ) VALUES (
              'eval-result-1', 'eval-case-1', 'runtime-hash', 'pass',
              1.0, 'grader-v1', 1000
            );
            INSERT INTO pulse_candidate_edge_state(
              candidate_id, observed_at_ms, created_at_ms, updated_at_ms
            ) VALUES ('candidate-1', 1000, 1000, 1000);
            INSERT INTO pulse_candidate_run_budget(
              candidate_id, hour_bucket_ms, created_at_ms, updated_at_ms
            ) VALUES ('candidate-1', 0, 1000, 1000);
            INSERT INTO pulse_target_run_budget(
              target_type, target_id, hour_bucket_ms, created_at_ms, updated_at_ms
            ) VALUES ('Asset', 'asset-1', 0, 1000, 1000);
            INSERT INTO pulse_trigger_dirty_targets(
              target_type, target_id, "window", scope, dirty_reason,
              payload_hash, due_at_ms, first_dirty_at_ms, updated_at_ms
            ) VALUES (
              'Asset', 'asset-1', '1h', 'all', 'source_changed',
              'dirty-hash', 1000, 1000, 1000
            )
            """
        )
        conn.execute(
            """
            INSERT INTO notifications(
              notification_id, dedup_key, rule_id, severity, title, body,
              entity_type, source_table, source_id,
              first_seen_at_ms, last_seen_at_ms, created_at_ms, updated_at_ms
            ) VALUES
              ('notification-pulse-rule', 'dedup-pulse-rule', 'signal_pulse_candidate',
               'info', 'pulse', 'pulse', 'token', 'events', 'event-kappa-retained', 1000, 1000, 1000, 1000),
              ('notification-pulse-source', 'dedup-pulse-source', 'generic',
               'info', 'pulse', 'pulse', 'token', 'pulse_candidates', 'candidate-1', 1000, 1000, 1000, 1000),
              ('notification-pulse-entity', 'dedup-pulse-entity', 'generic',
               'info', 'pulse', 'pulse', 'pulse_candidate', 'events', 'event-kappa-retained',
               1000, 1000, 1000, 1000),
              ('notification-kappa-retained', 'dedup-kappa-retained', 'generic',
               'info', 'kappa', 'kappa', 'event', 'events', 'event-kappa-retained',
               1000, 1000, 1000, 1000)
            """
        )
        conn.execute(
            """
            INSERT INTO worker_queue_terminal_events(
              terminal_id, worker_name, source_table, target_key,
              source_row_json, source_row_hash, final_status, final_reason,
              terminalized_at_ms
            ) VALUES
              ('terminal-pulse-worker', 'pulse_candidate', 'events', 'event-kappa-retained',
               '{}'::jsonb, 'source-hash-1', 'failed', 'seed', 1000),
              ('terminal-pulse-job', 'generic', 'pulse_agent_jobs', 'job-1',
               '{}'::jsonb, 'source-hash-2', 'failed', 'seed', 1000),
              ('terminal-pulse-dirty', 'generic', 'pulse_trigger_dirty_targets', 'Asset:asset-1:1h:all',
               '{}'::jsonb, 'source-hash-3', 'failed', 'seed', 1000),
              ('terminal-kappa-retained', 'generic', 'events', 'event-kappa-retained',
               '{}'::jsonb, 'source-hash-4', 'failed', 'seed', 1000)
            """
        )
        conn.commit()

        pulse_counts_before = {
            table: conn.execute(f'SELECT count(*) AS count FROM "{table}"').fetchone()["count"]
            for table in _SIGNAL_PULSE_TABLES
        }

        command.upgrade(config, "head")

        retired_relations = {
            table: conn.execute("SELECT to_regclass(%s) AS relation", (f"public.{table}",)).fetchone()["relation"]
            for table in _SIGNAL_PULSE_TABLES
        }
        notification_ids = [
            row["notification_id"]
            for row in conn.execute("SELECT notification_id FROM notifications ORDER BY notification_id").fetchall()
        ]
        terminal_ids = [
            row["terminal_id"]
            for row in conn.execute(
                "SELECT terminal_id FROM worker_queue_terminal_events ORDER BY terminal_id"
            ).fetchall()
        ]
        retained_event = conn.execute(
            "SELECT event_id, logical_dedup_key FROM events WHERE event_id = 'event-kappa-retained'"
        ).fetchone()
        retained_radar = conn.execute(
            "SELECT row_id, payload_hash FROM token_radar_current_rows WHERE row_id = 'radar-kappa-retained'"
        ).fetchone()
        migration_version = conn.execute("SELECT version_num FROM alembic_version").fetchone()["version_num"]
    finally:
        conn.close()

    assert pulse_counts_before == dict.fromkeys(_SIGNAL_PULSE_TABLES, 1)
    assert retired_relations == dict.fromkeys(_SIGNAL_PULSE_TABLES)
    assert notification_ids == ["notification-kappa-retained"]
    assert terminal_ids == ["terminal-kappa-retained"]
    assert tuple(retained_event.values()) == ("event-kappa-retained", "tweet:event-kappa-retained")
    assert tuple(retained_radar.values()) == ("radar-kappa-retained", "radar-kappa-hash")
    assert migration_version == latest_migration_version()


def test_postgres_generated_tsvector_matches_inserted_event(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        EvidenceRepository(conn).insert_event(
            make_event(text="$PEPE mainnet stablecoin on base"),
            is_watched=True,
        )
        rows = conn.execute(
            """
            SELECT event_id
            FROM events
            WHERE search_tsv @@ websearch_to_tsquery('simple', %s)
            """,
            ("stablecoin base",),
        ).fetchall()
    finally:
        conn.close()

    assert [row["event_id"] for row in rows] == ["event-1"]


def test_search_v2_schema_contains_trigram_extension_and_indexes(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        extensions = {
            row["extname"]
            for row in conn.execute("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'").fetchall()
        }
        indexes = {
            row["indexname"]
            for row in conn.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'events'"
            ).fetchall()
        }
        columns = {
            row["column_name"]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'events'
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert "pg_trgm" in extensions
    assert "idx_events_search_tsv" in indexes
    assert "idx_events_search_text_trgm" in indexes
    assert "search_tsv" in columns


def test_alembic_migration_is_idempotent(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        migrate(conn)
        rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
    finally:
        conn.close()

    assert [row["version_num"] for row in rows] == [latest_migration_version()]


def test_token_radar_schema_supports_span_aware_intents(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        entity_columns = {
            row["column_name"]: row["is_nullable"]
            for row in conn.execute(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'event_entities'
                """
            ).fetchall()
        }
        intent_columns = {
            row["column_name"]: row["is_nullable"]
            for row in conn.execute(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'token_intents'
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert {"text_surface", "span_start", "span_end", "sentence_id", "local_group_key"}.issubset(entity_columns)
    assert {"display_symbol", "chain_hint", "address_hint", "intent_status"}.issubset(intent_columns)
    assert intent_columns["intent_status"] == "NO"


def test_token_radar_schema_supports_hard_cut_targets(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        table_names = {
            row["table_name"]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()
        }
        resolution_columns = {
            row["column_name"]: row["is_nullable"]
            for row in conn.execute(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'token_intent_resolutions'
                """
            ).fetchall()
        }
        radar_columns = {
            row["column_name"]: row
            for row in conn.execute(
                """
                SELECT column_name, is_nullable, data_type, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'token_radar_current_rows'
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert {"registry_assets", "cex_tokens", "price_feeds"}.issubset(table_names)
    assert {"market_ticks", "enriched_events", "token_capture_tier"}.issubset(table_names)
    assert _legacy_price_table() not in table_names
    assert {"token_discovery_results", "token_intent_lookup_keys"}.issubset(table_names)
    assert "discovery_tasks" not in table_names
    assert {"target_type", "target_id", "pricefeed_id", "reason_codes_json", "lookup_keys_json"}.issubset(
        resolution_columns
    )
    assert resolution_columns["identity_status"] == "YES"
    assert {"target_type", "target_id", "pricefeed_id"}.issubset(radar_columns)
    assert {
        "asset_json",
        "primary_venue_json",
        "target_json",
        "attention_json",
        "market_json",
        "price_json",
        "score_json",
    }.isdisjoint(radar_columns)
    assert radar_columns["rank_score"]["is_nullable"] == "NO"
    assert radar_columns["quality_status"]["is_nullable"] == "NO"
    assert radar_columns["degraded_reasons_json"]["is_nullable"] == "NO"
    assert radar_columns["factor_snapshot_json"]["is_nullable"] == "NO"


def test_runtime_schema_drops_retired_product_tables(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        equity_prefix = "equity"
        deleted_event_prefix = "_".join(("equity", "event"))
        deleted_company_prefix = "_".join(("equity", "company"))
        deleted_tables = {
            f"{deleted_event_prefix}_process_jobs",
            f"{deleted_event_prefix}_evidence_jobs",
            f"{deleted_event_prefix}_projection_dirty_targets",
            f"{deleted_event_prefix}_brief_states",
            f"{deleted_event_prefix}_evidence_artifacts",
            f"{deleted_company_prefix}_timeline_rows",
            f"{deleted_event_prefix}_alert_candidates",
            f"{deleted_event_prefix}_calendar_rows",
            f"{deleted_event_prefix}_page_rows",
            f"{deleted_event_prefix}_agent_briefs",
            f"{deleted_event_prefix}_agent_runs",
            f"{deleted_event_prefix}_story_members",
            f"{deleted_event_prefix}_story_groups",
            f"{deleted_event_prefix}_fact_candidates",
            f"{deleted_event_prefix}_source_spans",
            f"{deleted_company_prefix}_events",
            f"{equity_prefix}_section_diffs",
            f"{equity_prefix}_document_revisions",
            f"{deleted_event_prefix}_documents",
            f"{equity_prefix}_provider_documents",
            f"{equity_prefix}_expected_events",
            f"{deleted_event_prefix}_universe_members",
            f"{deleted_event_prefix}_fetch_runs",
            f"{deleted_event_prefix}_sources",
        }
        table_names = {
            row["table_name"]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert deleted_tables.isdisjoint(table_names)


def test_runtime_schema_drops_dead_token_factor_evaluations_and_keeps_market_fact_indexes(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        token_factor_table = conn.execute(
            """
            SELECT to_regclass('public.token_score_evaluations') AS table_name
            """
        ).fetchone()
        market_fact_indexes = {
            row["indexname"]
            for row in conn.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename IN ('market_ticks', 'enriched_events')
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert token_factor_table["table_name"] is None
    assert {
        "idx_market_ticks_target_observed",
        "idx_enriched_events_target_time",
    }.issubset(market_fact_indexes)


def test_market_ticks_update_still_rejected_by_trigger(tmp_path):
    import pytest
    from psycopg.errors import RaiseException

    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_pending_backfill_row(conn)
        try:
            with pytest.raises(RaiseException) as exc_info:
                conn.execute(
                    """
                    UPDATE market_ticks
                    SET liquidity_usd = liquidity_usd + 1
                    WHERE tick_id = %s
                    """,
                    ("tick-async-target",),
                )
        finally:
            conn.rollback()
    finally:
        conn.close()

    assert "market facts are append-only" in str(exc_info.value)


def test_enriched_events_pending_backfill_to_async_backfill_transition_succeeds(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_pending_backfill_row(conn)
        conn.execute(
            """
            UPDATE enriched_events
            SET tick_id = %s,
                tick_observed_at_ms = %s,
                tick_lag_ms = 100,
                capture_method = 'tier3_inline',
                capture_reason = 'async_backfill'
            WHERE event_id = 'event-async'
              AND intent_id = 'intent-async'
              AND capture_method = 'unavailable'
              AND capture_reason = 'pending_backfill'
              AND tick_id IS NULL
            """,
            ("tick-async-target", 1),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT capture_method, capture_reason, tick_observed_at_ms, tick_id, tick_lag_ms
            FROM enriched_events
            WHERE event_id = 'event-async' AND intent_id = 'intent-async'
            """
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["capture_method"] == "tier3_inline"
    assert row["capture_reason"] == "async_backfill"
    assert row["tick_observed_at_ms"] == 1
    assert row["tick_id"] == "tick-async-target"
    assert row["tick_lag_ms"] == 100


def test_enriched_events_pending_backfill_to_terminal_unavailable_transition_succeeds(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_pending_backfill_row(conn)
        conn.execute(
            """
            UPDATE enriched_events
            SET capture_method = 'unavailable',
                capture_reason = 'backfill_expired'
            WHERE event_id = 'event-async'
              AND intent_id = 'intent-async'
              AND capture_method = 'unavailable'
              AND capture_reason = 'pending_backfill'
              AND tick_id IS NULL
            """
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT capture_method, capture_reason, tick_id, tick_lag_ms
            FROM enriched_events
            WHERE event_id = 'event-async' AND intent_id = 'intent-async'
            """
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["capture_method"] == "unavailable"
    assert row["capture_reason"] == "backfill_expired"
    assert row["tick_id"] is None
    assert row["tick_lag_ms"] is None


def test_enriched_events_other_updates_are_rejected_by_trigger(tmp_path):
    import pytest
    from psycopg.errors import RaiseException

    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_pending_backfill_row(conn)
        try:
            # Same pending_backfill -> async_backfill semantics, but mutating
            # an immutable column (t_event_ms) must still be denied.
            with pytest.raises(RaiseException) as exc_info:
                conn.execute(
                    """
                    UPDATE enriched_events
                    SET tick_id = %s,
                        tick_observed_at_ms = %s,
                        tick_lag_ms = 100,
                        capture_method = 'tier3_inline',
                        capture_reason = 'async_backfill',
                        t_event_ms = t_event_ms + 1
                    WHERE event_id = 'event-async' AND intent_id = 'intent-async'
                    """,
                    ("tick-async-target", 1),
                )
        finally:
            conn.rollback()
    finally:
        conn.close()

    assert "market facts are append-only" in str(exc_info.value)


def test_pending_backfill_partial_index_present(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        indexes = {
            row["indexname"]
            for row in conn.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = 'enriched_events'
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert "idx_enriched_events_pending_backfill" in indexes


def test_event_anchor_backfill_jobs_control_plane_table_present(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        tables = {
            row["tablename"]
            for row in conn.execute(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                """
            ).fetchall()
        }
        indexes = {
            row["indexname"]
            for row in conn.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = 'event_anchor_backfill_jobs'
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert "event_anchor_backfill_jobs" in tables
    assert "idx_event_anchor_backfill_jobs_due" in indexes


def test_runtime_schema_contains_token_radar_current_storage_and_watchlist_signal_stats(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        tables = {
            row["table_name"]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()
        }
        first_seen_columns = {
            row["column_name"]: row
            for row in conn.execute(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'token_radar_target_first_seen'
                """
            ).fetchall()
        }
        indexes = {
            row["indexname"]
            for row in conn.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename IN (
                    'token_radar_current_rows',
                    'token_radar_publication_state',
                    'token_radar_target_first_seen'
                  )
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert {
        "token_radar_current_rows",
        "token_radar_publication_state",
        "token_radar_target_first_seen",
    }.issubset(tables)
    assert "token_radar_storage_maintenance_runs" not in tables
    assert "social_event_extractions" not in tables
    assert "watchlist_handle_signal_stats" not in tables
    assert "watchlist_handle_signal_events" not in tables
    assert "token_radar_rows" not in tables
    assert "token_radar_projection_coverage" not in tables
    assert "token_radar_rank_history" not in tables
    assert "token_radar_snapshot_audit" not in tables
    assert "token_radar_retention_runs" not in tables
    assert "pulse_playbook_outcomes" not in tables
    assert first_seen_columns["target_type_key"]["data_type"] == "text"
    assert first_seen_columns["target_type_key"]["is_nullable"] == "NO"
    assert first_seen_columns["identity_id"]["data_type"] == "text"
    assert first_seen_columns["identity_id"]["is_nullable"] == "NO"
    assert {
        "idx_token_radar_current_rows_venue_rank",
        "idx_token_radar_current_rows_generation",
        "idx_token_radar_first_seen_updated",
    }.issubset(indexes)


def test_token_radar_postgres_hard_cut_runtime_schema_uses_partitioned_facts_and_hot_tables(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        tables = {
            row["table_name"]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()
        }
        partition_keys = {
            row["relname"]: row["partition_key"]
            for row in conn.execute(
                """
                SELECT c.relname, pg_get_partkeydef(c.oid) AS partition_key
                FROM pg_partitioned_table pt
                JOIN pg_class c ON c.oid = pt.partrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname IN (
                    'market_ticks'
                  )
                """
            ).fetchall()
        }
        primary_keys = {
            row["table_name"]: _postgres_array_text(row["columns"])
            for row in conn.execute(
                """
                SELECT tc.table_name, array_agg(kcu.column_name ORDER BY kcu.ordinal_position) AS columns
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                 AND tc.table_name = kcu.table_name
                WHERE tc.table_schema = 'public'
                  AND tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_name IN ('market_ticks', 'market_tick_current')
                GROUP BY tc.table_name
                """
            ).fetchall()
        }
        fk_defs = [
            row["constraint_def"]
            for row in conn.execute(
                """
                SELECT pg_get_constraintdef(c.oid) AS constraint_def
                FROM pg_constraint c
                JOIN pg_class child ON child.oid = c.conrelid
                JOIN pg_class parent ON parent.oid = c.confrelid
                JOIN pg_namespace n ON n.oid = child.relnamespace
                WHERE n.nspname = 'public'
                  AND c.contype = 'f'
                  AND child.relname = 'enriched_events'
                  AND parent.relname = 'market_ticks'
                """
            ).fetchall()
        ]
        indexes = {
            row["indexname"]: row["indexdef"]
            for row in conn.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename IN (
                    'market_ticks',
                    'enriched_events',
                    'token_radar_target_features'
                  )
                """
            ).fetchall()
        }
        payload_hash_columns = {
            row["table_name"]
            for row in conn.execute(
                """
                SELECT table_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND column_name = 'payload_hash'
                  AND table_name IN (
                    'market_tick_current',
                    'token_radar_current_rows',
                    'token_radar_target_features',
                    'token_radar_dirty_targets'
                  )
                """
            ).fetchall()
        }
        current_row_columns = {
            row["column_name"]: row
            for row in conn.execute(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'token_radar_current_rows'
                """
            ).fetchall()
        }
        target_feature_columns = {
            row["column_name"]: row
            for row in conn.execute(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'token_radar_target_features'
                """
            ).fetchall()
        }
        reloptions = {
            row["relname"]: set(row["reloptions"] or [])
            for row in conn.execute(
                """
                SELECT relname, reloptions
                FROM pg_class
                WHERE relnamespace = 'public'::regnamespace
                  AND relname IN (
                    'market_tick_current',
                    'token_radar_current_rows',
                    'token_radar_dirty_targets'
                  )
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert "token_radar_rows" not in tables
    assert {
        "market_tick_current",
        "token_radar_dirty_targets",
        "token_radar_target_features",
        "token_radar_publication_state",
    }.issubset(tables)
    assert "token_radar_projection_coverage" not in tables
    assert "token_radar_target_projection_coverage" not in tables
    assert "token_radar_rank_history" not in tables
    assert "token_radar_snapshot_audit" not in tables
    assert partition_keys == {"market_ticks": "RANGE (observed_at_ms)"}
    assert primary_keys["market_ticks"] == ["observed_at_ms", "tick_id"]
    assert primary_keys["market_tick_current"] == ["target_type", "target_id"]
    assert any(
        "FOREIGN KEY (tick_observed_at_ms, tick_id) REFERENCES market_ticks(observed_at_ms, tick_id)" in constraint_def
        for constraint_def in fk_defs
    )
    assert "idx_market_ticks_dedupe" in indexes
    assert "(observed_at_ms, target_type, target_id, source_provider)" in indexes["idx_market_ticks_dedupe"]
    assert "idx_market_ticks_target_observed" in indexes
    assert "idx_enriched_events_tick" in indexes
    assert "idx_token_radar_target_features_freshness" in indexes
    assert (
        "(projection_version, target_type_key, identity_id, latest_market_observed_at_ms DESC)"
        in indexes["idx_token_radar_target_features_freshness"]
    )
    assert payload_hash_columns == {
        "market_tick_current",
        "token_radar_current_rows",
        "token_radar_target_features",
        "token_radar_dirty_targets",
    }
    assert {"generation_id", "published_at_ms", "source_frontier_ms"}.issubset(current_row_columns)
    assert {
        "asset_json",
        "primary_venue_json",
        "target_json",
        "attention_json",
        "market_json",
        "price_json",
        "score_json",
    }.isdisjoint(current_row_columns)
    assert current_row_columns["rank_score"]["data_type"] == "double precision"
    assert current_row_columns["rank_score"]["is_nullable"] == "NO"
    assert current_row_columns["quality_status"]["data_type"] == "text"
    assert current_row_columns["quality_status"]["is_nullable"] == "NO"
    assert current_row_columns["degraded_reasons_json"]["data_type"] == "jsonb"
    assert current_row_columns["degraded_reasons_json"]["is_nullable"] == "NO"
    assert current_row_columns["factor_snapshot_json"]["data_type"] == "jsonb"
    assert current_row_columns["factor_snapshot_json"]["is_nullable"] == "NO"
    for column in ("intent_json", "resolution_json"):
        assert target_feature_columns[column]["data_type"] == "jsonb"
        assert target_feature_columns[column]["is_nullable"] == "NO"
    for table_options in reloptions.values():
        assert "fillfactor=70" in table_options
        assert "autovacuum_vacuum_scale_factor=0.02" in table_options
        assert "autovacuum_analyze_scale_factor=0.02" in table_options


def _seed_pending_backfill_row(conn) -> None:
    """Insert the minimum graph of events + intents + resolutions + ticks
    + enriched_events needed to exercise the trigger transitions."""
    EvidenceRepository(conn).insert_event(make_event(event_id="event-async"), is_watched=True)
    conn.execute(
        """
        INSERT INTO token_evidence(
          evidence_id, event_id, source_kind, source_id, evidence_type, raw_value,
          normalized_symbol, chain_hint, address_hint, provider, provider_ref,
          text_surface, span_start, span_end, sentence_id, local_group_key,
          strength, confidence, created_at_ms
        )
        VALUES (
          'evidence-async', 'event-async', 'entity', 'entity-async', 'cashtag', '$ASYNC',
          'ASYNC', NULL, NULL, NULL, NULL, 'primary', 0, 5, 0, 'primary:0',
          'medium', 0.8, 1
        )
        ON CONFLICT(evidence_id) DO NOTHING
        """
    )
    conn.execute(
        """
        INSERT INTO token_intents(
          intent_id, event_id, intent_key, construction_policy, primary_evidence_id,
          display_symbol, display_name, chain_hint, address_hint, intent_status,
          intent_confidence, created_at_ms, updated_at_ms
        )
        VALUES (
          'intent-async', 'event-async', 'symbol:ASYNC', 'test', 'evidence-async',
          'ASYNC', NULL, NULL, NULL, 'pending', 1.0, 1, 1
        )
        ON CONFLICT(intent_id) DO NOTHING
        """
    )
    conn.execute(
        """
        INSERT INTO token_intent_resolutions(
          resolution_id, intent_id, event_id, resolution_status, resolver_policy_version,
          target_type, target_id, pricefeed_id, reason_codes_json, candidate_ids_json,
          lookup_keys_json, record_status, is_current, decision_time_ms, created_at_ms
        )
        VALUES (
          'resolution-async', 'intent-async', 'event-async', 'YES', 'v1',
          'chain_token', 'solana:ASYNC', NULL, '[]'::jsonb, '[]'::jsonb, '["symbol:ASYNC"]'::jsonb,
          'current', true, 1, 1
        )
        ON CONFLICT(resolution_id) DO NOTHING
        """
    )
    conn.execute(
        """
        INSERT INTO market_ticks(
          tick_id, target_type, target_id, chain, token_address,
          exchange, instrument, pricefeed_id,
          source_tier, source_provider,
          observed_at_ms, received_at_ms,
          price_usd, liquidity_usd, volume_24h_usd, market_cap_usd, holders,
          raw_payload_json, created_at_ms
        )
        VALUES (
          'tick-async-target', 'chain_token', 'solana:ASYNC', 'solana', 'ASYNC',
          NULL, NULL, NULL,
          'tier3_inline', 'okx_dex_rest',
          1, 1,
          1.5, 100, 1000, 5000, 10,
          '{}'::jsonb, 1
        )
        ON CONFLICT(target_type, target_id, source_provider, observed_at_ms) DO NOTHING
        """
    )
    conn.execute(
        """
        INSERT INTO enriched_events(
          event_id, intent_id, resolution_id, target_type, target_id,
          t_event_ms, tick_observed_at_ms, tick_id, tick_lag_ms,
          capture_method, capture_reason, created_at_ms
        )
        VALUES (
          'event-async', 'intent-async', 'resolution-async', 'chain_token', 'solana:ASYNC',
          1, NULL, NULL, NULL,
          'unavailable', 'pending_backfill', 1
        )
        ON CONFLICT(event_id, intent_id) DO NOTHING
        """
    )
    conn.commit()


def _legacy_price_table() -> str:
    return "_".join(("price", "observations"))


def _postgres_array_text(value) -> list[str]:
    if isinstance(value, list):
        return value
    return str(value).strip("{}").split(",")
