from __future__ import annotations

import hashlib
import json
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
    "target_type_key",
    "identity_id",
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
    "payload_hash",
    "listed_at_ms",
    "created_at_ms",
)
RADAR_ROW_INSERT_COLUMNS_SQL = """
  row_id, projection_version, "window", scope, computed_at_ms, source_max_received_at_ms,
  lane, target_type_key, identity_id, rank, intent_id, event_id, target_type, target_id,
  pricefeed_id, intent_json, asset_json, primary_venue_json, target_json, attention_json,
  resolution_json, market_json, price_json, score_json, factor_snapshot_json,
  factor_version, decision, data_health_json, source_event_ids_json, payload_hash,
  listed_at_ms, created_at_ms
"""
RADAR_ROW_INSERT_VALUES_SQL = """
  %(row_id)s, %(projection_version)s, %(window)s, %(scope)s, %(computed_at_ms)s,
  %(source_max_received_at_ms)s, %(lane)s, %(target_type_key)s, %(identity_id)s,
  %(rank)s, %(intent_id)s, %(event_id)s, %(target_type)s, %(target_id)s,
  %(pricefeed_id)s, %(intent_json)s, %(asset_json)s, %(primary_venue_json)s,
  %(target_json)s, %(attention_json)s, %(resolution_json)s, %(market_json)s,
  %(price_json)s, %(score_json)s, %(factor_snapshot_json)s, %(factor_version)s,
  %(decision)s, %(data_health_json)s, %(source_event_ids_json)s, %(payload_hash)s,
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
        existing_current = self._current_rows_for_projection_set(
            projection_version=projection_version,
            window=window,
            scope=scope,
        )
        existing_by_key = {_current_key(row): row for row in existing_current}
        current_keys = {_current_key(row) for row in rows_to_insert}
        exited_rows = [row for key, row in existing_by_key.items() if key not in current_keys]
        self._write_rank_exit_audits(exited_rows, computed_at_ms=int(computed_at_ms))
        self._delete_exited_current_rows(exited_rows)

        change_baselines = [(row, existing_by_key.get(_current_key(row))) for row in rows_to_insert]
        for index, (row, previous) in enumerate(change_baselines, start=1):
            if previous is not None and str(previous.get("payload_hash") or "") != str(row["payload_hash"]):
                self._neutralize_current_rank(row, temporary_rank=-(int(computed_at_ms) + index))

        for row, previous in change_baselines:
            changed = previous is None or str(previous.get("payload_hash") or "") != str(row["payload_hash"])
            payload = _json_payload(row)
            self.conn.execute(
                f"""
                INSERT INTO token_radar_current_rows({RADAR_ROW_INSERT_COLUMNS_SQL})
                VALUES ({RADAR_ROW_INSERT_VALUES_SQL})
                ON CONFLICT(projection_version, "window", scope, lane, target_type_key, identity_id)
                DO UPDATE SET
                  row_id = excluded.row_id,
                  computed_at_ms = excluded.computed_at_ms,
                  source_max_received_at_ms = excluded.source_max_received_at_ms,
                  rank = excluded.rank,
                  intent_id = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.intent_id
                    ELSE token_radar_current_rows.intent_id
                  END,
                  event_id = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.event_id
                    ELSE token_radar_current_rows.event_id
                  END,
                  target_type = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.target_type
                    ELSE token_radar_current_rows.target_type
                  END,
                  target_id = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.target_id
                    ELSE token_radar_current_rows.target_id
                  END,
                  pricefeed_id = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.pricefeed_id
                    ELSE token_radar_current_rows.pricefeed_id
                  END,
                  intent_json = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.intent_json
                    ELSE token_radar_current_rows.intent_json
                  END,
                  asset_json = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.asset_json
                    ELSE token_radar_current_rows.asset_json
                  END,
                  primary_venue_json = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.primary_venue_json
                    ELSE token_radar_current_rows.primary_venue_json
                  END,
                  target_json = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.target_json
                    ELSE token_radar_current_rows.target_json
                  END,
                  attention_json = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.attention_json
                    ELSE token_radar_current_rows.attention_json
                  END,
                  resolution_json = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.resolution_json
                    ELSE token_radar_current_rows.resolution_json
                  END,
                  market_json = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.market_json
                    ELSE token_radar_current_rows.market_json
                  END,
                  price_json = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.price_json
                    ELSE token_radar_current_rows.price_json
                  END,
                  score_json = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.score_json
                    ELSE token_radar_current_rows.score_json
                  END,
                  factor_snapshot_json = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.factor_snapshot_json
                    ELSE token_radar_current_rows.factor_snapshot_json
                  END,
                  factor_version = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.factor_version
                    ELSE token_radar_current_rows.factor_version
                  END,
                  decision = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.decision
                    ELSE token_radar_current_rows.decision
                  END,
                  data_health_json = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.data_health_json
                    ELSE token_radar_current_rows.data_health_json
                  END,
                  source_event_ids_json = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.source_event_ids_json
                    ELSE token_radar_current_rows.source_event_ids_json
                  END,
                  payload_hash = excluded.payload_hash,
                  listed_at_ms = excluded.listed_at_ms,
                  created_at_ms = CASE
                    WHEN token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash
                      THEN excluded.created_at_ms
                    ELSE token_radar_current_rows.created_at_ms
                  END
                """,
                payload,
            )
            if not changed:
                continue
            self.conn.execute(
                """
                INSERT INTO token_radar_rank_history(
                  row_id, projection_version, "window", scope, lane, target_type_key, identity_id,
                  recorded_at_ms, computed_at_ms, source_max_received_at_ms, previous_rank, rank,
                  rank_delta, rank_score, decision, target_type, target_id, pricefeed_id, target_json,
                  payload_hash, listed_at_ms, created_at_ms
                )
                VALUES (
                  %(row_id)s, %(projection_version)s, %(window)s, %(scope)s, %(lane)s,
                  %(target_type_key)s, %(identity_id)s, %(recorded_at_ms)s, %(computed_at_ms)s,
                  %(source_max_received_at_ms)s, %(previous_rank)s, %(rank)s, %(rank_delta)s,
                  %(rank_score)s, %(decision)s, %(target_type)s, %(target_id)s, %(pricefeed_id)s,
                  %(target_json)s, %(payload_hash)s, %(listed_at_ms)s, %(created_at_ms)s
                )
                """,
                _rank_history_payload(row, previous=previous),
            )
            self.conn.execute(
                f"""
                INSERT INTO token_radar_snapshot_audit(
                  snapshot_id, audit_reason, recorded_at_ms, {RADAR_ROW_INSERT_COLUMNS_SQL}
                )
                VALUES (%(snapshot_id)s, %(audit_reason)s, %(recorded_at_ms)s, {RADAR_ROW_INSERT_VALUES_SQL})
                """,
                {
                    "snapshot_id": str(row["row_id"]),
                    "audit_reason": _audit_reason(row, previous=previous),
                    "recorded_at_ms": int(computed_at_ms),
                    **payload,
                },
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

    def _current_rows_for_projection_set(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM token_radar_current_rows
            WHERE projection_version = %s
              AND "window" = %s
              AND scope = %s
            """,
            (projection_version, window, scope),
        ).fetchall()
        return [dict(row) for row in rows]

    def _write_rank_exit_audits(self, rows: list[dict[str, Any]], *, computed_at_ms: int) -> None:
        for row in rows:
            payload_row = {**row, "computed_at_ms": int(computed_at_ms)}
            payload = _json_payload(payload_row)
            self.conn.execute(
                f"""
                INSERT INTO token_radar_snapshot_audit(
                  snapshot_id, audit_reason, recorded_at_ms, {RADAR_ROW_INSERT_COLUMNS_SQL}
                )
                VALUES (%(snapshot_id)s, 'rank_exit', %(recorded_at_ms)s, {RADAR_ROW_INSERT_VALUES_SQL})
                """,
                {
                    "snapshot_id": f"{row.get('row_id')}:rank_exit",
                    "recorded_at_ms": int(computed_at_ms),
                    **payload,
                },
            )

    def _delete_exited_current_rows(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        cursor = self.conn.execute(
            """
            WITH exited(lane, target_type_key, identity_id) AS (
              SELECT *
              FROM unnest(%s::text[], %s::text[], %s::text[])
            )
            DELETE FROM token_radar_current_rows current_rows
            USING exited
            WHERE current_rows.lane = exited.lane
              AND current_rows.target_type_key = exited.target_type_key
              AND current_rows.identity_id = exited.identity_id
              AND current_rows.projection_version = %s
              AND current_rows."window" = %s
              AND current_rows.scope = %s
            """,
            (
                [str(row["lane"]) for row in rows],
                [str(row["target_type_key"]) for row in rows],
                [str(row["identity_id"]) for row in rows],
                str(rows[0]["projection_version"]),
                str(rows[0]["window"]),
                str(rows[0]["scope"]),
            ),
        )
        return int(getattr(cursor, "rowcount", 0) or 0)

    def _neutralize_current_rank(self, row: dict[str, Any], *, temporary_rank: int) -> None:
        self.conn.execute(
            """
            UPDATE token_radar_current_rows
            SET rank = %s
            WHERE projection_version = %s
              AND "window" = %s
              AND scope = %s
              AND lane = %s
              AND target_type_key = %s
              AND identity_id = %s
              AND payload_hash IS DISTINCT FROM %s
            """,
            (
                int(temporary_rank),
                row.get("projection_version"),
                row.get("window"),
                row.get("scope"),
                row.get("lane"),
                row.get("target_type_key"),
                row.get("identity_id"),
                row.get("payload_hash"),
            ),
        )

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

    def upsert_target_feature(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
        row: dict[str, Any],
        computed_at_ms: int,
        commit: bool = True,
    ) -> int:
        _validate_factor_contract(row)
        payload = _target_feature_payload(
            row,
            projection_version=projection_version,
            window=window,
            scope=scope,
            computed_at_ms=int(computed_at_ms),
        )
        self.conn.execute(
            """
            INSERT INTO token_radar_target_features(
              projection_version, "window", scope, lane, target_type_key, identity_id,
              target_type, target_id, pricefeed_id, latest_event_received_at_ms,
              latest_market_observed_at_ms, attention_score, market_score, credibility_score,
              rank_score, factor_snapshot_json, source_event_ids_json, source_intent_ids_json,
              source_resolution_ids_json, payload_hash, last_scored_at_ms, created_at_ms, updated_at_ms
            )
            VALUES (
              %(projection_version)s, %(window)s, %(scope)s, %(lane)s, %(target_type_key)s, %(identity_id)s,
              %(target_type)s, %(target_id)s, %(pricefeed_id)s, %(latest_event_received_at_ms)s,
              %(latest_market_observed_at_ms)s, %(attention_score)s, %(market_score)s, %(credibility_score)s,
              %(rank_score)s, %(factor_snapshot_json)s, %(source_event_ids_json)s, %(source_intent_ids_json)s,
              %(source_resolution_ids_json)s, %(payload_hash)s, %(last_scored_at_ms)s, %(created_at_ms)s,
              %(updated_at_ms)s
            )
            ON CONFLICT(projection_version, "window", scope, lane, target_type_key, identity_id)
            DO UPDATE SET
              target_type = excluded.target_type,
              target_id = excluded.target_id,
              pricefeed_id = excluded.pricefeed_id,
              latest_event_received_at_ms = excluded.latest_event_received_at_ms,
              latest_market_observed_at_ms = excluded.latest_market_observed_at_ms,
              attention_score = excluded.attention_score,
              market_score = excluded.market_score,
              credibility_score = excluded.credibility_score,
              rank_score = excluded.rank_score,
              factor_snapshot_json = excluded.factor_snapshot_json,
              source_event_ids_json = excluded.source_event_ids_json,
              source_intent_ids_json = excluded.source_intent_ids_json,
              source_resolution_ids_json = excluded.source_resolution_ids_json,
              payload_hash = excluded.payload_hash,
              last_scored_at_ms = excluded.last_scored_at_ms,
              updated_at_ms = excluded.updated_at_ms
            WHERE token_radar_target_features.payload_hash IS DISTINCT FROM excluded.payload_hash
               OR token_radar_target_features.last_scored_at_ms < excluded.last_scored_at_ms
            """,
            payload,
        )
        if commit:
            self.conn.commit()
        return 1

    def delete_target_feature(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
        lane: str,
        target_type_key: str,
        identity_id: str,
        commit: bool = True,
    ) -> int:
        cursor = self.conn.execute(
            """
            DELETE FROM token_radar_target_features
            WHERE projection_version = %s
              AND "window" = %s
              AND scope = %s
              AND lane = %s
              AND target_type_key = %s
              AND identity_id = %s
            """,
            (projection_version, window, scope, lane, target_type_key, identity_id),
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def list_target_features_for_rank_set(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM token_radar_target_features
            WHERE projection_version = %s
              AND "window" = %s
              AND scope = %s
            ORDER BY lane DESC, rank_score DESC, latest_event_received_at_ms DESC, identity_id ASC
            """,
            (projection_version, window, scope),
        ).fetchall()
        return [_row_from_target_feature(dict(row)) for row in rows]

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
    target_type_key, identity_id = _identity_key(out)
    out.update(
        {
            "projection_version": projection_version,
            "window": window,
            "scope": scope,
            "computed_at_ms": int(computed_at_ms),
            "target_type_key": target_type_key,
            "identity_id": identity_id,
            "listed_at_ms": int(listed_at_ms),
        }
    )
    out["payload_hash"] = _payload_hash(out)
    return out


def _target_feature_payload(
    row: dict[str, Any],
    *,
    projection_version: str,
    window: str,
    scope: str,
    computed_at_ms: int,
) -> dict[str, Any]:
    target_type_key, identity_id = _identity_key(row)
    factor_snapshot = row.get("factor_snapshot_json") or {}
    families = factor_snapshot.get("families") if isinstance(factor_snapshot, dict) else {}
    social_heat = families.get("social_heat") if isinstance(families, dict) else {}
    social_propagation = families.get("social_propagation") if isinstance(families, dict) else {}
    semantic_catalyst = families.get("semantic_catalyst") if isinstance(families, dict) else {}
    latest_market_observed_at_ms = _latest_market_observed_at_ms(factor_snapshot)
    payload = {
        "projection_version": projection_version,
        "window": window,
        "scope": scope,
        "lane": str(row.get("lane") or "attention"),
        "target_type_key": target_type_key,
        "identity_id": identity_id,
        "target_type": row.get("target_type"),
        "target_id": row.get("target_id"),
        "pricefeed_id": row.get("pricefeed_id"),
        "latest_event_received_at_ms": int(row.get("source_max_received_at_ms") or computed_at_ms),
        "latest_market_observed_at_ms": latest_market_observed_at_ms,
        "attention_score": _family_score(social_heat),
        "market_score": _family_score(families.get("timing_risk") if isinstance(families, dict) else {}),
        "credibility_score": max(_family_score(social_propagation), _family_score(semantic_catalyst)),
        "rank_score": _rank_score(factor_snapshot) or 0.0,
        "factor_snapshot_json": factor_snapshot,
        "source_event_ids_json": list(row.get("source_event_ids_json") or []),
        "source_intent_ids_json": [str(row.get("intent_id") or "")] if row.get("intent_id") else [],
        "source_resolution_ids_json": _resolution_ids(row),
        "last_scored_at_ms": int(computed_at_ms),
        "created_at_ms": int(row.get("created_at_ms") or computed_at_ms),
        "updated_at_ms": int(computed_at_ms),
    }
    payload["payload_hash"] = _target_feature_hash(payload)
    for key in (
        "factor_snapshot_json",
        "source_event_ids_json",
        "source_intent_ids_json",
        "source_resolution_ids_json",
    ):
        payload[key] = Jsonb(_json_ready(payload[key]))
    return payload


def _row_from_target_feature(row: dict[str, Any]) -> dict[str, Any]:
    factor_snapshot = _json_value(row.get("factor_snapshot_json")) or {}
    source_event_ids = _json_list(row.get("source_event_ids_json"))
    source_intent_ids = _json_list(row.get("source_intent_ids_json"))
    source_resolution_ids = _json_list(row.get("source_resolution_ids_json"))
    intent_id = source_intent_ids[0] if source_intent_ids else str(row.get("identity_id") or "")
    event_id = source_event_ids[-1] if source_event_ids else intent_id
    target_type = row.get("target_type")
    target_id = row.get("target_id")
    subject = factor_snapshot.get("subject") if isinstance(factor_snapshot, dict) else {}
    data_health = factor_snapshot.get("data_health") if isinstance(factor_snapshot, dict) else {}
    return {
        "row_id": _stable_row_id(
            str(row.get("projection_version") or ""),
            str(row.get("window") or ""),
            str(row.get("scope") or ""),
            str(row.get("lane") or ""),
            str(row.get("target_type_key") or ""),
            str(row.get("identity_id") or ""),
        ),
        "source_max_received_at_ms": int(row.get("latest_event_received_at_ms") or 0),
        "lane": str(row.get("lane") or "attention"),
        "rank": 0,
        "intent_id": intent_id,
        "event_id": event_id,
        "target_type_key": str(row.get("target_type_key") or ""),
        "identity_id": str(row.get("identity_id") or ""),
        "target_type": target_type,
        "target_id": target_id,
        "pricefeed_id": row.get("pricefeed_id"),
        "intent_json": {
            "intent_id": intent_id,
            "display_symbol": (subject or {}).get("symbol") if isinstance(subject, dict) else None,
            "display_name": (subject or {}).get("name") if isinstance(subject, dict) else None,
            "evidence": [],
        },
        "asset_json": subject if target_type == "Asset" and isinstance(subject, dict) else {},
        "target_json": subject if isinstance(subject, dict) else {},
        "primary_venue_json": None,
        "factor_snapshot_json": factor_snapshot,
        "factor_version": factor_snapshot.get("schema_version") if isinstance(factor_snapshot, dict) else None,
        "attention_json": {},
        "resolution_json": {
            "status": "EXACT" if target_id else "NIL",
            "target_type": target_type,
            "target_id": target_id,
            "pricefeed_id": row.get("pricefeed_id"),
            "resolution_ids": source_resolution_ids,
            "reason_codes": [],
            "candidate_ids": [],
            "lookup_keys": [],
            "discovery": [],
        },
        "market_json": {},
        "price_json": {},
        "score_json": {},
        "decision": (factor_snapshot.get("composite") or {}).get("recommended_decision")
        if isinstance(factor_snapshot, dict)
        else None,
        "data_health_json": {
            "factor_snapshot": "ready",
            "identity": (data_health or {}).get("identity") if isinstance(data_health, dict) else None,
            "market": (data_health or {}).get("market") if isinstance(data_health, dict) else None,
            "social": (data_health or {}).get("social") if isinstance(data_health, dict) else None,
            "alpha": (data_health or {}).get("alpha") if isinstance(data_health, dict) else None,
        },
        "source_event_ids_json": source_event_ids,
        "created_at_ms": int(row.get("last_scored_at_ms") or row.get("updated_at_ms") or _now_ms()),
    }


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


def _rank_history_payload(row: dict[str, Any], *, previous: dict[str, Any] | None) -> dict[str, Any]:
    previous_rank = int(previous["rank"]) if previous and previous.get("rank") is not None else None
    rank = int(row.get("rank") or 0)
    return {
        "row_id": row.get("row_id"),
        "projection_version": row.get("projection_version"),
        "window": row.get("window"),
        "scope": row.get("scope"),
        "recorded_at_ms": row.get("computed_at_ms"),
        "computed_at_ms": row.get("computed_at_ms"),
        "source_max_received_at_ms": row.get("source_max_received_at_ms"),
        "lane": row.get("lane"),
        "target_type_key": row.get("target_type_key"),
        "identity_id": row.get("identity_id"),
        "previous_rank": previous_rank,
        "rank": rank,
        "rank_delta": previous_rank - rank if previous_rank is not None else None,
        "rank_score": _rank_score(row.get("factor_snapshot_json")),
        "decision": row.get("decision"),
        "target_type": row.get("target_type"),
        "target_id": row.get("target_id"),
        "pricefeed_id": row.get("pricefeed_id"),
        "target_json": Jsonb(_json_ready(row.get("target_json") or {})),
        "payload_hash": row.get("payload_hash"),
        "listed_at_ms": row.get("listed_at_ms"),
        "created_at_ms": row.get("created_at_ms"),
    }


def _audit_reason(row: dict[str, Any], *, previous: dict[str, Any] | None) -> str:
    if previous is None:
        return "rank_enter"
    if str(previous.get("decision") or "") != str(row.get("decision") or ""):
        return "decision_change"
    return "rank_enter"


def _current_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("lane") or ""),
        str(row.get("target_type_key") or row.get("target_type") or ""),
        str(row.get("identity_id") or row.get("target_id") or row.get("intent_id") or ""),
    )


def _identity_key(row: dict[str, Any]) -> tuple[str, str]:
    target_type_key = str(row.get("target_type_key") or row.get("target_type") or "")
    identity_id = str(row.get("identity_id") or row.get("target_id") or row.get("intent_id") or "")
    return (target_type_key, identity_id)


def _nonempty_identities(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return list(dict.fromkeys(identity for identity in (_identity_key(row) for row in rows) if identity[1]))


def _payload_hash(row: dict[str, Any]) -> str:
    stable_payload = {
        column: _json_ready(row.get(column))
        for column in RADAR_ROW_COLUMNS
        if column
        not in {
            "row_id",
            "computed_at_ms",
            "payload_hash",
            "listed_at_ms",
            "created_at_ms",
        }
    }
    encoded = json.dumps(stable_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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


def _family_score(family: Any) -> float:
    if not isinstance(family, dict):
        return 0.0
    try:
        return float(family.get("score") or 0.0)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _latest_market_observed_at_ms(factor_snapshot: Any) -> int | None:
    if not isinstance(factor_snapshot, dict):
        return None
    market = factor_snapshot.get("market")
    if not isinstance(market, dict):
        return None
    latest = market.get("decision_latest")
    if not isinstance(latest, dict):
        return None
    value = latest.get("observed_at_ms")
    return int(value) if value is not None else None


def _resolution_ids(row: dict[str, Any]) -> list[str]:
    resolution_id = row.get("resolution_id")
    if resolution_id:
        return [str(resolution_id)]
    resolution_json = row.get("resolution_json")
    if isinstance(resolution_json, dict):
        return [str(item) for item in resolution_json.get("resolution_ids") or [] if str(item)]
    return []


def _target_feature_hash(row: dict[str, Any]) -> str:
    stable_payload = {
        key: _json_ready(value)
        for key, value in row.items()
        if key not in {"payload_hash", "last_scored_at_ms", "created_at_ms", "updated_at_ms"}
    }
    encoded = json.dumps(stable_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json_value(value: Any) -> Any:
    return getattr(value, "obj", value)


def _json_list(value: Any) -> list[str]:
    raw = _json_value(value)
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item)]


def _stable_row_id(*parts: str) -> str:
    encoded = "|".join(parts).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
