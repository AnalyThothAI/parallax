from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION
from gmgn_twitter_intel.domains.narrative_intel.services.fingerprints import (
    label_fingerprint as build_label_fingerprint,
)
from gmgn_twitter_intel.domains.narrative_intel.services.fingerprints import (
    source_fingerprint as build_source_fingerprint,
)
from gmgn_twitter_intel.domains.narrative_intel.services.fingerprints import (
    text_fingerprint,
)
from gmgn_twitter_intel.domains.narrative_intel.services.narrative_currentness import (
    public_currentness,
    unsupported_digest_sentinel,
)
from gmgn_twitter_intel.domains.narrative_intel.services.narrative_epoch_policy import DIGEST_WINDOWS

_SEMANTIC_COVERAGE_KEYS = (
    "source_event_count",
    "semantic_row_count",
    "missing_semantic_count",
    "pending_semantic_count",
    "retryable_semantic_count",
    "labeled_event_count",
    "terminal_unavailable_count",
)


class NarrativeRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_admissions(
        self,
        rows: Sequence[dict[str, Any]],
        *,
        now_ms: int,
        limit: int | None = None,
    ) -> dict[str, int]:
        upserted = 0
        selected = list(rows)[: max(1, int(limit))] if limit is not None else list(rows)
        for row in selected:
            target_type = _clean(row.get("target_type"))
            target_id = _clean(row.get("target_id"))
            if not target_type or not target_id:
                continue
            window = _required(row, "window")
            scope = _required(row, "scope")
            schema_version = str(row.get("schema_version") or NARRATIVE_SCHEMA_VERSION)
            source_event_ids = _json_list(row.get("source_event_ids") or row.get("source_event_ids_json"))
            source_max_received_at_ms = _int(row.get("source_max_received_at_ms") or row.get("source_window_end_ms"))
            payload = {
                "admission_id": deterministic_admission_id(
                    target_type=target_type,
                    target_id=target_id,
                    window=window,
                    scope=scope,
                    schema_version=schema_version,
                ),
                "target_type": target_type,
                "target_id": target_id,
                "window": window,
                "scope": scope,
                "schema_version": schema_version,
                "status": str(row.get("status") or "admitted"),
                "reason": str(row.get("reason") or "radar_row"),
                "priority": _int(row.get("priority")) or 0,
                "last_radar_rank": _int(row.get("rank") or row.get("last_radar_rank")),
                "last_rank_score": _float(row.get("rank_score") or row.get("last_rank_score")),
                "source_event_ids_json": _json(source_event_ids),
                "source_fingerprint": build_source_fingerprint(source_event_ids, source_max_received_at_ms),
                "source_max_received_at_ms": source_max_received_at_ms,
                "projection_computed_at_ms": _int(row.get("projection_computed_at_ms") or row.get("computed_at_ms")),
                "source_window_start_ms": _int(row.get("source_window_start_ms")),
                "source_window_end_ms": _int(row.get("source_window_end_ms") or source_max_received_at_ms),
                "source_event_count": (
                    _int(row.get("source_event_count"))
                    if row.get("source_event_count") is not None
                    else len(source_event_ids)
                ),
                "independent_author_count": _int(row.get("independent_author_count")) or 0,
                "admission_generation": row.get("admission_generation"),
                "admitted_at_ms": now_ms,
                "last_seen_at_ms": now_ms,
                "updated_at_ms": now_ms,
            }
            self.conn.execute(
                """
                INSERT INTO narrative_admissions (
                  admission_id, target_type, target_id, "window", scope, schema_version, status, reason,
                  priority, last_radar_rank, last_rank_score, source_event_ids_json, source_fingerprint,
                  source_max_received_at_ms, projection_computed_at_ms, source_window_start_ms,
                  source_window_end_ms, source_event_count, independent_author_count, admission_generation,
                  admitted_at_ms, last_seen_at_ms, updated_at_ms
                )
                VALUES (
                  %(admission_id)s, %(target_type)s, %(target_id)s, %(window)s, %(scope)s, %(schema_version)s,
                  %(status)s, %(reason)s, %(priority)s, %(last_radar_rank)s, %(last_rank_score)s,
                  %(source_event_ids_json)s, %(source_fingerprint)s, %(source_max_received_at_ms)s,
                  %(projection_computed_at_ms)s, %(source_window_start_ms)s, %(source_window_end_ms)s,
                  %(source_event_count)s, %(independent_author_count)s, %(admission_generation)s,
                  %(admitted_at_ms)s, %(last_seen_at_ms)s, %(updated_at_ms)s
                )
                ON CONFLICT (target_type, target_id, "window", scope, schema_version)
                DO UPDATE SET
                  status = EXCLUDED.status,
                  reason = EXCLUDED.reason,
                  priority = EXCLUDED.priority,
                  last_radar_rank = EXCLUDED.last_radar_rank,
                  last_rank_score = EXCLUDED.last_rank_score,
                  source_event_ids_json = EXCLUDED.source_event_ids_json,
                  source_fingerprint = EXCLUDED.source_fingerprint,
                  source_max_received_at_ms = EXCLUDED.source_max_received_at_ms,
                  projection_computed_at_ms = EXCLUDED.projection_computed_at_ms,
                  source_window_start_ms = EXCLUDED.source_window_start_ms,
                  source_window_end_ms = EXCLUDED.source_window_end_ms,
                  source_event_count = EXCLUDED.source_event_count,
                  independent_author_count = EXCLUDED.independent_author_count,
                  admission_generation = EXCLUDED.admission_generation,
                  last_seen_at_ms = EXCLUDED.last_seen_at_ms,
                  updated_at_ms = EXCLUDED.updated_at_ms
                """,
                payload,
            )
            upserted += 1
        _commit_if_available(self.conn)
        return {"upserted": upserted, "seen": len(selected)}

    def admitted_radar_rows(
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
              SELECT computed_at_ms
              FROM token_radar_projection_coverage
              WHERE projection_version = %s
                AND "window" = %s
                AND scope = %s
                AND status = 'ready'
                AND computed_at_ms IS NOT NULL
              ORDER BY computed_at_ms DESC
              LIMIT 1
            )
            SELECT token_radar_rows.row_id,
                   token_radar_rows.target_type,
                   token_radar_rows.target_id,
                   token_radar_rows.rank,
                   token_radar_rows.computed_at_ms,
                   NULLIF(
                     token_radar_rows.factor_snapshot_json->'composite'->>'rank_score', ''
                   )::double precision AS rank_score,
                   token_radar_rows.source_event_ids_json,
                   token_radar_rows.source_max_received_at_ms
            FROM token_radar_rows
            JOIN latest ON latest.computed_at_ms = token_radar_rows.computed_at_ms
            WHERE token_radar_rows."window" = %s
              AND token_radar_rows.scope = %s
              AND token_radar_rows.projection_version = %s
              AND token_radar_rows.target_type IS NOT NULL
              AND token_radar_rows.target_id IS NOT NULL
            ORDER BY token_radar_rows.rank ASC
            LIMIT %s
            """,
            (projection_version, window, scope, window, scope, projection_version, int(limit)),
        ).fetchall()
        return [_row(row) for row in rows]

    def source_set_for_admission(
        self,
        *,
        target_type: str,
        target_id: str,
        since_ms: int,
        until_ms: int,
        watched_only: bool,
        limit: int,
    ) -> dict[str, Any]:
        watched_clause = "AND events.is_watched = true" if watched_only else ""
        rows = self.conn.execute(
            f"""
            SELECT
              events.event_id,
              events.received_at_ms AS source_received_at_ms,
              events.author_handle
            FROM token_intent_resolutions AS resolution
            JOIN events ON events.event_id = resolution.event_id
            WHERE resolution.target_type = %s
              AND resolution.target_id = %s
              AND resolution.is_current = true
              AND events.received_at_ms >= %s
              AND events.received_at_ms <= %s
              {watched_clause}
            ORDER BY events.received_at_ms DESC, events.event_id DESC
            LIMIT %s
            """,
            (target_type, target_id, int(since_ms), int(until_ms), int(limit)),
        ).fetchall()
        source_rows = [_row(row) for row in rows]
        event_ids = [str(row["event_id"]) for row in source_rows if row.get("event_id")]
        max_received_at_ms = max((_int(row.get("source_received_at_ms")) or 0 for row in source_rows), default=None)
        return {
            "source_event_ids": event_ids,
            "source_event_count": len(event_ids),
            "independent_author_count": _author_count(source_rows),
            "source_max_received_at_ms": max_received_at_ms,
        }

    def admissions_for_window_scope(
        self,
        *,
        window: str,
        scope: str,
        schema_version: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM narrative_admissions
            WHERE "window" = %s
              AND scope = %s
              AND schema_version = %s
            ORDER BY priority DESC, last_seen_at_ms DESC
            LIMIT %s
            """,
            (window, scope, schema_version, int(limit)),
        ).fetchall()
        return [_row(row) for row in rows]

    def suppress_admissions_outside_frontier(
        self,
        *,
        window: str,
        scope: str,
        schema_version: str,
        active_target_keys: Sequence[tuple[str, str]],
        now_ms: int,
    ) -> dict[str, int]:
        keys = {(str(target_type), str(target_id)) for target_type, target_id in active_target_keys}
        existing = self.admissions_for_window_scope(
            window=window,
            scope=scope,
            schema_version=schema_version,
            limit=10_000,
        )
        suppress_ids = [
            row["admission_id"]
            for row in existing
            if str(row.get("status") or "") == "admitted"
            and (str(row.get("target_type") or ""), str(row.get("target_id") or "")) not in keys
        ]
        if not suppress_ids:
            return {"suppressed": 0}
        cursor = self.conn.execute(
            """
            UPDATE narrative_admissions
            SET status = 'suppressed',
                reason = 'not_in_current_frontier',
                suppressed_at_ms = %s,
                updated_at_ms = %s
            WHERE admission_id = ANY(%s)
            """,
            (int(now_ms), int(now_ms), suppress_ids),
        )
        _commit_if_available(self.conn)
        return {"suppressed": int(getattr(cursor, "rowcount", 0) or 0)}

    def due_admissions_for_semantics(
        self, *, now_ms: int, limit: int, windows: tuple[str, ...] = ("1h",)
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM narrative_admissions
            WHERE status = 'admitted'
              AND next_semantics_due_at_ms <= %s
              AND "window" = ANY(%s)
            ORDER BY priority DESC, last_seen_at_ms DESC
            LIMIT %s
            """,
            (int(now_ms), list(windows), int(limit)),
        ).fetchall()
        return [_row(row) for row in rows]

    def source_rows_for_admission(self, admission: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
        source_event_ids = _json_list(admission.get("source_event_ids") or admission.get("source_event_ids_json"))
        if not source_event_ids:
            return []
        rows = self.conn.execute(
            """
            SELECT
              events.event_id,
              events.text_clean AS text_clean,
              events.author_handle,
              events.received_at_ms AS source_received_at_ms,
              events.tweet_id,
              events.raw_json AS reference_json
            FROM events
            WHERE events.event_id = ANY(%s)
            ORDER BY events.received_at_ms DESC, events.event_id DESC
            LIMIT %s
            """,
            (source_event_ids, int(limit)),
        ).fetchall()
        target_type = _required(admission, "target_type")
        target_id = _required(admission, "target_id")
        return [
            {
                **_row(row),
                "target_type": target_type,
                "target_id": target_id,
            }
            for row in rows
        ]

    def missing_source_rows_for_mention_semantics(
        self,
        admission: dict[str, Any],
        *,
        limit: int,
        schema_version: str,
    ) -> list[dict[str, Any]]:
        source_event_ids = _json_list(admission.get("source_event_ids") or admission.get("source_event_ids_json"))
        if not source_event_ids:
            return []
        target_type = _required(admission, "target_type")
        target_id = _required(admission, "target_id")
        rows = self.conn.execute(
            """
            SELECT
              events.event_id,
              events.text_clean AS text_clean,
              events.author_handle,
              events.received_at_ms AS source_received_at_ms,
              events.tweet_id,
              events.raw_json AS reference_json
            FROM events
            LEFT JOIN token_mention_semantics AS semantics
              ON semantics.event_id = events.event_id
             AND semantics.target_type = %s
             AND semantics.target_id = %s
             AND semantics.schema_version = %s
            WHERE events.event_id = ANY(%s)
              AND semantics.semantic_id IS NULL
            ORDER BY events.received_at_ms DESC, events.event_id DESC
            LIMIT %s
            """,
            (target_type, target_id, schema_version, source_event_ids, int(limit)),
        ).fetchall()
        return [
            {
                **_row(row),
                "target_type": target_type,
                "target_id": target_id,
            }
            for row in rows
        ]

    def due_mentions_for_labeling(
        self,
        *,
        now_ms: int,
        limit: int,
        max_per_target: int | None = None,
        windows: tuple[str, ...] = ("1h",),
    ) -> list[dict[str, Any]]:
        per_target_filter = ""
        params: list[Any] = [int(now_ms), list(windows)]
        if max_per_target is not None and int(max_per_target) > 0:
            per_target_filter = "WHERE target_rank <= %s"
            params.append(int(max_per_target))
        params.append(int(limit))
        rows = self.conn.execute(
            f"""
            WITH ranked AS (
              SELECT semantics.*,
                     row_number() OVER (
                       PARTITION BY semantics.target_type, semantics.target_id
                       ORDER BY semantics.source_received_at_ms DESC, semantics.semantic_id ASC
                     ) AS target_rank
              FROM token_mention_semantics AS semantics
              WHERE semantics.status IN ('queued', 'retryable_error', 'stale')
                AND semantics.next_retry_at_ms <= %s
                AND EXISTS (
                  SELECT 1
                  FROM narrative_admissions AS admissions
                  WHERE admissions.status = 'admitted'
                    AND admissions.schema_version = semantics.schema_version
                    AND admissions.target_type = semantics.target_type
                    AND admissions.target_id = semantics.target_id
                    AND admissions."window" = ANY(%s)
                    AND admissions.source_event_ids_json ? semantics.event_id
                )
            )
            SELECT ranked.*,
                   events.text_clean AS text_clean,
                   events.author_handle,
                   events.tweet_id,
                   events.raw_json AS reference_json
            FROM ranked
            JOIN events ON events.event_id = ranked.event_id
            {per_target_filter}
            ORDER BY ranked.source_received_at_ms DESC, ranked.semantic_id ASC
            LIMIT %s
            """,
            tuple(params),
        ).fetchall()
        return [_row(row) for row in rows]

    def semantic_coverage_for_admission(self, admission: dict[str, Any]) -> dict[str, int]:
        source_event_ids = _json_list(admission.get("source_event_ids") or admission.get("source_event_ids_json"))
        if not source_event_ids:
            return _empty_semantic_coverage()
        target_type = _required(admission, "target_type")
        target_id = _required(admission, "target_id")
        schema_version = str(admission.get("schema_version") or NARRATIVE_SCHEMA_VERSION)
        return self._semantic_coverage_for_source_ids(
            source_event_ids=source_event_ids,
            target_type=target_type,
            target_id=target_id,
            schema_version=schema_version,
        )

    def missing_semantic_count_for_admission(self, admission: dict[str, Any], *, schema_version: str) -> int:
        source_event_ids = _json_list(admission.get("source_event_ids") or admission.get("source_event_ids_json"))
        if not source_event_ids:
            return 0
        target_type = _required(admission, "target_type")
        target_id = _required(admission, "target_id")
        row = self.conn.execute(
            """
            WITH source_ids AS (
              SELECT jsonb_array_elements_text(%s::jsonb) AS event_id
            )
            SELECT COUNT(*) AS missing_count
            FROM source_ids
            WHERE NOT EXISTS (
              SELECT 1
              FROM token_mention_semantics AS semantics
              WHERE semantics.event_id = source_ids.event_id
                AND semantics.target_type = %s
                AND semantics.target_id = %s
                AND semantics.schema_version = %s
            )
            """,
            (_json(source_event_ids), target_type, target_id, schema_version),
        ).fetchone()
        return int(row["missing_count"] if row else 0)

    def _semantic_coverage_for_source_ids(
        self,
        *,
        source_event_ids: Sequence[str],
        target_type: str,
        target_id: str,
        schema_version: str,
    ) -> dict[str, int]:
        row = self.conn.execute(
            """
            WITH source_ids AS (
              SELECT jsonb_array_elements_text(%s::jsonb) AS event_id
            )
            SELECT
              COUNT(*) AS source_event_count,
              COUNT(*) FILTER (
                WHERE EXISTS (
                  SELECT 1
                  FROM token_mention_semantics AS semantics
                  WHERE semantics.event_id = source_ids.event_id
                    AND semantics.target_type = %s
                    AND semantics.target_id = %s
                    AND semantics.schema_version = %s
                )
              ) AS semantic_row_count,
              COUNT(*) FILTER (
                WHERE NOT EXISTS (
                  SELECT 1
                  FROM token_mention_semantics AS semantics
                  WHERE semantics.event_id = source_ids.event_id
                    AND semantics.target_type = %s
                    AND semantics.target_id = %s
                    AND semantics.schema_version = %s
                )
              ) AS missing_semantic_count,
              COUNT(*) FILTER (
                WHERE EXISTS (
                  SELECT 1
                  FROM token_mention_semantics AS semantics
                  WHERE semantics.event_id = source_ids.event_id
                    AND semantics.target_type = %s
                    AND semantics.target_id = %s
                    AND semantics.schema_version = %s
                    AND semantics.status IN ('queued', 'stale')
                )
              ) AS pending_semantic_count,
              COUNT(*) FILTER (
                WHERE EXISTS (
                  SELECT 1
                  FROM token_mention_semantics AS semantics
                  WHERE semantics.event_id = source_ids.event_id
                    AND semantics.target_type = %s
                    AND semantics.target_id = %s
                    AND semantics.schema_version = %s
                    AND semantics.status = 'retryable_error'
                )
              ) AS retryable_semantic_count,
              COUNT(*) FILTER (
                WHERE EXISTS (
                  SELECT 1
                  FROM token_mention_semantics AS semantics
                  WHERE semantics.event_id = source_ids.event_id
                    AND semantics.target_type = %s
                    AND semantics.target_id = %s
                    AND semantics.schema_version = %s
                    AND semantics.status = 'labeled'
                )
              ) AS labeled_event_count,
              COUNT(*) FILTER (
                WHERE EXISTS (
                  SELECT 1
                  FROM token_mention_semantics AS semantics
                  WHERE semantics.event_id = source_ids.event_id
                    AND semantics.target_type = %s
                    AND semantics.target_id = %s
                    AND semantics.schema_version = %s
                    AND semantics.status = 'semantic_unavailable'
                )
              ) AS terminal_unavailable_count
            FROM source_ids
            """,
            (
                _json(source_event_ids),
                target_type,
                target_id,
                schema_version,
                target_type,
                target_id,
                schema_version,
                target_type,
                target_id,
                schema_version,
                target_type,
                target_id,
                schema_version,
                target_type,
                target_id,
                schema_version,
                target_type,
                target_id,
                schema_version,
            ),
        ).fetchone()
        if not row:
            return _empty_semantic_coverage()
        return {key: int(row[key] or 0) for key in _SEMANTIC_COVERAGE_KEYS}

    def pending_mention_semantics_count(
        self,
        *,
        target_type: str,
        target_id: str,
        schema_version: str,
        model_version: str | None = None,
        windows: tuple[str, ...] = ("1h",),
    ) -> int:
        model_clause = "AND model_version = %s" if model_version else ""
        params: list[Any] = [target_type, target_id, schema_version, list(windows)]
        if model_version:
            params.append(model_version)
        row = self.conn.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM token_mention_semantics
            WHERE target_type = %s
              AND target_id = %s
              AND schema_version = %s
              AND EXISTS (
                SELECT 1
                FROM narrative_admissions AS admissions
                WHERE admissions.status = 'admitted'
                  AND admissions.schema_version = token_mention_semantics.schema_version
                  AND admissions.target_type = token_mention_semantics.target_type
                  AND admissions.target_id = token_mention_semantics.target_id
                  AND admissions."window" = ANY(%s)
                  AND admissions.source_event_ids_json ? token_mention_semantics.event_id
              )
              {model_clause}
              AND status IN ('queued', 'retryable_error', 'stale')
            """,
            tuple(params),
        ).fetchone()
        return int(row["count"] if row else 0)

    def enqueue_missing_mention_semantics(
        self,
        source_rows: Sequence[dict[str, Any]],
        *,
        schema_version: str,
        model_version: str,
        now_ms: int,
    ) -> dict[str, int]:
        inserted = 0
        existing = 0
        for source in source_rows:
            event_id = _required(source, "event_id")
            target_type = _required(source, "target_type")
            target_id = _required(source, "target_id")
            fingerprint = str(source.get("text_fingerprint") or text_fingerprint(str(source.get("text_clean") or "")))
            semantic_id = deterministic_semantic_id(
                event_id=event_id,
                target_type=target_type,
                target_id=target_id,
                schema_version=schema_version,
                text_fingerprint=fingerprint,
            )
            cursor = self.conn.execute(
                """
                INSERT INTO token_mention_semantics (
                  semantic_id, event_id, target_type, target_id, schema_version, model_version,
                  text_fingerprint, status, source_received_at_ms, queued_at_ms, next_retry_at_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued', %s, %s, 0)
                ON CONFLICT (event_id, target_type, target_id, schema_version, text_fingerprint)
                DO NOTHING
                """,
                (
                    semantic_id,
                    event_id,
                    target_type,
                    target_id,
                    schema_version,
                    model_version,
                    fingerprint,
                    _int(source.get("source_received_at_ms") or source.get("received_at_ms")) or now_ms,
                    now_ms,
                ),
            )
            if int(getattr(cursor, "rowcount", 0) or 0) > 0:
                inserted += 1
            else:
                existing += 1
        _commit_if_available(self.conn)
        return {"inserted": inserted, "existing": existing}

    def mark_admissions_semantics_scanned(
        self,
        admission_ids: Sequence[str],
        *,
        next_due_at_ms: int,
        now_ms: int,
    ) -> dict[str, int]:
        ids = _stable_ids(admission_ids)
        if not ids:
            return {"updated": 0}
        cursor = self.conn.execute(
            """
            UPDATE narrative_admissions
            SET next_semantics_due_at_ms = %s,
                updated_at_ms = %s
            WHERE admission_id = ANY(%s)
            """,
            (int(next_due_at_ms), int(now_ms), ids),
        )
        _commit_if_available(self.conn)
        return {"updated": int(getattr(cursor, "rowcount", 0) or 0)}

    def cleanup_narrative_current_hard_cut(
        self,
        *,
        schema_version: str,
        now_ms: int,
        realtime_windows: Sequence[str] = ("1h",),
    ) -> dict[str, int]:
        windows = tuple(dict.fromkeys(str(window) for window in realtime_windows if str(window)))
        if not windows:
            windows = ("1h",)
        suppressed_non_realtime = self.conn.execute(
            """
            UPDATE narrative_admissions
            SET status = 'suppressed',
                reason = 'non_realtime_narrative_window',
                suppressed_at_ms = %s,
                updated_at_ms = %s
            WHERE schema_version = %s
              AND status = 'admitted'
              AND NOT ("window" = ANY(%s))
            """,
            (int(now_ms), int(now_ms), schema_version, list(windows)),
        )
        staled_non_realtime = self.conn.execute(
            """
            UPDATE token_discussion_digests
            SET status = 'stale',
                is_current = false,
                superseded_at_ms = %s
            WHERE schema_version = %s
              AND is_current = true
              AND NOT ("window" = ANY(%s))
            """,
            (int(now_ms), schema_version, list(windows)),
        )
        obsolete = self.conn.execute(
            """
            WITH current_sources AS (
              SELECT
                admissions.target_type,
                admissions.target_id,
                jsonb_array_elements_text(admissions.source_event_ids_json) AS event_id
              FROM narrative_admissions AS admissions
              WHERE admissions.status = 'admitted'
                AND admissions.schema_version = %s
                AND admissions."window" = ANY(%s)
            )
            DELETE FROM token_mention_semantics AS semantics
            WHERE semantics.schema_version = %s
              AND semantics.status IN ('queued', 'retryable_error', 'stale')
              AND NOT EXISTS (
                SELECT 1
                FROM current_sources
                WHERE current_sources.event_id = semantics.event_id
                  AND current_sources.target_type = semantics.target_type
                  AND current_sources.target_id = semantics.target_id
              )
            """,
            (schema_version, list(windows), schema_version),
        )
        stale_suppressed = self.conn.execute(
            """
            UPDATE token_discussion_digests AS digest
            SET status = 'stale',
                is_current = false,
                superseded_at_ms = %s
            FROM narrative_admissions AS admissions
            WHERE admissions.status = 'suppressed'
              AND admissions.schema_version = %s
              AND digest.target_type = admissions.target_type
              AND digest.target_id = admissions.target_id
              AND digest."window" = admissions."window"
              AND digest.scope = admissions.scope
              AND digest.schema_version = admissions.schema_version
              AND digest.is_current = true
              AND digest."window" = ANY(%s)
            """,
            (int(now_ms), schema_version, list(windows)),
        )
        mismatch_preserved = self.conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM token_discussion_digests AS digest
            JOIN narrative_admissions AS admissions
              ON admissions.target_type = digest.target_type
             AND admissions.target_id = digest.target_id
             AND admissions."window" = digest."window"
             AND admissions.scope = digest.scope
             AND admissions.schema_version = digest.schema_version
             AND admissions.status = 'admitted'
             AND admissions.schema_version = %s
             AND admissions."window" = ANY(%s)
            WHERE digest.is_current = true
              AND digest.status = 'ready'
              AND COALESCE(digest.source_fingerprint, '') <> COALESCE(admissions.source_fingerprint, '')
            """,
            (schema_version, list(windows)),
        ).fetchone()
        _commit_if_available(self.conn)
        return {
            "suppressed_non_realtime_admissions": int(getattr(suppressed_non_realtime, "rowcount", 0) or 0),
            "staled_non_realtime_digests": int(getattr(staled_non_realtime, "rowcount", 0) or 0),
            "deleted_obsolete_pending_semantics": int(getattr(obsolete, "rowcount", 0) or 0),
            "stale_suppressed_digests": int(getattr(stale_suppressed, "rowcount", 0) or 0),
            "fingerprint_mismatch_digests_preserved": int(mismatch_preserved["count"] if mismatch_preserved else 0),
        }

    def record_narrative_model_run(self, run: dict[str, Any], *, commit: bool = True) -> dict[str, Any]:
        payload = dict(run)
        payload.setdefault(
            "run_id",
            deterministic_run_id(
                stage=str(payload.get("stage") or ""),
                input_hash=str(payload.get("input_hash") or ""),
                started_at_ms=int(payload.get("started_at_ms") or 0),
            ),
        )
        payload.setdefault("schema_version", NARRATIVE_SCHEMA_VERSION)
        payload.setdefault("prompt_version", "unknown")
        payload.setdefault("request_json", {})
        payload.setdefault("response_json", None)
        payload.setdefault("usage_json", {})
        payload.setdefault("trace_metadata_json", {})
        payload.setdefault("target_type", None)
        payload.setdefault("target_id", None)
        payload.setdefault("window", None)
        payload.setdefault("scope", None)
        payload.setdefault("artifact_version_hash", None)
        payload.setdefault("output_hash", None)
        payload.setdefault("error", None)
        payload.setdefault("status", "done")
        payload.setdefault("finished_at_ms", payload.get("started_at_ms") or 0)
        payload.setdefault(
            "latency_ms",
            max(0, int(payload["finished_at_ms"]) - int(payload.get("started_at_ms") or 0)),
        )
        payload.setdefault("evidence_event_ids_json", [])
        self.conn.execute(
            """
            INSERT INTO narrative_model_runs (
              run_id, stage, target_type, target_id, "window", scope, provider, model, schema_version,
              prompt_version, artifact_version_hash, input_hash, output_hash, evidence_event_ids_json,
              request_json, response_json, usage_json, trace_metadata_json, status, error,
              started_at_ms, finished_at_ms, latency_ms
            )
            VALUES (
              %(run_id)s, %(stage)s, %(target_type)s, %(target_id)s, %(window)s, %(scope)s, %(provider)s,
              %(model)s, %(schema_version)s, %(prompt_version)s, %(artifact_version_hash)s,
              %(input_hash)s, %(output_hash)s, %(evidence_event_ids_json)s, %(request_json)s,
              %(response_json)s, %(usage_json)s, %(trace_metadata_json)s, %(status)s, %(error)s,
              %(started_at_ms)s, %(finished_at_ms)s, %(latency_ms)s
            )
            ON CONFLICT (run_id) DO UPDATE SET
              response_json = EXCLUDED.response_json,
              usage_json = EXCLUDED.usage_json,
              trace_metadata_json = EXCLUDED.trace_metadata_json,
              status = EXCLUDED.status,
              error = EXCLUDED.error,
              finished_at_ms = EXCLUDED.finished_at_ms,
              latency_ms = EXCLUDED.latency_ms
            """,
            {
                **payload,
                "evidence_event_ids_json": _json(payload.get("evidence_event_ids_json") or []),
                "request_json": _json(payload.get("request_json") or {}),
                "response_json": None if payload.get("response_json") is None else _json(payload.get("response_json")),
                "usage_json": _json(payload.get("usage_json") or {}),
                "trace_metadata_json": _json(payload.get("trace_metadata_json") or {}),
            },
        )
        if commit:
            _commit_if_available(self.conn)
        return payload

    def complete_mention_semantics_batch(
        self,
        *,
        run_id: str,
        labels: Sequence[dict[str, Any]],
        failures: Sequence[dict[str, Any]],
        now_ms: int,
    ) -> dict[str, int]:
        labeled = 0
        unavailable = 0
        failed = 0
        for label in labels:
            status = str(label.get("status") or "labeled")
            is_unavailable = status == "semantic_unavailable"
            if not is_unavailable:
                status = "labeled"
            cursor = self.conn.execute(
                """
                UPDATE token_mention_semantics
                SET status = %s,
                    trade_stance = %s,
                    attention_valence = %s,
                    narrative_cluster_key = %s,
                    claim_type = %s,
                    evidence_type = %s,
                    semantic_confidence = %s,
                    co_mentioned_targets_json = %s,
                    evidence_refs_json = %s,
                    raw_label_json = %s,
                    model_run_id = %s,
                    computed_at_ms = %s,
                    error = NULL
                WHERE (
                    semantic_id = %s
                    OR (
                      COALESCE(%s, '') = ''
                      AND event_id = %s
                      AND target_type = %s
                      AND target_id = %s
                      AND schema_version = %s
                      AND text_fingerprint = %s
                    )
                    OR (
                      COALESCE(%s, '') = ''
                      AND COALESCE(%s, '') = ''
                      AND event_id = %s
                      AND target_type = %s
                      AND target_id = %s
                      AND (
                        SELECT COUNT(*)
                        FROM token_mention_semantics AS matching
                        WHERE matching.event_id = token_mention_semantics.event_id
                          AND matching.target_type = token_mention_semantics.target_type
                          AND matching.target_id = token_mention_semantics.target_id
                      ) = 1
                    )
                )
                """,
                (
                    status,
                    str(label.get("trade_stance") or "unknown"),
                    str(label.get("attention_valence") or "unknown"),
                    label.get("narrative_cluster_key"),
                    str(label.get("claim_type") or "other"),
                    str(label.get("evidence_type") or "unknown"),
                    float(label.get("semantic_confidence") or 0.0),
                    _json(label.get("co_mentioned_targets") or []),
                    _json(label.get("evidence_refs") or []),
                    _json(label.get("raw_label") or label),
                    run_id,
                    now_ms,
                    str(label.get("semantic_id") or ""),
                    str(label.get("semantic_id") or ""),
                    _required(label, "event_id"),
                    _required(label, "target_type"),
                    _required(label, "target_id"),
                    str(label.get("schema_version") or NARRATIVE_SCHEMA_VERSION),
                    str(label.get("text_fingerprint") or ""),
                    str(label.get("semantic_id") or ""),
                    str(label.get("text_fingerprint") or ""),
                    _required(label, "event_id"),
                    _required(label, "target_type"),
                    _required(label, "target_id"),
                ),
            )
            if int(getattr(cursor, "rowcount", 0) or 0) > 0:
                if is_unavailable:
                    unavailable += 1
                else:
                    labeled += 1
        for failure in failures:
            failure_status = str(failure.get("status") or "retryable_error")
            if failure_status == "semantic_unavailable":
                cursor = self.conn.execute(
                    """
                    UPDATE token_mention_semantics
                    SET status = 'semantic_unavailable',
                        retry_count = retry_count + 1,
                        next_retry_at_ms = 0,
                        computed_at_ms = %s,
                        error = %s
                    WHERE (
                        semantic_id = %s
                        OR (
                          COALESCE(%s, '') = ''
                          AND event_id = %s
                          AND target_type = %s
                          AND target_id = %s
                          AND schema_version = %s
                          AND text_fingerprint = %s
                        )
                        OR (
                          COALESCE(%s, '') = ''
                          AND COALESCE(%s, '') = ''
                          AND event_id = %s
                          AND target_type = %s
                          AND target_id = %s
                          AND (
                            SELECT COUNT(*)
                            FROM token_mention_semantics AS matching
                            WHERE matching.event_id = token_mention_semantics.event_id
                              AND matching.target_type = token_mention_semantics.target_type
                              AND matching.target_id = token_mention_semantics.target_id
                          ) = 1
                        )
                    )
                    """,
                    (
                        now_ms,
                        str(failure.get("error") or "provider_failure"),
                        str(failure.get("semantic_id") or ""),
                        str(failure.get("semantic_id") or ""),
                        _required(failure, "event_id"),
                        _required(failure, "target_type"),
                        _required(failure, "target_id"),
                        str(failure.get("schema_version") or NARRATIVE_SCHEMA_VERSION),
                        str(failure.get("text_fingerprint") or ""),
                        str(failure.get("semantic_id") or ""),
                        str(failure.get("text_fingerprint") or ""),
                        _required(failure, "event_id"),
                        _required(failure, "target_type"),
                        _required(failure, "target_id"),
                    ),
                )
                unavailable += int(getattr(cursor, "rowcount", 0) or 0)
            else:
                cursor = self.conn.execute(
                    """
                    UPDATE token_mention_semantics
                    SET status = 'retryable_error',
                        retry_count = retry_count + 1,
                        next_retry_at_ms = %s,
                        error = %s
                    WHERE (
                        semantic_id = %s
                        OR (
                          COALESCE(%s, '') = ''
                          AND event_id = %s
                          AND target_type = %s
                          AND target_id = %s
                          AND schema_version = %s
                          AND text_fingerprint = %s
                        )
                        OR (
                          COALESCE(%s, '') = ''
                          AND COALESCE(%s, '') = ''
                          AND event_id = %s
                          AND target_type = %s
                          AND target_id = %s
                          AND (
                            SELECT COUNT(*)
                            FROM token_mention_semantics AS matching
                            WHERE matching.event_id = token_mention_semantics.event_id
                              AND matching.target_type = token_mention_semantics.target_type
                              AND matching.target_id = token_mention_semantics.target_id
                          ) = 1
                        )
                    )
                    """,
                    (
                        int(failure.get("next_retry_at_ms") or now_ms + 60_000),
                        str(failure.get("error") or "provider_failure"),
                        str(failure.get("semantic_id") or ""),
                        str(failure.get("semantic_id") or ""),
                        _required(failure, "event_id"),
                        _required(failure, "target_type"),
                        _required(failure, "target_id"),
                        str(failure.get("schema_version") or NARRATIVE_SCHEMA_VERSION),
                        str(failure.get("text_fingerprint") or ""),
                        str(failure.get("semantic_id") or ""),
                        str(failure.get("text_fingerprint") or ""),
                        _required(failure, "event_id"),
                        _required(failure, "target_type"),
                        _required(failure, "target_id"),
                    ),
                )
                failed += int(getattr(cursor, "rowcount", 0) or 0)
        _commit_if_available(self.conn)
        return {"labeled": labeled, "semantic_unavailable": unavailable, "failed": failed}

    def due_digest_targets(
        self, *, now_ms: int, limit: int, windows: tuple[str, ...] = ("1h",)
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM narrative_admissions
            WHERE status = 'admitted'
              AND next_digest_due_at_ms <= %s
              AND "window" = ANY(%s)
            ORDER BY priority DESC, last_seen_at_ms DESC
            LIMIT %s
            """,
            (int(now_ms), list(windows), int(limit)),
        ).fetchall()
        return [_row(row) for row in rows]

    def digest_context(
        self,
        *,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        max_mentions: int,
    ) -> dict[str, Any]:
        admission_row = self.conn.execute(
            """
            SELECT *
            FROM narrative_admissions
            WHERE target_type = %s
              AND target_id = %s
              AND "window" = %s
              AND scope = %s
              AND schema_version = %s
              AND status = 'admitted'
            ORDER BY last_seen_at_ms DESC
            LIMIT 1
            """,
            (target_type, target_id, window, scope, NARRATIVE_SCHEMA_VERSION),
        ).fetchone()
        if not admission_row:
            return {
                "target_type": target_type,
                "target_id": target_id,
                "window": window,
                "scope": scope,
                "mentions": [],
                "semantic_rows": [],
                "source_event_count": 0,
                "semantic_row_count": 0,
                "missing_semantic_count": 0,
                "pending_semantic_count": 0,
                "retryable_semantic_count": 0,
                "labeled_event_count": 0,
                "terminal_unavailable_count": 0,
                "independent_author_count": 0,
                "allowed_refs": [],
                "data_gaps": [{"reason": "not_admitted"}],
            }
        admission = _row(admission_row)
        source_event_ids = _json_list(admission.get("source_event_ids_json"))
        coverage = self._semantic_coverage_for_source_ids(
            source_event_ids=source_event_ids,
            target_type=target_type,
            target_id=target_id,
            schema_version=NARRATIVE_SCHEMA_VERSION,
        )
        if not source_event_ids:
            return {
                "target_type": target_type,
                "target_id": target_id,
                "window": window,
                "scope": scope,
                "admission_id": admission.get("admission_id"),
                "source_fingerprint": admission.get("source_fingerprint"),
                "source_event_ids": [],
                "mentions": [],
                "semantic_rows": [],
                "source_event_count": int(admission.get("source_event_count") or 0),
                "semantic_row_count": 0,
                "missing_semantic_count": 0,
                "pending_semantic_count": 0,
                "retryable_semantic_count": 0,
                "labeled_event_count": 0,
                "terminal_unavailable_count": 0,
                "independent_author_count": int(admission.get("independent_author_count") or 0),
                "prompt_mention_count": 0,
                "prompt_mention_limit": int(max_mentions),
                "allowed_refs": [],
            }
        joined_rows = self.conn.execute(
            """
            WITH source_ids AS (
              SELECT jsonb_array_elements_text(%s::jsonb) AS event_id
            )
            SELECT
              events.event_id,
              events.text_clean AS text_clean,
              events.author_handle,
              events.tweet_id,
              events.raw_json AS reference_json,
              events.received_at_ms AS source_received_at_ms,
              semantics.semantic_id,
              semantics.schema_version,
              semantics.model_version,
              semantics.text_fingerprint,
              semantics.language,
              semantics.status,
              semantics.trade_stance,
              semantics.attention_valence,
              semantics.narrative_cluster_key,
              semantics.claim_type,
              semantics.evidence_type,
              semantics.semantic_confidence,
              semantics.co_mentioned_targets_json,
              semantics.evidence_refs_json,
              semantics.raw_label_json,
              semantics.model_run_id,
              semantics.computed_at_ms,
              semantics.retry_count,
              semantics.next_retry_at_ms,
              semantics.error
            FROM source_ids
            JOIN events ON events.event_id = source_ids.event_id
            LEFT JOIN LATERAL (
              SELECT semantics.*
              FROM token_mention_semantics AS semantics
              WHERE semantics.event_id = events.event_id
                AND semantics.target_type = %s
                AND semantics.target_id = %s
                AND semantics.schema_version = %s
              ORDER BY semantics.computed_at_ms DESC NULLS LAST,
                       semantics.queued_at_ms DESC NULLS LAST,
                       semantics.semantic_id ASC
              LIMIT 1
            ) AS semantics ON true
            ORDER BY events.received_at_ms DESC, events.event_id DESC
            LIMIT %s
            """,
            (_json(source_event_ids), target_type, target_id, NARRATIVE_SCHEMA_VERSION, int(max_mentions)),
        ).fetchall()
        mentions = [_row(row) for row in joined_rows]
        semantics = [row for row in mentions if row.get("semantic_id")]
        return {
            "target_type": target_type,
            "target_id": target_id,
            "window": window,
            "scope": scope,
            "admission_id": admission.get("admission_id"),
            "source_fingerprint": admission.get("source_fingerprint"),
            "source_event_ids": source_event_ids,
            "mentions": mentions,
            "semantic_rows": semantics,
            "source_event_count": coverage["source_event_count"],
            "semantic_row_count": coverage["semantic_row_count"],
            "missing_semantic_count": coverage["missing_semantic_count"],
            "pending_semantic_count": coverage["pending_semantic_count"],
            "retryable_semantic_count": coverage["retryable_semantic_count"],
            "labeled_event_count": coverage["labeled_event_count"],
            "terminal_unavailable_count": coverage["terminal_unavailable_count"],
            "independent_author_count": int(admission.get("independent_author_count") or _author_count(mentions)),
            "prompt_mention_count": len(mentions),
            "prompt_mention_limit": int(max_mentions),
            "allowed_refs": _allowed_refs_for_semantics(semantics),
        }

    def replace_current_digest(self, digest: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
        payload = _digest_payload(digest, now_ms=now_ms)
        self.conn.execute(
            """
            UPDATE token_discussion_digests
            SET is_current = false,
                superseded_at_ms = %s
            WHERE target_type = %s
              AND target_id = %s
              AND "window" = %s
              AND scope = %s
              AND schema_version = %s
              AND is_current = true
            """,
            (
                now_ms,
                payload["target_type"],
                payload["target_id"],
                payload["window"],
                payload["scope"],
                payload["schema_version"],
            ),
        )
        self.conn.execute(
            """
            INSERT INTO token_discussion_digests (
              digest_id, target_type, target_id, "window", scope, schema_version, model_version,
              status, is_current, epoch_id, epoch_policy_version, source_event_ids_json,
              source_window_start_ms, source_window_end_ms, epoch_closed_at_ms,
              display_current_until_ms, refresh_reason, source_fingerprint, label_fingerprint, headline_zh,
              dominant_narratives_json, bull_view_json, bear_view_json, stance_mix_json,
              attention_valence_mix_json, propagation_read_json, reflexivity_read_json,
              watch_triggers_json, invalidation_conditions_json, data_gaps_json,
              semantic_coverage, source_event_count, labeled_event_count, independent_author_count,
              evidence_refs_json, model_run_id, computed_at_ms, expires_at_ms, superseded_at_ms
            )
            VALUES (
              %(digest_id)s, %(target_type)s, %(target_id)s, %(window)s, %(scope)s, %(schema_version)s,
              %(model_version)s, %(status)s, true, %(epoch_id)s, %(epoch_policy_version)s,
              %(source_event_ids_json)s, %(source_window_start_ms)s, %(source_window_end_ms)s,
              %(epoch_closed_at_ms)s, %(display_current_until_ms)s, %(refresh_reason)s,
              %(source_fingerprint)s, %(label_fingerprint)s,
              %(headline_zh)s, %(dominant_narratives_json)s, %(bull_view_json)s, %(bear_view_json)s,
              %(stance_mix_json)s, %(attention_valence_mix_json)s, %(propagation_read_json)s,
              %(reflexivity_read_json)s, %(watch_triggers_json)s, %(invalidation_conditions_json)s,
              %(data_gaps_json)s, %(semantic_coverage)s, %(source_event_count)s, %(labeled_event_count)s,
              %(independent_author_count)s, %(evidence_refs_json)s, %(model_run_id)s, %(computed_at_ms)s,
              %(expires_at_ms)s, %(superseded_at_ms)s
            )
            ON CONFLICT (digest_id)
            DO UPDATE SET
              model_version = EXCLUDED.model_version,
              status = EXCLUDED.status,
              is_current = true,
              epoch_id = EXCLUDED.epoch_id,
              epoch_policy_version = EXCLUDED.epoch_policy_version,
              source_event_ids_json = EXCLUDED.source_event_ids_json,
              source_window_start_ms = EXCLUDED.source_window_start_ms,
              source_window_end_ms = EXCLUDED.source_window_end_ms,
              epoch_closed_at_ms = EXCLUDED.epoch_closed_at_ms,
              display_current_until_ms = EXCLUDED.display_current_until_ms,
              refresh_reason = EXCLUDED.refresh_reason,
              headline_zh = EXCLUDED.headline_zh,
              dominant_narratives_json = EXCLUDED.dominant_narratives_json,
              bull_view_json = EXCLUDED.bull_view_json,
              bear_view_json = EXCLUDED.bear_view_json,
              stance_mix_json = EXCLUDED.stance_mix_json,
              attention_valence_mix_json = EXCLUDED.attention_valence_mix_json,
              propagation_read_json = EXCLUDED.propagation_read_json,
              reflexivity_read_json = EXCLUDED.reflexivity_read_json,
              watch_triggers_json = EXCLUDED.watch_triggers_json,
              invalidation_conditions_json = EXCLUDED.invalidation_conditions_json,
              data_gaps_json = EXCLUDED.data_gaps_json,
              semantic_coverage = EXCLUDED.semantic_coverage,
              source_event_count = EXCLUDED.source_event_count,
              labeled_event_count = EXCLUDED.labeled_event_count,
              independent_author_count = EXCLUDED.independent_author_count,
              evidence_refs_json = EXCLUDED.evidence_refs_json,
              model_run_id = EXCLUDED.model_run_id,
              computed_at_ms = EXCLUDED.computed_at_ms,
              expires_at_ms = EXCLUDED.expires_at_ms,
              superseded_at_ms = EXCLUDED.superseded_at_ms
            """,
            payload,
        )
        _commit_if_available(self.conn)
        return {
            **digest,
            "digest_id": payload["digest_id"],
            "computed_at_ms": payload["computed_at_ms"],
            "is_current": True,
        }

    def mark_admissions_digest_scanned(
        self,
        admission_ids: Sequence[str],
        *,
        next_due_at_ms: int,
        now_ms: int,
    ) -> dict[str, int]:
        ids = _stable_ids(admission_ids)
        if not ids:
            return {"updated": 0}
        cursor = self.conn.execute(
            """
            UPDATE narrative_admissions
            SET next_digest_due_at_ms = %s,
                updated_at_ms = %s
            WHERE admission_id = ANY(%s)
            """,
            (int(next_due_at_ms), int(now_ms), ids),
        )
        _commit_if_available(self.conn)
        return {"updated": int(getattr(cursor, "rowcount", 0) or 0)}

    def latest_ready_digest_for_target(
        self,
        *,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        schema_version: str,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT digest.*,
                   COALESCE(backlog.pending, 0) AS semantic_backlog_pending,
                   COALESCE(backlog.retryable, 0) AS semantic_backlog_retryable,
                   COALESCE(backlog.unavailable, 0) AS semantic_backlog_unavailable,
                   backlog.oldest_due_at_ms AS semantic_backlog_oldest_due_at_ms
            FROM token_discussion_digests AS digest
            LEFT JOIN LATERAL (
              SELECT
                COUNT(*) FILTER (
                  WHERE semantics.status IN ('queued', 'retryable_error', 'stale')
                ) AS pending,
                COUNT(*) FILTER (WHERE semantics.status = 'retryable_error') AS retryable,
                COUNT(*) FILTER (WHERE semantics.status = 'semantic_unavailable') AS unavailable,
                MIN(semantics.next_retry_at_ms) FILTER (
                  WHERE semantics.status IN ('queued', 'retryable_error', 'stale')
                ) AS oldest_due_at_ms
              FROM token_mention_semantics AS semantics
              WHERE semantics.target_type = digest.target_type
                AND semantics.target_id = digest.target_id
                AND semantics.schema_version = digest.schema_version
            ) AS backlog ON true
            WHERE digest.target_type = %s
              AND digest.target_id = %s
              AND digest."window" = %s
              AND digest.scope = %s
              AND digest.schema_version = %s
              AND digest.status = 'ready'
            ORDER BY digest.computed_at_ms DESC, digest.digest_id DESC
            LIMIT 1
            """,
            (target_type, target_id, window, scope, schema_version),
        ).fetchone()
        return _row(row) if row else None

    def current_admission_for_target(
        self,
        *,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        schema_version: str,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM narrative_admissions
            WHERE target_type = %s
              AND target_id = %s
              AND "window" = %s
              AND scope = %s
              AND schema_version = %s
            ORDER BY CASE
                       WHEN status = 'admitted' THEN 0
                       WHEN status = 'suppressed' THEN 1
                       ELSE 2
                     END,
                     last_seen_at_ms DESC
            LIMIT 1
            """,
            (target_type, target_id, window, scope, schema_version),
        ).fetchone()
        return _row(row) if row else None

    def market_context_for_admission(
        self,
        admission: dict[str, Any],
        *,
        last_ready_digest: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if last_ready_digest is None:
            return {}
        target_type = str(admission.get("target_type") or "")
        target_id = str(admission.get("target_id") or "")
        if target_type not in {"chain_token", "cex_symbol"} or not target_id:
            return {}
        ready_at_ms = _int(
            last_ready_digest.get("epoch_closed_at_ms")
            or last_ready_digest.get("source_window_end_ms")
            or last_ready_digest.get("computed_at_ms")
        )
        current_at_ms = _int(
            admission.get("source_max_received_at_ms")
            or admission.get("source_window_end_ms")
            or admission.get("last_seen_at_ms")
        )
        if ready_at_ms is None or current_at_ms is None:
            return {}
        ready_tick = self._latest_market_tick_at_or_before(
            target_type=target_type,
            target_id=target_id,
            observed_at_ms=ready_at_ms,
        )
        current_tick = self._latest_market_tick_at_or_before(
            target_type=target_type,
            target_id=target_id,
            observed_at_ms=current_at_ms,
        )
        ready_price = _float((ready_tick or {}).get("price_usd"))
        current_price = _float((current_tick or {}).get("price_usd"))
        if ready_price is None or ready_price <= 0 or current_price is None:
            return {}
        price_move_pct = ((current_price - ready_price) / ready_price) * 100.0
        return {
            "price_move_pct": price_move_pct,
            "price_move_pct_since_ready": price_move_pct,
            "ready_price_usd": ready_price,
            "current_price_usd": current_price,
            "ready_tick_observed_at_ms": (ready_tick or {}).get("observed_at_ms"),
            "current_tick_observed_at_ms": (current_tick or {}).get("observed_at_ms"),
        }

    def _latest_market_tick_at_or_before(
        self,
        *,
        target_type: str,
        target_id: str,
        observed_at_ms: int,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM market_ticks
            WHERE target_type = %s
              AND target_id = %s
              AND observed_at_ms <= %s
            ORDER BY observed_at_ms DESC, tick_id DESC
            LIMIT 1
            """,
            (target_type, target_id, int(observed_at_ms)),
        ).fetchone()
        return _row(row) if row else None

    def current_narrative_snapshots_for_targets(
        self,
        targets: Sequence[dict[str, str]],
        *,
        window: str,
        scope: str,
        schema_version: str,
        now_ms: int,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        result: dict[tuple[str, str], dict[str, Any]] = {}
        for target in targets:
            target_type = str(target.get("target_type") or "")
            target_id = str(target.get("target_id") or "")
            key = (target_type, target_id)
            if window not in DIGEST_WINDOWS:
                result[key] = unsupported_digest_sentinel(
                    target_type=target_type,
                    target_id=target_id,
                    window=window,
                    scope=scope,
                    schema_version=schema_version,
                )
                continue

            admission = self.current_admission_for_target(
                target_type=target_type,
                target_id=target_id,
                window=window,
                scope=scope,
                schema_version=schema_version,
            )
            last_ready = self.latest_ready_digest_for_target(
                target_type=target_type,
                target_id=target_id,
                window=window,
                scope=scope,
                schema_version=schema_version,
            )
            current_admission = admission if _is_admitted(admission) else None
            if last_ready is not None:
                currentness = public_currentness(
                    digest=last_ready,
                    admission=current_admission,
                    window=window,
                    now_ms=now_ms,
                    reason="not_in_current_frontier" if admission and not current_admission else None,
                )
                result[key] = {**last_ready, "_current_admission": current_admission, "currentness": currentness}
                continue

            reason = self._not_ready_reason_for_admission(admission)
            missing = _missing_digest_row(
                target_type=target_type,
                target_id=target_id,
                window=window,
                scope=scope,
                schema_version=schema_version,
                reason=reason,
            )
            if current_admission is not None:
                coverage = self.semantic_coverage_for_admission(current_admission)
                missing.update(
                    {
                        "source_event_count": coverage["source_event_count"],
                        "labeled_event_count": coverage["labeled_event_count"],
                        "independent_author_count": int(current_admission.get("independent_author_count") or 0),
                        "semantic_backlog_pending": (
                            coverage["missing_semantic_count"] + coverage["pending_semantic_count"]
                        ),
                        "semantic_backlog_retryable": coverage["retryable_semantic_count"],
                        "semantic_backlog_unavailable": coverage["terminal_unavailable_count"],
                    }
                )
            missing["currentness"] = public_currentness(
                digest=None,
                admission=current_admission,
                window=window,
                now_ms=now_ms,
                reason=reason,
            )
            result[key] = missing
        return result

    def current_digests_for_targets(
        self,
        targets: Sequence[dict[str, str]],
        *,
        window: str,
        scope: str,
        schema_version: str,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        return self.current_narrative_snapshots_for_targets(
            targets,
            window=window,
            scope=scope,
            schema_version=schema_version,
            now_ms=_now_ms(),
        )

    def _not_ready_reason_for_admission(self, admission: dict[str, Any] | None) -> str:
        if admission is None:
            return "no_ready_digest"
        if not _is_admitted(admission):
            return "not_in_current_frontier"
        if (_int(admission.get("source_event_count")) or 0) == 0:
            return "low_source_volume"
        if (_int(admission.get("independent_author_count")) or 0) == 0:
            return "low_independent_author_count"
        coverage = self.semantic_coverage_for_admission(admission)
        pending = (
            coverage["missing_semantic_count"]
            + coverage["pending_semantic_count"]
            + coverage["retryable_semantic_count"]
        )
        if pending > 0:
            return "semantic_labeling_pending"
        if coverage["source_event_count"] > 0 and coverage["labeled_event_count"] == 0:
            return "low_semantic_coverage"
        return "no_ready_digest"

    def semantics_for_posts(
        self,
        posts: Sequence[dict[str, Any]],
        *,
        schema_version: str,
    ) -> dict[tuple[str, str, str], dict[str, Any]]:
        result: dict[tuple[str, str, str], dict[str, Any]] = {}
        for post in posts:
            row = self.conn.execute(
                """
                SELECT *
                FROM token_mention_semantics
                WHERE event_id = %s
                  AND target_type = %s
                  AND target_id = %s
                  AND schema_version = %s
                ORDER BY computed_at_ms DESC NULLS LAST, queued_at_ms DESC NULLS LAST
                LIMIT 1
                """,
                (
                    post["event_id"],
                    post["target_type"],
                    post["target_id"],
                    schema_version,
                ),
            ).fetchone()
            if row:
                decoded = _row(row)
                result[(decoded["event_id"], decoded["target_type"], decoded["target_id"])] = decoded
        return result


def _empty_semantic_coverage() -> dict[str, int]:
    return {key: 0 for key in _SEMANTIC_COVERAGE_KEYS}


def _missing_digest_row(
    *,
    target_type: str,
    target_id: str,
    window: str,
    scope: str,
    schema_version: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "target_type": target_type,
        "target_id": target_id,
        "window": window,
        "scope": scope,
        "schema_version": schema_version,
        "status": "pending",
        "is_current": False,
        "data_gaps_json": [{"reason": reason}],
        "semantic_coverage": 0.0,
        "source_event_count": 0,
        "labeled_event_count": 0,
        "independent_author_count": 0,
        "evidence_refs_json": [],
    }


def deterministic_admission_id(
    *,
    target_type: str,
    target_id: str,
    window: str,
    scope: str,
    schema_version: str,
) -> str:
    return _stable_id("narrative_admission", target_type, target_id, window, scope, schema_version)


def deterministic_semantic_id(
    *,
    event_id: str,
    target_type: str,
    target_id: str,
    schema_version: str,
    text_fingerprint: str,
) -> str:
    return _stable_id("mention_semantic", event_id, target_type, target_id, schema_version, text_fingerprint)


def deterministic_digest_id(
    *,
    target_type: str,
    target_id: str,
    window: str,
    scope: str,
    schema_version: str,
    source_fingerprint: str | None,
    label_fingerprint: str | None,
) -> str:
    return _stable_id(
        "discussion_digest",
        target_type,
        target_id,
        window,
        scope,
        schema_version,
        source_fingerprint or "",
        label_fingerprint or "",
    )


def deterministic_run_id(*, stage: str, input_hash: str, started_at_ms: int) -> str:
    return _stable_id("narrative_model_run", stage, input_hash, str(started_at_ms))


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def _stable_ids(values: Sequence[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _digest_payload(digest: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
    source_event_ids = _json_list(digest.get("source_event_ids") or digest.get("source_event_ids_json"))
    source_fingerprint = digest.get("source_fingerprint")
    if not source_fingerprint:
        source_fingerprint = build_source_fingerprint(
            source_event_ids,
            digest.get("source_max_received_at_ms"),
        )
    label_fingerprint = digest.get("label_fingerprint")
    if not label_fingerprint:
        label_fingerprint = build_label_fingerprint(digest.get("semantic_rows") or [])
    digest_id = deterministic_digest_id(
        target_type=_required(digest, "target_type"),
        target_id=_required(digest, "target_id"),
        window=_required(digest, "window"),
        scope=_required(digest, "scope"),
        schema_version=str(digest.get("schema_version") or NARRATIVE_SCHEMA_VERSION),
        source_fingerprint=source_fingerprint,
        label_fingerprint=label_fingerprint,
    )
    return {
        "digest_id": digest_id,
        "target_type": _required(digest, "target_type"),
        "target_id": _required(digest, "target_id"),
        "window": _required(digest, "window"),
        "scope": _required(digest, "scope"),
        "schema_version": str(digest.get("schema_version") or NARRATIVE_SCHEMA_VERSION),
        "model_version": str(digest.get("model_version") or "unknown"),
        "status": str(digest.get("status") or "pending"),
        "epoch_id": digest.get("epoch_id"),
        "epoch_policy_version": digest.get("epoch_policy_version"),
        "source_event_ids_json": _json(source_event_ids),
        "source_window_start_ms": _int(digest.get("source_window_start_ms")),
        "source_window_end_ms": _int(digest.get("source_window_end_ms")),
        "epoch_closed_at_ms": _int(digest.get("epoch_closed_at_ms")),
        "display_current_until_ms": _int(digest.get("display_current_until_ms")),
        "refresh_reason": digest.get("refresh_reason"),
        "source_fingerprint": source_fingerprint,
        "label_fingerprint": label_fingerprint,
        "headline_zh": digest.get("headline_zh"),
        "dominant_narratives_json": _json(digest.get("dominant_narratives") or []),
        "bull_view_json": _json(digest.get("bull_view") or {}),
        "bear_view_json": _json(digest.get("bear_view") or {}),
        "stance_mix_json": _json(digest.get("stance_mix") or {}),
        "attention_valence_mix_json": _json(digest.get("attention_valence_mix") or {}),
        "propagation_read_json": _json(digest.get("propagation_read") or {}),
        "reflexivity_read_json": _json(digest.get("reflexivity_read") or {}),
        "watch_triggers_json": _json(digest.get("watch_triggers") or []),
        "invalidation_conditions_json": _json(digest.get("invalidation_conditions") or []),
        "data_gaps_json": _json(digest.get("data_gaps") or []),
        "semantic_coverage": float(digest.get("semantic_coverage") or 0.0),
        "source_event_count": int(digest.get("source_event_count") or 0),
        "labeled_event_count": int(digest.get("labeled_event_count") or 0),
        "independent_author_count": int(digest.get("independent_author_count") or 0),
        "evidence_refs_json": _json(digest.get("evidence_refs") or []),
        "model_run_id": digest.get("model_run_id"),
        "computed_at_ms": int(digest.get("computed_at_ms") or now_ms),
        "expires_at_ms": digest.get("expires_at_ms"),
        "superseded_at_ms": digest.get("superseded_at_ms"),
    }


def _allowed_refs_for_semantics(semantics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for row in semantics:
        if row.get("event_id"):
            refs.append({"ref_id": f"event:{row['event_id']}", "kind": "event", "source_table": "events"})
        if row.get("semantic_id"):
            refs.append(
                {
                    "ref_id": f"semantic:{row['semantic_id']}",
                    "kind": "semantic",
                    "source_table": "token_mention_semantics",
                }
            )
    return refs


def _author_count(rows: Sequence[dict[str, Any]]) -> int:
    return len({str(row.get("author_handle") or "").strip() for row in rows if str(row.get("author_handle") or "")})


def _json(value: Any) -> Jsonb:
    return Jsonb(value, dumps=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, default=str))


def _json_list(value: Any) -> list[str]:
    if value is None:
        return []
    decoded = value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = [value]
    if not isinstance(decoded, Sequence) or isinstance(decoded, (bytes, bytearray, str)):
        return []
    return [str(item) for item in decoded if str(item)]


def _row(row: Any) -> dict[str, Any]:
    decoded = dict(row)
    if "source_event_ids_json" in decoded and "source_event_ids" not in decoded:
        decoded["source_event_ids"] = _json_list(decoded.get("source_event_ids_json"))
    return decoded


def _is_admitted(row: dict[str, Any] | None) -> bool:
    return row is not None and str(row.get("status") or "") == "admitted"


def _required(row: dict[str, Any], key: str) -> str:
    value = _clean(row.get(key))
    if not value:
        raise ValueError(f"missing required narrative repository value: {key}")
    return value


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _now_ms() -> int:
    return int(time.time() * 1000)


def _commit_if_available(conn: Any) -> None:
    commit = getattr(conn, "commit", None)
    if commit is not None:
        commit()
