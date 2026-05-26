from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.app.runtime.token_radar_postgres_hard_reset import (
    ensure_postgres_partitions,
    reset_token_radar_postgres_hard_cut,
)


def test_reset_token_radar_postgres_hard_cut_dry_run_lists_attached_partitions() -> None:
    conn = _RecordingConn(
        rows=[
            {"parent": "token_radar_rank_history", "partition": "token_radar_rank_history_default"},
            {"parent": "token_radar_rank_history", "partition": "token_radar_rank_history_202605"},
            {"parent": "token_radar_snapshot_audit", "partition": "token_radar_snapshot_audit_default"},
            {"parent": "token_radar_snapshot_audit", "partition": "token_radar_snapshot_audit_202605"},
        ]
    )

    result = reset_token_radar_postgres_hard_cut(conn, dry_run=True, execute=False)

    assert result["mode"] == "dry_run"
    assert result["executed"] is False
    assert result["affected_derived_tables"] == [
        "token_radar_dirty_targets",
        "token_radar_current_rows",
        "token_radar_rank_history",
        "token_radar_snapshot_audit",
        "token_radar_target_features",
        "token_radar_target_first_seen",
        "token_radar_target_projection_coverage",
    ]
    assert result["affected_partitions"] == [
        {"parent": "token_radar_rank_history", "partition": "token_radar_rank_history_default"},
        {"parent": "token_radar_rank_history", "partition": "token_radar_rank_history_202605"},
        {"parent": "token_radar_snapshot_audit", "partition": "token_radar_snapshot_audit_default"},
        {"parent": "token_radar_snapshot_audit", "partition": "token_radar_snapshot_audit_202605"},
    ]
    assert result["hard_dropped_legacy_tables"] == ["token_radar_rows", "token_radar_retention_runs"]
    assert result["deleted_projection_controls"] == [
        "token_radar_projection_coverage",
        "projection_offsets",
        "projection_runs",
    ]
    assert result["deleted_projection_control_filters"] == {
        "token_radar_projection_coverage": "projection_version LIKE 'token-radar-%'",
        "projection_offsets": "projection_name = 'token-radar'",
        "projection_runs": "projection_name = 'token-radar'",
    }
    assert result["preserved_fact_tables"] == [
        "events",
        "token_intents",
        "token_intent_resolutions",
        "market_ticks",
        "enriched_events",
    ]
    assert result["fact_tables_touched"] is False
    assert result["config_or_secrets_touched"] is False
    assert "FROM pg_inherits" in conn.sql[0]
    assert conn.commits == 0


def test_reset_token_radar_postgres_hard_cut_execute_runs_only_projection_storage_sql() -> None:
    conn = _RecordingConn()

    result = reset_token_radar_postgres_hard_cut(conn, dry_run=False, execute=True)

    joined_sql = "\n".join(conn.sql)
    assert result["mode"] == "execute"
    assert result["executed"] is True
    assert result["fact_tables_touched"] is False
    assert result["config_or_secrets_touched"] is False
    assert conn.commits == 1
    assert "DROP TABLE IF EXISTS token_radar_rows CASCADE" in joined_sql
    assert "DROP TABLE IF EXISTS token_radar_retention_runs" in joined_sql
    assert (
        "TRUNCATE token_radar_dirty_targets, token_radar_current_rows, "
        "token_radar_rank_history, token_radar_snapshot_audit, "
        "token_radar_target_features, token_radar_target_first_seen, "
        "token_radar_target_projection_coverage RESTART IDENTITY"
    ) in joined_sql
    assert "DELETE FROM token_radar_projection_coverage WHERE projection_version LIKE 'token-radar-%'" in joined_sql
    assert "DELETE FROM projection_offsets WHERE projection_name = 'token-radar'" in joined_sql
    assert "DELETE FROM projection_runs WHERE projection_name = 'token-radar'" in joined_sql
    assert not any(
        f"TRUNCATE {fact_table}" in joined_sql or f"DELETE FROM {fact_table}" in joined_sql
        for fact_table in result["preserved_fact_tables"]
    )


def test_ensure_postgres_partitions_execute_creates_current_and_next_month_partitions() -> None:
    conn = _RecordingConn()

    result = ensure_postgres_partitions(
        conn,
        now_ms=1_769_987_654_321,
        dry_run=False,
        execute=True,
    )

    joined_sql = "\n".join(conn.sql)
    assert result["mode"] == "execute"
    assert result["executed"] is True
    assert result["parents"] == ["token_radar_rank_history", "token_radar_snapshot_audit"]
    assert result["months"] == ["202602", "202603"]
    assert conn.commits == 1
    assert "CREATE TABLE IF NOT EXISTS token_radar_rank_history_202602" in joined_sql
    assert "PARTITION OF token_radar_rank_history" in joined_sql
    assert "CREATE TABLE IF NOT EXISTS token_radar_snapshot_audit_202603" in joined_sql
    assert "PARTITION OF token_radar_snapshot_audit" in joined_sql


class _RecordingConn:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.sql: list[str] = []
        self.params: list[Any] = []
        self.commits = 0
        self.rows = rows or []

    def execute(self, sql: str, params: object = ()) -> _RecordingConn:
        self.sql.append(" ".join(sql.split()))
        self.params.append(params)
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self.rows)

    def commit(self) -> None:
        self.commits += 1
