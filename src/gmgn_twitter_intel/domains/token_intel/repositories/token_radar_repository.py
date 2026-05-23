from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.token_intel._constants import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
)
from gmgn_twitter_intel.domains.token_intel.scoring.factor_snapshot_contract import require_token_factor_snapshot

RADAR_ROW_COLUMNS = (
    "row_id",
    "projection_version",
    "window",
    "scope",
    "computed_at_ms",
    "source_max_received_at_ms",
    "lane",
    "rank",
    "intent_id",
    "event_id",
    "target_type",
    "target_id",
    "pricefeed_id",
    "intent_json",
    "asset_json",
    "primary_venue_json",
    "target_json",
    "attention_json",
    "resolution_json",
    "market_json",
    "price_json",
    "score_json",
    "factor_snapshot_json",
    "factor_version",
    "decision",
    "data_health_json",
    "source_event_ids_json",
    "listed_at_ms",
    "created_at_ms",
)
RADAR_ROW_INSERT_COLUMNS_SQL = """
  row_id, projection_version, "window", scope, computed_at_ms, source_max_received_at_ms,
  lane, rank, intent_id, event_id, target_type, target_id, pricefeed_id, intent_json,
  asset_json, primary_venue_json, target_json, attention_json, resolution_json,
  market_json, price_json, score_json, factor_snapshot_json, factor_version, decision,
  data_health_json, source_event_ids_json, listed_at_ms, created_at_ms
"""
RADAR_ROW_INSERT_VALUES_SQL = """
  %(row_id)s, %(projection_version)s, %(window)s, %(scope)s, %(computed_at_ms)s,
  %(source_max_received_at_ms)s, %(lane)s, %(rank)s, %(intent_id)s, %(event_id)s,
  %(target_type)s, %(target_id)s, %(pricefeed_id)s, %(intent_json)s, %(asset_json)s,
  %(primary_venue_json)s, %(target_json)s, %(attention_json)s, %(resolution_json)s,
  %(market_json)s, %(price_json)s, %(score_json)s, %(factor_snapshot_json)s,
  %(factor_version)s, %(decision)s, %(data_health_json)s, %(source_event_ids_json)s,
  %(listed_at_ms)s, %(created_at_ms)s
"""


class TokenRadarRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def publish_rows(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
        computed_at_ms: int,
        rows: list[dict[str, Any]],
        commit: bool = True,
    ) -> bool:
        self.conn.execute(
            """
            SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))
            """,
            (projection_version, f"{window}:{scope}"),
        )
        latest = self.conn.execute(
            """
            SELECT MAX(computed_at_ms) AS computed_at_ms
            FROM (
              SELECT MAX(computed_at_ms) AS computed_at_ms
              FROM token_radar_current_rows
              WHERE projection_version = %s AND "window" = %s AND scope = %s
              UNION ALL
              SELECT MAX(computed_at_ms) AS computed_at_ms
              FROM token_radar_projection_coverage
              WHERE projection_version = %s AND "window" = %s AND scope = %s
            ) publication_watermark
            """,
            (projection_version, window, scope, projection_version, window, scope),
        ).fetchone()
        latest_computed_at_ms = (
            int(latest["computed_at_ms"]) if latest and latest["computed_at_ms"] is not None else None
        )
        if latest_computed_at_ms is not None and latest_computed_at_ms > int(computed_at_ms):
            if commit:
                self.conn.commit()
            return False

        self.ensure_storage_partitions(computed_at_ms=int(computed_at_ms), commit=False)
        for row in rows:
            _validate_factor_contract(row)
        listed_at_by_key = self.first_seen_by_identity(
            projection_version=projection_version,
            window=window,
            scope=scope,
            rows=rows,
        )
        rows_to_insert = [
            _runtime_row_payload(
                row,
                projection_version=projection_version,
                window=window,
                scope=scope,
                computed_at_ms=int(computed_at_ms),
                listed_at_ms=listed_at_by_key.get(_identity_key(row), int(computed_at_ms)),
            )
            for row in rows
        ]

        self.conn.execute(
            """
            DELETE FROM token_radar_current_rows
            WHERE projection_version = %s AND "window" = %s AND scope = %s
            """,
            (projection_version, window, scope),
        )
        self.conn.execute(
            """
            DELETE FROM token_radar_rank_history
            WHERE projection_version = %s AND "window" = %s AND scope = %s AND computed_at_ms = %s
            """,
            (projection_version, window, scope, int(computed_at_ms)),
        )
        self.conn.execute(
            """
            DELETE FROM token_radar_snapshot_audit
            WHERE projection_version = %s AND "window" = %s AND scope = %s AND computed_at_ms = %s
            """,
            (projection_version, window, scope, int(computed_at_ms)),
        )
        for row in rows_to_insert:
            payload = _json_payload(row)
            self.conn.execute(
                f"""
                INSERT INTO token_radar_current_rows({RADAR_ROW_INSERT_COLUMNS_SQL})
                VALUES ({RADAR_ROW_INSERT_VALUES_SQL})
                """,
                payload,
            )
            self.conn.execute(
                """
                INSERT INTO token_radar_rank_history(
                  row_id, projection_version, "window", scope, computed_at_ms, source_max_received_at_ms,
                  lane, rank, rank_score, decision, intent_id, event_id, target_type, target_id, pricefeed_id,
                  target_json, listed_at_ms, created_at_ms
                )
                VALUES (
                  %(row_id)s, %(projection_version)s, %(window)s, %(scope)s, %(computed_at_ms)s,
                  %(source_max_received_at_ms)s, %(lane)s, %(rank)s, %(rank_score)s, %(decision)s,
                  %(intent_id)s, %(event_id)s, %(target_type)s, %(target_id)s, %(pricefeed_id)s,
                  %(target_json)s, %(listed_at_ms)s, %(created_at_ms)s
                )
                """,
                _rank_history_payload(row),
            )
            self.conn.execute(
                f"""
                INSERT INTO token_radar_snapshot_audit(snapshot_id, {RADAR_ROW_INSERT_COLUMNS_SQL})
                VALUES (%(snapshot_id)s, {RADAR_ROW_INSERT_VALUES_SQL})
                """,
                {"snapshot_id": str(row["row_id"]), **payload},
            )
        self.upsert_first_seen_batch(
            projection_version=projection_version,
            window=window,
            scope=scope,
            rows=rows_to_insert,
            computed_at_ms=int(computed_at_ms),
            commit=False,
        )
        if commit:
            self.conn.commit()
        return True

    def latest_current_rows(
        self,
        *,
        window: str,
        scope: str,
        limit: int,
        projection_version: str,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH ranked AS (
              SELECT *
              FROM (
                SELECT
                  current_rows.*,
                  row_number() OVER (PARTITION BY lane ORDER BY rank ASC) AS lane_rank
                FROM token_radar_current_rows current_rows
                WHERE current_rows.projection_version = %s
                  AND current_rows."window" = %s
                  AND current_rows.scope = %s
              ) latest_ranked
              WHERE lane_rank <= %s
            )
            SELECT ranked.*
            FROM ranked
            ORDER BY lane DESC, rank ASC
            LIMIT %s
            """,
            (
                projection_version,
                window,
                scope,
                max(0, int(limit)),
                max(0, int(limit)) * 2,
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def latest_snapshot_audit_rows(
        self,
        *,
        window: str,
        scope: str,
        limit: int,
        projection_version: str,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH latest AS (
              SELECT MAX(computed_at_ms) AS computed_at_ms
              FROM token_radar_snapshot_audit
              WHERE projection_version = %s AND "window" = %s AND scope = %s
            )
            SELECT audit.*
            FROM token_radar_snapshot_audit audit
            JOIN latest ON audit.computed_at_ms = latest.computed_at_ms
            WHERE audit.projection_version = %s
              AND audit."window" = %s
              AND audit.scope = %s
            ORDER BY audit.lane DESC, audit.rank ASC
            LIMIT %s
            """,
            (
                projection_version,
                window,
                scope,
                projection_version,
                window,
                scope,
                max(0, int(limit)),
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def first_seen_by_identity(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
        rows: list[dict[str, Any]],
    ) -> dict[tuple[str, str], int]:
        identities = _nonempty_identities(rows)
        if not identities:
            return {}
        target_type_keys = [target_type for target_type, _ in identities]
        identity_ids = [identity_id for _, identity_id in identities]
        compact_rows = self.conn.execute(
            """
            WITH requested(target_type_key, identity_id) AS (
              SELECT *
              FROM unnest(%s::text[], %s::text[])
            )
            SELECT
              requested.target_type_key,
              requested.identity_id,
              first_seen.first_seen_ms
            FROM token_radar_target_first_seen first_seen
            JOIN requested
              ON requested.target_type_key = first_seen.target_type_key
             AND requested.identity_id = first_seen.identity_id
            WHERE first_seen.projection_version = %s
              AND first_seen."window" = %s
              AND first_seen.scope = %s
            """,
            (target_type_keys, identity_ids, projection_version, window, scope),
        ).fetchall()
        return {
            (str(row["target_type_key"]), str(row["identity_id"])): int(row["first_seen_ms"])
            for row in compact_rows
            if row.get("first_seen_ms") is not None
        }

    def upsert_first_seen_batch(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
        rows: list[dict[str, Any]],
        computed_at_ms: int,
        commit: bool = True,
    ) -> int:
        now_ms = _now_ms()
        records: list[tuple[Any, ...]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            target_type_key, identity_id = _identity_key(row)
            if not identity_id or (target_type_key, identity_id) in seen:
                continue
            seen.add((target_type_key, identity_id))
            first_seen_ms = int(row.get("listed_at_ms") or computed_at_ms)
            last_seen_ms = int(computed_at_ms)
            row_id = row.get("row_id")
            records.append(
                (
                    projection_version,
                    window,
                    scope,
                    target_type_key,
                    identity_id,
                    first_seen_ms,
                    last_seen_ms,
                    row_id,
                    row_id,
                    now_ms,
                    now_ms,
                )
            )
        if not records:
            return 0
        values_sql = ",".join(["(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(records))
        params = [value for record in records for value in record]
        self.conn.execute(
            f"""
            INSERT INTO token_radar_target_first_seen(
              projection_version, "window", scope, target_type_key, identity_id,
              first_seen_ms, last_seen_ms, first_row_id, latest_row_id, created_at_ms, updated_at_ms
            )
            VALUES {values_sql}
            ON CONFLICT(projection_version, "window", scope, target_type_key, identity_id)
            DO UPDATE SET
              first_seen_ms = LEAST(token_radar_target_first_seen.first_seen_ms, excluded.first_seen_ms),
              last_seen_ms = GREATEST(token_radar_target_first_seen.last_seen_ms, excluded.last_seen_ms),
              first_row_id = CASE
                WHEN excluded.first_seen_ms <= token_radar_target_first_seen.first_seen_ms
                  THEN excluded.first_row_id
                ELSE token_radar_target_first_seen.first_row_id
              END,
              latest_row_id = CASE
                WHEN excluded.last_seen_ms >= token_radar_target_first_seen.last_seen_ms
                  THEN excluded.latest_row_id
                ELSE token_radar_target_first_seen.latest_row_id
              END,
              updated_at_ms = excluded.updated_at_ms
            """,
            params,
        )
        if commit:
            self.conn.commit()
        return len(records)

    def ensure_storage_partitions(self, *, computed_at_ms: int, commit: bool = True) -> None:
        year_month, start_ms, end_ms = _month_partition_bounds(int(computed_at_ms))
        for parent in ("token_radar_rank_history", "token_radar_snapshot_audit"):
            partition = f"{parent}_{year_month}"
            self.conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {partition}
                  PARTITION OF {parent}
                  FOR VALUES FROM ({start_ms}) TO ({end_ms})
                """
            )
        if commit:
            self.conn.commit()

    def mark_coverage(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
        status: str,
        reason: str | None = None,
        source_rows: int = 0,
        row_count: int = 0,
        computed_at_ms: int | None = None,
        started_at_ms: int | None = None,
        finished_at_ms: int | None = None,
        error: str | None = None,
        commit: bool = True,
    ) -> None:
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO token_radar_projection_coverage(
              projection_version, "window", scope, status, reason, source_rows, row_count,
              computed_at_ms, started_at_ms, finished_at_ms, error, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(projection_version, "window", scope) DO UPDATE SET
              status = excluded.status,
              reason = excluded.reason,
              source_rows = excluded.source_rows,
              row_count = excluded.row_count,
              computed_at_ms = excluded.computed_at_ms,
              started_at_ms = excluded.started_at_ms,
              finished_at_ms = excluded.finished_at_ms,
              error = excluded.error,
              updated_at_ms = excluded.updated_at_ms
            WHERE token_radar_projection_coverage.computed_at_ms IS NULL
               OR excluded.computed_at_ms IS NULL
               OR token_radar_projection_coverage.computed_at_ms <= excluded.computed_at_ms
            """,
            (
                projection_version,
                window,
                scope,
                status,
                reason,
                max(0, int(source_rows)),
                max(0, int(row_count)),
                int(computed_at_ms) if computed_at_ms is not None else None,
                int(started_at_ms) if started_at_ms is not None else None,
                int(finished_at_ms) if finished_at_ms is not None else None,
                error,
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()

    def latest_coverage(
        self,
        *,
        projection_version: str,
        windows: tuple[str, ...],
        scopes: tuple[str, ...],
    ) -> dict[tuple[str, str], dict[str, Any]]:
        requested = [(window, scope) for window in windows for scope in scopes]
        if not requested:
            return {}
        values_sql = ",".join(["(%s, %s)"] * len(requested))
        params: list[Any] = []
        for window, scope in requested:
            params.extend([window, scope])
        rows = self.conn.execute(
            f"""
            WITH requested("window", scope) AS (VALUES {values_sql})
            SELECT coverage.*
            FROM requested
            JOIN token_radar_projection_coverage coverage
              ON coverage."window" = requested."window"
             AND coverage.scope = requested.scope
            WHERE coverage.projection_version = %s
            """,
            [*params, projection_version],
        ).fetchall()
        return {
            (str(row["window"]), str(row["scope"])): {
                "status": str(row["status"]),
                "reason": row.get("reason"),
                "source_rows": int(row.get("source_rows") or 0),
                "row_count": int(row.get("row_count") or 0),
                "computed_at_ms": int(row["computed_at_ms"]) if row.get("computed_at_ms") is not None else None,
                "error": row.get("error"),
            }
            for row in rows
        }


def _runtime_row_payload(
    row: dict[str, Any],
    *,
    projection_version: str,
    window: str,
    scope: str,
    computed_at_ms: int,
    listed_at_ms: int,
) -> dict[str, Any]:
    out = dict(row)
    out.update(
        {
            "projection_version": projection_version,
            "window": window,
            "scope": scope,
            "computed_at_ms": int(computed_at_ms),
            "listed_at_ms": int(listed_at_ms),
        }
    )
    return out


def _json_payload(row: dict[str, Any]) -> dict[str, Any]:
    _validate_factor_contract(row)
    out = {column: row.get(column) for column in RADAR_ROW_COLUMNS}
    for key in (
        "factor_snapshot_json",
        "intent_json",
        "asset_json",
        "primary_venue_json",
        "target_json",
        "attention_json",
        "resolution_json",
        "market_json",
        "price_json",
        "score_json",
        "data_health_json",
        "source_event_ids_json",
    ):
        payload = out.get(key) if out.get(key) is not None else ([] if key.endswith("_ids_json") else {})
        out[key] = Jsonb(_json_ready(payload))
    return out


def _rank_history_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_id": row.get("row_id"),
        "projection_version": row.get("projection_version"),
        "window": row.get("window"),
        "scope": row.get("scope"),
        "computed_at_ms": row.get("computed_at_ms"),
        "source_max_received_at_ms": row.get("source_max_received_at_ms"),
        "lane": row.get("lane"),
        "rank": row.get("rank"),
        "rank_score": _rank_score(row.get("factor_snapshot_json")),
        "decision": row.get("decision"),
        "intent_id": row.get("intent_id"),
        "event_id": row.get("event_id"),
        "target_type": row.get("target_type"),
        "target_id": row.get("target_id"),
        "pricefeed_id": row.get("pricefeed_id"),
        "target_json": Jsonb(_json_ready(row.get("target_json") or {})),
        "listed_at_ms": row.get("listed_at_ms"),
        "created_at_ms": row.get("created_at_ms"),
    }


def _identity_key(row: dict[str, Any]) -> tuple[str, str]:
    target_type = str(row.get("target_type") or "")
    identity_id = str(row.get("target_id") or row.get("intent_id") or "")
    return (target_type, identity_id)


def _nonempty_identities(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return list(dict.fromkeys(identity for identity in (_identity_key(row) for row in rows) if identity[1]))


def _now_ms() -> int:
    return int(time.time() * 1000)


def _month_partition_bounds(computed_at_ms: int) -> tuple[str, int, int]:
    current = datetime.fromtimestamp(computed_at_ms / 1000, tz=UTC)
    start = datetime(current.year, current.month, 1, tzinfo=UTC)
    if current.month == 12:
        end = datetime(current.year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(current.year, current.month + 1, 1, tzinfo=UTC)
    return start.strftime("%Y%m"), int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def _rank_score(factor_snapshot: Any) -> float | None:
    if not isinstance(factor_snapshot, dict):
        return None
    composite = factor_snapshot.get("composite")
    if not isinstance(composite, dict):
        return None
    value = composite.get("rank_score")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _validate_factor_contract(row: dict[str, Any]) -> None:
    if "factor_snapshot_json" not in row:
        raise ValueError("factor_snapshot_json is required for token radar row hard-cut contract")
    factor_snapshot = row.get("factor_snapshot_json")
    if not isinstance(factor_snapshot, dict) or not factor_snapshot:
        raise ValueError("factor_snapshot_json must be non-empty for token radar row hard-cut contract")
    factor_version = str(row.get("factor_version") or "").strip()
    if not factor_version:
        raise ValueError("factor_version is required for token radar row hard-cut contract")
    schema_version = str(factor_snapshot.get("schema_version") or "").strip()
    if not schema_version:
        raise ValueError("factor_snapshot_json.schema_version is required for token radar row hard-cut contract")
    if schema_version != factor_version:
        raise ValueError("factor_snapshot_json.schema_version must match factor_version")
    if schema_version != TOKEN_FACTOR_SNAPSHOT_VERSION:
        raise ValueError(f"factor_snapshot_json.schema_version must be {TOKEN_FACTOR_SNAPSHOT_VERSION}")
    require_token_factor_snapshot(factor_snapshot, field_name="factor_snapshot_json")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    return value
