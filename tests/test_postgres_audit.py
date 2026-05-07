from __future__ import annotations

from gmgn_twitter_intel.storage.postgres_audit import HOT_QUERIES, PostgresOperationalAudit, PostgresQueryAudit
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_operational_audit_reports_counts_fk_checks_and_projection_schema(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)

        payload = PostgresOperationalAudit(conn).run()
    finally:
        conn.close()

    assert payload["ok"] is True
    assert payload["engine"] == "postgresql"
    assert payload["migration_version"] == "20260507_0009"
    assert payload["counts"]["events"] == 0
    assert payload["counts"]["assets"] == 0
    assert payload["projection_schema"]["projection_offsets"] is True
    assert payload["projection_schema"]["token_radar_rows"] is True
    assert payload["foreign_key_checks"]["token_radar_rows_missing_intents"] == 0


def test_query_audit_explains_hot_read_paths_without_analyze(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)

        payload = PostgresQueryAudit(conn).run(analyze=False)
    finally:
        conn.close()

    names = {item["name"] for item in payload["queries"]}
    assert payload["ok"] is True
    assert payload["analyze"] is False
    assert {"recent_all", "search_fts", "token_radar_latest", "target_posts_recent"}.issubset(names)
    assert all(item["plan"] for item in payload["queries"])


def test_query_audit_target_posts_uses_v4_resolution_targets():
    query = next(item for item in HOT_QUERIES if item["name"] == "target_posts_recent")

    assert "target_type" in query["sql"]
    assert "target_id" in query["sql"]
    assert "first_seen_ms" not in query["sql"]
    assert "confidence" not in query["sql"]
