from __future__ import annotations

from gmgn_twitter_intel.storage.postgres_audit import PostgresOperationalAudit, PostgresQueryAudit
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
    assert payload["migration_version"] == "20260506_0005"
    assert payload["counts"]["events"] == 0
    assert payload["counts"]["assets"] == 0
    assert payload["projection_schema"]["projection_offsets"] is True
    assert payload["projection_schema"]["asset_flow_window_snapshots"] is True
    assert payload["foreign_key_checks"]["asset_attributions_missing_events"] == 0


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
    assert {"recent_all", "search_fts", "asset_flow_5m_shape", "asset_posts_recent"}.issubset(names)
    assert all(item["plan"] for item in payload["queries"])
