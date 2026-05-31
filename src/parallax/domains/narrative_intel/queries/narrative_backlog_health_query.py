from __future__ import annotations

from typing import Any

from parallax.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION
from parallax.domains.narrative_intel.types.narrative_epoch_policy import EPOCH_POLICY_VERSION

_HOUR_MS = 60 * 60 * 1000


class NarrativeBacklogHealthQuery:
    def __init__(
        self,
        conn: Any,
        *,
        realtime_windows: tuple[str, ...] = ("1h",),
        realtime_scopes: tuple[str, ...] = ("all",),
        semantics_rows_per_cycle: int = 10,
        semantics_interval_seconds: int = 60,
        digest_calls_per_cycle: int = 3,
        digest_interval_seconds: int = 120,
    ) -> None:
        self.conn = conn
        self.realtime_windows = tuple(dict.fromkeys(str(window) for window in realtime_windows if str(window))) or (
            "1h",
        )
        self.realtime_scopes = tuple(dict.fromkeys(str(scope) for scope in realtime_scopes if str(scope))) or ("all",)
        self.semantics_rows_per_cycle = max(1, int(semantics_rows_per_cycle or 1))
        self.semantics_interval_seconds = max(0, int(semantics_interval_seconds or 0))
        self.digest_calls_per_cycle = max(1, int(digest_calls_per_cycle or 1))
        self.digest_interval_seconds = max(0, int(digest_interval_seconds or 0))

    def health(
        self,
        *,
        now_ms: int,
        since_hours: int = 4,
        schema_version: str = NARRATIVE_SCHEMA_VERSION,
    ) -> dict[str, Any]:
        since_hours = max(1, int(since_hours or 1))
        since_ms = max(0, int(now_ms) - since_hours * _HOUR_MS)
        backlog = self._semantic_backlog(now_ms=int(now_ms), schema_version=schema_version)
        pending_digest_count = self._pending_digest_count(schema_version=schema_version)
        return {
            "schema_version": schema_version,
            "now_ms": int(now_ms),
            "since_hours": since_hours,
            "realtime_windows": list(self.realtime_windows),
            "realtime_scopes": list(self.realtime_scopes),
            "admissions": self._admission_health(schema_version=schema_version),
            "semantic_backlog": backlog,
            "recent_runs": self._recent_runs(since_ms=since_ms, schema_version=schema_version),
            "digest_status_counts": self._digest_status_counts(schema_version=schema_version),
            "digest_reason_counts": self._digest_reason_counts(schema_version=schema_version),
            "pending_digest_count": pending_digest_count,
            "estimated_digest_drain_seconds": _estimate_drain_seconds(
                pending_digest_count,
                per_cycle=self.digest_calls_per_cycle,
                interval_seconds=self.digest_interval_seconds,
            ),
            "epoch": self._epoch_health(now_ms=int(now_ms), schema_version=schema_version),
        }

    def _admission_health(self, *, schema_version: str) -> dict[str, int]:
        row = self.conn.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE status = 'admitted') AS current_admissions,
              COUNT(*) FILTER (WHERE status = 'suppressed') AS suppressed_admissions,
              COALESCE(SUM(source_event_count) FILTER (WHERE status = 'admitted'), 0) AS current_source_events,
              COALESCE(
                SUM(independent_author_count) FILTER (WHERE status = 'admitted'), 0
              ) AS current_independent_authors
            FROM narrative_admissions
            WHERE schema_version = %s
              AND "window" = ANY(%s)
              AND scope = ANY(%s)
            """,
            (schema_version, list(self.realtime_windows), list(self.realtime_scopes)),
        ).fetchone()
        data = _row(row)
        return {
            "current_admissions": _int(data.get("current_admissions")),
            "suppressed_admissions": _int(data.get("suppressed_admissions")),
            "current_source_events": _int(data.get("current_source_events")),
            "current_independent_authors": _int(data.get("current_independent_authors")),
        }

    def _semantic_backlog(self, *, now_ms: int, schema_version: str) -> dict[str, int | None]:
        row = self.conn.execute(
            """
            WITH current_admissions AS (
              SELECT
                admission_id,
                target_type,
                target_id,
                "window",
                scope,
                schema_version,
                source_fingerprint,
                source_event_ids_json
              FROM narrative_admissions
              WHERE schema_version = %s
                AND status = 'admitted'
                AND "window" = ANY(%s)
                AND scope = ANY(%s)
            ),
            current_sources AS (
              SELECT
                admissions.admission_id,
                admissions.target_type,
                admissions.target_id,
                admissions."window",
                admissions.scope,
                admissions.schema_version,
                source_event.event_id
              FROM current_admissions AS admissions
              CROSS JOIN LATERAL jsonb_array_elements_text(
                COALESCE(admissions.source_event_ids_json, '[]'::jsonb)
              ) AS source_event(event_id)
            ),
            source_semantic_coverage AS (
              SELECT
                current_sources.admission_id,
                EXISTS (
                  SELECT 1
                  FROM token_mention_semantics AS semantics
                  WHERE semantics.event_id = current_sources.event_id
                    AND semantics.target_type = current_sources.target_type
                    AND semantics.target_id = current_sources.target_id
                    AND semantics.schema_version = current_sources.schema_version
                ) AS has_semantics
              FROM current_sources
            ),
            existing_semantics AS (
              SELECT status, queued_at_ms, source_received_at_ms, next_retry_at_ms
              FROM token_mention_semantics
              WHERE schema_version = %s
                AND EXISTS (
                  SELECT 1
                  FROM current_sources
                  WHERE current_sources.event_id = token_mention_semantics.event_id
                    AND current_sources.target_type = token_mention_semantics.target_type
                    AND current_sources.target_id = token_mention_semantics.target_id
                    AND current_sources.schema_version = token_mention_semantics.schema_version
                )
            ),
            current_digests AS (
              SELECT
                target_type,
                target_id,
                "window",
                scope,
                schema_version,
                source_fingerprint
              FROM token_discussion_digests
              WHERE schema_version = %s
                AND is_current = true
                AND "window" = ANY(%s)
                AND scope = ANY(%s)
            )
            SELECT
              (SELECT COUNT(*) FROM current_sources) AS current_source_rows,
              (
                SELECT COUNT(*)
                FROM source_semantic_coverage
                WHERE has_semantics
              ) AS semantic_rows_for_current_sources,
              (
                SELECT COUNT(*)
                FROM source_semantic_coverage
                WHERE NOT has_semantics
              ) AS missing_semantic_rows,
              (
                SELECT COUNT(DISTINCT admission_id)
                FROM source_semantic_coverage
                WHERE NOT has_semantics
              ) AS admissions_with_missing_semantics,
              (
                SELECT COUNT(*)
                FROM existing_semantics
                WHERE status = 'queued'
              ) AS queued,
              (
                SELECT COUNT(*)
                FROM existing_semantics
                WHERE status = 'retryable_error'
              ) AS retryable,
              (
                SELECT COUNT(*)
                FROM existing_semantics
                WHERE status = 'stale'
              ) AS stale,
              (
                SELECT COUNT(*)
                FROM existing_semantics
                WHERE status = 'semantic_unavailable'
              ) AS unavailable,
              (
                SELECT MIN(
                  CASE
                    WHEN status = 'queued' AND next_retry_at_ms <= %s THEN
                      COALESCE(NULLIF(queued_at_ms, 0), source_received_at_ms, next_retry_at_ms)
                    WHEN status IN ('retryable_error', 'stale') AND next_retry_at_ms <= %s THEN
                      next_retry_at_ms
                    ELSE NULL
                  END
                )
                FROM existing_semantics
              ) AS oldest_due_at_ms,
              (
                SELECT COUNT(*)
                FROM current_digests AS digest
                WHERE EXISTS (
                  SELECT 1
                  FROM narrative_admissions AS admissions
                  WHERE admissions.target_type = digest.target_type
                    AND admissions.target_id = digest.target_id
                    AND admissions."window" = digest."window"
                    AND admissions.scope = digest.scope
                    AND admissions.schema_version = digest.schema_version
                    AND admissions.status = 'suppressed'
                )
              ) AS suppressed_current_digest_count,
              (
                SELECT COUNT(*)
                FROM current_digests AS digest
                WHERE EXISTS (
                  SELECT 1
                  FROM narrative_admissions AS admissions
                  WHERE admissions.target_type = digest.target_type
                    AND admissions.target_id = digest.target_id
                    AND admissions."window" = digest."window"
                    AND admissions.scope = digest.scope
                    AND admissions.schema_version = digest.schema_version
                    AND admissions.status = 'admitted'
                    AND COALESCE(admissions.source_fingerprint, '') <>
                        COALESCE(digest.source_fingerprint, '')
                )
              ) AS stale_fingerprint_current_digest_count
            """,
            (
                schema_version,
                list(self.realtime_windows),
                list(self.realtime_scopes),
                schema_version,
                schema_version,
                list(self.realtime_windows),
                list(self.realtime_scopes),
                int(now_ms),
                int(now_ms),
            ),
        ).fetchone()
        data = _row(row)
        current_source_rows = _int(data.get("current_source_rows"))
        semantic_rows_for_current_sources = _int(data.get("semantic_rows_for_current_sources"))
        missing_semantic_rows = _int(data.get("missing_semantic_rows"))
        admissions_with_missing_semantics = _int(data.get("admissions_with_missing_semantics"))
        queued = _int(data.get("queued"))
        retryable = _int(data.get("retryable"))
        stale = _int(data.get("stale"))
        pending_existing_rows = queued + retryable + stale
        oldest_due_at_ms = data.get("oldest_due_at_ms")
        oldest_due_age_ms = None
        if oldest_due_at_ms is not None:
            oldest_due_age_ms = max(0, int(now_ms) - int(oldest_due_at_ms))
        return {
            "total_pending": missing_semantic_rows + pending_existing_rows,
            "current_source_rows": current_source_rows,
            "semantic_rows_for_current_sources": semantic_rows_for_current_sources,
            "missing_semantic_rows": missing_semantic_rows,
            "admissions_with_missing_semantics": admissions_with_missing_semantics,
            "pending_existing_rows": pending_existing_rows,
            "queued": queued,
            "retryable": retryable,
            "stale": stale,
            "unavailable": _int(data.get("unavailable")),
            "suppressed_current_digest_count": _int(data.get("suppressed_current_digest_count")),
            "stale_fingerprint_current_digest_count": _int(data.get("stale_fingerprint_current_digest_count")),
            "oldest_due_age_ms": oldest_due_age_ms,
            "estimated_semantic_drain_seconds": _estimate_drain_seconds(
                missing_semantic_rows + pending_existing_rows,
                per_cycle=self.semantics_rows_per_cycle,
                interval_seconds=self.semantics_interval_seconds,
            ),
        }

    def _recent_runs(self, *, since_ms: int, schema_version: str) -> dict[str, dict[str, int]]:
        rows = self.conn.execute(
            """
            SELECT
              stage,
              COUNT(*) FILTER (WHERE status = 'done') AS success,
              COUNT(*) FILTER (WHERE status = 'failed') AS failure,
              COUNT(*) FILTER (
                WHERE status = 'failed'
                  AND (
                    COALESCE(error, '') ILIKE '%%timeout%%'
                    OR COALESCE(trace_metadata_json->>'error_type', '') ILIKE '%%timeout%%'
                  )
              ) AS timeout
            FROM narrative_model_runs
            WHERE schema_version = %s
              AND finished_at_ms >= %s
              AND (stage <> 'discussion_digest' OR ("window" = ANY(%s) AND scope = ANY(%s)))
            GROUP BY stage
            """,
            (schema_version, int(since_ms), list(self.realtime_windows), list(self.realtime_scopes)),
        ).fetchall()
        result = {
            "mention_semantics": {"success": 0, "failure": 0, "timeout": 0},
            "discussion_digest": {"success": 0, "failure": 0, "timeout": 0},
        }
        for row in rows:
            data = _row(row)
            stage = str(data.get("stage") or "")
            if stage not in result:
                continue
            result[stage] = {
                "success": _int(data.get("success")),
                "failure": _int(data.get("failure")),
                "timeout": _int(data.get("timeout")),
            }
        return result

    def _pending_digest_count(self, *, schema_version: str) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS pending_digest_count
            FROM token_discussion_digests
            WHERE schema_version = %s
              AND is_current = true
              AND status = 'pending'
              AND "window" = ANY(%s)
              AND scope = ANY(%s)
            """,
            (schema_version, list(self.realtime_windows), list(self.realtime_scopes)),
        ).fetchone()
        return _int(_row(row).get("pending_digest_count"))

    def _digest_status_counts(self, *, schema_version: str) -> dict[str, int]:
        rows = self.conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM token_discussion_digests
            WHERE schema_version = %s
              AND is_current = true
              AND "window" = ANY(%s)
              AND scope = ANY(%s)
            GROUP BY status
            """,
            (schema_version, list(self.realtime_windows), list(self.realtime_scopes)),
        ).fetchall()
        return {str(row["status"]): _int(row.get("count")) for row in rows}

    def _digest_reason_counts(self, *, schema_version: str) -> dict[str, int]:
        rows = self.conn.execute(
            """
            SELECT gap->>'reason' AS reason, COUNT(*) AS count
            FROM token_discussion_digests
            CROSS JOIN LATERAL jsonb_array_elements(data_gaps_json) AS gap
            WHERE schema_version = %s
              AND is_current = true
              AND "window" = ANY(%s)
              AND scope = ANY(%s)
              AND gap->>'reason' IS NOT NULL
            GROUP BY gap->>'reason'
            ORDER BY count DESC, reason ASC
            LIMIT 20
            """,
            (schema_version, list(self.realtime_windows), list(self.realtime_scopes)),
        ).fetchall()
        return {str(row["reason"]): _int(row.get("count")) for row in rows if row.get("reason")}

    def _epoch_health(self, *, now_ms: int, schema_version: str) -> dict[str, Any]:
        row = self.conn.execute(
            """
            WITH admitted AS (
              SELECT *
              FROM narrative_admissions
              WHERE schema_version = %s
                AND status = 'admitted'
                AND "window" = ANY(%s)
                AND scope = ANY(%s)
            ),
            latest_ready AS (
              SELECT DISTINCT ON (
                target_type, target_id, "window", scope, schema_version
              )
                target_type,
                target_id,
                "window",
                scope,
                schema_version,
                source_fingerprint,
                source_event_count,
                independent_author_count,
                computed_at_ms,
                display_current_until_ms,
                refresh_reason
              FROM token_discussion_digests
              WHERE schema_version = %s
                AND status = 'ready'
                AND "window" = ANY(%s)
                AND scope = ANY(%s)
              ORDER BY target_type, target_id, "window", scope, schema_version, computed_at_ms DESC
            ),
            joined AS (
              SELECT
                admitted.target_type,
                admitted.target_id,
                admitted."window",
                admitted.scope,
                admitted.source_fingerprint AS admission_source_fingerprint,
                admitted.source_event_count AS admission_source_event_count,
                admitted.independent_author_count AS admission_independent_author_count,
                admitted.next_digest_due_at_ms,
                ready.source_fingerprint AS ready_source_fingerprint,
                ready.source_event_count AS ready_source_event_count,
                ready.independent_author_count AS ready_independent_author_count,
                ready.computed_at_ms AS ready_computed_at_ms,
                ready.display_current_until_ms AS ready_display_current_until_ms,
                ready.refresh_reason AS ready_refresh_reason
              FROM admitted
              LEFT JOIN latest_ready AS ready
                ON ready.target_type = admitted.target_type
               AND ready.target_id = admitted.target_id
               AND ready."window" = admitted."window"
               AND ready.scope = admitted.scope
               AND ready.schema_version = admitted.schema_version
            )
            SELECT
              %s AS epoch_policy_version,
              COUNT(*) FILTER (WHERE "window" = '5m') AS unsupported_window_admissions,
              (SELECT COUNT(*) FROM latest_ready) AS last_ready_digest_count,
              COUNT(*) FILTER (
                WHERE ready_computed_at_ms IS NOT NULL
                  AND COALESCE(admission_source_fingerprint, '') <> COALESCE(ready_source_fingerprint, '')
              ) AS updating_snapshot_count,
              COUNT(*) FILTER (
                WHERE next_digest_due_at_ms <= %s
                  AND ready_computed_at_ms IS NOT NULL
              ) AS material_delta_due_count,
              COUNT(*) FILTER (
                WHERE next_digest_due_at_ms > %s
                  AND ready_computed_at_ms IS NOT NULL
              ) AS no_material_delta_deferred_count,
              percentile_cont(0.50) WITHIN GROUP (
                ORDER BY GREATEST(0, %s - ready_computed_at_ms)
              ) FILTER (WHERE ready_computed_at_ms IS NOT NULL) AS last_ready_p50_age_ms,
              percentile_cont(0.95) WITHIN GROUP (
                ORDER BY GREATEST(0, %s - ready_computed_at_ms)
              ) FILTER (WHERE ready_computed_at_ms IS NOT NULL) AS last_ready_p95_age_ms,
              COALESCE(
                SUM(
                  GREATEST(
                    COALESCE(admission_source_event_count, 0) - COALESCE(ready_source_event_count, 0),
                    0
                  )
                ),
                0
              ) AS delta_source_rows,
              COALESCE(
                SUM(
                  GREATEST(
                    COALESCE(admission_independent_author_count, 0)
                      - COALESCE(ready_independent_author_count, 0),
                    0
                  )
                ),
                0
              ) AS delta_independent_authors,
              COALESCE(
                (
                  SELECT jsonb_object_agg(due_by_window."window", due_by_window.count)
                  FROM (
                    SELECT "window", COUNT(*) AS count
                    FROM joined
                    WHERE next_digest_due_at_ms <= %s
                    GROUP BY "window"
                  ) AS due_by_window
                ),
                '{}'::jsonb
              ) AS digest_refresh_due_by_window,
              COALESCE(
                (
                  SELECT jsonb_object_agg(reason_counts.refresh_reason, reason_counts.count)
                  FROM (
                    SELECT COALESCE(ready_refresh_reason, 'unknown') AS refresh_reason, COUNT(*) AS count
                    FROM joined
                    WHERE ready_computed_at_ms IS NOT NULL
                      AND next_digest_due_at_ms > %s
                    GROUP BY COALESCE(ready_refresh_reason, 'unknown')
                  ) AS reason_counts
                ),
                '{}'::jsonb
              ) AS digest_refresh_deferred_by_epoch_policy
            FROM joined
            """,
            (
                schema_version,
                list(self.realtime_windows),
                list(self.realtime_scopes),
                schema_version,
                list(self.realtime_windows),
                list(self.realtime_scopes),
                EPOCH_POLICY_VERSION,
                int(now_ms),
                int(now_ms),
                int(now_ms),
                int(now_ms),
                int(now_ms),
                int(now_ms),
            ),
        ).fetchone()
        data = _row(row)
        return {
            "epoch_policy_version": str(data.get("epoch_policy_version") or EPOCH_POLICY_VERSION),
            "unsupported_window_admissions": _int(data.get("unsupported_window_admissions")),
            "last_ready_digest_count": _int(data.get("last_ready_digest_count")),
            "updating_snapshot_count": _int(data.get("updating_snapshot_count")),
            "material_delta_due_count": _int(data.get("material_delta_due_count")),
            "no_material_delta_deferred_count": _int(data.get("no_material_delta_deferred_count")),
            "last_ready_p50_age_ms": _int_or_none(data.get("last_ready_p50_age_ms")),
            "last_ready_p95_age_ms": _int_or_none(data.get("last_ready_p95_age_ms")),
            "delta_source_rows": _int(data.get("delta_source_rows")),
            "delta_independent_authors": _int(data.get("delta_independent_authors")),
            "digest_refresh_due_by_window": _dict_of_ints(data.get("digest_refresh_due_by_window")),
            "digest_refresh_deferred_by_epoch_policy": _dict_of_ints(
                data.get("digest_refresh_deferred_by_epoch_policy")
            ),
        }


def _row(row: Any) -> dict[str, Any]:
    return dict(row or {})


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dict_of_ints(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _int(item) for key, item in value.items()}


def _estimate_drain_seconds(total: int, *, per_cycle: int, interval_seconds: int) -> int:
    if total <= 0:
        return 0
    cycles = (int(total) + int(per_cycle) - 1) // int(per_cycle)
    return cycles * int(interval_seconds)


__all__ = ["NarrativeBacklogHealthQuery"]
