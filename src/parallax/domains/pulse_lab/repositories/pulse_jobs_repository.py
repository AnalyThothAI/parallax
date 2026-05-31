from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from typing import Any, cast

from parallax.domains.pulse_lab.repositories._pulse_repository_shared import (
    _id,
    _json,
    _normalize_subject,
    _now_ms,
    _optional_row,
    _row,
)
from parallax.platform.db.queue_terminal import terminalize_source_row

ACTIVE_JOB_STATUSES = ("pending", "failed", "running")


class PulseJobsRepository:
    def __init__(self, conn: Any, *, running_timeout_ms: int = 300_000):
        self.conn = conn
        self.running_timeout_ms = int(running_timeout_ms)

    def enqueue_job(
        self,
        *,
        candidate_id: str,
        candidate_type: str,
        subject_key: str,
        window: str,
        scope: str,
        trigger_signature: str,
        timeline_signature: str,
        priority: int,
        job_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        context_json: dict[str, Any] | None = None,
        status: str = "pending",
        attempt_count: int = 0,
        max_attempts: int = 3,
        next_run_at_ms: int | None = None,
        last_error: str | None = None,
        now_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        now = int(now_ms if now_ms is not None else _now_ms())
        run_at = int(next_run_at_ms if next_run_at_ms is not None else now)
        resolved_job_id = job_id or _id("pulse-job", candidate_id, trigger_signature, timeline_signature)
        row = self.conn.execute(
            """
            INSERT INTO pulse_agent_jobs(
              job_id, candidate_id, candidate_type, subject_key, target_type, target_id,
              "window", scope, trigger_signature, timeline_signature, context_json, priority, status,
              attempt_count, max_attempts, next_run_at_ms, last_error,
              created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(candidate_id) DO UPDATE SET
              candidate_type = excluded.candidate_type,
              subject_key = excluded.subject_key,
              target_type = excluded.target_type,
              target_id = excluded.target_id,
              "window" = excluded."window",
              scope = excluded.scope,
              trigger_signature = CASE
                WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
                 AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
                THEN pulse_agent_jobs.trigger_signature
                ELSE excluded.trigger_signature
              END,
              timeline_signature = CASE
                WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
                 AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
                THEN pulse_agent_jobs.timeline_signature
                ELSE excluded.timeline_signature
              END,
              context_json = CASE
                WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
                 AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
                THEN pulse_agent_jobs.context_json
                ELSE excluded.context_json
              END,
              priority = GREATEST(pulse_agent_jobs.priority, excluded.priority),
              status = CASE
                WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
                 AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
                THEN pulse_agent_jobs.status
                ELSE excluded.status
              END,
              attempt_count = CASE
                WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
                 AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
                THEN pulse_agent_jobs.attempt_count
                ELSE excluded.attempt_count
              END,
              max_attempts = excluded.max_attempts,
              next_run_at_ms = CASE
                WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
                 AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
                THEN pulse_agent_jobs.next_run_at_ms
                ELSE excluded.next_run_at_ms
              END,
              last_error = CASE
                WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
                 AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
                THEN pulse_agent_jobs.last_error
                ELSE excluded.last_error
              END,
              updated_at_ms = excluded.updated_at_ms
            RETURNING *
            """,
            (
                resolved_job_id,
                candidate_id,
                candidate_type,
                _normalize_subject(subject_key),
                target_type,
                target_id,
                window,
                scope,
                trigger_signature,
                timeline_signature,
                _json(context_json or {}),
                int(priority),
                status,
                int(attempt_count),
                max(1, int(max_attempts)),
                run_at,
                last_error,
                now,
                now,
            ),
        ).fetchone()
        if commit and not callable(getattr(self.conn, "transaction", None)):
            self.conn.commit()
        return _row(row)

    def claim_due_job(self, now_ms: int | None = None) -> dict[str, Any] | None:
        now = int(now_ms if now_ms is not None else _now_ms())
        stale_before = now - self.running_timeout_ms
        row = self.conn.execute(
            """
            WITH picked AS (
              SELECT job_id
              FROM pulse_agent_jobs
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
            UPDATE pulse_agent_jobs AS job
            SET status = 'running',
                attempt_count = job.attempt_count + 1,
                last_error = NULL,
                updated_at_ms = %s
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
        return _optional_row(row)

    def terminalize_exhausted_stale_running_jobs(
        self,
        *,
        now_ms: int,
        stale_after_ms: int,
        limit: int = 100,
        commit: bool = True,
    ) -> int:
        now = int(now_ms)
        stale_before_ms = now - max(0, int(stale_after_ms))
        bounded_limit = max(1, min(500, int(limit)))
        with _transaction(self.conn):
            rows = self.conn.execute(
                """
                WITH candidates AS (
                  SELECT job_id
                  FROM pulse_agent_jobs
                  WHERE status = 'running'
                    AND attempt_count >= max_attempts
                    AND updated_at_ms < %s
                  ORDER BY updated_at_ms ASC, job_id ASC
                  LIMIT %s
                  FOR UPDATE SKIP LOCKED
                )
                UPDATE pulse_agent_jobs AS job
                SET status = 'dead',
                    last_error = 'stale_running_timeout',
                    updated_at_ms = %s
                FROM candidates
                WHERE job.job_id = candidates.job_id
                RETURNING job.*
                """,
                (stale_before_ms, bounded_limit, now),
            ).fetchall()
            for row in rows:
                _terminalize_pulse_job(
                    self.conn,
                    row=_row(row),
                    reason="stale_running_timeout",
                    final_reason_bucket="stale_window_ttl",
                    now_ms=now,
                )
        if commit and not callable(getattr(self.conn, "transaction", None)):
            self.conn.commit()
        return len(rows)

    def mark_job_succeeded(
        self,
        job_id: str,
        now_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        now = int(now_ms if now_ms is not None else _now_ms())
        row = self.conn.execute(
            """
            UPDATE pulse_agent_jobs
            SET status = 'done',
                last_error = NULL,
                updated_at_ms = %s
            WHERE job_id = %s
            RETURNING *
            """,
            (now, job_id),
        ).fetchone()
        if commit:
            self.conn.commit()
        return _optional_row(row)

    def mark_job_failed(
        self,
        job: dict[str, Any],
        error: str,
        now_ms: int | None = None,
        *,
        failure_reason: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        if job is None:
            return None
        now = int(now_ms if now_ms is not None else _now_ms())
        attempts = int(job.get("attempt_count") or 0)
        max_attempts = int(job.get("max_attempts") or 3)
        status = "dead" if attempts >= max_attempts else "failed"
        delay_ms = 0 if status == "dead" else min(300_000, 5_000 * max(1, attempts))
        stored_error = str(failure_reason or error)[:1000]
        with _transaction(self.conn):
            row = self.conn.execute(
                """
                UPDATE pulse_agent_jobs
                SET status = %s,
                    next_run_at_ms = %s,
                    last_error = %s,
                    updated_at_ms = %s
                WHERE job_id = %s
                RETURNING *
                """,
                (status, now + delay_ms, stored_error, now, job["job_id"]),
            ).fetchone()
            updated = _optional_row(row)
            if updated is not None and str(updated.get("status") or "") == "dead":
                _terminalize_pulse_job(
                    self.conn,
                    row=updated,
                    reason=stored_error,
                    now_ms=now,
                )
        if commit:
            self.conn.commit()
        return updated

    def retry_terminal_job_from_snapshot(
        self,
        source_row: dict[str, Any],
        *,
        now_ms: int,
        reason: str,
    ) -> dict[str, Any] | None:
        job_id = str(source_row.get("job_id") or "")
        if not job_id:
            raise ValueError("pulse_terminal_job_id_required")
        row = self.conn.execute(
            """
            UPDATE pulse_agent_jobs
            SET status = 'pending',
                attempt_count = 0,
                next_run_at_ms = %s,
                last_error = %s,
                updated_at_ms = %s
            WHERE job_id = %s
              AND status = 'dead'
            RETURNING *
            """,
            (int(now_ms), f"terminal_retry:{reason}"[:1000], int(now_ms), job_id),
        ).fetchone()
        return _optional_row(row)

    def mark_job_cancelled_by_worker_timeout(
        self,
        job: dict[str, Any],
        *,
        now_ms: int,
        execution_started: bool,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        if job is None:
            return None
        now = int(now_ms)
        claim_attempt_count = int(job.get("attempt_count") or 0)
        claim_updated_at_ms = int(job.get("updated_at_ms") or 0)
        with _transaction(self.conn):
            if not execution_started:
                row = self.conn.execute(
                    """
                    UPDATE pulse_agent_jobs
                    SET status = 'pending',
                        attempt_count = GREATEST(0, attempt_count - 1),
                        next_run_at_ms = %s,
                        last_error = 'worker_timeout_before_execution',
                        updated_at_ms = %s
                    WHERE job_id = %s
                      AND status = 'running'
                      AND attempt_count = %s
                      AND updated_at_ms = %s
                    RETURNING *
                    """,
                    (now + 5_000, now, str(job["job_id"]), claim_attempt_count, claim_updated_at_ms),
                ).fetchone()
            else:
                row = self.conn.execute(
                    """
                    UPDATE pulse_agent_jobs
                    SET status = CASE
                          WHEN attempt_count >= max_attempts THEN 'dead'
                          ELSE 'failed'
                        END,
                        next_run_at_ms = CASE
                          WHEN attempt_count >= max_attempts THEN %s
                          ELSE %s + LEAST(300000, 5000 * GREATEST(1, attempt_count))
                        END,
                        last_error = 'worker_timeout_after_execution',
                        updated_at_ms = %s
                    WHERE job_id = %s
                      AND status = 'running'
                      AND attempt_count = %s
                      AND updated_at_ms = %s
                    RETURNING *
                    """,
                    (now, now, now, str(job["job_id"]), claim_attempt_count, claim_updated_at_ms),
                ).fetchone()
            updated = _optional_row(row)
            if updated is not None and str(updated.get("status") or "") == "dead":
                _terminalize_pulse_job(
                    self.conn,
                    row=updated,
                    reason="worker_timeout_after_execution",
                    now_ms=now,
                )
        if commit and not callable(getattr(self.conn, "transaction", None)):
            self.conn.commit()
        return updated

    def release_running_job_for_backpressure(
        self,
        job: dict[str, Any],
        *,
        reason: str,
        now_ms: int,
        delay_ms: int = 30_000,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        if job is None:
            return None
        now = int(now_ms)
        attempts = int(job.get("attempt_count") or 0)
        row = self.conn.execute(
            """
            UPDATE pulse_agent_jobs
            SET status = 'pending',
                next_run_at_ms = %s,
                last_error = %s,
                attempt_count = GREATEST(0, attempt_count - 1),
                updated_at_ms = %s
            WHERE job_id = %s
              AND status = 'running'
              AND attempt_count = %s
            RETURNING *
            """,
            (
                now + int(delay_ms),
                str(reason)[:1000],
                now,
                str(job["job_id"]),
                attempts,
            ),
        ).fetchone()
        if commit and not callable(getattr(self.conn, "transaction", None)):
            self.conn.commit()
        return _optional_row(row)

    def release_running_job_for_provider_cooldown(
        self,
        job: dict[str, Any],
        *,
        reason: str,
        now_ms: int,
        cooldown_until_ms: int,
        decrement_attempt: bool = True,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        if job is None:
            return None
        now = int(now_ms)
        attempts = int(job.get("attempt_count") or 0)
        row = self.conn.execute(
            """
            UPDATE pulse_agent_jobs
            SET status = 'pending',
                next_run_at_ms = %s,
                last_error = %s,
                attempt_count = CASE
                  WHEN %s THEN GREATEST(0, attempt_count - 1)
                  ELSE attempt_count
                END,
                updated_at_ms = %s
            WHERE job_id = %s
              AND status = 'running'
              AND attempt_count = %s
            RETURNING *
            """,
            (
                max(now, int(cooldown_until_ms)),
                str(reason)[:1000],
                bool(decrement_attempt),
                now,
                str(job["job_id"]),
                attempts,
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return _optional_row(row)

    def job_for_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM pulse_agent_jobs
            WHERE candidate_id = %s
            ORDER BY updated_at_ms DESC, created_at_ms DESC, job_id DESC
            LIMIT 1
            """,
            (candidate_id,),
        ).fetchone()
        return _optional_row(row)

    def pending_agent_job_count(self) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM pulse_agent_jobs
            WHERE status = ANY(%s)
            """,
            (list(ACTIVE_JOB_STATUSES),),
        ).fetchone()
        return int(row["count"] if row else 0)

    def pending_agent_job_count_for_window_scope(self, *, window: str, scope: str) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM pulse_agent_jobs
            WHERE status = ANY(%s)
              AND "window" = %s
              AND scope = %s
            """,
            (list(ACTIVE_JOB_STATUSES), window, scope),
        ).fetchone()
        return int(row["count"] if row else 0)

    def terminalize_stale_jobs_by_window(
        self,
        *,
        now_ms: int | None = None,
        ttl_by_window_seconds: dict[str, int],
        commit: bool = True,
    ) -> int:
        if not ttl_by_window_seconds:
            return 0
        now = int(now_ms if now_ms is not None else _now_ms())
        terminalized = 0
        for window, ttl_seconds in ttl_by_window_seconds.items():
            ttl = int(ttl_seconds)
            if ttl <= 0:
                continue
            with _transaction(self.conn):
                rows = self.conn.execute(
                    """
                    UPDATE pulse_agent_jobs
                    SET status = 'dead',
                        last_error = 'stale_window_ttl',
                        updated_at_ms = %s
                    WHERE "window" = %s
                      AND status = ANY(%s)
                      AND created_at_ms < %s
                    RETURNING *
                    """,
                    (now, str(window), list(ACTIVE_JOB_STATUSES), now - ttl * 1000),
                ).fetchall()
                for row in rows:
                    _terminalize_pulse_job(
                        self.conn,
                        row=_row(row),
                        reason="stale_window_ttl",
                        now_ms=now,
                    )
            terminalized += len(rows)
        if commit:
            self.conn.commit()
        return terminalized

    def mark_stale_agent_runs_failed(
        self,
        *,
        now_ms: int | None = None,
        stale_before_ms: int | None = None,
        commit: bool = True,
    ) -> int:
        now = int(now_ms if now_ms is not None else _now_ms())
        stale_before = int(stale_before_ms if stale_before_ms is not None else now - self.running_timeout_ms)
        cursor = self.conn.execute(
            """
            UPDATE pulse_agent_runs
            SET status = 'failed',
                outcome = 'timeout',
                error = COALESCE(NULLIF(error, ''), 'stale_running_timeout'),
                trace_metadata_json = COALESCE(trace_metadata_json, '{}'::jsonb)
                  || '{"failure_reason":"stale_running_timeout"}'::jsonb,
                latency_ms = GREATEST(0, %s - started_at_ms),
                finished_at_ms = %s
            WHERE status = 'running'
              AND started_at_ms < %s
            """,
            (now, now, stale_before),
        )
        if commit:
            self.conn.commit()
        return int(cursor.rowcount or 0)


def _terminalize_pulse_job(
    conn: Any,
    *,
    row: dict[str, Any],
    reason: str,
    now_ms: int,
    final_reason_bucket: str | None = None,
) -> None:
    terminalize_source_row(
        conn,
        worker_name="pulse_candidate",
        source_table="pulse_agent_jobs",
        target_key=str(row.get("job_id") or ""),
        source_row=row,
        final_status="dead",
        final_reason=str(reason or row.get("last_error") or "dead"),
        final_reason_bucket=final_reason_bucket,
        now_ms=now_ms,
        attempt_count=int(row.get("attempt_count") or 0),
        first_seen_at_ms=_optional_int(row.get("created_at_ms")),
        last_attempted_at_ms=now_ms,
        commit=False,
    )


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    transaction = getattr(conn, "transaction", None)
    if callable(transaction):
        return cast(AbstractContextManager[Any], transaction())
    return nullcontext()


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
