from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..collector.gmgn_token_payload import parse_gmgn_token_payload
from ..storage.signal_repository import SignalRepository
from ..storage.sqlite_client import transaction
from ..storage.token_repository import TokenRepository
from .token_identity_resolver import TokenMention


@dataclass(frozen=True, slots=True)
class TokenBackfillResult:
    token_payload_events: int
    entity_events: int
    mentions_inserted: int


class TokenBackfillService:
    def __init__(self, *, tokens: TokenRepository, signals: SignalRepository):
        self.tokens = tokens
        self.signals = signals

    def backfill_existing_events(self) -> TokenBackfillResult:
        with transaction(self.tokens.conn):
            token_payload_events, token_payload_mentions = self._backfill_gmgn_token_payloads()
            entity_events, entity_mentions = self._backfill_entity_mentions()
        return TokenBackfillResult(
            token_payload_events=token_payload_events,
            entity_events=entity_events,
            mentions_inserted=token_payload_mentions + entity_mentions,
        )

    def _backfill_gmgn_token_payloads(self) -> tuple[int, int]:
        rows = self.tokens.conn.execute(
            """
            SELECT
              e.event_id,
              e.channel,
              e.raw_json,
              e.received_at_ms,
              e.author_handle,
              e.author_followers,
              e.is_watched
            FROM events e
            WHERE e.channel = 'twitter_monitor_token'
              AND e.raw_json IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM event_token_mentions etm
                WHERE etm.event_id = e.event_id
              )
            ORDER BY e.received_at_ms ASC, e.event_id ASC
            """
        ).fetchall()
        events = 0
        inserted = 0
        for row in rows:
            raw = _json_loads(row["raw_json"])
            if not isinstance(raw, dict):
                continue
            snapshot = parse_gmgn_token_payload(raw)
            if snapshot is None:
                continue
            identity = self.tokens.upsert_snapshot(
                event_id=str(row["event_id"]),
                snapshot=snapshot,
                received_at_ms=int(row["received_at_ms"]),
                source_channel=str(row["channel"]),
                commit=False,
            )
            mention = TokenMention(
                identity_key=identity.token_id or f"symbol:{identity.symbol}",
                token_id=identity.token_id,
                identity_status=identity.identity_status,
                chain=identity.chain,
                address=identity.address,
                symbol=identity.symbol or snapshot.symbol,
                source="gmgn_token_payload_backfill",
            )
            inserted += self.signals.insert_event_token_mentions(
                event_id=str(row["event_id"]),
                token_mentions=[mention],
                received_at_ms=int(row["received_at_ms"]),
                author_handle=row["author_handle"],
                author_followers=row["author_followers"],
                is_watched=bool(row["is_watched"]),
                commit=False,
            )
            events += 1
        return events, inserted

    def _backfill_entity_mentions(self) -> tuple[int, int]:
        rows = self.tokens.conn.execute(
            """
            SELECT
              ee.event_id,
              ee.entity_type,
              ee.normalized_value,
              ee.chain,
              ee.source,
              ee.received_at_ms,
              ee.author_handle,
              ee.is_watched,
              e.author_followers,
              symbol_lookup.symbol
            FROM event_entities ee
            JOIN events e ON e.event_id = ee.event_id
            LEFT JOIN (
              SELECT event_id, normalized_value AS symbol
              FROM event_entities
              WHERE entity_type = 'symbol'
              GROUP BY event_id
              HAVING COUNT(*) = 1
            ) symbol_lookup ON symbol_lookup.event_id = ee.event_id
            WHERE ee.entity_type IN ('ca', 'symbol')
              AND NOT EXISTS (
                SELECT 1 FROM event_token_mentions etm
                WHERE etm.event_id = ee.event_id
              )
            ORDER BY ee.received_at_ms ASC, ee.event_id ASC
            """
        ).fetchall()
        event_ids: set[str] = set()
        inserted = 0
        for row in rows:
            mention = self._mention_from_entity_row(dict(row))
            if mention is None:
                continue
            inserted += self.signals.insert_event_token_mentions(
                event_id=str(row["event_id"]),
                token_mentions=[mention],
                received_at_ms=int(row["received_at_ms"]),
                author_handle=row["author_handle"],
                author_followers=row["author_followers"],
                is_watched=bool(row["is_watched"]),
                commit=False,
            )
            event_ids.add(str(row["event_id"]))
        return len(event_ids), inserted

    def _mention_from_entity_row(self, row: dict[str, Any]) -> TokenMention | None:
        if row["entity_type"] == "ca":
            identity = self.tokens.upsert_ca(
                event_id=str(row["event_id"]),
                chain=str(row["chain"] or "unknown"),
                address=str(row["normalized_value"]),
                symbol=row.get("symbol"),
                received_at_ms=int(row["received_at_ms"]),
                commit=False,
            )
            return TokenMention(
                identity_key=identity.token_id or f"symbol:{identity.symbol}",
                token_id=identity.token_id,
                identity_status=identity.identity_status,
                chain=identity.chain,
                address=identity.address,
                symbol=identity.symbol or str(row["normalized_value"]),
                source=str(row["source"] or "entity_backfill"),
            )

        if row["entity_type"] != "symbol":
            return None
        identity = self.tokens.resolve_symbol(str(row["normalized_value"]))
        if identity.token_id:
            return TokenMention(
                identity_key=identity.token_id,
                token_id=identity.token_id,
                identity_status=identity.identity_status,
                chain=identity.chain,
                address=identity.address,
                symbol=identity.symbol or str(row["normalized_value"]),
                source=str(row["source"] or "entity_backfill"),
            )
        symbol = str(row["normalized_value"])
        return TokenMention(
            identity_key=f"symbol:{symbol}",
            token_id=None,
            identity_status=identity.identity_status,
            chain=None,
            address=None,
            symbol=symbol,
            source=str(row["source"] or "entity_backfill"),
        )


def _json_loads(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None
