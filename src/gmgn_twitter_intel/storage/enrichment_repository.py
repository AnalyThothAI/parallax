from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from psycopg.types.json import Jsonb

from ..pipeline.social_event_extraction import SocialEventExtraction
from .postgres_client import transaction

RUNNING_TIMEOUT_MS = 120_000
WATCHED_SOCIAL_EVENT_JOB_TYPE = "watched_social_event_extraction"


class EnrichmentRepository:
    def __init__(self, conn: Any, *, running_timeout_ms: int = RUNNING_TIMEOUT_MS):
        self.conn = conn
        self.running_timeout_ms = running_timeout_ms

    def enqueue_watched_event(
        self,
        *,
        event_id: str,
        received_at_ms: int,
        priority: int = 100,
        commit: bool = True,
    ) -> str | None:
        job_id = _id("job", event_id, WATCHED_SOCIAL_EVENT_JOB_TYPE)
        now_ms = _now_ms()
        cursor = self.conn.execute(
            """
            INSERT INTO enrichment_jobs(
              job_id, event_id, job_type, priority, status, attempt_count, max_attempts,
              next_run_at_ms, last_error, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(event_id, job_type) DO NOTHING
            """,
            (
                job_id,
                event_id,
                WATCHED_SOCIAL_EVENT_JOB_TYPE,
                priority,
                "pending",
                0,
                3,
                int(received_at_ms),
                None,
                now_ms,
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()
        if cursor.rowcount == 0:
            return self._job_id_for_event(event_id, WATCHED_SOCIAL_EVENT_JOB_TYPE)
        return job_id

    def claim_next_job(self, *, now_ms: int | None = None) -> dict[str, Any] | None:
        now = now_ms if now_ms is not None else _now_ms()
        stale_before = now - self.running_timeout_ms
        self.conn.execute(
            """
            UPDATE enrichment_jobs
            SET status = 'dead',
                last_error = 'stale_running_timeout',
                updated_at_ms = %s
            WHERE status = 'running'
              AND updated_at_ms < %s
              AND attempt_count >= max_attempts
            """,
            (now, stale_before),
        )
        row = self.conn.execute(
            """
            WITH picked AS (
              SELECT job_id, status AS picked_status
              FROM enrichment_jobs
              WHERE (
                status IN ('pending', 'failed')
                AND attempt_count < max_attempts
                AND next_run_at_ms <= %s
              )
              OR (
                status = 'running'
                AND updated_at_ms < %s
                AND attempt_count < max_attempts
              )
              ORDER BY priority DESC, next_run_at_ms ASC, created_at_ms ASC, job_id ASC
              LIMIT 1
              FOR UPDATE SKIP LOCKED
            )
            UPDATE enrichment_jobs AS job
            SET status = 'running',
                attempt_count = job.attempt_count + 1,
                updated_at_ms = %s,
                last_error = NULL
            FROM picked
            WHERE job.job_id = picked.job_id
              AND (
                (
                  job.status IN ('pending', 'failed')
                  AND job.attempt_count < job.max_attempts
                  AND job.next_run_at_ms <= %s
                )
                OR (
                  job.status = 'running'
                  AND job.updated_at_ms < %s
                  AND job.attempt_count < job.max_attempts
                )
              )
            RETURNING job.*
            """,
            (now, stale_before, now, now, stale_before),
        ).fetchone()
        return dict(row) if row else None

    def complete_social_event_job(
        self,
        *,
        job: dict[str, Any],
        result: SocialEventExtraction,
        provider: str,
        model: str,
        request: dict[str, Any],
        commit: bool = True,
    ) -> dict[str, Any]:
        now_ms = _now_ms()
        run_id = _id("run", str(job["job_id"]), str(now_ms))

        def write() -> None:
            self.conn.execute(
                """
                INSERT INTO model_runs(
                  run_id, job_id, event_id, provider, model, status, request_json,
                  response_json, error, started_at_ms, finished_at_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id,
                    job["job_id"],
                    job["event_id"],
                    provider,
                    model,
                    "done",
                    _json(request),
                    _json(result.raw_response),
                    None,
                    now_ms,
                    now_ms,
                ),
            )
            self.conn.execute(
                """
                UPDATE enrichment_jobs
                SET status = 'done', updated_at_ms = %s, last_error = NULL
                WHERE job_id = %s
                """,
                (now_ms, job["job_id"]),
            )

        if commit:
            with transaction(self.conn):
                write()
        else:
            write()
        row = self.conn.execute("SELECT * FROM model_runs WHERE run_id = %s", (run_id,)).fetchone()
        return dict(row) if row else {"run_id": run_id}

    def fail_job(self, *, job: dict[str, Any], error: str) -> None:
        now_ms = _now_ms()
        attempts = int(job.get("attempt_count") or 0)
        max_attempts = int(job.get("max_attempts") or 3)
        status = "dead" if attempts >= max_attempts else "failed"
        delay_ms = min(300_000, 5_000 * max(1, attempts))
        self.conn.execute(
            """
            UPDATE enrichment_jobs
            SET status = %s, last_error = %s, next_run_at_ms = %s, updated_at_ms = %s
            WHERE job_id = %s
            """,
            (status, error[:1000], now_ms + delay_ms, now_ms, job["job_id"]),
        )
        self.conn.commit()

    def list_jobs(self, *, limit: int, status: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = %s")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT * FROM enrichment_jobs
            {where}
            ORDER BY priority DESC, next_run_at_ms ASC, created_at_ms ASC
            LIMIT %s
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def job_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS count FROM enrichment_jobs GROUP BY status"
        ).fetchall()
        counts = {str(row["status"]): int(row["count"]) for row in rows}
        for status in ("pending", "running", "failed", "dead", "done"):
            counts.setdefault(status, 0)
        return counts

    def job_success_rate(self) -> float | None:
        counts = self.job_counts()
        terminal = counts["done"] + counts["dead"]
        return None if terminal == 0 else counts["done"] / terminal

    def enqueue_missing_watched_events(self, *, limit: int) -> dict[str, Any]:
        rows = self.conn.execute(
            """
            SELECT e.event_id, e.received_at_ms
            FROM events e
            WHERE e.is_watched = true
              AND COALESCE(NULLIF(e.search_text, ''), NULLIF(e.text_clean, ''), NULLIF(e.text, '')) IS NOT NULL
              AND NOT EXISTS (
                SELECT 1
                FROM enrichment_jobs j
                WHERE j.event_id = e.event_id
                  AND j.job_type = %s
              )
              AND NOT EXISTS (
                SELECT 1
                FROM social_event_extractions se
                WHERE se.event_id = e.event_id
              )
            ORDER BY e.received_at_ms ASC
            LIMIT %s
            """,
            (WATCHED_SOCIAL_EVENT_JOB_TYPE, max(0, int(limit))),
        ).fetchall()
        enqueued = 0
        with transaction(self.conn):
            for row in rows:
                job_id = self.enqueue_watched_event(
                    event_id=str(row["event_id"]),
                    received_at_ms=int(row["received_at_ms"]),
                    commit=False,
                )
                if job_id is not None:
                    enqueued += 1
        return {
            "watched_events_scanned": len(rows),
            "jobs_enqueued": enqueued,
            "counts": self.job_counts(),
        }

    def _job_id_for_event(self, event_id: str, job_type: str) -> str | None:
        row = self.conn.execute(
            "SELECT job_id FROM enrichment_jobs WHERE event_id = %s AND job_type = %s",
            (event_id, job_type),
        ).fetchone()
        return str(row["job_id"]) if row else None


def _json(value: Any) -> Jsonb:
    return Jsonb(value, dumps=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)
