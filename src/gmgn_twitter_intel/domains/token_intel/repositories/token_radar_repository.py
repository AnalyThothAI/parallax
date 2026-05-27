from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any, TypedDict

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
    "generation_id",
    "published_at_ms",
    "source_frontier_ms",
    "lane",
    "target_type_key",
    "identity_id",
    "rank",
    "rank_score",
    "intent_id",
    "event_id",
    "target_type",
    "target_id",
    "pricefeed_id",
    "intent_json",
    "resolution_json",
    "factor_snapshot_json",
    "factor_version",
    "decision",
    "quality_status",
    "degraded_reasons_json",
    "data_health_json",
    "source_event_ids_json",
    "payload_hash",
    "listed_at_ms",
    "created_at_ms",
)
RADAR_ROW_INSERT_COLUMNS_SQL = """
  row_id, projection_version, "window", scope, computed_at_ms, source_max_received_at_ms,
  generation_id, published_at_ms, source_frontier_ms,
  lane, target_type_key, identity_id, rank, rank_score, intent_id, event_id, target_type, target_id,
  pricefeed_id, intent_json, resolution_json, factor_snapshot_json,
  factor_version, decision, quality_status, degraded_reasons_json,
  data_health_json, source_event_ids_json, payload_hash,
  listed_at_ms, created_at_ms
"""
RADAR_ROW_INSERT_VALUES_SQL = """
  %(row_id)s, %(projection_version)s, %(window)s, %(scope)s, %(computed_at_ms)s,
  %(source_max_received_at_ms)s, %(generation_id)s, %(published_at_ms)s,
  %(source_frontier_ms)s, %(lane)s, %(target_type_key)s, %(identity_id)s,
  %(rank)s, %(rank_score)s, %(intent_id)s, %(event_id)s, %(target_type)s, %(target_id)s,
  %(pricefeed_id)s, %(intent_json)s, %(resolution_json)s,
  %(factor_snapshot_json)s, %(factor_version)s,
  %(decision)s, %(quality_status)s, %(degraded_reasons_json)s, %(data_health_json)s,
  %(source_event_ids_json)s, %(payload_hash)s,
  %(listed_at_ms)s, %(created_at_ms)s
"""


class PublicationResult(TypedDict):
    status: str
    generation_id: str
    rows_written: int


class TokenRadarRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def publish_current_generation(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
        generation_id: str,
        published_at_ms: int,
        source_frontier_ms: int,
        rows: list[dict[str, Any]],
        source_rows: int | None = None,
        started_at_ms: int | None = None,
        finished_at_ms: int | None = None,
        on_current_changes: Callable[..., None] | None = None,
        commit: bool = True,
    ) -> PublicationResult:
        self.conn.execute(
            """
            SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))
            """,
            (projection_version, f"{window}:{scope}"),
        )
        latest = self.conn.execute(
            """
            SELECT current_generation_id, current_published_at_ms
            FROM token_radar_publication_state
            WHERE projection_version = %s
              AND "window" = %s
              AND scope = %s
            """,
            (projection_version, window, scope),
        ).fetchone()
        latest_current_generation_id = (
            str(latest["current_generation_id"])
            if latest and latest.get("current_generation_id") is not None
            else None
        )
        latest_published_at_ms = (
            int(latest["current_published_at_ms"])
            if latest and latest.get("current_published_at_ms") is not None
            else None
        )
        if latest_published_at_ms is not None and latest_published_at_ms > int(published_at_ms):
            if commit:
                self.conn.commit()
            return {"status": "stale_skipped", "generation_id": str(generation_id), "rows_written": 0}

        for row in rows:
            _validate_factor_contract(row)
        existing_current = self._current_rows_for_projection_set(
            projection_version=projection_version,
            window=window,
            scope=scope,
        )
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
                generation_id=generation_id,
                published_at_ms=int(published_at_ms),
                source_frontier_ms=int(source_frontier_ms),
                listed_at_ms=listed_at_by_key.get(_identity_key(row), int(published_at_ms)),
            )
            for row in rows
        ]
        existing_generation_id = latest_current_generation_id or _first_generation_id(existing_current)
        existing_signature = stable_generation_id(
            projection_version=projection_version,
            window=window,
            scope=scope,
            rows=existing_current,
        )
        incoming_signature = stable_generation_id(
            projection_version=projection_version,
            window=window,
            scope=scope,
            rows=rows_to_insert,
        )
        if existing_generation_id is not None and existing_signature == incoming_signature:
            self._upsert_ready_publication_state(
                projection_version=projection_version,
                window=window,
                scope=scope,
                generation_id=existing_generation_id,
                published_at_ms=published_at_ms,
                source_frontier_ms=source_frontier_ms,
                row_count=len(rows_to_insert),
                source_rows=source_rows,
                started_at_ms=started_at_ms,
                finished_at_ms=finished_at_ms,
            )
            if commit:
                self.conn.commit()
            return {"status": "unchanged", "generation_id": existing_generation_id, "rows_written": 0}

        existing_by_key = {_current_key(row): row for row in existing_current}
        current_keys = {_current_key(row) for row in rows_to_insert}
        exited_rows = [row for key, row in existing_by_key.items() if key not in current_keys]
        self.conn.execute(
            """
            DELETE FROM token_radar_current_rows
            WHERE projection_version = %s
              AND "window" = %s
              AND scope = %s
            """,
            (projection_version, window, scope),
        )
        for row in rows_to_insert:
            self.conn.execute(
                f"""
                INSERT INTO token_radar_current_rows({RADAR_ROW_INSERT_COLUMNS_SQL})
                VALUES ({RADAR_ROW_INSERT_VALUES_SQL})
                """,
                _json_payload(row),
            )
        self.upsert_first_seen_batch(
            projection_version=projection_version,
            window=window,
            scope=scope,
            rows=rows_to_insert,
            computed_at_ms=int(published_at_ms),
            commit=False,
        )
        self._upsert_ready_publication_state(
            projection_version=projection_version,
            window=window,
            scope=scope,
            generation_id=generation_id,
            published_at_ms=published_at_ms,
            source_frontier_ms=source_frontier_ms,
            row_count=len(rows_to_insert),
            source_rows=source_rows,
            started_at_ms=started_at_ms,
            finished_at_ms=finished_at_ms,
        )
        if on_current_changes is not None:
            on_current_changes(
                window=window,
                scope=scope,
                rows=rows_to_insert,
                exited_rows=exited_rows,
                previous_by_key=existing_by_key,
                computed_at_ms=int(published_at_ms),
            )
        if commit:
            self.conn.commit()
        return {"status": "published", "generation_id": str(generation_id), "rows_written": len(rows_to_insert)}

    def _upsert_ready_publication_state(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
        generation_id: str,
        published_at_ms: int,
        source_frontier_ms: int,
        row_count: int,
        source_rows: int | None,
        started_at_ms: int | None,
        finished_at_ms: int | None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO token_radar_publication_state(
              projection_version, "window", scope, current_generation_id, current_published_at_ms,
              current_source_frontier_ms, current_row_count, current_source_rows,
              latest_attempt_generation_id, latest_attempt_status, latest_attempt_started_at_ms,
              latest_attempt_finished_at_ms, latest_attempt_error, updated_at_ms
            )
            VALUES (
              %(projection_version)s, %(window)s, %(scope)s, %(current_generation_id)s,
              %(current_published_at_ms)s, %(current_source_frontier_ms)s, %(current_row_count)s,
              %(current_source_rows)s, %(latest_attempt_generation_id)s, %(latest_attempt_status)s,
              %(latest_attempt_started_at_ms)s, %(latest_attempt_finished_at_ms)s,
              %(latest_attempt_error)s, %(updated_at_ms)s
            )
            ON CONFLICT(projection_version, "window", scope) DO UPDATE SET
              current_generation_id = excluded.current_generation_id,
              current_published_at_ms = excluded.current_published_at_ms,
              current_source_frontier_ms = excluded.current_source_frontier_ms,
              current_row_count = excluded.current_row_count,
              current_source_rows = excluded.current_source_rows,
              latest_attempt_generation_id = excluded.latest_attempt_generation_id,
              latest_attempt_status = excluded.latest_attempt_status,
              latest_attempt_started_at_ms = excluded.latest_attempt_started_at_ms,
              latest_attempt_finished_at_ms = excluded.latest_attempt_finished_at_ms,
              latest_attempt_error = excluded.latest_attempt_error,
              updated_at_ms = excluded.updated_at_ms
            WHERE token_radar_publication_state.current_published_at_ms IS NULL
               OR token_radar_publication_state.current_published_at_ms <= excluded.current_published_at_ms
            """,
            {
                "projection_version": projection_version,
                "window": window,
                "scope": scope,
                "current_generation_id": str(generation_id),
                "current_published_at_ms": int(published_at_ms),
                "current_source_frontier_ms": int(source_frontier_ms),
                "current_row_count": max(0, int(row_count)),
                "current_source_rows": max(0, int(source_rows if source_rows is not None else row_count)),
                "latest_attempt_generation_id": str(generation_id),
                "latest_attempt_status": "ready",
                "latest_attempt_started_at_ms": int(started_at_ms) if started_at_ms is not None else None,
                "latest_attempt_finished_at_ms": (
                    int(finished_at_ms) if finished_at_ms is not None else int(published_at_ms)
                ),
                "latest_attempt_error": None,
                "updated_at_ms": _now_ms(),
            },
        )

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
                JOIN token_radar_publication_state state
                  ON state.projection_version = current_rows.projection_version
                 AND state."window" = current_rows."window"
                 AND state.scope = current_rows.scope
                 AND state.current_generation_id = current_rows.generation_id
                WHERE current_rows.projection_version = %s
                  AND current_rows."window" = %s
                  AND current_rows.scope = %s
                  AND state.latest_attempt_status = 'ready'
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

    def current_rows_for_generation(
        self,
        *,
        window: str,
        scope: str,
        generation_id: str,
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
                JOIN token_radar_publication_state state
                  ON state.projection_version = current_rows.projection_version
                 AND state."window" = current_rows."window"
                 AND state.scope = current_rows.scope
                 AND state.current_generation_id = current_rows.generation_id
                WHERE current_rows.projection_version = %s
                  AND current_rows."window" = %s
                  AND current_rows.scope = %s
                  AND current_rows.generation_id = %s
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
                str(generation_id),
                max(0, int(limit)),
                max(0, int(limit)) * 2,
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def current_row_for_target(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
        target_type: str,
        target_id: str,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT current_rows.*
            FROM token_radar_current_rows current_rows
            JOIN token_radar_publication_state state
              ON state.projection_version = current_rows.projection_version
             AND state."window" = current_rows."window"
             AND state.scope = current_rows.scope
             AND state.current_generation_id = current_rows.generation_id
            WHERE current_rows.projection_version = %s
              AND current_rows."window" = %s
              AND current_rows.scope = %s
              AND current_rows.target_type = %s
              AND current_rows.target_id = %s
              AND state.latest_attempt_status = 'ready'
            ORDER BY current_rows.lane DESC, current_rows.rank ASC
            LIMIT 1
            """,
            (projection_version, window, scope, target_type, target_id),
        ).fetchone()
        return dict(row) if row is not None else None

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
        cursor = self.conn.execute(
            """
            INSERT INTO token_radar_target_features(
              projection_version, "window", scope, lane, target_type_key, identity_id,
              target_type, target_id, pricefeed_id, latest_event_received_at_ms,
              latest_market_observed_at_ms, attention_score, market_score, credibility_score,
              rank_score, factor_snapshot_json, source_event_ids_json, source_intent_ids_json,
              source_resolution_ids_json, payload_hash, last_scored_at_ms, created_at_ms, updated_at_ms,
              social_heat_raw_score, social_heat_weight, social_propagation_raw_score,
              social_propagation_weight, semantic_catalyst_raw_score, semantic_catalyst_weight,
              timing_risk_raw_score, timing_risk_weight, cohort_high_confidence_mentions,
              cohort_kol_mentions, cohort_public_followup_authors, cohort_first_seen_global_24h,
              cohort_symbol, social_heat_watched_mentions, social_heat_mentions_1h,
              social_propagation_mentions, social_heat_latest_seen_ms, raw_composite_score,
              recommended_decision, gates_max_decision
            )
            VALUES (
              %(projection_version)s, %(window)s, %(scope)s, %(lane)s, %(target_type_key)s, %(identity_id)s,
              %(target_type)s, %(target_id)s, %(pricefeed_id)s, %(latest_event_received_at_ms)s,
              %(latest_market_observed_at_ms)s, %(attention_score)s, %(market_score)s, %(credibility_score)s,
              %(rank_score)s, %(factor_snapshot_json)s, %(source_event_ids_json)s, %(source_intent_ids_json)s,
              %(source_resolution_ids_json)s, %(payload_hash)s, %(last_scored_at_ms)s, %(created_at_ms)s,
              %(updated_at_ms)s, %(social_heat_raw_score)s, %(social_heat_weight)s,
              %(social_propagation_raw_score)s, %(social_propagation_weight)s,
              %(semantic_catalyst_raw_score)s, %(semantic_catalyst_weight)s,
              %(timing_risk_raw_score)s, %(timing_risk_weight)s,
              %(cohort_high_confidence_mentions)s, %(cohort_kol_mentions)s,
              %(cohort_public_followup_authors)s, %(cohort_first_seen_global_24h)s,
              %(cohort_symbol)s, %(social_heat_watched_mentions)s, %(social_heat_mentions_1h)s,
              %(social_propagation_mentions)s, %(social_heat_latest_seen_ms)s,
              %(raw_composite_score)s, %(recommended_decision)s, %(gates_max_decision)s
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
              updated_at_ms = excluded.updated_at_ms,
              social_heat_raw_score = excluded.social_heat_raw_score,
              social_heat_weight = excluded.social_heat_weight,
              social_propagation_raw_score = excluded.social_propagation_raw_score,
              social_propagation_weight = excluded.social_propagation_weight,
              semantic_catalyst_raw_score = excluded.semantic_catalyst_raw_score,
              semantic_catalyst_weight = excluded.semantic_catalyst_weight,
              timing_risk_raw_score = excluded.timing_risk_raw_score,
              timing_risk_weight = excluded.timing_risk_weight,
              cohort_high_confidence_mentions = excluded.cohort_high_confidence_mentions,
              cohort_kol_mentions = excluded.cohort_kol_mentions,
              cohort_public_followup_authors = excluded.cohort_public_followup_authors,
              cohort_first_seen_global_24h = excluded.cohort_first_seen_global_24h,
              cohort_symbol = excluded.cohort_symbol,
              social_heat_watched_mentions = excluded.social_heat_watched_mentions,
              social_heat_mentions_1h = excluded.social_heat_mentions_1h,
              social_propagation_mentions = excluded.social_propagation_mentions,
              social_heat_latest_seen_ms = excluded.social_heat_latest_seen_ms,
              raw_composite_score = excluded.raw_composite_score,
              recommended_decision = excluded.recommended_decision,
              gates_max_decision = excluded.gates_max_decision
            WHERE token_radar_target_features.payload_hash IS DISTINCT FROM excluded.payload_hash
            """,
            payload,
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

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

    def prune_target_features(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
        latest_event_before_ms: int,
        commit: bool = True,
    ) -> int:
        cursor = self.conn.execute(
            """
            DELETE FROM token_radar_target_features
            WHERE projection_version = %s
              AND "window" = %s
              AND scope = %s
              AND latest_event_received_at_ms < %s
            """,
            (projection_version, window, scope, int(latest_event_before_ms)),
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def list_rank_inputs_for_rank_set(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
        min_latest_event_received_at_ms: int,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              projection_version,
              "window",
              scope,
              lane,
              target_type_key,
              identity_id,
              target_type,
              target_id,
              pricefeed_id,
              latest_event_received_at_ms,
              latest_market_observed_at_ms,
              social_heat_raw_score,
              social_heat_weight,
              social_propagation_raw_score,
              social_propagation_weight,
              semantic_catalyst_raw_score,
              semantic_catalyst_weight,
              timing_risk_raw_score,
              timing_risk_weight,
              cohort_high_confidence_mentions,
              cohort_kol_mentions,
              cohort_public_followup_authors,
              cohort_first_seen_global_24h,
              cohort_symbol,
              social_heat_watched_mentions,
              social_heat_mentions_1h,
              social_propagation_mentions,
              social_heat_latest_seen_ms,
              raw_composite_score,
              recommended_decision,
              gates_max_decision,
              factor_snapshot_json,
              source_event_ids_json,
              source_intent_ids_json,
              source_resolution_ids_json,
              payload_hash,
              last_scored_at_ms,
              updated_at_ms
            FROM token_radar_target_features
            WHERE projection_version = %s
              AND "window" = %s
              AND scope = %s
              AND latest_event_received_at_ms >= %s
            ORDER BY lane DESC, rank_score DESC, latest_event_received_at_ms DESC, identity_id ASC
            """,
            (projection_version, window, scope, int(min_latest_event_received_at_ms)),
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

    def mark_publication_failed(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
        generation_id: str,
        started_at_ms: int | None = None,
        finished_at_ms: int | None = None,
        error: str | None = None,
        commit: bool = True,
    ) -> None:
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO token_radar_publication_state(
              projection_version, "window", scope, latest_attempt_generation_id, latest_attempt_status,
              latest_attempt_started_at_ms, latest_attempt_finished_at_ms, latest_attempt_error,
              updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(projection_version, "window", scope) DO UPDATE SET
              latest_attempt_generation_id = excluded.latest_attempt_generation_id,
              latest_attempt_status = excluded.latest_attempt_status,
              latest_attempt_started_at_ms = excluded.latest_attempt_started_at_ms,
              latest_attempt_finished_at_ms = excluded.latest_attempt_finished_at_ms,
              latest_attempt_error = excluded.latest_attempt_error,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                projection_version,
                window,
                scope,
                str(generation_id),
                "failed",
                int(started_at_ms) if started_at_ms is not None else None,
                int(finished_at_ms) if finished_at_ms is not None else None,
                error,
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()

    def latest_publication_state(
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
            SELECT state.*
            FROM requested
            JOIN token_radar_publication_state state
              ON state."window" = requested."window"
             AND state.scope = requested.scope
            WHERE state.projection_version = %s
            """,
            [*params, projection_version],
        ).fetchall()
        return {
            (str(row["window"]), str(row["scope"])): {
                "current_generation_id": row.get("current_generation_id"),
                "current_published_at_ms": (
                    int(row["current_published_at_ms"]) if row.get("current_published_at_ms") is not None else None
                ),
                "current_source_frontier_ms": (
                    int(row["current_source_frontier_ms"])
                    if row.get("current_source_frontier_ms") is not None
                    else None
                ),
                "current_row_count": int(row.get("current_row_count") or 0),
                "current_source_rows": int(row.get("current_source_rows") or 0),
                "latest_attempt_generation_id": row.get("latest_attempt_generation_id"),
                "latest_attempt_status": str(row["latest_attempt_status"]),
                "latest_attempt_started_at_ms": (
                    int(row["latest_attempt_started_at_ms"])
                    if row.get("latest_attempt_started_at_ms") is not None
                    else None
                ),
                "latest_attempt_finished_at_ms": (
                    int(row["latest_attempt_finished_at_ms"])
                    if row.get("latest_attempt_finished_at_ms") is not None
                    else None
                ),
                "latest_attempt_error": row.get("latest_attempt_error"),
                "updated_at_ms": int(row["updated_at_ms"]) if row.get("updated_at_ms") is not None else None,
            }
            for row in rows
        }


def _runtime_row_payload(
    row: dict[str, Any],
    *,
    projection_version: str,
    window: str,
    scope: str,
    generation_id: str,
    published_at_ms: int,
    source_frontier_ms: int,
    listed_at_ms: int,
) -> dict[str, Any]:
    out = dict(row)
    target_type_key, identity_id = _identity_key(out)
    out.update(
        {
            "projection_version": projection_version,
            "window": window,
            "scope": scope,
            "computed_at_ms": int(published_at_ms),
            "generation_id": str(generation_id),
            "published_at_ms": int(published_at_ms),
            "source_frontier_ms": int(source_frontier_ms),
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
    timing_risk = families.get("timing_risk") if isinstance(families, dict) else {}
    social_heat_facts = social_heat.get("facts") if isinstance(social_heat, dict) else {}
    social_propagation_facts = social_propagation.get("facts") if isinstance(social_propagation, dict) else {}
    composite = factor_snapshot.get("composite") if isinstance(factor_snapshot, dict) else {}
    gates = factor_snapshot.get("gates") if isinstance(factor_snapshot, dict) else {}
    subject = factor_snapshot.get("subject") if isinstance(factor_snapshot, dict) else {}
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
        "social_heat_raw_score": _family_raw_score(social_heat),
        "social_heat_weight": _family_weight(social_heat),
        "social_propagation_raw_score": _family_raw_score(social_propagation),
        "social_propagation_weight": _family_weight(social_propagation),
        "semantic_catalyst_raw_score": _family_raw_score(semantic_catalyst),
        "semantic_catalyst_weight": _family_weight(semantic_catalyst),
        "timing_risk_raw_score": _family_raw_score(timing_risk),
        "timing_risk_weight": _family_weight(timing_risk),
        "cohort_high_confidence_mentions": int(row.get("_cohort_high_conf_count") or 0),
        "cohort_kol_mentions": int(row.get("_cohort_kol_count") or 0),
        "cohort_public_followup_authors": int(row.get("_cohort_public_followup_count") or 0),
        "cohort_first_seen_global_24h": row.get("_cohort_first_seen_global_24h") is True
        or row.get("first_seen_global_24h") is True,
        "cohort_symbol": str(
            (subject.get("symbol") if isinstance(subject, dict) else None)
            or (row.get("intent_json") or {}).get("display_symbol")
            or ""
        ).upper(),
        "social_heat_watched_mentions": _int_value(
            social_heat_facts.get("watched_mentions") if isinstance(social_heat_facts, dict) else None
        ),
        "social_heat_mentions_1h": _int_value(
            social_heat_facts.get("mentions_1h") if isinstance(social_heat_facts, dict) else None
        ),
        "social_propagation_mentions": _int_value(
            social_propagation_facts.get("mentions") if isinstance(social_propagation_facts, dict) else None
        ),
        "social_heat_latest_seen_ms": _optional_int_value(
            social_heat_facts.get("latest_seen_ms") if isinstance(social_heat_facts, dict) else None
        ),
        "raw_composite_score": _composite_score(composite if isinstance(composite, dict) else {}),
        "recommended_decision": str(
            (composite.get("recommended_decision") if isinstance(composite, dict) else None) or "discard"
        ),
        "gates_max_decision": str((gates.get("max_decision") if isinstance(gates, dict) else None) or "discard"),
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


def _json_payload(row: dict[str, Any]) -> dict[str, Any]:
    _validate_factor_contract(row)
    out = {column: row.get(column) for column in RADAR_ROW_COLUMNS}
    for key in (
        "intent_json",
        "resolution_json",
        "factor_snapshot_json",
        "data_health_json",
        "source_event_ids_json",
        "degraded_reasons_json",
    ):
        payload = out.get(key) if out.get(key) is not None else ([] if key.endswith("_ids_json") else {})
        if key == "degraded_reasons_json":
            payload = out.get(key) if out.get(key) is not None else []
        out[key] = Jsonb(_json_ready(payload))
    return out


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


def stable_generation_id(*, projection_version: str, window: str, scope: str, rows: list[dict[str, Any]]) -> str:
    stable_rows = [
        {
            "lane": str(row.get("lane") or ""),
            "rank": int(row.get("rank") or 0),
            "target_type_key": str(row.get("target_type_key") or row.get("target_type") or ""),
            "identity_id": str(row.get("identity_id") or row.get("target_id") or row.get("intent_id") or ""),
            "decision": row.get("decision"),
            "rank_score": _stable_rank_score(row),
            "quality_status": row.get("quality_status"),
            "degraded_reasons_json": _stable_degraded_reasons(row),
            "source_max_received_at_ms": row.get("source_max_received_at_ms"),
            "payload_hash": row.get("payload_hash"),
        }
        for row in rows
    ]
    stable_rows.sort(key=lambda item: (item["lane"], item["rank"], item["target_type_key"], item["identity_id"]))
    payload = {
        "projection_version": projection_version,
        "window": window,
        "scope": scope,
        "rows": stable_rows,
    }
    encoded = json.dumps(_json_ready(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _first_generation_id(rows: list[dict[str, Any]]) -> str | None:
    for row in rows:
        generation_id = row.get("generation_id")
        if generation_id is not None:
            return str(generation_id)
    return None


def _stable_rank_score(row: dict[str, Any]) -> Any:
    if row.get("rank_score") is not None:
        return _float_or_none(row.get("rank_score"))
    factor_snapshot = row.get("factor_snapshot_json")
    if not isinstance(factor_snapshot, dict):
        return None
    composite = factor_snapshot.get("composite")
    if not isinstance(composite, dict):
        return None
    return _float_or_none(composite.get("rank_score"))


def _stable_degraded_reasons(row: dict[str, Any]) -> list[str]:
    value = _json_ready(row.get("degraded_reasons_json"))
    if not isinstance(value, list):
        return []
    return sorted(str(item) for item in value if str(item))


def _payload_hash(row: dict[str, Any]) -> str:
    stable_payload = {
        column: _json_ready(row.get(column))
        for column in RADAR_ROW_COLUMNS
        if column
        not in {
            "row_id",
            "computed_at_ms",
            "generation_id",
            "published_at_ms",
            "source_frontier_ms",
            "payload_hash",
            "listed_at_ms",
            "created_at_ms",
        }
    }
    encoded = json.dumps(stable_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _rank_score(factor_snapshot: Any) -> float | None:
    if not isinstance(factor_snapshot, dict):
        return None
    composite = factor_snapshot.get("composite")
    if not isinstance(composite, dict):
        return None
    value = composite.get("rank_score")
    return _float_or_none(value)


def _composite_score(composite: dict[str, Any]) -> float | None:
    value = composite.get("rank_score")
    if value is None:
        value = composite.get("raw_alpha_score")
    return _float_or_none(value)


def _family_raw_score(family: Any) -> float | None:
    if not isinstance(family, dict):
        return None
    raw_score = _float_or_none(family.get("raw_score"))
    if raw_score is not None:
        return raw_score
    return _float_or_none(family.get("score"))


def _family_weight(family: Any) -> float:
    if not isinstance(family, dict):
        return 0.0
    return _float_or_none(family.get("weight")) or 0.0


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _int_value(value: Any) -> int:
    return _optional_int_value(value) or 0


def _optional_int_value(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
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
