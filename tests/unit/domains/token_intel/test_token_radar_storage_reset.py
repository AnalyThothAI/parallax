from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.token_intel.services.token_radar_storage_reset import (
    clean_reset_token_radar_storage,
)


def test_clean_reset_token_radar_storage_dry_run_returns_plan_without_sql() -> None:
    conn = _RecordingConn()

    result = clean_reset_token_radar_storage(conn, dry_run=True, execute=False)

    assert result == {
        "mode": "dry_run",
        "executed": False,
        "dropped_tables": ["token_radar_rows", "token_radar_retention_runs"],
        "truncated_tables": [
            "token_radar_current_rows",
            "token_radar_rank_history",
            "token_radar_snapshot_audit",
            "token_radar_target_first_seen",
        ],
        "deleted_control_rows": [
            "token_radar_projection_coverage",
            "projection_offsets",
            "projection_runs",
        ],
        "fact_tables_touched": False,
    }
    assert conn.sql == []
    assert conn.commits == 0


def test_clean_reset_token_radar_storage_execute_runs_only_projection_storage_sql() -> None:
    conn = _RecordingConn()

    result = clean_reset_token_radar_storage(conn, dry_run=False, execute=True)

    joined_sql = "\n".join(conn.sql)
    assert result["mode"] == "execute"
    assert result["executed"] is True
    assert result["fact_tables_touched"] is False
    assert conn.commits == 1
    assert "DROP TABLE IF EXISTS token_radar_rows CASCADE" in joined_sql
    assert "DROP TABLE IF EXISTS token_radar_retention_runs" in joined_sql
    assert (
        "TRUNCATE token_radar_current_rows, token_radar_rank_history, "
        "token_radar_snapshot_audit, token_radar_target_first_seen RESTART IDENTITY"
    ) in joined_sql
    assert "DELETE FROM token_radar_projection_coverage WHERE projection_version LIKE 'token-radar-%'" in joined_sql
    assert "DELETE FROM projection_offsets WHERE projection_name='token-radar'" in joined_sql
    assert "DELETE FROM projection_runs WHERE projection_name='token-radar'" in joined_sql
    assert not any(
        fact_table in joined_sql
        for fact_table in (
            "events",
            "token_intents",
            "token_intent_resolutions",
            "asset_identity",
            "market_ticks",
            "enriched_events",
        )
    )


class _RecordingConn:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.params: list[Any] = []
        self.commits = 0

    def execute(self, sql: str, params: object = ()) -> _RecordingConn:
        self.sql.append(" ".join(sql.split()))
        self.params.append(params)
        return self

    def commit(self) -> None:
        self.commits += 1
