from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from ..models import TwitterEvent
from ..pipeline.processing_policy import decide_processing
from ..pipeline.token_extractor import TokenEntity, extract_token_entities, normalize_ca
from ..pipeline.tweet_identity import canonical_tweet_url, logical_dedup_key
from ..pipeline.tweet_text import build_text_projection
from .lancedb_client import LanceDbClient


class TweetRepository:
    def __init__(self, client: LanceDbClient):
        self.client = client

    def insert_event(self, event: TwitterEvent) -> bool:
        now_ms = _now_ms()
        dedup_key = logical_dedup_key(event)
        existing_logical = self.client.get_one("twitter_events", logical_dedup_key=dedup_key)
        if existing_logical and existing_logical.get("event_id") != event.event_id:
            return False
        inserted = self.client.insert_if_missing(
            "twitter_events",
            row=_event_row(
                event,
                embedding_dim=self.client.embedding_dim,
                is_matched=False,
                matched_at_ms=0,
                created_at_ms=now_ms,
                updated_at_ms=now_ms,
            ),
            key_fields=("event_id",),
        )
        if inserted:
            self._insert_entities(event, created_at_ms=now_ms)
        return inserted

    def mark_event_matched(self, event: TwitterEvent) -> bool:
        current = self.client.get_one("twitter_events", event_id=event.event_id)
        if current and bool(current.get("is_matched")):
            return False
        now_ms = _now_ms()
        self.client.upsert(
            "twitter_events",
            key_fields=("event_id",),
            row=_event_row(
                event,
                embedding_dim=self.client.embedding_dim,
                is_matched=True,
                matched_at_ms=now_ms,
                created_at_ms=int(current.get("created_at_ms") or now_ms) if current else now_ms,
                updated_at_ms=now_ms,
            ),
        )
        return True

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
        return self.client.insert_if_missing(
            "raw_frames",
            row={
                "frame_id": frame_id,
                "source": source,
                "channel": channel,
                "received_at_ms": received_at_ms,
                "payload_hash": payload_hash,
                "raw_payload_json": raw_payload_json,
                "created_at_ms": _now_ms(),
            },
            key_fields=("frame_id",),
        )

    def recent_events(
        self,
        *,
        limit: int,
        handles: set[str] | None = None,
        ca: str | None = None,
        chain: str | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        normalized_handles = {item.strip().lstrip("@").lower() for item in handles or set() if item.strip()}
        event_ids = self._event_ids_for_token_filter(ca=ca, chain=chain, symbol=symbol)
        if event_ids is not None and not event_ids:
            return []
        if event_ids is None:
            rows = self.client.query_where(
                "twitter_events",
                where="matched_at_ms > 0",
                order_by="received_at_ms",
                descending=True,
            )
        else:
            rows = [
                row
                for row in self.client.query_in("twitter_events", column="event_id", values=sorted(event_ids))
                if int(row.get("matched_at_ms") or 0) > 0
            ]
            rows.sort(key=lambda item: item.get("received_at_ms") or 0, reverse=True)
        events: list[dict[str, Any]] = []
        for row in rows:
            if normalized_handles and not _row_matches_handles(row, normalized_handles):
                continue
            events.append(_decode_event(row))
            if len(events) >= limit:
                break
        return events

    def event_counts(self) -> dict[str, int]:
        return {
            "twitter_events": self.client.count_where("twitter_events"),
            "matched_twitter_events": self.client.count_where("twitter_events", where="matched_at_ms > 0"),
            "tweet_entities": self.client.count_where("tweet_entities"),
        }

    def health_counts(self) -> dict[str, int]:
        return {
            **self.event_counts(),
            "unresolved_entities": self.client.count_where(
                "tweet_entities",
                where="token_resolution_status = 'unresolved'",
            ),
            "pending_embeddings": self.client.count_where("twitter_events", where="embedding_status = 'pending'"),
        }

    def matched_event_rows(self) -> list[dict[str, Any]]:
        return self.client.query_where("twitter_events", where="matched_at_ms > 0")

    def pending_embedding_rows(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self.client.query_where(
            "twitter_events",
            where="embedding_status = 'pending'",
            order_by="processing_priority",
            descending=True,
        )
        return rows[: max(0, int(limit))]

    def update_event_embedding(self, *, event_id: str, embedding: list[float], status: str = "embedded") -> None:
        current = self.client.get_one("twitter_events", event_id=event_id)
        if not current:
            return
        now_ms = _now_ms()
        current["embedding"] = embedding
        current["embedding_status"] = status
        current["embedding_updated_at_ms"] = now_ms
        current["updated_at_ms"] = now_ms
        self.client.upsert("twitter_events", key_fields=("event_id",), row=current)

    def decode_event_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return _decode_event(row)

    def reprocess_entities(self, *, limit: int) -> int:
        processed = 0
        rows = self.client.query_where("twitter_events", order_by="received_at_ms", descending=True, limit=limit)
        now_ms = _now_ms()
        for row in rows:
            projection = build_text_projection(row.get("text"), reference_text=_reference_text_from_row(row))
            for entity in _entities_from_projection(projection):
                self.client.insert_if_missing(
                    "tweet_entities",
                    row=_entity_row(str(row["event_id"]), entity, created_at_ms=now_ms),
                    key_fields=("entity_id",),
                )
            processed += 1
        return processed

    def symbol_ca_candidates(self, symbol: str) -> list[dict[str, str | None]]:
        normalized_symbol = symbol.strip().lstrip("$").upper()
        symbol_rows = self.client.query_where(
            "tweet_entities",
            where=f"entity_type = 'symbol' AND normalized_value = '{_sql_literal(normalized_symbol)}'",
        )
        event_ids = {row["event_id"] for row in symbol_rows if row.get("event_id")}
        ca_rows = [
            row
            for row in self.client.query_in("tweet_entities", column="event_id", values=sorted(event_ids))
            if row.get("entity_type") == "ca" and row.get("token_resolution_status") == "resolved"
        ]
        candidates = {
            (str(row.get("chain") or ""), str(row.get("normalized_value") or "")): {
                "symbol": normalized_symbol,
                "chain": row.get("chain"),
                "ca": row.get("normalized_value"),
            }
            for row in ca_rows
        }
        return sorted(candidates.values(), key=lambda item: (item.get("chain") or "", item.get("ca") or ""))

    def table_names(self) -> list[str]:
        return self.client.table_names()

    def close(self) -> None:
        self.client.close()

    def _insert_entities(self, event: TwitterEvent, *, created_at_ms: int) -> None:
        for entity in _entities_for_event(event):
            self.client.insert_if_missing(
                "tweet_entities",
                row=_entity_row(event.event_id, entity, created_at_ms=created_at_ms),
                key_fields=("entity_id",),
            )

    def _event_ids_for_token_filter(
        self,
        *,
        ca: str | None,
        chain: str | None,
        symbol: str | None,
    ) -> set[str] | None:
        clauses: list[str] = []
        if ca:
            normalized_chain, normalized_ca = normalize_ca(ca, chain=chain)
            clauses.extend(
                [
                    "entity_type = 'ca'",
                    f"normalized_value = '{_sql_literal(normalized_ca)}'",
                    f"chain = '{_sql_literal(normalized_chain)}'",
                ]
            )
        elif symbol:
            normalized_symbol = symbol.strip().lstrip("$").upper()
            clauses.extend(["entity_type = 'symbol'", f"normalized_value = '{_sql_literal(normalized_symbol)}'"])
        else:
            return None
        rows = self.client.query_where("tweet_entities", where=" AND ".join(clauses))
        return {str(row["event_id"]) for row in rows if row.get("event_id")}


def _event_row(
    event: TwitterEvent,
    *,
    embedding_dim: int,
    is_matched: bool,
    matched_at_ms: int,
    created_at_ms: int,
    updated_at_ms: int,
) -> dict[str, Any]:
    event_dict = event.to_dict()
    projection = _projection_for_event(event)
    entities = _entities_from_projection(projection)
    decision = decide_processing(projection, entities)
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
        "timestamp": event.timestamp,
        "received_at_ms": event.received_at_ms,
        "author_handle": event.author.handle.lower() if event.author.handle else None,
        "author_name": event.author.name,
        "author_avatar": event.author.avatar,
        "author_followers": event.author.followers,
        "author_tags_json": _json(event.author.tags),
        "text": event.content.text,
        "text_raw": projection.text_raw,
        "text_clean": projection.text_clean,
        "embedding_text": projection.embedding_text,
        "urls_json": _json(projection.urls),
        "cashtags_json": _json(projection.cashtags),
        "hashtags_json": _json(projection.hashtags),
        "mentions_json": _json(projection.mentions),
        "media_json": _json(event_dict["content"]["media"]),
        "reference_json": _json(event_dict["reference"]),
        "unfollow_target_json": _json(event_dict["unfollow_target"]),
        "avatar_change_json": _json(event_dict["avatar_change"]),
        "bio_change_json": _json(event_dict["bio_change"]),
        "matched_handles_json": _json([handle.lower() for handle in event.matched_handles]),
        "is_matched": is_matched,
        "matched_at_ms": matched_at_ms,
        "raw_json": _json(event.raw),
        "event_json": _json(event_dict),
        "token_resolution_status": decision.token_resolution_status,
        "processing_priority": decision.processing_priority,
        "quality_flags_json": _json(decision.quality_flags),
        "embedding": [0.0] * embedding_dim,
        "embedding_status": decision.embedding_status,
        "embedding_updated_at_ms": 0,
        "created_at_ms": created_at_ms,
        "updated_at_ms": updated_at_ms,
    }


def _decode_event(row: dict[str, Any]) -> dict[str, Any]:
    event_json = row.get("event_json")
    if isinstance(event_json, str) and event_json.strip():
        decoded = json.loads(event_json)
        if isinstance(decoded, dict):
            decoded.update(_event_metadata(row))
            return decoded
    return {
        "event_id": row.get("event_id"),
        "source": {
            "provider": row.get("source_provider"),
            "transport": row.get("source_transport"),
            "coverage": row.get("coverage"),
            "channel": row.get("channel"),
        },
        "action": row.get("action"),
        "original_action": row.get("original_action"),
        "tweet_id": row.get("tweet_id"),
        "internal_id": row.get("internal_id"),
        "timestamp": row.get("timestamp"),
        "received_at_ms": row.get("received_at_ms"),
        "author": {
            "handle": row.get("author_handle"),
            "name": row.get("author_name"),
            "avatar": row.get("author_avatar"),
            "followers": row.get("author_followers"),
            "tags": _json_loads(row.get("author_tags_json"), []),
        },
        "content": {"text": row.get("text"), "media": _json_loads(row.get("media_json"), [])},
        "reference": _json_loads(row.get("reference_json"), None),
        "unfollow_target": _json_loads(row.get("unfollow_target_json"), None),
        "avatar_change": _json_loads(row.get("avatar_change_json"), None),
        "bio_change": _json_loads(row.get("bio_change_json"), None),
        "matched_handles": _json_loads(row.get("matched_handles_json"), []),
        "raw": _json_loads(row.get("raw_json"), None),
        **_event_metadata(row),
    }


def _event_metadata(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "logical_dedup_key": row.get("logical_dedup_key"),
        "canonical_url": row.get("canonical_url"),
        "text_clean": row.get("text_clean"),
        "embedding_text": row.get("embedding_text"),
        "urls": _json_loads(row.get("urls_json"), []),
        "cashtags": _json_loads(row.get("cashtags_json"), []),
        "hashtags": _json_loads(row.get("hashtags_json"), []),
        "mentions": _json_loads(row.get("mentions_json"), []),
        "token_resolution_status": row.get("token_resolution_status"),
        "processing_priority": row.get("processing_priority"),
        "quality_flags": _json_loads(row.get("quality_flags_json"), []),
        "embedding_status": row.get("embedding_status"),
        "embedding_updated_at_ms": row.get("embedding_updated_at_ms"),
    }


def _row_matches_handles(row: dict[str, Any], handles: set[str]) -> bool:
    author_handle = str(row.get("author_handle") or "").lower()
    if author_handle in handles:
        return True
    matched_handles = _json_loads(row.get("matched_handles_json"), [])
    return bool(handles.intersection(str(handle).lower() for handle in matched_handles))


def _json(value: Any) -> str | None:
    if value is None:
        return None
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


def _projection_for_event(event: TwitterEvent):
    reference_text = event.reference.text if event.reference else None
    return build_text_projection(event.content.text, reference_text=reference_text)


def _reference_text_from_row(row: dict[str, Any]) -> str | None:
    reference = _json_loads(row.get("reference_json"), None)
    return reference.get("text") if isinstance(reference, dict) else None


def _entities_for_event(event: TwitterEvent) -> list[TokenEntity]:
    return _entities_from_projection(_projection_for_event(event))


def _entities_from_projection(projection) -> list[TokenEntity]:
    return extract_token_entities(projection.embedding_text or projection.text_raw)


def _entity_row(event_id: str, entity: TokenEntity, *, created_at_ms: int) -> dict[str, Any]:
    return {
        "entity_id": _entity_id(event_id, entity),
        "event_id": event_id,
        "entity_type": entity.entity_type,
        "raw_value": entity.raw_value,
        "normalized_value": entity.normalized_value,
        "chain": entity.chain,
        "token_resolution_status": entity.token_resolution_status,
        "confidence": entity.confidence,
        "source": entity.source,
        "created_at_ms": created_at_ms,
    }


def _entity_id(event_id: str, entity: TokenEntity) -> str:
    payload = "|".join([event_id, entity.entity_type, entity.normalized_value, entity.chain or ""])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")
