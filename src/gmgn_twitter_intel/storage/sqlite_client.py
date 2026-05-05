from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SQLITE_OPERATIONAL_PROBES = (
    ("raw_frames", "SELECT frame_id FROM raw_frames ORDER BY received_at_ms DESC LIMIT 1"),
    ("events", "SELECT event_id FROM events ORDER BY received_at_ms DESC LIMIT 1"),
    ("event_fts", "SELECT event_id FROM event_fts LIMIT 1"),
    ("event_entities", "SELECT entity_id FROM event_entities ORDER BY received_at_ms DESC LIMIT 1"),
    ("tokens", "SELECT token_id FROM tokens LIMIT 1"),
    ("token_aliases", "SELECT alias_id FROM token_aliases LIMIT 1"),
    ("token_market_snapshots", "SELECT snapshot_id FROM token_market_snapshots ORDER BY received_at_ms DESC LIMIT 1"),
    ("event_token_mentions", "SELECT mention_id FROM event_token_mentions ORDER BY received_at_ms DESC LIMIT 1"),
    (
        "event_token_attributions",
        "SELECT attribution_id FROM event_token_attributions ORDER BY received_at_ms DESC LIMIT 1",
    ),
    (
        "token_market_observations",
        "SELECT observation_id FROM token_market_observations ORDER BY updated_at_ms DESC LIMIT 1",
    ),
    ("notifications", "SELECT notification_id FROM notifications ORDER BY last_seen_at_ms DESC LIMIT 1"),
    (
        "notification_deliveries",
        "SELECT delivery_id FROM notification_deliveries ORDER BY updated_at_ms DESC LIMIT 1",
    ),
)


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
    row = conn.execute("PRAGMA quick_check(1)").fetchone()
    quick_check = str(row[0] if row else "")
    if quick_check != "ok":
        return {"ok": False, "quick_check": quick_check or "missing_result"}

    for _, sql in SQLITE_OPERATIONAL_PROBES:
        conn.execute(sql).fetchone()
    return {
        "ok": True,
        "quick_check": "ok",
        "probes": [name for name, _ in SQLITE_OPERATIONAL_PROBES],
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
