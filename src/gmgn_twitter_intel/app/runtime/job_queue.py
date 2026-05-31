from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BackoffPolicy:
    base_ms: int = 5_000
    max_ms: int = 300_000

    def delay_ms(self, attempt_count: int) -> int:
        return min(max(0, int(self.max_ms)), max(0, int(self.base_ms)) * max(1, int(attempt_count)))


@dataclass(frozen=True, slots=True)
class JobQueueDescriptor:
    name: str
    table: str
    id_column: str
    next_run_column: str = "next_run_at_ms"
    priority_order: str | None = None
    success_status: str = "done"
    last_attempt_at_column: str | None = None
    delivered_at_column: str | None = None
    has_lease_columns: bool = False


PULSE_AGENT_JOBS = JobQueueDescriptor(
    name="pulse_agent_jobs",
    table="pulse_agent_jobs",
    id_column="job_id",
    priority_order="priority DESC, next_run_at_ms ASC, created_at_ms ASC, job_id ASC",
)
NOTIFICATION_DELIVERIES = JobQueueDescriptor(
    name="notification_deliveries",
    table="notification_deliveries",
    id_column="delivery_id",
    priority_order="next_run_at_ms ASC, created_at_ms ASC, delivery_id ASC",
    success_status="delivered",
    last_attempt_at_column="last_attempt_at_ms",
    delivered_at_column="delivered_at_ms",
)

JOB_QUEUE_DESCRIPTORS: Mapping[str, JobQueueDescriptor] = {
    descriptor.name: descriptor
    for descriptor in (PULSE_AGENT_JOBS, NOTIFICATION_DELIVERIES)
}
_DESCRIPTORS_BY_TABLE: Mapping[str, JobQueueDescriptor] = {
    descriptor.table: descriptor for descriptor in JOB_QUEUE_DESCRIPTORS.values()
}


