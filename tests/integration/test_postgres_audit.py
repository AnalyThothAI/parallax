from __future__ import annotations

from gmgn_twitter_intel.platform.db.postgres_audit import HOT_QUERIES, PostgresOperationalAudit, PostgresQueryAudit
from gmgn_twitter_intel.platform.db.postgres_migrations import latest_migration_version
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
    assert payload["migration_version"] == latest_migration_version()
    assert payload["migration_status"] == "ready"
    assert payload["counts"]["events"] == 0
    assert payload["counts"]["registry_assets"] == 0
    assert payload["projection_schema"]["projection_offsets"] is True
    assert payload["projection_schema"]["token_radar_rows"] is True
    assert payload["foreign_key_checks"]["token_radar_rows_missing_intents"] == 0


def test_query_audit_explains_hot_read_paths_without_analyze(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)

        payload = PostgresQueryAudit(conn, token_radar_projection_version="token-radar-test").run(analyze=False)
    finally:
        conn.close()

    names = {item["name"] for item in payload["queries"]}
    assert payload["ok"] is True
    assert payload["analyze"] is False
    expected = {"recent_all", "search_v2_lexical", "search_v2_trigram", "token_radar_latest", "target_posts_recent"}
    assert expected.issubset(names)
    assert all(item["plan"] for item in payload["queries"])


def test_query_audit_target_posts_uses_resolution_targets():
    query = next(item for item in HOT_QUERIES if item["name"] == "target_posts_recent")

    assert "target_type" in query["sql"]
    assert "target_id" in query["sql"]
    assert "first_seen_ms" not in query["sql"]
    assert "confidence" not in query["sql"]


def test_query_audit_token_radar_latest_declares_caller_supplied_projection_version_param():
    query = next(item for item in HOT_QUERIES if item["name"] == "token_radar_latest")

    assert "%(token_radar_projection_version)s" in query["sql"]
    assert query["params"] == {"token_radar_projection_version": None}


def test_query_audit_includes_token_factor_settlement_hot_path():
    query = next(item for item in HOT_QUERIES if item["name"] == "token_factor_settlement_rows")

    assert "factor_version" in query["sql"]
    assert "computed_at_ms + %(horizon_ms)s <= %(generated_at_ms)s" in query["sql"]
    assert query["params"]["token_factor_version"] is None


def test_query_audit_binds_caller_supplied_token_radar_projection_version():
    conn = RecordingExplainConn()

    payload = PostgresQueryAudit(
        conn,
        token_radar_projection_version="token-radar-custom",
        token_factor_version="token-factor-custom",
    ).run(analyze=False)

    assert payload["ok"] is True
    assert {"token_radar_projection_version": "token-radar-custom"} in conn.params_seen
    assert any(
        params.get("token_factor_version") == "token-factor-custom"
        for params in conn.params_seen
        if isinstance(params, dict)
    )


class RecordingExplainConn:
    def __init__(self):
        self.params_seen = []

    def execute(self, sql, params=None):
        self.params_seen.append(params)
        return self

    def fetchall(self):
        return [{"QUERY PLAN": "ok"}]
