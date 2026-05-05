from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def connect_sqlite(path: str | Path, *, read_only: bool = False) -> sqlite3.Connection:
    db_path = Path(path).expanduser()
    if read_only:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
        conn.execute("PRAGMA query_only=ON")
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def sqlite_health_check(conn: sqlite3.Connection) -> dict[str, object]:
    row = conn.execute("SELECT 1").fetchone()
    if row is None or int(row[0]) != 1:
        return {"ok": False, "probe": "sqlite_liveness", "detail": "missing_select_result"}
    schema_row = conn.execute("PRAGMA schema_version").fetchone()
    return {
        "ok": True,
        "probe": "sqlite_liveness",
        "schema_version": int(schema_row[0]) if schema_row else 0,
    }


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[None]:
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
