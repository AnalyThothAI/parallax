from __future__ import annotations

import hashlib
import time
from typing import Any

KNOWN_PROJECTIONS = (
    {
        "projection_name": "token-social-buckets",
        "projection_version": "token-social-buckets-v1",
        "source_table": "event_token_attributions",
    },
    {
        "projection_name": "token-flow-window-snapshots",
        "projection_version": "token-flow-window-snapshots-v1",
        "source_table": "token_social_buckets",
    },
    {
        "projection_name": "account-quality",
        "projection_version": "account-quality-v1",
        "source_table": "event_token_attributions",
    },
)


class ProjectionRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def get_offset(self, projection_name: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM projection_offsets WHERE projection_name = %s",
            (projection_name,),
        ).fetchone()
        return dict(row) if row else None

    def list_offsets(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM projection_offsets
            ORDER BY projection_name ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def advance_offset(
        self,
        *,
        projection_name: str,
        projection_version: str,
        source_table: str,
        source_max_received_at_ms: int,
        source_max_id: str,
        last_run_id: str | None,
        lag_ms: int,
        status: str = "ready",
        last_error: str | None = None,
        commit: bool = True,
    ) -> None:
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO projection_offsets(
              projection_name, projection_version, source_table, source_max_received_at_ms,
              source_max_id, last_run_id, status, lag_ms, last_error, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(projection_name) DO UPDATE SET
              projection_version = excluded.projection_version,
              source_table = excluded.source_table,
              source_max_received_at_ms = excluded.source_max_received_at_ms,
              source_max_id = excluded.source_max_id,
              last_run_id = excluded.last_run_id,
              status = excluded.status,
              lag_ms = excluded.lag_ms,
              last_error = excluded.last_error,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                projection_name,
                projection_version,
                source_table,
                int(source_max_received_at_ms),
                source_max_id,
                last_run_id,
                status,
                int(lag_ms),
                last_error,
                now_ms,
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()

    def start_run(
        self,
        *,
        projection_name: str,
        projection_version: str,
        mode: str,
        source_start_ms: int | None,
        source_end_ms: int | None,
        run_id: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        now_ms = _now_ms()
        resolved_run_id = run_id or _id("projection_run", projection_name, projection_version, mode, str(now_ms))
        self.conn.execute(
            """
            INSERT INTO projection_runs(
              run_id, projection_name, projection_version, mode, status, source_start_ms, source_end_ms,
              rows_read, rows_written, dirty_ranges_written, started_at_ms
            )
            VALUES (%s, %s, %s, %s, 'running', %s, %s, 0, 0, 0, %s)
            """,
            (
                resolved_run_id,
                projection_name,
                projection_version,
                mode,
                source_start_ms,
                source_end_ms,
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()
        return self.run_by_id(resolved_run_id) or {}

    def finish_run(
        self,
        *,
        run_id: str,
        status: str,
        rows_read: int,
        rows_written: int,
        dirty_ranges_written: int,
        error: str | None = None,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            UPDATE projection_runs
            SET status = %s,
                rows_read = %s,
                rows_written = %s,
                dirty_ranges_written = %s,
                finished_at_ms = %s,
                error = %s
            WHERE run_id = %s
            """,
            (
                status,
                int(rows_read),
                int(rows_written),
                int(dirty_ranges_written),
                _now_ms(),
                error,
                run_id,
            ),
        )
        if commit:
            self.conn.commit()

    def run_by_id(self, run_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM projection_runs WHERE run_id = %s", (run_id,)).fetchone()
        return dict(row) if row else None

    def list_runs(self, *, projection_name: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if projection_name:
            where = "WHERE projection_name = %s"
            params.append(projection_name)
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM projection_runs
            {where}
            ORDER BY started_at_ms DESC, run_id DESC
            LIMIT %s
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def enqueue_dirty_range(
        self,
        *,
        projection_name: str,
        projection_version: str,
        entity_type: str,
        entity_key: str,
        window: str | None,
        scope: str | None,
        start_ms: int,
        end_ms: int,
        reason: str,
        commit: bool = True,
    ) -> str:
        dirty_id = _id(
            "projection_dirty_range",
            projection_name,
            projection_version,
            entity_type,
            entity_key,
            window or "",
            scope or "",
            str(int(start_ms)),
            str(int(end_ms)),
            reason,
        )
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO projection_dirty_ranges(
              dirty_id, projection_name, projection_version, entity_type, entity_key,
              "window", scope, start_ms, end_ms, reason, status, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s)
            ON CONFLICT(dirty_id) DO UPDATE SET
              status = CASE
                WHEN projection_dirty_ranges.status = 'running' THEN 'running'
                ELSE 'pending'
              END,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                dirty_id,
                projection_name,
                projection_version,
                entity_type,
                entity_key,
                window,
                scope,
                int(start_ms),
                int(end_ms),
                reason,
                now_ms,
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()
        return dirty_id

    def claim_dirty_ranges(
        self,
        *,
        projection_name: str,
        projection_version: str,
        limit: int,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH picked AS (
              SELECT dirty_id
              FROM projection_dirty_ranges
              WHERE projection_name = %s
                AND projection_version = %s
                AND status = 'pending'
              ORDER BY created_at_ms ASC, dirty_id ASC
              LIMIT %s
              FOR UPDATE SKIP LOCKED
            )
            UPDATE projection_dirty_ranges ranges
            SET status = 'running',
                updated_at_ms = %s
            FROM picked
            WHERE ranges.dirty_id = picked.dirty_id
            RETURNING ranges.*
            """,
            (projection_name, projection_version, max(0, int(limit)), _now_ms()),
        ).fetchall()
        if commit:
            self.conn.commit()
        return [dict(row) for row in rows]

    def list_dirty_ranges(self, *, projection_name: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if projection_name:
            where = "WHERE projection_name = %s"
            params.append(projection_name)
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM projection_dirty_ranges
            {where}
            ORDER BY created_at_ms DESC, dirty_id DESC
            LIMIT %s
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def status_summary(self) -> dict[str, Any]:
        offsets = {row["projection_name"]: row for row in self.list_offsets()}
        latest_runs = {
            name: self.list_runs(projection_name=name, limit=1)
            for name in {item["projection_name"] for item in KNOWN_PROJECTIONS}
        }
        known = []
        for item in KNOWN_PROJECTIONS:
            name = item["projection_name"]
            offset = offsets.get(name)
            known.append(
                {
                    **item,
                    "status": offset["status"] if offset else "missing",
                    "lag_ms": offset["lag_ms"] if offset else None,
                    "source_max_received_at_ms": offset["source_max_received_at_ms"] if offset else None,
                    "source_max_id": offset["source_max_id"] if offset else None,
                    "last_run_id": offset["last_run_id"] if offset else None,
                    "last_error": offset["last_error"] if offset else None,
                    "latest_run": latest_runs.get(name, [None])[0] if latest_runs.get(name) else None,
                }
            )
        return {
            "known_projections": known,
            "offsets": list(offsets.values()),
        }


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)