class JobQueue:
    def __init__(
        self,
        descriptor: JobQueueDescriptor | str | None = None,
        *,
        table: str | None = None,
        worker_name: str,
        lease_ms: int,
        max_attempts: int,
        backoff: BackoffPolicy | None = None,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        self.descriptor = _resolve_descriptor(descriptor=descriptor, table=table)
        self.worker_name = _normalize_worker_name(worker_name)
        self.lease_ms = max(1, int(lease_ms))
        self.max_attempts = max(1, int(max_attempts))
        self.backoff = backoff or BackoffPolicy()
        self._now_ms = now_ms or _now_ms

    def claim_batch(self, *, limit: int, conn: Any) -> list[dict[str, Any]]:
        now = int(self._now_ms())
        stale_before = now - self.lease_ms
        descriptor = self.descriptor
        if descriptor.has_lease_columns:
            lease_token = f"worker:{self.worker_name}:{_new_token_suffix()}"
            params = (
                now,
                now,
                max(1, int(limit)),
                lease_token,
                now + self.lease_ms,
                now,
            )
            sql = f"""
            WITH picked AS (
                  SELECT {descriptor.id_column}
              FROM {descriptor.table}
              WHERE (
                  status IN ('pending', 'failed')
                  AND attempt_count < max_attempts
                  AND {descriptor.next_run_column} <= %s
                )
                OR (
                  status = 'running'
                  AND lease_expires_at_ms < %s
                  AND attempt_count < max_attempts
                )
              ORDER BY {descriptor.priority_order}
              LIMIT %s
              FOR UPDATE SKIP LOCKED
            )
            UPDATE {descriptor.table} AS job
            SET status = 'running',
                attempt_count = job.attempt_count + 1,
                lease_token = %s,
                lease_expires_at_ms = %s,
                last_error = NULL,
                updated_at_ms = %s
            FROM picked
            WHERE job.{descriptor.id_column} = picked.{descriptor.id_column}
            RETURNING job.*
            """
        else:
            last_attempt_clause = (
                f", {descriptor.last_attempt_at_column} = %s" if descriptor.last_attempt_at_column else ""
            )
            params = (
                now,
                stale_before,
                max(1, int(limit)),
                now,
                *((now,) if descriptor.last_attempt_at_column else ()),
            )
            sql = f"""
            WITH picked AS (
              SELECT {descriptor.id_column}
              FROM {descriptor.table}
              WHERE (
                  status IN ('pending', 'failed')
                  AND attempt_count < max_attempts
                  AND {descriptor.next_run_column} <= %s
                )
                OR (
                  status = 'running'
                  AND updated_at_ms < %s
                  AND attempt_count < max_attempts
                )
              ORDER BY {descriptor.priority_order}
              LIMIT %s
              FOR UPDATE SKIP LOCKED
            )
            UPDATE {descriptor.table} AS job
            SET status = 'running',
                attempt_count = job.attempt_count + 1,
                last_error = NULL,
                updated_at_ms = %s
                {last_attempt_clause}
            FROM picked
            WHERE job.{descriptor.id_column} = picked.{descriptor.id_column}
            RETURNING job.*
            """
        return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def finalize_success(self, job_id: str, *, conn: Any, lease_token: str | None = None) -> dict[str, Any] | None:
        now = int(self._now_ms())
        descriptor = self.descriptor
        if descriptor.has_lease_columns:
            token = _require_lease_token(descriptor, lease_token)
            row = conn.execute(
                f"""
                UPDATE {descriptor.table}
                SET status = %s,
                    last_error = NULL,
                    lease_token = NULL,
                    lease_expires_at_ms = NULL,
                    updated_at_ms = %s
                WHERE {descriptor.id_column} = %s
                  AND status = 'running'
                  AND lease_token = %s
                RETURNING *
                """,
                (descriptor.success_status, now, str(job_id), token),
            ).fetchone()
            return dict(row) if row is not None else None
        delivered_clause = f", {descriptor.delivered_at_column} = %s" if descriptor.delivered_at_column else ""
        params = (
            (descriptor.success_status, now, now, str(job_id))
            if descriptor.delivered_at_column
            else (descriptor.success_status, now, str(job_id))
        )
        conn.execute(
            f"""
            UPDATE {descriptor.table}
            SET status = %s,
                last_error = NULL,
                updated_at_ms = %s
                {delivered_clause}
            WHERE {descriptor.id_column} = %s
            """,
            params,
        )
        return None

    def finalize_failure(
        self,
        job_id: str,
        *,
        error: str,
        conn: Any,
        lease_token: str | None = None,
    ) -> dict[str, Any] | None:
        now = int(self._now_ms())
        descriptor = self.descriptor
        if descriptor.has_lease_columns:
            token = _require_lease_token(descriptor, lease_token)
            row = conn.execute(
                f"""
                UPDATE {descriptor.table}
                SET status = CASE WHEN attempt_count >= max_attempts THEN 'dead' ELSE 'failed' END,
                    next_run_at_ms = CASE
                      WHEN attempt_count >= max_attempts THEN {descriptor.next_run_column}
                      ELSE %s + (LEAST(%s, %s * GREATEST(1, attempt_count)))::BIGINT
                    END,
                    lease_token = NULL,
                    lease_expires_at_ms = NULL,
                    last_error = %s,
                    updated_at_ms = %s
                WHERE {descriptor.id_column} = %s
                  AND status = 'running'
                  AND lease_token = %s
                RETURNING *
                """,
                (now, self.backoff.max_ms, self.backoff.base_ms, str(error)[:1000], now, str(job_id), token),
            ).fetchone()
            return dict(row) if row is not None else None
        conn.execute(
            f"""
            UPDATE {descriptor.table}
            SET status = CASE WHEN attempt_count >= max_attempts THEN 'dead' ELSE 'failed' END,
                next_run_at_ms = CASE
                  WHEN attempt_count >= max_attempts THEN {descriptor.next_run_column}
                  ELSE %s + (LEAST(%s, %s * GREATEST(1, attempt_count)))::BIGINT
                END,
                last_error = %s,
                updated_at_ms = %s
            WHERE {descriptor.id_column} = %s
            """,
            (now, self.backoff.max_ms, self.backoff.base_ms, str(error)[:1000], now, str(job_id)),
        )
        return None

    def reclaim_stale(self, *, conn: Any) -> None:
        now = int(self._now_ms())
        descriptor = self.descriptor
        if descriptor.has_lease_columns:
            conn.execute(
                f"""
                UPDATE {descriptor.table}
                SET status = CASE WHEN attempt_count >= max_attempts THEN 'dead' ELSE 'failed' END,
                    last_error = 'stale_running_timeout',
                    updated_at_ms = %s
                WHERE status = 'running'
                  AND lease_expires_at_ms < %s
                """,
                (now, now),
            )
            return
        conn.execute(
            f"""
            UPDATE {descriptor.table}
            SET status = CASE WHEN attempt_count >= max_attempts THEN 'dead' ELSE 'failed' END,
                last_error = 'stale_running_timeout',
                updated_at_ms = %s
            WHERE status = 'running'
              AND updated_at_ms < %s
            """,
            (now, now - self.lease_ms),
        )


def _resolve_descriptor(*, descriptor: JobQueueDescriptor | str | None, table: str | None) -> JobQueueDescriptor:
    if descriptor is not None and table is not None:
        raise ValueError("job_queue_descriptor_or_table_only")
    if isinstance(descriptor, JobQueueDescriptor):
        if descriptor.name not in JOB_QUEUE_DESCRIPTORS or JOB_QUEUE_DESCRIPTORS[descriptor.name] != descriptor:
            raise ValueError(f"job_queue_not_allowlisted:{descriptor.name}")
        return descriptor
    if isinstance(descriptor, str):
        try:
            return JOB_QUEUE_DESCRIPTORS[descriptor]
        except KeyError as exc:
            raise ValueError(f"job_queue_not_allowlisted:{descriptor}") from exc
    if table is not None:
        try:
            return _DESCRIPTORS_BY_TABLE[table]
        except KeyError as exc:
            raise ValueError(f"job_queue_not_allowlisted:{table}") from exc
    raise ValueError("job_queue_descriptor_required")


def _normalize_worker_name(name: str) -> str:
    return str(name).strip().replace(" ", "_") or "unknown"


def _require_lease_token(descriptor: JobQueueDescriptor, lease_token: str | None) -> str:
    token = str(lease_token or "").strip()
    if not token:
        raise ValueError(f"lease_token_required:{descriptor.name}")
    return token


def _new_token_suffix() -> str:
    return uuid.uuid4().hex


def _now_ms() -> int:
    return int(time.time() * 1000)
