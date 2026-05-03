from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from dataclasses import asdict
from typing import Any

from ..models import TwitterEvent
from ..pipeline.entity_extractor import EVM_QUERY_CHAINS, normalize_ca
from ..pipeline.tweet_identity import canonical_tweet_url, logical_dedup_key
from ..pipeline.tweet_text import build_text_projection
from .sqlite_client import transaction


class EvidenceRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert_raw_frame(
        self,
        *,
        source: str,
        channel: str,
        received_at_ms: int,
        raw_payload_json: str,
    ) -> bool:
        payload_hash = hashlib.sha256(raw_payload_json.encode("utf-8")).hexdigest()
        frame_id = f"{source}:{channel}:{payload_hash}"
        try:
            self.conn.execute(
                """
                INSERT INTO raw_frames(
                  frame_id, source, channel, received_at_ms, payload_hash, raw_payload_json, created_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (frame_id, source, channel, received_at_ms, payload_hash, raw_payload_json, _now_ms()),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            self.conn.rollback()
            return False
        return True

    def insert_event(self, event: TwitterEvent, *, is_watched: bool) -> bool:
        now_ms = _now_ms()
        row = event_to_row(event, is_watched=is_watched, now_ms=now_ms)
        with transaction(self.conn):
            return self.insert_event_without_commit(row)

    def insert_event_without_commit(self, row: dict[str, Any]) -> bool:
        try:
            self.conn.execute(
                """
                INSERT INTO events(
                  event_id, logical_dedup_key, canonical_url, source_provider, source_transport,
                  coverage, channel, action, original_action, tweet_id, internal_id, timestamp_ms,
                  received_at_ms, author_handle, author_name, author_avatar, author_followers,
                  author_tags_json, text, text_raw, text_clean, search_text, urls_json, cashtags_json,
                  hashtags_json, mentions_json, media_json, reference_json, matched_handles_json,
                  is_watched, matched_at_ms, raw_json, event_json, created_at_ms, updated_at_ms
                )
                VALUES (
                  :event_id, :logical_dedup_key, :canonical_url, :source_provider, :source_transport,
                  :coverage, :channel, :action, :original_action, :tweet_id, :internal_id, :timestamp_ms,
                  :received_at_ms, :author_handle, :author_name, :author_avatar, :author_followers,
                  :author_tags_json, :text, :text_raw, :text_clean, :search_text, :urls_json, :cashtags_json,
                  :hashtags_json, :mentions_json, :media_json, :reference_json, :matched_handles_json,
                  :is_watched, :matched_at_ms, :raw_json, :event_json, :created_at_ms, :updated_at_ms
                )
                """,
                row,
            )
        except sqlite3.IntegrityError:
            return False
        self.conn.execute(
            """
            INSERT INTO event_fts(
              event_id, author_handle, text_clean, search_text, cashtags, hashtags, mentions
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["event_id"],
                row["author_handle"] or "",
                row["text_clean"] or "",
                row["search_text"] or "",
                " ".join(_json_loads(row["cashtags_json"], [])),
                " ".join(_json_loads(row["hashtags_json"], [])),
                " ".join(_json_loads(row["mentions_json"], [])),
            ),
        )
        return True

    def recent_events(
        self,
        *,
        limit: int,
        handles: set[str] | None = None,
        ca: str | None = None,
        chain: str | None = None,
        symbol: str | None = None,
        watched_only: bool = True,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        clauses: list[str] = []
        params: list[Any] = []
        if watched_only:
            clauses.append("e.is_watched = 1")
        normalized_handles = {item.strip().lstrip("@").lower() for item in handles or set() if item.strip()}
        if normalized_handles:
            placeholders = ",".join("?" for _ in normalized_handles)
            clauses.append(f"e.author_handle IN ({placeholders})")
            params.extend(sorted(normalized_handles))
        join = ""
        if ca:
            normalized_chain, normalized_ca = normalize_ca(ca, chain=chain)
            join = "JOIN event_entities ee ON ee.event_id = e.event_id"
            clauses.extend(["ee.entity_type = 'ca'", "ee.normalized_value = ?"])
            params.append(normalized_ca)
            if normalized_chain == "evm_unknown":
                placeholders = ",".join("?" for _ in EVM_QUERY_CHAINS)
                clauses.append(f"ee.chain IN ({placeholders})")
                params.extend(sorted(EVM_QUERY_CHAINS))
            else:
                clauses.append("ee.chain = ?")
                params.append(normalized_chain)
        elif symbol:
            join = "JOIN event_entities ee ON ee.event_id = e.event_id"
            clauses.extend(["ee.entity_type = 'symbol'", "ee.normalized_value = ?"])
            params.append(symbol.strip().lstrip("$").upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT e.* FROM events e {join} {where} ORDER BY e.received_at_ms DESC LIMIT ?",
            (*params, max(0, int(limit))),
        ).fetchall()
        return [decode_event_row(row) for row in rows]

    def events_by_ids(self, event_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not event_ids:
            return {}
        placeholders = ",".join("?" for _ in event_ids)
        rows = self.conn.execute(f"SELECT * FROM events WHERE event_id IN ({placeholders})", event_ids).fetchall()
        return {str(row["event_id"]): decode_event_row(row) for row in rows}

    def search_fts(self, query: str, *, limit: int, watched_only: bool = False) -> list[dict[str, Any]]:
        if not query.strip() or limit <= 0:
            return []
        fts_query = _fts_query(query)
        if not fts_query:
            return []
        watched_clause = "AND e.is_watched = 1" if watched_only else ""
        rows = self.conn.execute(
            f"""
            SELECT e.*, bm25(event_fts) AS score
            FROM event_fts
            JOIN events e ON e.event_id = event_fts.event_id
            WHERE event_fts MATCH ? {watched_clause}
            ORDER BY score
            LIMIT ?
            """,
            (fts_query, max(0, int(limit))),
        ).fetchall()
        return [decode_event_row(row) | {"score": row["score"]} for row in rows]

    def counts(self, *, since_ms: int | None = None) -> dict[str, int]:
        suffix = " WHERE received_at_ms >= ?" if since_ms is not None else ""
        params = (since_ms,) if since_ms is not None else ()
        return {
            "raw_frames": int(self.conn.execute(f"SELECT COUNT(*) FROM raw_frames{suffix}", params).fetchone()[0]),
            "events": int(self.conn.execute(f"SELECT COUNT(*) FROM events{suffix}", params).fetchone()[0]),
            "watched_events": int(
                self.conn.execute(
                    f"SELECT COUNT(*) FROM events{suffix}{' AND' if suffix else ' WHERE'} is_watched = 1",
                    params,
                ).fetchone()[0]
            ),
        }

    def db_write_probe(self) -> bool:
        self.conn.execute("SELECT 1").fetchone()
        return True

    def close(self) -> None:
        self.conn.close()


def event_to_row(event: TwitterEvent, *, is_watched: bool, now_ms: int) -> dict[str, Any]:
    event_dict = event.to_dict()
    reference_text = event.reference.text if event.reference else None
    projection = build_text_projection(event.content.text, reference_text=reference_text)
    matched_handles = [handle.lower() for handle in event.matched_handles]
    return {
        "event_id": event.event_id,
        "logical_dedup_key": logical_dedup_key(event),
        "canonical_url": canonical_tweet_url(event),
        "source_provider": event.source.provider,
        "source_transport": event.source.transport,
        "coverage": event.source.coverage,
        "channel": event.source.channel,
        "action": event.action,
        "original_action": event.original_action,
        "tweet_id": event.tweet_id,
        "internal_id": event.internal_id,
        "timestamp_ms": event.timestamp * 1000 if event.timestamp < 10_000_000_000 else event.timestamp,
        "received_at_ms": event.received_at_ms,
        "author_handle": event.author.handle.lower() if event.author.handle else None,
        "author_name": event.author.name,
        "author_avatar": event.author.avatar,
        "author_followers": event.author.followers,
        "author_tags_json": _json(event.author.tags),
        "text": event.content.text,
        "text_raw": projection.text_raw,
        "text_clean": projection.text_clean,
        "search_text": projection.search_text,
        "urls_json": _json(projection.urls),
        "cashtags_json": _json(projection.cashtags),
        "hashtags_json": _json(projection.hashtags),
        "mentions_json": _json(projection.mentions),
        "media_json": _json([asdict(item) for item in event.content.media]),
        "reference_json": _json(event_dict["reference"]),
        "matched_handles_json": _json(matched_handles),
        "is_watched": 1 if is_watched else 0,
        "matched_at_ms": now_ms if is_watched else 0,
        "raw_json": _json(event.raw),
        "event_json": _json(event_dict),
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    }


def decode_event_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    event = _json_loads(data.get("event_json"), {})
    if not isinstance(event, dict):
        event = {}
    event.update(
        {
            "event_id": data.get("event_id"),
            "logical_dedup_key": data.get("logical_dedup_key"),
            "canonical_url": data.get("canonical_url"),
            "received_at_ms": data.get("received_at_ms"),
            "author_handle": data.get("author_handle"),
            "text_clean": data.get("text_clean"),
            "search_text": data.get("search_text"),
            "urls": _json_loads(data.get("urls_json"), []),
            "cashtags": _json_loads(data.get("cashtags_json"), []),
            "hashtags": _json_loads(data.get("hashtags_json"), []),
            "mentions": _json_loads(data.get("mentions_json"), []),
            "is_watched": data.get("is_watched"),
            "matched_at_ms": data.get("matched_at_ms"),
        }
    )
    return event


def _fts_query(query: str) -> str:
    tokens = re.findall(r"\w+", query, flags=re.UNICODE)
    return " OR ".join(f'"{token}"' for token in tokens[:16])


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: Any, default: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _now_ms() -> int:
    return int(time.time() * 1000)
