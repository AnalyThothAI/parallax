from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import asdict
from typing import Any, cast

from psycopg.types.json import Jsonb

from parallax.domains.evidence.types.entity import EVM_QUERY_CHAINS, normalize_ca
from parallax.domains.evidence.types.tweet_identity import canonical_tweet_url, logical_dedup_key
from parallax.domains.evidence.types.tweet_text import build_text_projection
from parallax.domains.evidence.types.twitter_event import TwitterEvent
from parallax.platform.db.postgres_client import require_transaction, transaction


class EvidenceRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def unit_of_work(self) -> AbstractContextManager[None]:
        return transaction(self.conn)

    def require_transaction(self, *, operation: str) -> None:
        require_transaction(self.conn, operation=operation)

    def insert_raw_frame(
        self,
        *,
        source: str,
        channel: str,
        received_at_ms: int,
        raw_payload_json: str,
        commit: bool = True,
    ) -> bool:
        def _write() -> bool:
            sanitized_payload = _sanitize_postgres_value(raw_payload_json)
            payload_hash = hashlib.sha256(sanitized_payload.encode("utf-8")).hexdigest()
            frame_id = f"{source}:{channel}:{payload_hash}"
            cursor = self.conn.execute(
                """
                INSERT INTO raw_frames(
                  frame_id, source, channel, received_at_ms, payload_hash, raw_payload_json, created_at_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(frame_id) DO NOTHING
                """,
                (frame_id, source, channel, received_at_ms, payload_hash, sanitized_payload, _now_ms()),
            )
            return _single_rowcount(cursor) == 1

        return _run_repository_write(self.conn, commit, _write)

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
        return _single_rowcount(cursor) == 1

    def event_exists(self, *, event_id: str, logical_dedup_key: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1 AS found
            FROM events
            WHERE event_id = %s OR logical_dedup_key = %s
            LIMIT 1
            """,
            (event_id, logical_dedup_key),
        ).fetchone()
        return bool(row)

    def recent_events(
        self,
        *,
        limit: int,
        handles: set[str] | None = None,
        ca: str | None = None,
        chain: str | None = None,
        symbol: str | None = None,
        since_ms: int | None = None,
        watched_only: bool = True,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        clauses: list[str] = []
        params: list[Any] = []
        if watched_only:
            clauses.append("e.is_watched = true")
        if since_ms is not None:
            clauses.append("e.received_at_ms >= %s")
            params.append(int(since_ms))
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

    def recent_events_for_token_filters(
        self,
        *,
        limit: int,
        per_filter_limit: int,
        cas: set[tuple[str, str]] | None = None,
        symbols: set[str] | None = None,
        since_ms: int | None = None,
        watched_only: bool = True,
    ) -> list[dict[str, Any]]:
        parsed_limit = max(0, int(limit))
        parsed_per_filter_limit = max(0, int(per_filter_limit))
        if parsed_limit <= 0 or parsed_per_filter_limit <= 0:
            return []

        filter_kinds, filter_chains, filter_values = _token_filter_keysets(cas=cas, symbols=symbols)
        if not filter_kinds:
            return []

        clauses: list[str] = []
        params: list[Any] = [filter_kinds, filter_chains, filter_values, sorted(EVM_QUERY_CHAINS)]
        if watched_only:
            clauses.append("e.is_watched = true")
        if since_ms is not None:
            clauses.append("e.received_at_ms >= %s")
            params.append(int(since_ms))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            WITH input_filters AS (
              SELECT filter_kind, filter_chain, filter_value, ordinality
              FROM unnest(%s::text[], %s::text[], %s::text[]) WITH ORDINALITY
                AS filters(filter_kind, filter_chain, filter_value, ordinality)
            ),
            distinct_filters AS (
              SELECT DISTINCT ON (filter_kind, filter_chain, filter_value)
                     filter_kind, filter_chain, filter_value, ordinality
              FROM input_filters
              ORDER BY filter_kind, filter_chain, filter_value, ordinality
            ),
            ranked_events AS (
              SELECT e.*,
                     ROW_NUMBER() OVER (
                       PARTITION BY filters.filter_kind, filters.filter_chain, filters.filter_value
                       ORDER BY e.received_at_ms DESC, e.event_id DESC
                     ) AS event_rank
              FROM distinct_filters filters
              JOIN event_entities ee
                ON (
                  filters.filter_kind = 'symbol'
                  AND ee.entity_type = 'symbol'
                  AND ee.normalized_value = filters.filter_value
                )
                OR (
                  filters.filter_kind = 'ca'
                  AND ee.entity_type = 'ca'
                  AND ee.normalized_value = filters.filter_value
                  AND (
                    (filters.filter_chain = 'evm_unknown' AND ee.chain = ANY(%s::text[]))
                    OR ee.chain = filters.filter_chain
                  )
                )
              JOIN events e ON e.event_id = ee.event_id
              {where}
            ),
            bounded_events AS (
              SELECT *
              FROM ranked_events
              WHERE event_rank <= %s
            ),
            deduped_events AS (
              SELECT DISTINCT ON (event_id) *
              FROM bounded_events
              ORDER BY event_id, received_at_ms DESC
            )
            SELECT *
            FROM deduped_events
            ORDER BY received_at_ms DESC, event_id DESC
            LIMIT %s
            """,
            (*params, parsed_per_filter_limit, parsed_limit),
        ).fetchall()
        return [decode_event_row(row) for row in rows]

    def events_by_ids(self, event_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not event_ids:
            return {}
        placeholders = ",".join("%s" for _ in event_ids)
        rows = self.conn.execute(f"SELECT * FROM events WHERE event_id IN ({placeholders})", event_ids).fetchall()
        return {str(row["event_id"]): decode_event_row(row) for row in rows}

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


def _token_filter_keysets(
    *,
    cas: set[tuple[str, str]] | None,
    symbols: set[str] | None,
) -> tuple[list[str], list[str], list[str]]:
    filters: list[tuple[str, str, str]] = []
    for chain, ca in sorted(cas or set()):
        normalized_chain, normalized_ca = normalize_ca(ca, chain=chain)
        filters.append(("ca", normalized_chain, normalized_ca))
    for symbol in sorted(symbols or set()):
        normalized_symbol = str(symbol).strip().lstrip("$").upper()
        if normalized_symbol:
            filters.append(("symbol", "", normalized_symbol))

    if not filters:
        return [], [], []
    return [item[0] for item in filters], [item[1] for item in filters], [item[2] for item in filters]


def event_to_row(event: TwitterEvent, *, is_watched: bool, now_ms: int) -> dict[str, Any]:
    event_dict = event.to_dict()
    reference_text = event.reference.text if event.reference else None
    projection = build_text_projection(event.content.text, reference_text=reference_text)
    matched_handles = [handle.lower() for handle in event.matched_handles]
    sanitized: dict[str, Any] = _sanitize_postgres_value(
        {
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
        }
    )
    return sanitized


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


def _json(value: Any) -> Jsonb:
    return Jsonb(
        _sanitize_postgres_value(value),
        dumps=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True),
    )


def _sanitize_postgres_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {_sanitize_postgres_value(key): _sanitize_postgres_value(item) for key, item in value.items()}
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


def _single_rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("evidence_repository_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int):
        raise TypeError("evidence_repository_rowcount_invalid")
    if rowcount not in (0, 1):
        raise TypeError("evidence_repository_rowcount_invalid")
    return rowcount


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction_context = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("evidence_repository_transaction_required") from exc
    if not callable(transaction_context):
        raise RuntimeError("evidence_repository_transaction_required")
    return cast(AbstractContextManager[Any], transaction_context())


def _run_repository_write[T](conn: Any, commit: bool, write: Callable[[], T]) -> T:
    if commit:
        with _transaction(conn):
            return write()
    return write()
