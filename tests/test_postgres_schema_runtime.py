from __future__ import annotations

from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate
from tests.test_sqlite_repositories import make_event


def test_postgres_schema_bootstraps_core_tables(tmp_path):
    conn = connect_postgres_test(tmp_path / "twitter_intel.sqlite3", read_only=False)
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
    assert "tokens" in names
    assert "token_market_observations" in names
    assert "event_token_attributions" in names
    assert "harness_snapshots" in names
    assert "notifications" in names
    assert "token_signal_snapshots" in names


def test_postgres_generated_tsvector_matches_inserted_event(tmp_path):
    conn = connect_postgres_test(tmp_path / "twitter_intel.sqlite3", read_only=False)
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


def test_alembic_migration_is_idempotent(tmp_path):
    conn = connect_postgres_test(tmp_path / "twitter_intel.sqlite3", read_only=False)
    try:
        migrate(conn)
        migrate(conn)
        rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
    finally:
        conn.close()

    assert [row["version_num"] for row in rows] == ["20260506_0001"]
