from __future__ import annotations

from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.platform.db.postgres_migrations import latest_migration_version
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


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
    finally:
        conn.close()

    assert "alembic_version" in names
    assert "raw_frames" in names
    assert "events" in names
    assert "event_fts" not in names
    assert "event_entities" in names
    assert "harness_snapshots" in names
    assert "notifications" in names
    assert "projection_offsets" in names
    assert "projection_runs" in names
    assert "projection_dirty_ranges" in names
    assert "token_evidence" in names
    assert "token_intents" in names
    assert "token_intent_evidence" in names
    assert "token_intent_resolutions" in names
    assert "token_radar_rows" in names
    for legacy_table in (
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
    ):
        assert legacy_table not in names


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
            row["column_name"]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'token_radar_rows'
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert {"projects", "registry_assets", "cex_tokens", "price_feeds"}.issubset(table_names)
    assert {"market_ticks", "enriched_events", "token_capture_tier"}.issubset(table_names)
    assert _legacy_price_table() not in table_names
    assert {"token_discovery_results", "registry_versions", "token_intent_lookup_keys"}.issubset(table_names)
    assert "discovery_tasks" not in table_names
    assert {"target_type", "target_id", "pricefeed_id", "reason_codes_json", "lookup_keys_json"}.issubset(
        resolution_columns
    )
    assert resolution_columns["identity_status"] == "YES"
    assert {"target_type", "target_id", "pricefeed_id", "target_json", "price_json"}.issubset(radar_columns)


def test_runtime_schema_contains_signal_pulse_tables(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        table_names = {
            row["table_name"]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert {
        "pulse_agent_jobs",
        "pulse_agent_runs",
        "pulse_candidates",
        "pulse_playbook_snapshots",
        "pulse_playbook_outcomes",
    }.issubset(table_names)


def test_runtime_schema_contains_token_factor_evaluation_diagnostics(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        columns = {
            row["column_name"]: row
            for row in conn.execute(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'token_score_evaluations'
                """
            ).fetchall()
        }
        token_factor_indexes = {
            row["indexname"]
            for row in conn.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename IN ('token_score_evaluations', 'token_radar_rows')
                """
            ).fetchall()
        }
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

    assert columns["sample_start_ms"]["data_type"] == "bigint"
    assert columns["sample_end_ms"]["data_type"] == "bigint"
    assert columns["spearman_ic"]["data_type"] == "double precision"
    assert columns["icir"]["data_type"] == "double precision"
    assert columns["score_stddev"]["data_type"] == "double precision"
    assert columns["score_stddev"]["is_nullable"] == "YES"
    assert columns["diagnostics_json"]["is_nullable"] == "NO"
    assert {"idx_token_score_evaluations_generated", "idx_token_radar_rows_settlement"}.issubset(token_factor_indexes)
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
                tick_lag_ms = 100,
                capture_method = 'tier3_inline',
                capture_reason = 'async_backfill'
            WHERE event_id = 'event-async'
              AND intent_id = 'intent-async'
              AND capture_method = 'unavailable'
              AND capture_reason = 'pending_backfill'
              AND tick_id IS NULL
            """,
            ("tick-async-target",),
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
    assert row["capture_method"] == "tier3_inline"
    assert row["capture_reason"] == "async_backfill"
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
                        tick_lag_ms = 100,
                        capture_method = 'tier3_inline',
                        capture_reason = 'async_backfill',
                        t_event_ms = t_event_ms + 1
                    WHERE event_id = 'event-async' AND intent_id = 'intent-async'
                    """,
                    ("tick-async-target",),
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
          t_event_ms, tick_id, tick_lag_ms,
          capture_method, capture_reason, created_at_ms
        )
        VALUES (
          'event-async', 'intent-async', 'resolution-async', 'chain_token', 'solana:ASYNC',
          1, NULL, NULL,
          'unavailable', 'pending_backfill', 1
        )
        ON CONFLICT(event_id, intent_id) DO NOTHING
        """
    )
    conn.commit()


def _legacy_price_table() -> str:
    return "_".join(("price", "observations"))
