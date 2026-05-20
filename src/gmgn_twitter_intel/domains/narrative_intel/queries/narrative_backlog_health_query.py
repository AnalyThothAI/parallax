from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION

_HOUR_MS = 60 * 60 * 1000


class NarrativeBacklogHealthQuery:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

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
        return {
            "schema_version": schema_version,
            "now_ms": int(now_ms),
            "since_hours": since_hours,
            "admissions": self._admission_health(schema_version=schema_version),
            "semantic_backlog": backlog,
            "recent_runs": self._recent_runs(since_ms=since_ms, schema_version=schema_version),
            "digest_status_counts": self._digest_status_counts(schema_version=schema_version),
            "digest_reason_counts": self._digest_reason_counts(schema_version=schema_version),
            "pending_digest_count": self._pending_digest_count(schema_version=schema_version),
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
            """,
            (schema_version,),
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
            (schema_version, schema_version, schema_version, int(now_ms), int(now_ms)),
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
            GROUP BY stage
            """,
            (schema_version, int(since_ms)),
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
            """,
            (schema_version,),
        ).fetchone()
        return _int(_row(row).get("pending_digest_count"))

    def _digest_status_counts(self, *, schema_version: str) -> dict[str, int]:
        rows = self.conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM token_discussion_digests
            WHERE schema_version = %s
              AND is_current = true
            GROUP BY status
            """,
            (schema_version,),
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
              AND gap->>'reason' IS NOT NULL
            GROUP BY gap->>'reason'
            ORDER BY count DESC, reason ASC
            LIMIT 20
            """,
            (schema_version,),
        ).fetchall()
        return {str(row["reason"]): _int(row.get("count")) for row in rows if row.get("reason")}


def _row(row: Any) -> dict[str, Any]:
    return dict(row or {})


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


__all__ = ["NarrativeBacklogHealthQuery"]
