from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.platform.db.postgres_client import transaction

from ..models import TwitterEvent
from ..pipeline.entity_extractor import EVM_QUERY_CHAINS, normalize_ca
from ..pipeline.tweet_identity import canonical_tweet_url, logical_dedup_key
from ..pipeline.tweet_text import build_text_projection


class EvidenceRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def insert_raw_frame(
        self,
        *,
        source: str,
        channel: str,
        received_at_ms: int,
        raw_payload_json: str,
    ) -> bool:
        raw_payload_json = _sanitize_postgres_value(raw_payload_json)
        payload_hash = hashlib.sha256(raw_payload_json.encode("utf-8")).hexdigest()
        frame_id = f"{source}:{channel}:{payload_hash}"
        cursor = self.conn.execute(
            """
            INSERT INTO raw_frames(
              frame_id, source, channel, received_at_ms, payload_hash, raw_payload_json, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(frame_id) DO NOTHING
            """,
            (frame_id, source, channel, received_at_ms, payload_hash, raw_payload_json, _now_ms()),
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def insert_event(self, event: TwitterEvent, *, is_watched: bool) -> bool:
        now_ms = _now_ms()
        row = event_to_row(event, is_watched=is_watched, now_ms=now_ms)
        with transaction(self.conn):
            return self.insert_event_without_commit(row)

    def insert_event_without_commit(self, row: dict[str, Any]) -> bool:
        cursor = self.conn.execute(
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
              %(event_id)s, %(logical_dedup_key)s, %(canonical_url)s, %(source_provider)s, %(source_transport)s,
              %(coverage)s, %(channel)s, %(action)s, %(original_action)s, %(tweet_id)s, %(internal_id)s,
              %(timestamp_ms)s,
              %(received_at_ms)s, %(author_handle)s, %(author_name)s, %(author_avatar)s, %(author_followers)s,
              %(author_tags_json)s, %(text)s, %(text_raw)s, %(text_clean)s, %(search_text)s, %(urls_json)s,
              %(cashtags_json)s,
              %(hashtags_json)s, %(mentions_json)s, %(media_json)s, %(reference_json)s, %(matched_handles_json)s,
              %(is_watched)s, %(matched_at_ms)s, %(raw_json)s, %(event_json)s, %(created_at_ms)s, %(updated_at_ms)s
            )
            ON CONFLICT DO NOTHING
            """,
            row,
        )
        return cursor.rowcount != 0

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
            clauses.append("e.is_watched = true")
        normalized_handles = {item.strip().lstrip("@").lower() for item in handles or set() if item.strip()}
        if normalized_handles:
            placeholders = ",".join("%s" for _ in normalized_handles)
            clauses.append(f"e.author_handle IN ({placeholders})")
            params.extend(sorted(normalized_handles))
        join = ""
        if ca:
            normalized_chain, normalized_ca = normalize_ca(ca, chain=chain)
            join = "JOIN event_entities ee ON ee.event_id = e.event_id"
            clauses.extend(["ee.entity_type = 'ca'", "ee.normalized_value = %s"])
            params.append(normalized_ca)
            if normalized_chain == "evm_unknown":
                placeholders = ",".join("%s" for _ in EVM_QUERY_CHAINS)
                clauses.append(f"ee.chain IN ({placeholders})")
                params.extend(sorted(EVM_QUERY_CHAINS))
            else:
                clauses.append("ee.chain = %s")
                params.append(normalized_chain)
        elif symbol:
            join = "JOIN event_entities ee ON ee.event_id = e.event_id"
            clauses.extend(["ee.entity_type = 'symbol'", "ee.normalized_value = %s"])
            params.append(symbol.strip().lstrip("$").upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT e.* FROM events e {join} {where} ORDER BY e.received_at_ms DESC LIMIT %s",
            (*params, max(0, int(limit))),
        ).fetchall()
        return [decode_event_row(row) for row in rows]

    def events_by_ids(self, event_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not event_ids:
            return {}
        placeholders = ",".join("%s" for _ in event_ids)
        rows = self.conn.execute(f"SELECT * FROM events WHERE event_id IN ({placeholders})", event_ids).fetchall()
        return {str(row["event_id"]): decode_event_row(row) for row in rows}

    def search_fts(self, query: str, *, limit: int, watched_only: bool = False) -> list[dict[str, Any]]:
        if not query.strip() or limit <= 0:
            return []
        search_query = _fts_query(query)
        if not search_query:
            return []
        watched_clause = "AND e.is_watched = true" if watched_only else ""
        rows = self.conn.execute(
            f"""
            SELECT e.*, ts_rank_cd(e.search_tsv, websearch_to_tsquery('simple', %s)) AS score
            FROM events e
            WHERE e.search_tsv @@ websearch_to_tsquery('simple', %s) {watched_clause}
            ORDER BY score DESC, e.received_at_ms DESC
            LIMIT %s
            """,
            (search_query, search_query, max(0, int(limit))),
        ).fetchall()
        return [decode_event_row(row) | {"score": row["score"]} for row in rows]

    def count_fts(self, query: str, *, watched_only: bool = False) -> int:
        if not query.strip():
            return 0
        search_query = _fts_query(query)
        if not search_query:
            return 0
        watched_clause = "AND e.is_watched = true" if watched_only else ""
        row = self.conn.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM events e
            WHERE e.search_tsv @@ websearch_to_tsquery('simple', %s) {watched_clause}
            """,
            (search_query,),
        ).fetchone()
        return int(row["count"] or 0) if row else 0

    def counts(self, *, since_ms: int | None = None) -> dict[str, int]:
        suffix = " WHERE received_at_ms >= %s" if since_ms is not None else ""
        params = (since_ms,) if since_ms is not None else ()
        return {
            "raw_frames": int(
                self.conn.execute(f"SELECT COUNT(*) AS count FROM raw_frames{suffix}", params).fetchone()["count"]
            ),
            "events": int(
                self.conn.execute(f"SELECT COUNT(*) AS count FROM events{suffix}", params).fetchone()["count"]
            ),
            "watched_events": int(
                self.conn.execute(
                    f"SELECT COUNT(*) AS count FROM events{suffix}{' AND' if suffix else ' WHERE'} is_watched = true",
                    params,
                ).fetchone()["count"]
            ),
        }

    def close(self) -> None:
        self.conn.close()


def event_to_row(event: TwitterEvent, *, is_watched: bool, now_ms: int) -> dict[str, Any]:
    event_dict = event.to_dict()
    reference_text = event.reference.text if event.reference else None
    projection = build_text_projection(event.content.text, reference_text=reference_text)
    matched_handles = [handle.lower() for handle in event.matched_handles]
    return _sanitize_postgres_value({
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
        "is_watched": is_watched,
        "matched_at_ms": now_ms if is_watched else 0,
        "raw_json": _json(event.raw),
        "event_json": _json(event_dict),
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    })


def decode_event_row(row: dict[str, Any] | dict[str, Any]) -> dict[str, Any]:
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
    if query.count('"') % 2 == 1:
        query = query[: query.rfind('"')]
    return " ".join(re.findall(r"\w+", query, flags=re.UNICODE)[:16])


def _json(value: Any) -> Jsonb:
    return Jsonb(
        _sanitize_postgres_value(value),
        dumps=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True),
    )


def _sanitize_postgres_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {
            _sanitize_postgres_value(key): _sanitize_postgres_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_postgres_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_postgres_value(item) for item in value)
    return value


def _json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    if not value.strip():
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _now_ms() -> int:
    return int(time.time() * 1000)
