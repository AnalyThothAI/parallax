from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from psycopg import Connection, conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_COMPOSE_POSTGRES_HOST = "postgres"
_HOST_LOOPBACK = "127.0.0.1"
_DEFAULT_HOST_POSTGRES_PORT = "56532"


def with_password_from_file(dsn: str, password_file: Path | None) -> str:
    if password_file is None:
        return dsn
    password = password_file.read_text(encoding="utf-8").strip()
    if "://" in dsn:
        return _url_dsn_with_password(dsn, password)
    parts: dict[str, Any] = dict(conninfo.conninfo_to_dict(dsn))
    parts["password"] = password
    return str(conninfo.make_conninfo(**parts))


def local_docker_host_dsn(dsn: str) -> str:
    if _running_in_container():
        return dsn
    if "://" in dsn:
        return _url_dsn_with_local_docker_host(dsn)
    parts: dict[str, Any] = dict(conninfo.conninfo_to_dict(dsn))
    if parts.get("host") != _COMPOSE_POSTGRES_HOST:
        return dsn
    parts["host"] = _HOST_LOOPBACK
    parts["port"] = _host_postgres_port()
    return str(conninfo.make_conninfo(**parts))


def create_pool(
    dsn: str,
    *,
    min_size: int,
    max_size: int,
    connect_timeout_seconds: float,
) -> ConnectionPool:
    dsn = local_docker_host_dsn(dsn)
    return ConnectionPool(
        conninfo=dsn,
        min_size=min_size,
        max_size=max_size,
        kwargs={
            "autocommit": True,
            "connect_timeout": int(connect_timeout_seconds),
            "row_factory": dict_row,
        },
        open=True,
    )


def _running_in_container() -> bool:
    return Path("/.dockerenv").exists()


def _host_postgres_port() -> str:
    return os.environ.get("GMGN_POSTGRES_PORT") or _DEFAULT_HOST_POSTGRES_PORT


def _url_dsn_with_local_docker_host(dsn: str) -> str:
    parsed = urlsplit(dsn)
    if parsed.hostname != _COMPOSE_POSTGRES_HOST:
        return dsn
    username = parsed.username or ""
    password = parsed.password
    auth = ""
    if username and password is not None:
        auth = f"{quote(username, safe='')}:{quote(password, safe='')}@"
    elif username:
        auth = f"{quote(username, safe='')}@"
    host = f"{_HOST_LOOPBACK}:{_host_postgres_port()}"
    return urlunsplit((parsed.scheme, f"{auth}{host}", parsed.path, parsed.query, parsed.fragment))


def _url_dsn_with_password(dsn: str, password: str) -> str:
    parsed = urlsplit(dsn)
    username = parsed.username or ""
    hostname = parsed.hostname or ""
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    auth = ""
    if username:
        auth = f"{quote(username, safe='')}:{quote(password, safe='')}@"
    return urlunsplit((parsed.scheme, f"{auth}{host}", parsed.path, parsed.query, parsed.fragment))


def connect_postgres(dsn: str, *, connect_timeout_seconds: float = 5.0) -> Connection[dict[str, Any]]:
    dsn = local_docker_host_dsn(dsn)
    return Connection.connect(
        dsn,
        autocommit=True,
        connect_timeout=int(connect_timeout_seconds),
        row_factory=dict_row,
    )


@contextmanager
def transaction(conn: Connection) -> Iterator[None]:
    with conn.transaction():
        yield


def postgres_health_check(conn: Any, *, expected_migration_version: str | None = None) -> dict[str, object]:
    try:
        row = conn.execute("SELECT 1 AS ok").fetchone()
        if row is None or int(row["ok"]) != 1:
            return {"ok": False, "probe": "postgres_liveness", "detail": "missing_select_result"}
        version_row = conn.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
        migration_version = version_row["version_num"] if version_row else None
        migration_ok = expected_migration_version is None or migration_version == expected_migration_version
        if hasattr(conn, "commit"):
            conn.commit()
        return {
            "ok": migration_ok,
            "probe": "postgres_liveness",
            "migration_version": migration_version,
            **(
                {
                    "expected_migration_version": expected_migration_version,
                    "migration_status": "ready" if migration_ok else "stale",
                }
                if expected_migration_version is not None
                else {}
            ),
        }
    except Exception as exc:
        if hasattr(conn, "rollback"):
            conn.rollback()
        return {"ok": False, "probe": "postgres_liveness", "error": type(exc).__name__, "detail": str(exc)}
