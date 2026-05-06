from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from psycopg import Connection, conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def with_password_from_file(dsn: str, password_file: Path | None) -> str:
    if password_file is None:
        return dsn
    password = password_file.read_text(encoding="utf-8").strip()
    parts = conninfo.conninfo_to_dict(dsn)
    parts["password"] = password
    return conninfo.make_conninfo(**parts)


def create_pool(
    dsn: str,
    *,
    min_size: int,
    max_size: int,
    connect_timeout_seconds: float,
) -> ConnectionPool:
    return ConnectionPool(
        conninfo=dsn,
        min_size=min_size,
        max_size=max_size,
        kwargs={
            "autocommit": False,
            "connect_timeout": int(connect_timeout_seconds),
            "row_factory": dict_row,
        },
        open=True,
    )


def connect_postgres(dsn: str, *, connect_timeout_seconds: float = 5.0) -> Connection[dict[str, Any]]:
    return Connection.connect(
        dsn,
        autocommit=False,
        connect_timeout=int(connect_timeout_seconds),
        row_factory=dict_row,
    )


@contextmanager
def transaction(conn: Connection) -> Iterator[None]:
    with conn.transaction():
        yield


def postgres_health_check(conn) -> dict[str, object]:
    row = conn.execute("SELECT 1 AS ok").fetchone()
    if row is None or int(row["ok"]) != 1:
        return {"ok": False, "probe": "postgres_liveness", "detail": "missing_select_result"}
    version_row = conn.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
    return {
        "ok": True,
        "probe": "postgres_liveness",
        "migration_version": version_row["version_num"] if version_row else None,
    }
