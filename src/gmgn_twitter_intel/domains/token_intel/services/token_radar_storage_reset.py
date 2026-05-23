from __future__ import annotations

from typing import Any

DROPPED_TABLES = ["token_radar_rows", "token_radar_retention_runs"]
TRUNCATED_TABLES = [
    "token_radar_current_rows",
    "token_radar_rank_history",
    "token_radar_snapshot_audit",
    "token_radar_target_first_seen",
]
DELETED_CONTROL_ROW_TABLES = [
    "token_radar_projection_coverage",
    "projection_offsets",
    "projection_runs",
]

_RESET_SQL = (
    "DROP TABLE IF EXISTS token_radar_rows CASCADE",
    "DROP TABLE IF EXISTS token_radar_retention_runs",
    (
        "TRUNCATE token_radar_current_rows, token_radar_rank_history, "
        "token_radar_snapshot_audit, token_radar_target_first_seen RESTART IDENTITY"
    ),
    "DELETE FROM token_radar_projection_coverage WHERE projection_version LIKE 'token-radar-%'",
    "DELETE FROM projection_offsets WHERE projection_name='token-radar'",
    "DELETE FROM projection_runs WHERE projection_name='token-radar'",
)


def clean_reset_token_radar_storage(
    conn: Any,
    *,
    dry_run: bool,
    execute: bool,
) -> dict[str, Any]:
    if dry_run == execute:
        raise ValueError("exactly one of dry_run or execute must be true")

    mode = "execute" if execute else "dry_run"
    result = {
        "mode": mode,
        "executed": bool(execute),
        "dropped_tables": list(DROPPED_TABLES),
        "truncated_tables": list(TRUNCATED_TABLES),
        "deleted_control_rows": list(DELETED_CONTROL_ROW_TABLES),
        "fact_tables_touched": False,
    }
    if dry_run:
        return result

    for statement in _RESET_SQL:
        conn.execute(statement)
    conn.commit()
    return result


__all__ = [
    "DELETED_CONTROL_ROW_TABLES",
    "DROPPED_TABLES",
    "TRUNCATED_TABLES",
    "clean_reset_token_radar_storage",
]
