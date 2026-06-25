from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, cast

from parallax.domains.token_intel.interfaces import (
    TOKEN_RADAR_PROJECTION_NAME,
    TOKEN_RADAR_PROJECTION_VERSION,
    TOKEN_RADAR_SOURCE_TABLE,
)

KNOWN_PROJECTIONS = (
    {
        "projection_name": TOKEN_RADAR_PROJECTION_NAME,
        "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
        "source_table": TOKEN_RADAR_SOURCE_TABLE,
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
        def _write() -> None:
            now_ms = _now_ms()
            cursor = self.conn.execute(
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
            _required_single_rowcount(cursor)

        return _run_repository_write(self.conn, commit, _write)

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
        def _write() -> dict[str, Any]:
            now_ms = _now_ms()
            resolved_run_id = run_id or _id(
                "projection_run",
                projection_name,
                projection_version,
                mode,
                str(now_ms),
                uuid.uuid4().hex,
            )
            cursor = self.conn.execute(
                """
                INSERT INTO projection_runs(
                  run_id, projection_name, projection_version, mode, status, source_start_ms, source_end_ms,
                  rows_read, rows_written, dirty_ranges_written, started_at_ms
                )
                VALUES (%s, %s, %s, %s, 'running', %s, %s, 0, 0, 0, %s)
                RETURNING *
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
            row = cursor.fetchone()
            return _required_returning_row(cursor, row)

        return _run_repository_write(self.conn, commit, _write)

    def mark_stale_running_runs(
        self,
        *,
        projection_name: str,
        projection_version: str,
        stale_before_ms: int,
        finished_at_ms: int,
        commit: bool = True,
    ) -> int:
        def _write() -> int:
            result = self.conn.execute(
                """
                UPDATE projection_runs
                SET status = 'abandoned',
                    finished_at_ms = %s,
                    error = 'stale_running_timeout'
                WHERE projection_name = %s
                  AND projection_version = %s
                  AND status = 'running'
                  AND started_at_ms < %s
                """,
                (
                    int(finished_at_ms),
                    projection_name,
                    projection_version,
                    int(stale_before_ms),
                ),
            )
            return _cursor_rowcount(result)

        return _run_repository_write(self.conn, commit, _write)

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
        def _write() -> None:
            cursor = self.conn.execute(
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
            _required_single_rowcount(cursor)

        return _run_repository_write(self.conn, commit, _write)

    def run_by_id(self, run_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM projection_runs WHERE run_id = %s", (run_id,)).fetchone()
        return dict(row) if row else None

    def list_runs(self, *, limit: int, projection_name: str | None = None) -> list[dict[str, Any]]:
        parsed_limit = _required_nonnegative_int(limit, "projection_repository_limit_required")
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
            (*params, parsed_limit),
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
        def _write() -> str:
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
            cursor = self.conn.execute(
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
            _required_single_rowcount(cursor)
            return dirty_id

        return _run_repository_write(self.conn, commit, _write)

    def claim_dirty_ranges(
        self,
        *,
        projection_name: str,
        projection_version: str,
        limit: int,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        parsed_limit = _required_nonnegative_int(limit, "projection_repository_limit_required")

        def _write() -> list[dict[str, Any]]:
            cursor = self.conn.execute(
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
                (projection_name, projection_version, parsed_limit, _now_ms()),
            )
            rows = cursor.fetchall()
            _returned_rowcount(cursor, rows)
            return [dict(row) for row in rows]

        return _run_repository_write(self.conn, commit, _write)

    def list_dirty_ranges(self, *, limit: int, projection_name: str | None = None) -> list[dict[str, Any]]:
        parsed_limit = _required_nonnegative_int(limit, "projection_repository_limit_required")
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
            (*params, parsed_limit),
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
            offset_version = offset["projection_version"] if offset else None
            version_ready = offset_version == item["projection_version"] if offset else False
            known.append(
                {
                    **item,
                    "status": (offset["status"] if (offset and version_ready) else "wrong_version")
                    if offset
                    else "missing",
                    "offset_projection_version": offset_version,
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


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction_context = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("projection_repository_transaction_required") from exc
    if not callable(transaction_context):
        raise RuntimeError("projection_repository_transaction_required")
    return cast(AbstractContextManager[Any], transaction_context())


def _run_repository_write[T](conn: Any, commit: bool, write: Callable[[], T]) -> T:
    if commit:
        with _transaction(conn):
            return write()
    return write()


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("projection_repository_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int):
        raise TypeError("projection_repository_rowcount_invalid")
    if rowcount < 0:
        raise TypeError("projection_repository_rowcount_invalid")
    return int(rowcount)


def _returned_rowcount(cursor: Any, rows: list[Any]) -> int:
    rowcount = _cursor_rowcount(cursor)
    if rowcount != len(rows):
        raise TypeError("projection_repository_rowcount_invalid")
    return rowcount


def _required_single_rowcount(cursor: Any) -> int:
    rowcount = _cursor_rowcount(cursor)
    if rowcount != 1:
        raise TypeError("projection_repository_rowcount_invalid")
    return rowcount


def _required_nonnegative_int(value: Any, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(error_code)
    if value < 0:
        raise ValueError(error_code)
    return int(value)


def _required_returning_row(cursor: Any, row: Any) -> dict[str, Any]:
    _required_single_rowcount(cursor)
    if row is None:
        raise TypeError("projection_repository_rowcount_invalid")
    return dict(row)
