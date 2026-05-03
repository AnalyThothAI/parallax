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
    assert "account_token_alerts" in names
    assert "event_token_mentions" in names
    assert "token_windows" not in names
    assert "enrichment_jobs" in names
    assert "model_runs" in names
    assert "event_enrichments" in names
    assert "event_token_candidates" in names
    assert "event_narratives" in names
    assert "account_narrative_alerts" in names
    assert "narrative_windows" in names
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

    assert [row["version"] for row in rows] == [6]
