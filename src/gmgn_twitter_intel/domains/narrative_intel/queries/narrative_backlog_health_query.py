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
            SELECT
              COUNT(*) FILTER (WHERE status = 'queued') AS queued,
              COUNT(*) FILTER (WHERE status = 'retryable_error') AS retryable,
              COUNT(*) FILTER (WHERE status = 'stale') AS stale,
              COUNT(*) FILTER (WHERE status = 'semantic_unavailable') AS unavailable,
              MIN(next_retry_at_ms) FILTER (
                WHERE status IN ('queued', 'retryable_error', 'stale')
                  AND next_retry_at_ms <= %s
              ) AS oldest_due_at_ms
            FROM token_mention_semantics
            WHERE schema_version = %s
            """,
            (int(now_ms), schema_version),
        ).fetchone()
        data = _row(row)
        queued = _int(data.get("queued"))
        retryable = _int(data.get("retryable"))
        stale = _int(data.get("stale"))
        oldest_due_at_ms = data.get("oldest_due_at_ms")
        oldest_due_age_ms = None
        if oldest_due_at_ms is not None:
            oldest_due_age_ms = max(0, int(now_ms) - int(oldest_due_at_ms))
        return {
            "total_pending": queued + retryable + stale,
            "queued": queued,
            "retryable": retryable,
            "stale": stale,
            "unavailable": _int(data.get("unavailable")),
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
