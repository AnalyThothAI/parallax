from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from ..collector.subscriptions import event_matches_handles
from ..models import TwitterEvent


class EventStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def insert_observed_event(self, event: TwitterEvent) -> bool:
        record = _event_record(event)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                insert or ignore into observed_events (
                    event_id, source_channel, coverage, action, author_handle,
                    tweet_id, event_json, raw_json, received_at_ms
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["event_id"],
                    record["source_channel"],
                    record["coverage"],
                    record["action"],
                    record["author_handle"],
                    record["tweet_id"],
                    record["event_json"],
                    record["raw_json"],
                    record["received_at_ms"],
                ),
            )
            return cursor.rowcount == 1

    def insert_matched_event(self, event: TwitterEvent) -> bool:
        record = _event_record(event)
        watch_key = ",".join(event.matched_handles)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                insert or ignore into matched_events (
                    event_id, source_channel, coverage, action, author_handle,
                    tweet_id, matched_handles, event_json, received_at_ms
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["event_id"],
                    record["source_channel"],
                    record["coverage"],
                    record["action"],
                    record["author_handle"],
                    record["tweet_id"],
                    watch_key,
                    record["event_json"],
                    record["received_at_ms"],
                ),
            )
            return cursor.rowcount == 1

    def backfill_matches(self, *, handles: set[str]) -> int:
        rows = self._observed_candidate_rows(handles)
        inserted = 0
        for row in rows:
            event = json.loads(row["event_json"])
            if not event_matches_handles(event, handles):
                continue
            with self._lock, self._connection:
                cursor = self._connection.execute(
                    """
                    insert or ignore into matched_events (
                        event_id, source_channel, coverage, action, author_handle,
                        tweet_id, matched_handles, event_json, received_at_ms
                    )
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["event_id"],
                        row["source_channel"],
                        row["coverage"],
                        row["action"],
                        row["author_handle"],
                        row["tweet_id"],
                        ",".join(event.get("matched_handles") or []),
                        row["event_json"],
                        row["received_at_ms"],
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    def recent_events(self, *, limit: int, handles: set[str] | None = None) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                select event_json
                from matched_events
                order by received_at_ms desc, rowid desc
                limit ?
                """,
                (limit * 5 if handles else limit,),
            ).fetchall()

        events = [json.loads(row["event_json"]) for row in rows]
        if handles:
            events = [event for event in events if event_matches_handles(event, handles)]
        return events[:limit]

    def event_counts(self) -> dict[str, int]:
        with self._lock:
            observed = self._connection.execute("select count(*) from observed_events").fetchone()[0]
            matched = self._connection.execute("select count(*) from matched_events").fetchone()[0]
        return {"observed_events": observed, "matched_events": matched}

    def table_names(self) -> list[str]:
        with self._lock:
            rows = self._connection.execute(
                "select name from sqlite_master where type = 'table' order by name"
            ).fetchall()
        return [row["name"] for row in rows]

    def prune_observed_older_than(self, cutoff_ms: int) -> int:
        return self._delete_older_than("observed_events", cutoff_ms)

    def prune_matched_older_than(self, cutoff_ms: int) -> int:
        return self._delete_older_than("matched_events", cutoff_ms)

    def _observed_candidate_rows(self, handles: set[str]) -> list[sqlite3.Row]:
        with self._lock:
            if not handles:
                return self._connection.execute(
                    """
                    select event_id, source_channel, coverage, action, author_handle,
                           tweet_id, event_json, received_at_ms
                    from observed_events
                    order by received_at_ms asc, rowid asc
                    """
                ).fetchall()

            placeholders = ",".join("?" for _ in handles)
            return self._connection.execute(
                f"""
                select event_id, source_channel, coverage, action, author_handle,
                       tweet_id, event_json, received_at_ms
                from observed_events
                where lower(author_handle) in ({placeholders})
                order by received_at_ms asc, rowid asc
                """,
                tuple(sorted(handles)),
            ).fetchall()

    def _delete_older_than(self, table_name: str, cutoff_ms: int) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                f"delete from {table_name} where received_at_ms < ?",
                (cutoff_ms,),
            )
            return cursor.rowcount

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("pragma journal_mode=WAL")
            self._connection.execute("pragma synchronous=NORMAL")
            self._connection.execute("drop table if exists events")
            self._connection.execute(
                """
                create table if not exists observed_events (
                    event_id text primary key,
                    source_channel text not null,
                    coverage text not null,
                    action text not null,
                    author_handle text,
                    tweet_id text,
                    event_json text not null,
                    raw_json text,
                    received_at_ms integer not null,
                    created_at text not null default current_timestamp
                )
                """
            )
            self._connection.execute(
                """
                create table if not exists matched_events (
                    event_id text primary key,
                    source_channel text not null,
                    coverage text not null,
                    action text not null,
                    author_handle text,
                    tweet_id text,
                    matched_handles text not null,
                    event_json text not null,
                    received_at_ms integer not null,
                    created_at text not null default current_timestamp
                )
                """
            )
            self._connection.execute(
                "create index if not exists idx_observed_received_at on observed_events(received_at_ms desc)"
            )
            self._connection.execute(
                "create index if not exists idx_observed_author_handle on observed_events(author_handle)"
            )
            self._connection.execute(
                "create index if not exists idx_matched_received_at on matched_events(received_at_ms desc)"
            )
            self._connection.execute(
                "create index if not exists idx_matched_author_handle on matched_events(author_handle)"
            )


def _event_record(event: TwitterEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "source_channel": event.source.channel,
        "coverage": event.source.coverage,
        "action": event.action,
        "author_handle": event.author.handle,
        "tweet_id": event.tweet_id,
        "event_json": json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":")),
        "raw_json": json.dumps(event.raw, ensure_ascii=False, separators=(",", ":")) if event.raw is not None else None,
        "received_at_ms": event.received_at_ms,
    }
