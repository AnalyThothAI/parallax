from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

LOCK_KEY = 2_026_051_806


class _LockingDB:
    def acquire_advisory_lock_connection(self, worker_name: str, key: int) -> _PgAdvisoryLock:
        conn = connect_postgres_test(read_only=False)
        row = conn.execute("SELECT pg_try_advisory_lock(%s) AS locked", (int(key),)).fetchone()
        if not bool(row["locked"]):
            conn.close()
            raise RuntimeError("advisory_lock_unavailable")
        return _PgAdvisoryLock(conn=conn, key=int(key))


class _PgAdvisoryLock:
    def __init__(self, *, conn: Any, key: int) -> None:
        self.conn = conn
        self.key = key

    def release(self) -> None:
        try:
            self.conn.execute("SELECT pg_advisory_unlock(%s)", (self.key,))
            self.conn.commit()
        finally:
            self.conn.close()


class _SingleWriterWorker(WorkerBase):
    SINGLE_WRITER_KEY = LOCK_KEY

    async def run_once(self) -> WorkerResult:
        return WorkerResult(processed=1)


def test_worker_base_single_writer_uses_real_postgres_advisory_lock(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
    finally:
        conn.close()

    async def scenario() -> None:
        db = _LockingDB()
        settings = SimpleNamespace(
            enabled=True,
            interval_seconds=0.01,
            soft_timeout_seconds=1,
            hard_timeout_seconds=2,
        )
        first = _SingleWriterWorker(name="single_writer", settings=settings, db=db, telemetry=object())
        second = _SingleWriterWorker(name="single_writer", settings=settings, db=db, telemetry=object())
        try:
            assert await first._ensure_advisory_lock() is True
            assert await second._ensure_advisory_lock() is False
            assert second.last_result == WorkerResult(
                skipped=1,
                notes={"reason": "advisory_lock_unavailable"},
            )

            await first.aclose()

            assert await second._ensure_advisory_lock() is True
        finally:
            await first.aclose()
            await second.aclose()

    asyncio.run(scenario())
