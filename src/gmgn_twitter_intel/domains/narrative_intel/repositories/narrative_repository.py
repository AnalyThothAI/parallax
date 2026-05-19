from __future__ import annotations

import hashlib
import json
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
from gmgn_twitter_intel.domains.narrative_intel.services.fingerprints import text_fingerprint


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

    def due_admissions_for_semantics(self, *, now_ms: int, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM narrative_admissions
            WHERE status = 'admitted' AND next_semantics_due_at_ms <= %s
            ORDER BY priority DESC, last_seen_at_ms DESC
            LIMIT %s
            """,
            (int(now_ms), int(limit)),
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

    def due_mentions_for_labeling(self, *, now_ms: int, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT semantics.*,
                   events.text_clean AS text_clean,
                   events.author_handle,
                   events.tweet_id,
                   events.raw_json AS reference_json
            FROM token_mention_semantics AS semantics
            JOIN events ON events.event_id = semantics.event_id
            WHERE semantics.status IN ('queued', 'retryable_error', 'stale')
              AND semantics.next_retry_at_ms <= %s
            ORDER BY semantics.source_received_at_ms DESC, semantics.semantic_id ASC
            LIMIT %s
            """,
            (int(now_ms), int(limit)),
        ).fetchall()
        return [_row(row) for row in rows]

    def pending_mention_semantics_count(
        self,
        *,
        target_type: str,
        target_id: str,
        schema_version: str,
        model_version: str | None = None,
    ) -> int:
        model_clause = "AND model_version = %s" if model_version else ""
        params: list[Any] = [target_type, target_id, schema_version]
        if model_version:
            params.append(model_version)
        row = self.conn.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM token_mention_semantics
            WHERE target_type = %s
              AND target_id = %s
              AND schema_version = %s
              {model_clause}
              AND status IN ('queued', 'retryable_error', 'stale')
            """,
            tuple(params),
        ).fetchone()
        return int(row["count"] if row else 0)

    def prune_pending_mention_semantics_backlog(
        self,
        *,
        schema_version: str,
        now_ms: int,
        max_source_age_ms: int | None = None,
        max_pending_per_target: int | None = None,
    ) -> dict[str, int]:
        deleted_old = 0
        if max_source_age_ms is not None and int(max_source_age_ms) > 0:
            cutoff_ms = int(now_ms) - int(max_source_age_ms)
            old_cursor = self.conn.execute(
                """
                DELETE FROM token_mention_semantics
                WHERE schema_version = %s
                  AND status IN ('queued', 'retryable_error', 'stale')
                  AND source_received_at_ms < %s
                """,
                (schema_version, cutoff_ms),
            )
            deleted_old = int(getattr(old_cursor, "rowcount", 0) or 0)

        deleted_overflow = 0
        if max_pending_per_target is not None and int(max_pending_per_target) > 0:
            overflow_cursor = self.conn.execute(
                """
                WITH ranked AS (
                  SELECT
                    semantic_id,
                    row_number() OVER (
                      PARTITION BY target_type, target_id
                      ORDER BY source_received_at_ms DESC, queued_at_ms DESC, semantic_id DESC
                    ) AS target_pending_rank
                  FROM token_mention_semantics
                  WHERE schema_version = %s
                    AND status IN ('queued', 'retryable_error', 'stale')
                )
                DELETE FROM token_mention_semantics AS semantics
                USING ranked
                WHERE semantics.semantic_id = ranked.semantic_id
                  AND ranked.target_pending_rank > %s
                """,
                (schema_version, int(max_pending_per_target)),
            )
            deleted_overflow = int(getattr(overflow_cursor, "rowcount", 0) or 0)

        _commit_if_available(self.conn)
        return {
            "deleted_old_semantics": deleted_old,
            "deleted_overflow_semantics": deleted_overflow,
        }

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

    def cleanup_current_backlog(
        self,
        *,
        schema_version: str,
        window: str | None = None,
        scope: str | None = None,
        now_ms: int,
    ) -> dict[str, int]:
        filters = ["admissions.status = 'admitted'", "admissions.schema_version = %s"]
        params: list[Any] = [schema_version]
        if window is not None:
            filters.append('admissions."window" = %s')
            params.append(window)
        if scope is not None:
            filters.append("admissions.scope = %s")
            params.append(scope)
        admission_filter = " AND ".join(filters)
        semantic_admission_filter = "admissions.status = 'admitted' AND admissions.schema_version = %s"
        semantic_params: list[Any] = [schema_version]
        obsolete = self.conn.execute(
            f"""
            WITH current_sources AS (
              SELECT
                admissions.target_type,
                admissions.target_id,
                jsonb_array_elements_text(admissions.source_event_ids_json) AS event_id
              FROM narrative_admissions AS admissions
              WHERE {semantic_admission_filter}
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
            (*semantic_params, schema_version),
        )
        reset_retryable = self.conn.execute(
            f"""
            WITH current_sources AS (
              SELECT
                admissions.target_type,
                admissions.target_id,
                jsonb_array_elements_text(admissions.source_event_ids_json) AS event_id
              FROM narrative_admissions AS admissions
              WHERE {semantic_admission_filter}
            )
            UPDATE token_mention_semantics AS semantics
            SET status = 'queued',
                next_retry_at_ms = 0,
                error = NULL
            WHERE semantics.schema_version = %s
              AND semantics.status = 'retryable_error'
              AND EXISTS (
                SELECT 1
                FROM current_sources
                WHERE current_sources.event_id = semantics.event_id
                  AND current_sources.target_type = semantics.target_type
                  AND current_sources.target_id = semantics.target_id
              )
            """,
            (*semantic_params, schema_version),
        )
        stale_digests = self.conn.execute(
            f"""
            UPDATE token_discussion_digests AS digest
            SET status = 'stale',
                superseded_at_ms = %s
            FROM narrative_admissions AS admissions
            WHERE {admission_filter}
              AND digest.target_type = admissions.target_type
              AND digest.target_id = admissions.target_id
              AND digest."window" = admissions."window"
              AND digest.scope = admissions.scope
              AND digest.schema_version = admissions.schema_version
              AND digest.is_current = true
              AND COALESCE(digest.source_fingerprint, '') <> COALESCE(admissions.source_fingerprint, '')
            """,
            (int(now_ms), *params),
        )
        _commit_if_available(self.conn)
        return {
            "deleted_obsolete_semantics": int(getattr(obsolete, "rowcount", 0) or 0),
            "reset_retryable_semantics": int(getattr(reset_retryable, "rowcount", 0) or 0),
            "stale_digests": int(getattr(stale_digests, "rowcount", 0) or 0),
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
            if status == "semantic_unavailable":
                unavailable += 1
            else:
                status = "labeled"
                labeled += 1
            self.conn.execute(
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
                WHERE event_id = %s AND target_type = %s AND target_id = %s
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
                    _required(label, "event_id"),
                    _required(label, "target_type"),
                    _required(label, "target_id"),
                ),
            )
        for failure in failures:
            failure_status = str(failure.get("status") or "retryable_error")
            if failure_status == "semantic_unavailable":
                unavailable += 1
                self.conn.execute(
                    """
                    UPDATE token_mention_semantics
                    SET status = 'semantic_unavailable',
                        retry_count = retry_count + 1,
                        next_retry_at_ms = 0,
                        computed_at_ms = %s,
                        error = %s
                    WHERE event_id = %s AND target_type = %s AND target_id = %s
                    """,
                    (
                        now_ms,
                        str(failure.get("error") or "provider_failure"),
                        _required(failure, "event_id"),
                        _required(failure, "target_type"),
                        _required(failure, "target_id"),
                    ),
                )
            else:
                failed += 1
                self.conn.execute(
                    """
                    UPDATE token_mention_semantics
                    SET status = 'retryable_error',
                        retry_count = retry_count + 1,
                        next_retry_at_ms = %s,
                        error = %s
                    WHERE event_id = %s AND target_type = %s AND target_id = %s
                    """,
                    (
                        int(failure.get("next_retry_at_ms") or now_ms + 60_000),
                        str(failure.get("error") or "provider_failure"),
                        _required(failure, "event_id"),
                        _required(failure, "target_type"),
                        _required(failure, "target_id"),
                    ),
                )
        _commit_if_available(self.conn)
        return {"labeled": labeled, "semantic_unavailable": unavailable, "failed": failed}

    def due_digest_targets(self, *, now_ms: int, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM narrative_admissions
            WHERE status = 'admitted' AND next_digest_due_at_ms <= %s
            ORDER BY priority DESC, last_seen_at_ms DESC
            LIMIT %s
            """,
            (int(now_ms), int(limit)),
        ).fetchall()
        return [_row(row) for row in rows]

    def digest_context(
        self,
        *,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        since_ms: int,
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
                "labeled_event_count": 0,
                "independent_author_count": 0,
                "allowed_refs": [],
                "data_gaps": [{"reason": "not_admitted"}],
            }
        admission = _row(admission_row)
        source_event_ids = _json_list(admission.get("source_event_ids_json"))
        if not source_event_ids:
            return {
                "target_type": target_type,
                "target_id": target_id,
                "window": window,
                "scope": scope,
                "mentions": [],
                "semantic_rows": [],
                "source_event_count": int(admission.get("source_event_count") or 0),
                "labeled_event_count": 0,
                "independent_author_count": int(admission.get("independent_author_count") or 0),
                "allowed_refs": [],
            }
        joined_rows = self.conn.execute(
            """
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
            FROM events
            LEFT JOIN token_mention_semantics AS semantics
              ON semantics.event_id = events.event_id
             AND semantics.target_type = %s
             AND semantics.target_id = %s
             AND semantics.schema_version = %s
            WHERE events.event_id = ANY(%s)
              AND events.received_at_ms >= %s
            ORDER BY events.received_at_ms DESC, events.event_id DESC
            LIMIT %s
            """,
            (target_type, target_id, NARRATIVE_SCHEMA_VERSION, source_event_ids, int(since_ms), int(max_mentions)),
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
            "source_event_count": int(admission.get("source_event_count") or len(source_event_ids)),
            "labeled_event_count": sum(1 for row in semantics if row.get("status") == "labeled"),
            "independent_author_count": int(admission.get("independent_author_count") or _author_count(mentions)),
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
              status, is_current, source_fingerprint, label_fingerprint, headline_zh,
              dominant_narratives_json, bull_view_json, bear_view_json, stance_mix_json,
              attention_valence_mix_json, propagation_read_json, reflexivity_read_json,
              watch_triggers_json, invalidation_conditions_json, data_gaps_json,
              semantic_coverage, source_event_count, labeled_event_count, independent_author_count,
              evidence_refs_json, model_run_id, computed_at_ms, expires_at_ms, superseded_at_ms
            )
            VALUES (
              %(digest_id)s, %(target_type)s, %(target_id)s, %(window)s, %(scope)s, %(schema_version)s,
              %(model_version)s, %(status)s, true, %(source_fingerprint)s, %(label_fingerprint)s,
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

    def current_digests_for_targets(
        self,
        targets: Sequence[dict[str, str]],
        *,
        window: str,
        scope: str,
        schema_version: str,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        result: dict[tuple[str, str], dict[str, Any]] = {}
        for target in targets:
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
                  AND digest.is_current = true
                """,
                (target["target_type"], target["target_id"], window, scope, schema_version),
            ).fetchone()
            if row:
                decoded = _row(row)
                result[(decoded["target_type"], decoded["target_id"])] = decoded
        return result

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
    source_fingerprint = digest.get("source_fingerprint")
    if not source_fingerprint:
        source_fingerprint = build_source_fingerprint(
            digest.get("source_event_ids") or [],
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
    return dict(row)


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


def _commit_if_available(conn: Any) -> None:
    commit = getattr(conn, "commit", None)
    if commit is not None:
        commit()
