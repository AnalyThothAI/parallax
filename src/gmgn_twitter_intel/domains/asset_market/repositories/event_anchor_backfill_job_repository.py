from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from typing import Any, cast

from gmgn_twitter_intel.domains.asset_market.types import EnrichedEventCapture
from gmgn_twitter_intel.platform.db.queue_terminal import terminalize_source_row

PENDING_CAPTURE_REASON = "pending_backfill"


class EventAnchorBackfillJobRepository:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def enqueue_for_capture(self, capture: EnrichedEventCapture, *, active_window_ms: int) -> None:
        if capture.capture_method != "unavailable" or capture.capture_reason != PENDING_CAPTURE_REASON:
            return
        self._conn.execute(
            """
            INSERT INTO event_anchor_backfill_jobs(
                event_id,
                intent_id,
                resolution_id,
                target_type,
                target_id,
                t_event_ms,
                status,
                next_run_at_ms,
                active_until_ms,
                attempt_count,
                last_reason,
                created_at_ms,
                updated_at_ms
            )
            VALUES (
                %(event_id)s,
                %(intent_id)s,
                %(resolution_id)s,
                %(target_type)s,
                %(target_id)s,
                %(t_event_ms)s,
                %(status)s,
                %(next_run_at_ms)s,
                %(active_until_ms)s,
                0,
                NULL,
                %(created_at_ms)s,
                %(updated_at_ms)s
            )
            ON CONFLICT(event_id, intent_id) DO NOTHING
            """,
            {
                "event_id": capture.event_id,
                "intent_id": capture.intent_id,
                "resolution_id": capture.resolution_id,
                "target_type": capture.target_type,
                "target_id": capture.target_id,
                "t_event_ms": capture.t_event_ms,
                "status": "pending",
                "next_run_at_ms": capture.created_at_ms,
                "active_until_ms": capture.created_at_ms + max(1, int(active_window_ms)),
                "created_at_ms": capture.created_at_ms,
                "updated_at_ms": capture.created_at_ms,
            },
        )

    def list_due(self, *, limit: int, now_ms: int, min_age_ms: int) -> list[dict[str, Any]]:
        return list(
            self._conn.execute(
                """
                SELECT *
                FROM event_anchor_backfill_jobs
                WHERE status = 'pending'
                  AND next_run_at_ms <= %(now_ms)s
                  AND created_at_ms <= %(ready_before_ms)s
                  AND active_until_ms >= %(now_ms)s
                ORDER BY next_run_at_ms ASC, created_at_ms ASC, event_id ASC, intent_id ASC
                LIMIT %(limit)s
                """,
                {
                    "now_ms": int(now_ms),
                    "ready_before_ms": int(now_ms) - int(min_age_ms),
                    "limit": max(1, int(limit)),
                },
            ).fetchall()
        )

    def list_expired(self, *, limit: int, now_ms: int) -> list[dict[str, Any]]:
        return list(
            self._conn.execute(
                """
                SELECT *
                FROM event_anchor_backfill_jobs
                WHERE status = 'pending'
                  AND active_until_ms < %(now_ms)s
                ORDER BY active_until_ms ASC, created_at_ms ASC, event_id ASC, intent_id ASC
                LIMIT %(limit)s
                """,
                {"now_ms": int(now_ms), "limit": max(1, int(limit))},
            ).fetchall()
        )

    def mark_done(self, *, event_id: str, intent_id: str, now_ms: int) -> bool:
        cursor = self._conn.execute(
            """
            UPDATE event_anchor_backfill_jobs
            SET status = 'done',
                updated_at_ms = %(now_ms)s
            WHERE event_id = %(event_id)s
              AND intent_id = %(intent_id)s
              AND status = 'pending'
            """,
            {"event_id": event_id, "intent_id": intent_id, "now_ms": int(now_ms)},
        )
        return int(getattr(cursor, "rowcount", 0) or 0) == 1

    def mark_terminal(self, *, event_id: str, intent_id: str, status: str, reason: str, now_ms: int) -> bool:
        if status not in {"expired", "failed"}:
            raise ValueError("terminal event-anchor job status must be expired or failed")
        with _transaction(self._conn):
            row = self._conn.execute(
                """
                UPDATE event_anchor_backfill_jobs
                SET status = %(status)s,
                    last_reason = %(reason)s,
                    updated_at_ms = %(now_ms)s
                WHERE event_id = %(event_id)s
                  AND intent_id = %(intent_id)s
                  AND status = 'pending'
                RETURNING *
                """,
                {
                    "event_id": event_id,
                    "intent_id": intent_id,
                    "status": status,
                    "reason": reason,
                    "now_ms": int(now_ms),
                },
            ).fetchone()
            if row is None:
                return False
            source_row = dict(row)
            terminalize_source_row(
                self._conn,
                worker_name="event_anchor_backfill",
                source_table="event_anchor_backfill_jobs",
                target_key=f"{event_id}:{intent_id}",
                source_row=source_row,
                final_status=status,
                final_reason=reason,
                now_ms=now_ms,
                attempt_count=int(source_row.get("attempt_count") or 0),
                first_seen_at_ms=_optional_int(source_row.get("created_at_ms")),
                last_attempted_at_ms=now_ms,
                commit=False,
            )
        return True

    def retry_terminal_job_from_snapshot(
        self,
        source_row: dict[str, Any],
        *,
        now_ms: int,
        reason: str,
    ) -> dict[str, Any] | None:
        event_id = str(source_row.get("event_id") or "")
        intent_id = str(source_row.get("intent_id") or "")
        if not event_id or not intent_id:
            raise ValueError("event_anchor_terminal_source_required")
        row = self._conn.execute(
            """
            UPDATE event_anchor_backfill_jobs
            SET status = 'pending',
                attempt_count = 0,
                last_reason = %(reason)s,
                next_run_at_ms = %(now_ms)s,
                active_until_ms = GREATEST(active_until_ms, %(now_ms)s),
                updated_at_ms = %(now_ms)s
            WHERE event_id = %(event_id)s
              AND intent_id = %(intent_id)s
              AND status IN ('failed', 'expired')
            RETURNING *
            """,
            {
                "event_id": event_id,
                "intent_id": intent_id,
                "reason": f"terminal_retry:{reason}"[:1000],
                "now_ms": int(now_ms),
            },
        ).fetchone()
        return dict(row) if row is not None else None

    def reconcile_ready_historical_jobs(
        self,
        *,
        limit: int,
        now_ms: int,
        execute: bool,
    ) -> dict[str, Any]:
        parsed_limit = max(1, int(limit))
        explain = [
            _explain_text(row)
            for row in self._conn.execute(
                """
                EXPLAIN (FORMAT TEXT)
                SELECT job.event_id, job.intent_id
                FROM event_anchor_backfill_jobs job
                JOIN enriched_events anchor
                  ON anchor.event_id = job.event_id
                 AND anchor.intent_id = job.intent_id
                WHERE job.status = 'pending'
                  AND anchor.capture_method <> 'unavailable'
                  AND anchor.tick_id IS NOT NULL
                  AND anchor.tick_lag_ms IS NOT NULL
                ORDER BY job.created_at_ms ASC, job.event_id ASC, job.intent_id ASC
                LIMIT %(limit)s
                """,
                {"limit": parsed_limit},
            ).fetchall()
        ]
        candidates_before = self._ready_historical_job_count(limit=parsed_limit)
        updated_rows: list[dict[str, Any]] = []
        if execute and candidates_before:
            updated_rows = [
                dict(row)
                for row in self._conn.execute(
                    """
                    WITH ready AS (
                      SELECT job.event_id, job.intent_id
                      FROM event_anchor_backfill_jobs job
                      JOIN enriched_events anchor
                        ON anchor.event_id = job.event_id
                       AND anchor.intent_id = job.intent_id
                      WHERE job.status = 'pending'
                        AND anchor.capture_method <> 'unavailable'
                        AND anchor.tick_id IS NOT NULL
                        AND anchor.tick_lag_ms IS NOT NULL
                      ORDER BY job.created_at_ms ASC, job.event_id ASC, job.intent_id ASC
                      LIMIT %(limit)s
                    )
                    UPDATE event_anchor_backfill_jobs job
                    SET status = 'done',
                        last_reason = 'historical_ready_reconcile',
                        updated_at_ms = %(now_ms)s
                    FROM ready
                    WHERE job.event_id = ready.event_id
                      AND job.intent_id = ready.intent_id
                    RETURNING job.event_id, job.intent_id
                    """,
                    {"limit": parsed_limit, "now_ms": int(now_ms)},
                ).fetchall()
            ]
        remaining = self._ready_historical_job_count(limit=parsed_limit)
        return {
            "mode": "execute" if execute else "dry_run",
            "execute": bool(execute),
            "limit": parsed_limit,
            "ready_pending_count": candidates_before,
            "updated_count": len(updated_rows),
            "remaining_ready_pending_count": remaining,
            "explain": explain,
            "updated": updated_rows[:20],
        }

    def _ready_historical_job_count(self, *, limit: int) -> int:
        row = self._conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM (
              SELECT 1
              FROM event_anchor_backfill_jobs job
              JOIN enriched_events anchor
                ON anchor.event_id = job.event_id
               AND anchor.intent_id = job.intent_id
              WHERE job.status = 'pending'
                AND anchor.capture_method <> 'unavailable'
                AND anchor.tick_id IS NOT NULL
                AND anchor.tick_lag_ms IS NOT NULL
              LIMIT %(limit)s
            ) ready
            """,
            {"limit": max(1, int(limit))},
        ).fetchone()
        return int((row or {}).get("count") or 0)

    def reschedule(
        self,
        *,
        event_id: str,
        intent_id: str,
        reason: str,
        now_ms: int,
        next_run_at_ms: int,
    ) -> bool:
        cursor = self._conn.execute(
            """
            UPDATE event_anchor_backfill_jobs
            SET status = 'pending',
                attempt_count = attempt_count + 1,
                last_reason = %(reason)s,
                next_run_at_ms = %(next_run_at_ms)s,
                updated_at_ms = %(now_ms)s
            WHERE event_id = %(event_id)s
              AND intent_id = %(intent_id)s
              AND status = 'pending'
            """,
            {
                "event_id": event_id,
                "intent_id": intent_id,
                "reason": reason,
                "now_ms": int(now_ms),
                "next_run_at_ms": int(next_run_at_ms),
            },
        )
        return int(getattr(cursor, "rowcount", 0) or 0) == 1


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    transaction = getattr(conn, "transaction", None)
    if callable(transaction):
        return cast(AbstractContextManager[Any], transaction())
    return nullcontext()


def _explain_text(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("QUERY PLAN") or row.get("QUERY_PLAN") or next(iter(row.values()), ""))
    try:
        return str(row[0])
    except Exception:
        return str(row)
