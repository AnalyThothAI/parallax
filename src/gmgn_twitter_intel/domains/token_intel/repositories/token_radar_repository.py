from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.token_intel._constants import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
)
from gmgn_twitter_intel.domains.token_intel.scoring.factor_snapshot_contract import require_token_factor_snapshot


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
        listed_at_by_key = self.first_seen_by_identity(
            projection_version=projection_version,
            window=window,
            scope=scope,
            rows=rows,
        )
        rows_to_insert = [
            {
                **row,
                "listed_at_ms": listed_at_by_key.get(_identity_key(row), int(computed_at_ms)),
            }
            for row in rows
        ]
        self.conn.execute(
            """
            DELETE FROM token_radar_rows
            WHERE projection_version = %s
              AND "window" = %s
              AND scope = %s
              AND computed_at_ms = %s
            """,
            (projection_version, window, scope, int(computed_at_ms)),
        )
        for row in rows_to_insert:
            self.conn.execute(
                """
                INSERT INTO token_radar_rows(
                  row_id, projection_version, "window", scope, computed_at_ms, source_max_received_at_ms,
                  lane, rank, intent_id, event_id, target_type, target_id, pricefeed_id, intent_json,
                  asset_json, primary_venue_json, target_json, factor_snapshot_json, factor_version,
                  decision, data_health_json,
                  source_event_ids_json, listed_at_ms, created_at_ms
                )
                VALUES (
                  %(row_id)s, %(projection_version)s, %(window)s, %(scope)s, %(computed_at_ms)s,
                  %(source_max_received_at_ms)s, %(lane)s, %(rank)s, %(intent_id)s, %(event_id)s,
                  %(target_type)s, %(target_id)s, %(pricefeed_id)s, %(intent_json)s, %(asset_json)s,
                  %(primary_venue_json)s, %(target_json)s, %(factor_snapshot_json)s, %(factor_version)s,
                  %(decision)s, %(data_health_json)s,
                  %(source_event_ids_json)s, %(listed_at_ms)s, %(created_at_ms)s
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
            WITH latest AS (
              SELECT MAX(computed_at_ms) AS computed_at_ms
              FROM token_radar_rows
              WHERE projection_version = %s AND "window" = %s AND scope = %s
            ),
            ranked AS (
              SELECT *
              FROM (
                SELECT
                  token_radar_rows.*,
                  row_number() OVER (PARTITION BY lane ORDER BY rank ASC) AS lane_rank
                FROM token_radar_rows
                JOIN latest
                  ON token_radar_rows.computed_at_ms = latest.computed_at_ms
                WHERE token_radar_rows.projection_version = %s
                  AND token_radar_rows."window" = %s
                  AND token_radar_rows.scope = %s
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
                projection_version,
                window,
                scope,
                max(0, int(limit)),
                max(0, int(limit)) * 2,
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def _listed_at_by_identity(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
        rows: list[dict[str, Any]],
    ) -> dict[tuple[str, str], int]:
        identities = list(dict.fromkeys(_identity_key(row) for row in rows))
        if not identities:
            return {}
        target_type_keys = [target_type for target_type, _ in identities]
        identity_ids = [identity_id for _, identity_id in identities]
        rows = self.conn.execute(
            """
            WITH requested(target_type_key, identity_id) AS (
              SELECT *
              FROM unnest(%s::text[], %s::text[])
            )
            SELECT
              requested.target_type_key,
              requested.identity_id,
              first_seen.listed_at_ms
            FROM requested
            LEFT JOIN LATERAL (
              SELECT COALESCE(history.listed_at_ms, history.computed_at_ms) AS listed_at_ms
              FROM token_radar_rows history
              WHERE history.projection_version = %s
                AND history."window" = %s
                AND history.scope = %s
                AND COALESCE(history.target_type, '') = requested.target_type_key
                AND COALESCE(history.target_id, history.intent_id) = requested.identity_id
              ORDER BY history.computed_at_ms ASC
              LIMIT 1
            ) first_seen ON true
            """,
            (target_type_keys, identity_ids, projection_version, window, scope),
        ).fetchall()
        return {
            (str(row["target_type_key"]), str(row["identity_id"])): int(row["listed_at_ms"])
            for row in rows
            if row.get("listed_at_ms") is not None
        }

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
        listed_at_by_key = {
            (str(row["target_type_key"]), str(row["identity_id"])): int(row["first_seen_ms"])
            for row in compact_rows
            if row.get("first_seen_ms") is not None
        }
        missing_rows = [
            row for row in rows if _identity_key(row) in identities and _identity_key(row) not in listed_at_by_key
        ]
        if missing_rows:
            listed_at_by_key.update(
                self._listed_at_by_identity(
                    projection_version=projection_version,
                    window=window,
                    scope=scope,
                    rows=missing_rows,
                )
            )
        return listed_at_by_key

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

    def backfill_first_seen_from_history(
        self,
        *,
        batch_size: int,
        after_key: tuple[str, str, str, str, str] | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        limit = max(1, int(batch_size))
        after_projection_version, after_window, after_scope, after_target_type_key, after_identity_id = after_key or (
            None,
            None,
            None,
            None,
            None,
        )
        rows = self.conn.execute(
            """
            WITH identity_page AS (
              SELECT DISTINCT ON (
                projection_version,
                "window",
                scope,
                COALESCE(target_type, ''),
                COALESCE(target_id, intent_id)
              )
                projection_version,
                "window",
                scope,
                COALESCE(target_type, '') AS target_type_key,
                COALESCE(target_id, intent_id) AS identity_id
              FROM token_radar_rows
              WHERE COALESCE(target_id, intent_id, '') <> ''
                AND (
                  %s::text IS NULL
                  OR (projection_version, "window", scope, COALESCE(target_type, ''), COALESCE(target_id, intent_id))
                     > (%s, %s, %s, %s, %s)
                )
              ORDER BY
                projection_version,
                "window",
                scope,
                COALESCE(target_type, ''),
                COALESCE(target_id, intent_id),
                computed_at_ms ASC
              LIMIT %s
            ),
            grouped AS (
              SELECT
                identity_page.projection_version,
                identity_page."window",
                identity_page.scope,
                identity_page.target_type_key,
                identity_page.identity_id,
                MIN(COALESCE(rows.listed_at_ms, rows.computed_at_ms)) AS first_seen_ms,
                MAX(rows.computed_at_ms) AS last_seen_ms,
                (
                  ARRAY_AGG(
                    rows.row_id
                    ORDER BY
                      COALESCE(rows.listed_at_ms, rows.computed_at_ms) ASC,
                      rows.computed_at_ms ASC,
                      rows.row_id ASC
                  )
                )[1] AS first_row_id,
                (ARRAY_AGG(rows.row_id ORDER BY rows.computed_at_ms DESC, rows.row_id DESC))[1] AS latest_row_id
              FROM identity_page
              JOIN token_radar_rows rows
                ON rows.projection_version = identity_page.projection_version
               AND rows."window" = identity_page."window"
               AND rows.scope = identity_page.scope
               AND COALESCE(rows.target_type, '') = identity_page.target_type_key
               AND COALESCE(rows.target_id, rows.intent_id) = identity_page.identity_id
              GROUP BY
                identity_page.projection_version,
                identity_page."window",
                identity_page.scope,
                identity_page.target_type_key,
                identity_page.identity_id
            )
            SELECT *
            FROM grouped
            ORDER BY projection_version, "window", scope, target_type_key, identity_id
            """,
            (
                after_projection_version,
                after_projection_version,
                after_window,
                after_scope,
                after_target_type_key,
                after_identity_id,
                limit,
            ),
        ).fetchall()
        records = [dict(row) for row in rows]
        if records:
            now_ms = _now_ms()
            values_sql = ",".join(["(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(records))
            params: list[Any] = []
            for row in records:
                params.extend(
                    [
                        row["projection_version"],
                        row["window"],
                        row["scope"],
                        row["target_type_key"],
                        row["identity_id"],
                        int(row["first_seen_ms"]),
                        int(row["last_seen_ms"]),
                        row.get("first_row_id"),
                        row.get("latest_row_id"),
                        now_ms,
                        now_ms,
                    ]
                )
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
        next_after_key = None
        if records:
            last = records[-1]
            next_after_key = (
                str(last["projection_version"]),
                str(last["window"]),
                str(last["scope"]),
                str(last["target_type_key"]),
                str(last["identity_id"]),
            )
        return {
            "rows_upserted": len(records),
            "next_after_key": next_after_key,
            "has_more": len(records) == limit,
        }

    def backfill_first_seen_rows_batch(
        self,
        *,
        batch_size: int,
        after_computed_at_ms: int | None = None,
        after_row_id: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        limit = max(1, int(batch_size))
        rows = self.conn.execute(
            """
            SELECT
              row_id,
              projection_version,
              "window",
              scope,
              computed_at_ms,
              COALESCE(listed_at_ms, computed_at_ms) AS first_seen_ms,
              COALESCE(target_type, '') AS target_type_key,
              COALESCE(target_id, intent_id) AS identity_id
            FROM token_radar_rows
            WHERE COALESCE(target_id, intent_id, '') <> ''
              AND (
                %s::bigint IS NULL
                OR (computed_at_ms, row_id) > (%s, %s)
              )
            ORDER BY computed_at_ms ASC, row_id ASC
            LIMIT %s
            """,
            (
                after_computed_at_ms,
                after_computed_at_ms,
                after_row_id,
                limit,
            ),
        ).fetchall()
        raw_records = [dict(row) for row in rows]
        compacted: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
        for row in raw_records:
            key = (
                str(row["projection_version"]),
                str(row["window"]),
                str(row["scope"]),
                str(row["target_type_key"]),
                str(row["identity_id"]),
            )
            first_seen_ms = int(row["first_seen_ms"])
            last_seen_ms = int(row["computed_at_ms"])
            current = compacted.get(key)
            if current is None:
                compacted[key] = {
                    "projection_version": key[0],
                    "window": key[1],
                    "scope": key[2],
                    "target_type_key": key[3],
                    "identity_id": key[4],
                    "first_seen_ms": first_seen_ms,
                    "last_seen_ms": last_seen_ms,
                    "first_row_id": row["row_id"],
                    "latest_row_id": row["row_id"],
                }
                continue
            if first_seen_ms <= int(current["first_seen_ms"]):
                current["first_seen_ms"] = first_seen_ms
                current["first_row_id"] = row["row_id"]
            if last_seen_ms >= int(current["last_seen_ms"]):
                current["last_seen_ms"] = last_seen_ms
                current["latest_row_id"] = row["row_id"]

        records = list(compacted.values())
        if records:
            now_ms = _now_ms()
            values_sql = ",".join(["(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(records))
            params: list[Any] = []
            for row in records:
                params.extend(
                    [
                        row["projection_version"],
                        row["window"],
                        row["scope"],
                        row["target_type_key"],
                        row["identity_id"],
                        int(row["first_seen_ms"]),
                        int(row["last_seen_ms"]),
                        row["first_row_id"],
                        row["latest_row_id"],
                        now_ms,
                        now_ms,
                    ]
                )
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
        last = raw_records[-1] if raw_records else None
        return {
            "rows_scanned": len(raw_records),
            "rows_upserted": len(records),
            "last_computed_at_ms": int(last["computed_at_ms"]) if last else after_computed_at_ms,
            "last_row_id": str(last["row_id"]) if last else after_row_id,
            "has_more": len(raw_records) == limit,
        }

    def protected_batch_counts(self) -> dict[str, int]:
        row = self.conn.execute(
            """
            WITH coverage_batches AS (
              SELECT projection_version, "window", scope, computed_at_ms
              FROM token_radar_projection_coverage
              WHERE computed_at_ms IS NOT NULL
            ),
            coverage_keys AS (
              SELECT DISTINCT projection_version, "window", scope
              FROM coverage_batches
            ),
            actual_latest_batches AS (
              SELECT
                coverage_keys.projection_version,
                coverage_keys."window",
                coverage_keys.scope,
                latest_rows.computed_at_ms
              FROM coverage_keys
              JOIN LATERAL (
                SELECT token_radar_rows.computed_at_ms
                FROM token_radar_rows
                WHERE token_radar_rows.projection_version = coverage_keys.projection_version
                  AND token_radar_rows."window" = coverage_keys."window"
                  AND token_radar_rows.scope = coverage_keys.scope
                ORDER BY token_radar_rows.computed_at_ms DESC
                LIMIT 1
              ) latest_rows ON true
            )
            SELECT
              (SELECT COUNT(*) FROM coverage_batches) AS protected_coverage_batches,
              (SELECT COUNT(*) FROM actual_latest_batches) AS protected_actual_latest_batches
            """
        ).fetchone()
        return {
            "protected_coverage_batches": int(row["protected_coverage_batches"] if row else 0),
            "protected_actual_latest_batches": int(row["protected_actual_latest_batches"] if row else 0),
        }

    def plan_prunable_rows(self, *, cutoff_ms: int, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH coverage_batches AS (
              SELECT projection_version, "window", scope, computed_at_ms
              FROM token_radar_projection_coverage
              WHERE computed_at_ms IS NOT NULL
            ),
            coverage_keys AS (
              SELECT DISTINCT projection_version, "window", scope
              FROM coverage_batches
            ),
            actual_latest_batches AS (
              SELECT
                coverage_keys.projection_version,
                coverage_keys."window",
                coverage_keys.scope,
                latest_rows.computed_at_ms
              FROM coverage_keys
              JOIN LATERAL (
                SELECT token_radar_rows.computed_at_ms
                FROM token_radar_rows
                WHERE token_radar_rows.projection_version = coverage_keys.projection_version
                  AND token_radar_rows."window" = coverage_keys."window"
                  AND token_radar_rows.scope = coverage_keys.scope
                ORDER BY token_radar_rows.computed_at_ms DESC
                LIMIT 1
              ) latest_rows ON true
            ),
            protected_batches AS (
              SELECT * FROM coverage_batches
              UNION
              SELECT * FROM actual_latest_batches
            )
            SELECT
              rows.row_id,
              rows.projection_version,
              rows."window",
              rows.scope,
              rows.computed_at_ms
            FROM token_radar_rows rows
            WHERE rows.computed_at_ms < %s
              AND NOT EXISTS (
                SELECT 1
                FROM protected_batches current
                WHERE current.projection_version = rows.projection_version
                  AND current."window" = rows."window"
                  AND current.scope = rows.scope
                  AND current.computed_at_ms = rows.computed_at_ms
              )
            ORDER BY rows.computed_at_ms ASC, rows.row_id ASC
            LIMIT %s
            """,
            (int(cutoff_ms), max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_prunable_rows_batch(self, *, cutoff_ms: int, batch_size: int, commit: bool = True) -> int:
        rows = self.conn.execute(
            """
            WITH coverage_batches AS (
              SELECT projection_version, "window", scope, computed_at_ms
              FROM token_radar_projection_coverage
              WHERE computed_at_ms IS NOT NULL
            ),
            coverage_keys AS (
              SELECT DISTINCT projection_version, "window", scope
              FROM coverage_batches
            ),
            actual_latest_batches AS (
              SELECT
                coverage_keys.projection_version,
                coverage_keys."window",
                coverage_keys.scope,
                latest_rows.computed_at_ms
              FROM coverage_keys
              JOIN LATERAL (
                SELECT token_radar_rows.computed_at_ms
                FROM token_radar_rows
                WHERE token_radar_rows.projection_version = coverage_keys.projection_version
                  AND token_radar_rows."window" = coverage_keys."window"
                  AND token_radar_rows.scope = coverage_keys.scope
                ORDER BY token_radar_rows.computed_at_ms DESC
                LIMIT 1
              ) latest_rows ON true
            ),
            protected_batches AS (
              SELECT * FROM coverage_batches
              UNION
              SELECT * FROM actual_latest_batches
            ),
            victims AS (
              SELECT rows.row_id
              FROM token_radar_rows rows
              WHERE rows.computed_at_ms < %s
                AND NOT EXISTS (
                  SELECT 1
                  FROM protected_batches current
                  WHERE current.projection_version = rows.projection_version
                    AND current."window" = rows."window"
                    AND current.scope = rows.scope
                    AND current.computed_at_ms = rows.computed_at_ms
                )
              ORDER BY rows.computed_at_ms ASC, rows.row_id ASC
              LIMIT %s
            )
            DELETE FROM token_radar_rows rows
            USING victims
            WHERE rows.row_id = victims.row_id
            RETURNING rows.row_id
            """,
            (int(cutoff_ms), max(0, int(batch_size))),
        ).fetchall()
        if commit:
            self.conn.commit()
        return len(rows)

    def insert_retention_run(self, payload: dict[str, Any], *, commit: bool = True) -> dict[str, Any]:
        row = self.conn.execute(
            """
            INSERT INTO token_radar_retention_runs(
              run_id, mode, retention_days, cutoff_ms, batch_size, max_batches,
              rows_planned, rows_deleted, status, error, started_at_ms, finished_at_ms, created_at_ms
            )
            VALUES (
              %(run_id)s, %(mode)s, %(retention_days)s, %(cutoff_ms)s, %(batch_size)s, %(max_batches)s,
              %(rows_planned)s, %(rows_deleted)s, %(status)s, %(error)s, %(started_at_ms)s, %(finished_at_ms)s,
              %(created_at_ms)s
            )
            RETURNING *
            """,
            payload,
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row) if row else dict(payload)

    def finish_retention_run(
        self,
        run_id: str,
        *,
        status: str,
        rows_deleted: int,
        error: str | None = None,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            UPDATE token_radar_retention_runs
            SET status = %s,
                rows_deleted = %s,
                error = %s,
                finished_at_ms = %s
            WHERE run_id = %s
            """,
            (status, max(0, int(rows_deleted)), error, _now_ms(), str(run_id)),
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


def _identity_key(row: dict[str, Any]) -> tuple[str, str]:
    target_type = str(row.get("target_type") or "")
    identity_id = str(row.get("target_id") or row.get("intent_id") or "")
    return (target_type, identity_id)


def _nonempty_identities(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return list(dict.fromkeys(identity for identity in (_identity_key(row) for row in rows) if identity[1]))


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
