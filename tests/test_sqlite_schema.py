from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate


def test_sqlite_schema_bootstraps_core_tables(tmp_path):
    db_path = tmp_path / "twitter_intel.sqlite3"
    conn = connect_sqlite(db_path, read_only=False)
    try:
        migrate(conn)
        names = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "schema_migrations" in names
    assert "raw_frames" in names
    assert "events" in names
    assert "event_fts" in names
    assert "event_entities" in names
    assert "tokens" in names
    assert "token_aliases" in names
    assert "token_market_snapshots" in names
    assert "token_market_observations" in names
    assert "account_token_alerts" in names
    assert "event_token_mentions" in names
    assert "event_token_attributions" in names
    assert "token_windows" not in names
    assert "enrichment_jobs" in names
    assert "model_runs" in names
    assert "social_event_extractions" in names
    assert "attention_seeds" in names
    assert "event_clusters" in names
    assert "harness_snapshots" in names
    assert "harness_decisions" in names
    assert "harness_outcomes" in names
    assert "harness_credits" in names
    assert "harness_weights" in names
    assert "event_enrichments" not in names
    assert "event_token_candidates" not in names
    assert "event_narratives" not in names
    assert "account_narrative_alerts" not in names
    assert "narrative_windows" not in names
    assert "narrative_seeds" not in names
    assert "narrative_token_links" not in names
    assert "account_keyword_alerts" not in names
    assert "keyword_windows" not in names


def test_sqlite_fts5_matches_inserted_text(tmp_path):
    db_path = tmp_path / "twitter_intel.sqlite3"
    conn = connect_sqlite(db_path, read_only=False)
    try:
        migrate(conn)
        conn.execute(
            "INSERT INTO event_fts(event_id, author_handle, text_clean, search_text, cashtags, hashtags, mentions) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("event-1", "toly", "stablecoin on base", "stablecoin on base", "", "", ""),
        )
        rows = conn.execute(
            "SELECT event_id FROM event_fts WHERE event_fts MATCH ?",
            ("stablecoin",),
        ).fetchall()
    finally:
        conn.close()

    assert [row["event_id"] for row in rows] == ["event-1"]


def test_migrations_are_idempotent(tmp_path):
    db_path = tmp_path / "twitter_intel.sqlite3"
    conn = connect_sqlite(db_path, read_only=False)
    try:
        migrate(conn)
        migrate(conn)
        rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    finally:
        conn.close()

    assert [row["version"] for row in rows] == [11]


def test_migrate_v8_to_v9_adds_market_observations_without_clearing_data(tmp_path):
    db_path = tmp_path / "twitter_intel.sqlite3"
    conn = connect_sqlite(db_path, read_only=False)
    try:
        migrate(conn)
        conn.execute("DROP TABLE token_market_observations")
        conn.execute("DELETE FROM schema_migrations")
        conn.execute(
            "INSERT INTO schema_migrations(version, name, applied_at_ms) "
            "VALUES (8, 'token_attribution_radar', 1)"
        )
        conn.execute(
            """
            INSERT INTO events(
              event_id, logical_dedup_key, source_provider, source_transport, coverage, channel,
              action, timestamp_ms, received_at_ms, urls_json, cashtags_json, hashtags_json,
              mentions_json, media_json, matched_handles_json, raw_json, event_json, created_at_ms, updated_at_ms
            )
            VALUES (
              'event-v8', 'dedup-v8', 'gmgn', 'direct_ws', 'public_stream', 'twitter_monitor_basic',
              'tweet', 1700000000, 1700000000000, '[]', '[]', '[]', '[]', '[]', '[]', '{}', '{}', 1, 1
            )
            """
        )
        conn.execute(
            """
            INSERT INTO tokens(
              token_id, chain, address, symbol, identity_status, first_seen_event_id,
              first_seen_ms, created_at_ms, updated_at_ms
            )
            VALUES (
              'token:eth:0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416', 'eth',
              '0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416', 'DOG', 'resolved_ca',
              'event-v8', 1700000000000, 1, 1
            )
            """
        )
        conn.execute(
            """
            INSERT INTO token_market_snapshots(
              snapshot_id, token_id, event_id, price, previous_price, market_cap,
              source_channel, received_at_ms, raw_json, created_at_ms
            )
            VALUES (
              'snapshot-v8', 'token:eth:0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416',
              'event-v8', 1.0, NULL, 1000000, 'gmgn_openapi_token_info',
              1700000000000, '{}', 1
            )
            """
        )
        conn.execute(
            """
            INSERT INTO event_token_mentions(
              mention_id, event_id, identity_key, token_id, identity_status, chain, address, symbol,
              source, received_at_ms, author_handle, author_followers, is_watched, created_at_ms
            )
            VALUES (
              'mention-v8', 'event-v8', 'token:eth:0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416',
              'token:eth:0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416', 'resolved_ca',
              'eth', '0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416', 'DOG',
              'regex', 1700000000000, 'toly', 100, 1, 1
            )
            """
        )
        conn.execute(
            """
            INSERT INTO event_token_attributions(
              attribution_id, mention_id, event_id, mention_identity_key, identity_key, token_id,
              identity_status, chain, address, symbol, source, attribution_status,
              attribution_confidence, attribution_weight, attribution_rank, candidate_count,
              score_features_json, reasons_json, risks_json, received_at_ms, author_handle,
              author_followers, is_watched, created_at_ms
            )
            VALUES (
              'attrib-v8', 'mention-v8', 'event-v8',
              'token:eth:0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416',
              'token:eth:0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416',
              'token:eth:0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416',
              'resolved_ca', 'eth', '0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416', 'DOG',
              'regex', 'direct', 1.0, 1.0, 1, 1, '{}', '[]', '[]',
              1700000000000, 'toly', 100, 1, 1
            )
            """
        )
        conn.commit()

        migrate(conn)
        names = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        event_count = conn.execute("SELECT COUNT(*) AS count FROM events").fetchone()
        attribution_count = conn.execute("SELECT COUNT(*) AS count FROM event_token_attributions").fetchone()
        snapshot_count = conn.execute("SELECT COUNT(*) AS count FROM token_market_snapshots").fetchone()
    finally:
        conn.close()

    assert "token_market_observations" in names
    assert [row["version"] for row in rows] == [11]
    assert event_count["count"] == 1
    assert attribution_count["count"] == 1
    assert snapshot_count["count"] == 1


def test_migrate_resets_legacy_narrative_schema_instead_of_keeping_compat_tables(tmp_path):
    db_path = tmp_path / "twitter_intel.sqlite3"
    conn = connect_sqlite(db_path, read_only=False)
    try:
        conn.execute(
            "CREATE TABLE schema_migrations("
            "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at_ms INTEGER NOT NULL)"
        )
        conn.execute("INSERT INTO schema_migrations(version, name, applied_at_ms) VALUES (7, 'old_schema', 1)")
        conn.execute("CREATE TABLE event_enrichments(event_id TEXT PRIMARY KEY, summary TEXT NOT NULL)")
        conn.execute("INSERT INTO event_enrichments(event_id, summary) VALUES ('old-event', 'old english summary')")
        conn.commit()

        migrate(conn)
        names = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    finally:
        conn.close()

    assert "event_enrichments" not in names
    assert [row["version"] for row in rows] == [11]
