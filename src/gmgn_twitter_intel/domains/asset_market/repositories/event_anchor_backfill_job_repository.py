from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.asset_market.types import EnrichedEventCapture

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

    def mark_ready_jobs_done(self, *, limit: int, now_ms: int) -> int:
        cursor = self._conn.execute(
            """
            WITH ready_jobs AS (
              SELECT jobs.event_id, jobs.intent_id
              FROM event_anchor_backfill_jobs jobs
              JOIN enriched_events anchors
                ON anchors.event_id = jobs.event_id
               AND anchors.intent_id = jobs.intent_id
              WHERE jobs.status <> 'done'
                AND anchors.capture_method <> 'unavailable'
                AND anchors.tick_id IS NOT NULL
                AND anchors.tick_lag_ms IS NOT NULL
              ORDER BY jobs.created_at_ms ASC, jobs.event_id ASC, jobs.intent_id ASC
              LIMIT %(limit)s
            )
            UPDATE event_anchor_backfill_jobs jobs
            SET status = 'done',
                updated_at_ms = %(now_ms)s
            FROM ready_jobs
            WHERE jobs.event_id = ready_jobs.event_id
              AND jobs.intent_id = ready_jobs.intent_id
            """,
            {"limit": max(1, int(limit)), "now_ms": int(now_ms)},
        )
        return int(getattr(cursor, "rowcount", 0) or 0)

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
        cursor = self._conn.execute(
            """
            UPDATE event_anchor_backfill_jobs
            SET status = %(status)s,
                last_reason = %(reason)s,
                updated_at_ms = %(now_ms)s
            WHERE event_id = %(event_id)s
              AND intent_id = %(intent_id)s
              AND status = 'pending'
            """,
            {
                "event_id": event_id,
                "intent_id": intent_id,
                "status": status,
                "reason": reason,
                "now_ms": int(now_ms),
            },
        )
        return int(getattr(cursor, "rowcount", 0) or 0) == 1

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
