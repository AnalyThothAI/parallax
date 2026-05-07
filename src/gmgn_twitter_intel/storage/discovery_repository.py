from __future__ import annotations

import hashlib
from typing import Any

from psycopg.types.json import Jsonb


class DiscoveryRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def enqueue(
        self,
        *,
        task_type: str,
        query_key: str,
        payload: dict[str, Any],
        next_run_at_ms: int,
        created_at_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        task_id = _stable_id("discovery-task", task_type, query_key)
        self.conn.execute(
            """
            INSERT INTO discovery_tasks(
              task_id, task_type, query_key, payload_json, status, attempt_count,
              next_run_at_ms, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, 'pending', 0, %s, %s, %s)
            ON CONFLICT(task_type, query_key) DO UPDATE SET
              payload_json = discovery_tasks.payload_json,
              status = CASE
                WHEN discovery_tasks.status = 'running' THEN 'running'
                ELSE 'pending'
              END,
              last_error = CASE
                WHEN discovery_tasks.status = 'running' THEN discovery_tasks.last_error
                ELSE NULL
              END,
              next_run_at_ms = LEAST(discovery_tasks.next_run_at_ms, excluded.next_run_at_ms),
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                task_id,
                task_type,
                query_key,
                Jsonb(payload),
                int(next_run_at_ms),
                int(created_at_ms),
                int(created_at_ms),
            ),
        )
        if commit:
            self.conn.commit()
        return self.task(task_id) or {}

    def claim_due(self, *, now_ms: int, limit: int, commit: bool = True) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH picked AS (
              SELECT task_id
              FROM discovery_tasks
              WHERE status IN ('pending', 'failed')
                AND next_run_at_ms <= %s
              ORDER BY next_run_at_ms ASC, created_at_ms ASC, task_id ASC
              LIMIT %s
              FOR UPDATE SKIP LOCKED
            )
            UPDATE discovery_tasks
            SET status = 'running',
                attempt_count = discovery_tasks.attempt_count + 1,
                updated_at_ms = %s
            FROM picked
            WHERE discovery_tasks.task_id = picked.task_id
            RETURNING discovery_tasks.*
            """,
            (int(now_ms), max(0, int(limit)), int(now_ms)),
        ).fetchall()
        if commit:
            self.conn.commit()
        return [dict(row) for row in rows]

    def complete(self, *, task_id: str, updated_at_ms: int, commit: bool = True) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            UPDATE discovery_tasks
            SET status = 'done',
                last_error = NULL,
                updated_at_ms = %s
            WHERE task_id = %s
            RETURNING *
            """,
            (int(updated_at_ms), task_id),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row) if row else None

    def fail(
        self,
        *,
        task_id: str,
        last_error: str,
        next_run_at_ms: int,
        updated_at_ms: int,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            UPDATE discovery_tasks
            SET status = 'failed',
                last_error = %s,
                next_run_at_ms = %s,
                updated_at_ms = %s
            WHERE task_id = %s
            RETURNING *
            """,
            (last_error[:500], int(next_run_at_ms), int(updated_at_ms), task_id),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row) if row else None

    def counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM discovery_tasks
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}

    def task(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM discovery_tasks WHERE task_id = %s", (task_id,)).fetchone()
        return dict(row) if row else None


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
