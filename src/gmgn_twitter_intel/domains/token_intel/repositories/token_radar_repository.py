from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.token_intel._constants import TOKEN_FACTOR_SNAPSHOT_VERSION


class TokenRadarRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def replace_rows(
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
            FROM token_radar_rows
            WHERE projection_version = %s AND "window" = %s AND scope = %s
            """,
            (projection_version, window, scope),
        ).fetchone()
        latest_computed_at_ms = (
            int(latest["computed_at_ms"]) if latest and latest["computed_at_ms"] is not None else None
        )
        if latest_computed_at_ms is not None and latest_computed_at_ms > int(computed_at_ms):
            if commit:
                self.conn.commit()
            return False
        for row in rows:
            _validate_factor_contract(row)
        self.conn.execute(
            """
            DELETE FROM token_radar_rows
            WHERE projection_version = %s AND "window" = %s AND scope = %s AND computed_at_ms = %s
            """,
            (projection_version, window, scope, int(computed_at_ms)),
        )
        for row in rows:
            self.conn.execute(
                """
                INSERT INTO token_radar_rows(
                  row_id, projection_version, "window", scope, computed_at_ms, source_max_received_at_ms,
                  lane, rank, intent_id, event_id, target_type, target_id, pricefeed_id, intent_json,
                  asset_json, primary_venue_json, target_json, factor_snapshot_json, factor_version,
                  decision, data_health_json,
                  source_event_ids_json, created_at_ms
                )
                VALUES (
                  %(row_id)s, %(projection_version)s, %(window)s, %(scope)s, %(computed_at_ms)s,
                  %(source_max_received_at_ms)s, %(lane)s, %(rank)s, %(intent_id)s, %(event_id)s,
                  %(target_type)s, %(target_id)s, %(pricefeed_id)s, %(intent_json)s, %(asset_json)s,
                  %(primary_venue_json)s, %(target_json)s, %(factor_snapshot_json)s, %(factor_version)s,
                  %(decision)s, %(data_health_json)s,
                  %(source_event_ids_json)s, %(created_at_ms)s
                )
                """,
                _json_payload(
                    {
                        **row,
                        "projection_version": projection_version,
                        "window": window,
                        "scope": scope,
                        "computed_at_ms": computed_at_ms,
                    }
                ),
            )
        if commit:
            self.conn.commit()
        return True

    def latest_rows(
        self,
        *,
        window: str,
        scope: str,
        limit: int,
        projection_version: str,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH published AS (
              SELECT published_computed_at_ms AS computed_at_ms
              FROM token_radar_publications
              WHERE projection_version = %s
                AND "window" = %s
                AND scope = %s
                AND published_computed_at_ms IS NOT NULL
            ), ranked AS (
              SELECT
                token_radar_rows.*,
                row_number() OVER (PARTITION BY lane ORDER BY rank ASC) AS lane_rank
              FROM token_radar_rows
              JOIN published
                ON token_radar_rows.computed_at_ms = published.computed_at_ms
              WHERE token_radar_rows.projection_version = %s
                AND token_radar_rows."window" = %s
                AND token_radar_rows.scope = %s
            )
            SELECT *
            FROM ranked
            WHERE lane_rank <= %s
            ORDER BY lane DESC, rank ASC
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
                max(0, int(limit)) * 2,
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_refresh_status(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
        refresh_status: str,
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
            INSERT INTO token_radar_publications(
              projection_version, "window", scope, refresh_status, reason,
              refresh_source_rows, refresh_row_count, refresh_computed_at_ms,
              refresh_started_at_ms, refresh_finished_at_ms, error, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(projection_version, "window", scope) DO UPDATE SET
              refresh_status = excluded.refresh_status,
              reason = excluded.reason,
              refresh_source_rows = excluded.refresh_source_rows,
              refresh_row_count = excluded.refresh_row_count,
              refresh_computed_at_ms = excluded.refresh_computed_at_ms,
              refresh_started_at_ms = excluded.refresh_started_at_ms,
              refresh_finished_at_ms = excluded.refresh_finished_at_ms,
              error = excluded.error,
              updated_at_ms = excluded.updated_at_ms
            WHERE token_radar_publications.refresh_computed_at_ms IS NULL
               OR excluded.refresh_computed_at_ms IS NULL
               OR token_radar_publications.refresh_computed_at_ms <= excluded.refresh_computed_at_ms
            """,
            (
                projection_version,
                window,
                scope,
                refresh_status,
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

    def publish_rows(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
        source_rows: int,
        row_count: int,
        computed_at_ms: int,
        source_max_received_at_ms: int = 0,
        started_at_ms: int | None = None,
        finished_at_ms: int | None = None,
        commit: bool = True,
    ) -> None:
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO token_radar_publications(
              projection_version, "window", scope, published_computed_at_ms,
              published_row_count, published_source_rows, published_source_max_received_at_ms,
              refresh_status, reason, refresh_computed_at_ms, refresh_started_at_ms,
              refresh_finished_at_ms, refresh_row_count, refresh_source_rows, error, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'ready', NULL, %s, %s, %s, %s, %s, NULL, %s)
            ON CONFLICT(projection_version, "window", scope) DO UPDATE SET
              published_computed_at_ms = excluded.published_computed_at_ms,
              published_row_count = excluded.published_row_count,
              published_source_rows = excluded.published_source_rows,
              published_source_max_received_at_ms = excluded.published_source_max_received_at_ms,
              refresh_status = excluded.refresh_status,
              reason = excluded.reason,
              refresh_computed_at_ms = excluded.refresh_computed_at_ms,
              refresh_started_at_ms = excluded.refresh_started_at_ms,
              refresh_finished_at_ms = excluded.refresh_finished_at_ms,
              refresh_row_count = excluded.refresh_row_count,
              refresh_source_rows = excluded.refresh_source_rows,
              error = excluded.error,
              updated_at_ms = excluded.updated_at_ms
            WHERE token_radar_publications.published_computed_at_ms IS NULL
               OR token_radar_publications.published_computed_at_ms <= excluded.published_computed_at_ms
            """,
            (
                projection_version,
                window,
                scope,
                int(computed_at_ms),
                max(0, int(row_count)),
                max(0, int(source_rows)),
                max(0, int(source_max_received_at_ms)),
                int(computed_at_ms),
                int(started_at_ms) if started_at_ms is not None else None,
                int(finished_at_ms) if finished_at_ms is not None else None,
                max(0, int(row_count)),
                max(0, int(source_rows)),
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()

    def latest_publications(
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
            SELECT publications.*
            FROM requested
            JOIN token_radar_publications publications
              ON publications."window" = requested."window"
             AND publications.scope = requested.scope
            WHERE publications.projection_version = %s
            """,
            [*params, projection_version],
        ).fetchall()
        return {
            (str(row["window"]), str(row["scope"])): {
                "status": "ready" if row.get("published_computed_at_ms") is not None else str(row["refresh_status"]),
                "refresh_status": str(row["refresh_status"]),
                "reason": row.get("reason"),
                "source_rows": int(row.get("published_source_rows") or 0),
                "row_count": int(row.get("published_row_count") or 0),
                "source_max_received_at_ms": int(row.get("published_source_max_received_at_ms") or 0),
                "computed_at_ms": (
                    int(row["published_computed_at_ms"]) if row.get("published_computed_at_ms") is not None else None
                ),
                "published_computed_at_ms": (
                    int(row["published_computed_at_ms"]) if row.get("published_computed_at_ms") is not None else None
                ),
                "refresh_started_at_ms": (
                    int(row["refresh_started_at_ms"]) if row.get("refresh_started_at_ms") is not None else None
                ),
                "refresh_finished_at_ms": (
                    int(row["refresh_finished_at_ms"]) if row.get("refresh_finished_at_ms") is not None else None
                ),
                "error": row.get("error"),
            }
            for row in rows
        }


def _json_payload(row: dict[str, Any]) -> dict[str, Any]:
    _validate_factor_contract(row)
    out = dict(row)
    for key in (
        "factor_snapshot_json",
        "intent_json",
        "asset_json",
        "primary_venue_json",
        "target_json",
        "data_health_json",
        "source_event_ids_json",
    ):
        payload = out.get(key) if out.get(key) is not None else ([] if key.endswith("_ids_json") else {})
        out[key] = Jsonb(_json_ready(payload))
    return out


def _now_ms() -> int:
    return int(time.time() * 1000)


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
    for key in ("families", "hard_gates", "composite"):
        payload = factor_snapshot.get(key)
        if not isinstance(payload, dict) or not payload:
            raise ValueError(f"factor_snapshot_json.{key} is required for token radar row hard-cut contract")


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
