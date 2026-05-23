from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, NamedTuple

DERIVED_TABLES = [
    "token_radar_dirty_targets",
    "token_radar_current_rows",
    "token_radar_rank_history",
    "token_radar_snapshot_audit",
    "token_radar_target_features",
    "token_radar_target_first_seen",
]
LEGACY_HARD_DROP_TABLES = ["token_radar_rows", "token_radar_retention_runs"]
PROJECTION_CONTROL_TABLES = [
    "token_radar_projection_coverage",
    "projection_offsets",
    "projection_runs",
]
PRESERVED_FACT_TABLES = [
    "events",
    "token_intents",
    "token_intent_resolutions",
    "market_ticks",
    "enriched_events",
]
PARTITION_PARENTS = ["token_radar_rank_history", "token_radar_snapshot_audit"]

_RESET_SQL = (
    "DROP TABLE IF EXISTS token_radar_rows CASCADE",
    "DROP TABLE IF EXISTS token_radar_retention_runs",
    (
        "TRUNCATE token_radar_dirty_targets, token_radar_current_rows, "
        "token_radar_rank_history, token_radar_snapshot_audit, "
        "token_radar_target_features, token_radar_target_first_seen RESTART IDENTITY"
    ),
    "DELETE FROM token_radar_projection_coverage WHERE projection_version LIKE 'token-radar-%'",
    "DELETE FROM projection_offsets WHERE projection_name = 'token-radar'",
    "DELETE FROM projection_runs WHERE projection_name = 'token-radar'",
)


def reset_token_radar_postgres_hard_cut(
    conn: Any,
    *,
    dry_run: bool,
    execute: bool,
) -> dict[str, Any]:
    if dry_run == execute:
        raise ValueError("exactly one of dry_run or execute must be true")

    affected_partitions = (
        _attached_partitions(conn)
        if dry_run
        else [{"parent": parent, "scope": "all_attached_partitions"} for parent in PARTITION_PARENTS]
    )
    result = {
        "mode": "execute" if execute else "dry_run",
        "executed": bool(execute),
        "affected_derived_tables": list(DERIVED_TABLES),
        "affected_partitions": affected_partitions,
        "hard_dropped_legacy_tables": list(LEGACY_HARD_DROP_TABLES),
        "deleted_projection_controls": list(PROJECTION_CONTROL_TABLES),
        "deleted_projection_control_filters": {
            "token_radar_projection_coverage": "projection_version LIKE 'token-radar-%'",
            "projection_offsets": "projection_name = 'token-radar'",
            "projection_runs": "projection_name = 'token-radar'",
        },
        "preserved_fact_tables": list(PRESERVED_FACT_TABLES),
        "fact_tables_touched": False,
        "config_or_secrets_touched": False,
    }
    if dry_run:
        return result

    for statement in _RESET_SQL:
        conn.execute(statement)
    conn.commit()
    return result


def _attached_partitions(conn: Any) -> list[dict[str, str]]:
    rows = conn.execute(
        """
        SELECT
          parent.relname AS parent,
          child.relname AS partition
        FROM pg_inherits
        JOIN pg_class parent ON parent.oid = pg_inherits.inhparent
        JOIN pg_class child ON child.oid = pg_inherits.inhrelid
        WHERE parent.relname = ANY(%s)
        ORDER BY parent.relname ASC, child.relname ASC
        """,
        (list(PARTITION_PARENTS),),
    ).fetchall()
    partitions: list[dict[str, str]] = []
    for row in rows:
        if isinstance(row, dict):
            partitions.append({"parent": str(row["parent"]), "partition": str(row["partition"])})
        else:
            partitions.append({"parent": str(row[0]), "partition": str(row[1])})
    return partitions


def ensure_postgres_partitions(
    conn: Any,
    *,
    now_ms: int,
    dry_run: bool,
    execute: bool,
) -> dict[str, Any]:
    if dry_run == execute:
        raise ValueError("exactly one of dry_run or execute must be true")

    months = [_month_bounds(int(now_ms)), _next_month_bounds(int(now_ms))]
    result = {
        "mode": "execute" if execute else "dry_run",
        "executed": bool(execute),
        "parents": list(PARTITION_PARENTS),
        "months": [month.year_month for month in months],
        "partitions": [
            {
                "parent": parent,
                "partition": f"{parent}_{month.year_month}",
                "from_ms": month.start_ms,
                "to_ms": month.end_ms,
            }
            for month in months
            for parent in PARTITION_PARENTS
        ],
    }
    if dry_run:
        return result

    for partition in result["partitions"]:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {partition["partition"]}
              PARTITION OF {partition["parent"]}
              FOR VALUES FROM ({partition["from_ms"]}) TO ({partition["to_ms"]})
            """
        )
    conn.commit()
    return result


def drop_expired_postgres_partitions(
    conn: Any,
    *,
    execute: bool,
) -> dict[str, Any]:
    _ = conn
    if not execute:
        raise ValueError("execute must be true")
    return {
        "mode": "execute",
        "executed": False,
        "reason": "retention_not_configured",
        "dropped_partitions": [],
        "fact_tables_touched": False,
        "config_or_secrets_touched": False,
    }


class _MonthBounds(NamedTuple):
    year_month: str
    start_ms: int
    end_ms: int


def _month_bounds(timestamp_ms: int) -> _MonthBounds:
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
    start = datetime(dt.year, dt.month, 1, tzinfo=UTC)
    end = (
        datetime(dt.year + 1, 1, 1, tzinfo=UTC)
        if dt.month == 12
        else datetime(dt.year, dt.month + 1, 1, tzinfo=UTC)
    )
    return _MonthBounds(
        year_month=f"{start.year:04d}{start.month:02d}",
        start_ms=int(start.timestamp() * 1000),
        end_ms=int(end.timestamp() * 1000),
    )


def _next_month_bounds(timestamp_ms: int) -> _MonthBounds:
    current = _month_bounds(timestamp_ms)
    return _month_bounds(current.end_ms)


__all__ = [
    "DERIVED_TABLES",
    "LEGACY_HARD_DROP_TABLES",
    "PARTITION_PARENTS",
    "PRESERVED_FACT_TABLES",
    "PROJECTION_CONTROL_TABLES",
    "drop_expired_postgres_partitions",
    "ensure_postgres_partitions",
    "reset_token_radar_postgres_hard_cut",
]
