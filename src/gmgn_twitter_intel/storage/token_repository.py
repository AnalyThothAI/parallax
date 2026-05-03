from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any

from ..market.gmgn_openapi_client import GmgnTokenInfo
from ..models import TokenSnapshot


@dataclass(frozen=True, slots=True)
class TokenIdentity:
    token_id: str | None
    identity_status: str
    chain: str | None = None
    address: str | None = None
    symbol: str | None = None
    candidate_token_ids: list[str] = field(default_factory=list)


class TokenRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert_snapshot(
        self,
        *,
        event_id: str,
        snapshot: TokenSnapshot,
        received_at_ms: int,
        source_channel: str,
        commit: bool = True,
    ) -> TokenIdentity:
        token_id = _token_id(snapshot.chain, snapshot.address)
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO tokens(
              token_id, chain, address, symbol, name, icon_url, identity_status,
              first_seen_event_id, first_seen_ms, created_at_ms, updated_at_ms
            )
            VALUES (?, ?, ?, ?, NULL, ?, 'resolved_ca', ?, ?, ?, ?)
            ON CONFLICT(chain, address) DO UPDATE SET
              symbol = excluded.symbol,
              icon_url = COALESCE(excluded.icon_url, tokens.icon_url),
              identity_status = 'resolved_ca',
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                token_id,
                snapshot.chain,
                snapshot.address,
                snapshot.symbol,
                snapshot.icon_url,
                event_id,
                received_at_ms,
                now_ms,
                now_ms,
            ),
        )
        self._upsert_alias(snapshot=snapshot, token_id=token_id, now_ms=now_ms)
        self._upsert_market_snapshot(
            event_id=event_id,
            token_id=token_id,
            snapshot=snapshot,
            received_at_ms=received_at_ms,
            source_channel=source_channel,
            now_ms=now_ms,
        )
        if commit:
            self.conn.commit()
        return TokenIdentity(
            token_id=token_id,
            identity_status="resolved_ca",
            chain=snapshot.chain,
            address=snapshot.address,
            symbol=snapshot.symbol,
            candidate_token_ids=[token_id],
        )

    def upsert_openapi_token_info(
        self,
        *,
        event_id: str,
        info: GmgnTokenInfo,
        received_at_ms: int,
        source_channel: str,
        commit: bool = True,
    ) -> TokenIdentity:
        token_id = _token_id(info.chain, info.address)
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO tokens(
              token_id, chain, address, symbol, name, icon_url, identity_status,
              first_seen_event_id, first_seen_ms, created_at_ms, updated_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, 'resolved_ca', ?, ?, ?, ?)
            ON CONFLICT(chain, address) DO UPDATE SET
              symbol = excluded.symbol,
              name = COALESCE(excluded.name, tokens.name),
              icon_url = COALESCE(excluded.icon_url, tokens.icon_url),
              identity_status = 'resolved_ca',
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                token_id,
                info.chain,
                info.address,
                info.symbol,
                info.name,
                info.icon_url,
                event_id,
                received_at_ms,
                now_ms,
                now_ms,
            ),
        )
        self._upsert_openapi_alias(info=info, token_id=token_id, now_ms=now_ms)
        self._upsert_openapi_market_snapshot(
            event_id=event_id,
            token_id=token_id,
            info=info,
            received_at_ms=received_at_ms,
            source_channel=source_channel,
            now_ms=now_ms,
        )
        if commit:
            self.conn.commit()
        return TokenIdentity(
            token_id=token_id,
            identity_status="resolved_ca",
            chain=info.chain,
            address=info.address,
            symbol=info.symbol,
            candidate_token_ids=[token_id],
        )

    def get_token(self, token_id: str | None) -> dict[str, Any] | None:
        if not token_id:
            return None
        row = self.conn.execute("SELECT * FROM tokens WHERE token_id = ?", (token_id,)).fetchone()
        return dict(row) if row else None

    def upsert_ca(
        self,
        *,
        event_id: str,
        chain: str,
        address: str,
        symbol: str | None,
        received_at_ms: int,
        commit: bool = True,
    ) -> TokenIdentity:
        normalized_symbol = _normalize_symbol(symbol or address)
        token_id = _token_id(chain, address)
        identity_status = "unresolved_chain_ca" if chain == "evm_unknown" else "resolved_ca"
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO tokens(
              token_id, chain, address, symbol, name, icon_url, identity_status,
              first_seen_event_id, first_seen_ms, created_at_ms, updated_at_ms
            )
            VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?)
            ON CONFLICT(chain, address) DO UPDATE SET
              symbol = CASE
                WHEN tokens.symbol = tokens.address THEN excluded.symbol
                ELSE tokens.symbol
              END,
              identity_status = excluded.identity_status,
              updated_at_ms = excluded.updated_at_ms
            """,
            (token_id, chain, address, normalized_symbol, identity_status, event_id, received_at_ms, now_ms, now_ms),
        )
        if symbol and identity_status == "resolved_ca":
            self.conn.execute(
                """
                INSERT INTO token_aliases(
                  alias_id, symbol, token_id, chain, address, source, confidence, created_at_ms, updated_at_ms
                )
                VALUES (?, ?, ?, ?, ?, 'co_occurring_ca_symbol', 0.95, ?, ?)
                ON CONFLICT(symbol, token_id) DO UPDATE SET
                  confidence = MAX(token_aliases.confidence, excluded.confidence),
                  updated_at_ms = excluded.updated_at_ms
                """,
                (_alias_id(normalized_symbol, token_id), normalized_symbol, token_id, chain, address, now_ms, now_ms),
            )
        if commit:
            self.conn.commit()
        return TokenIdentity(
            token_id=token_id,
            identity_status=identity_status,
            chain=chain,
            address=address,
            symbol=normalized_symbol,
            candidate_token_ids=[token_id],
        )

    def latest_market_snapshot(self, token_id: str | None) -> dict[str, Any] | None:
        if not token_id:
            return None
        row = self.conn.execute(
            """
            SELECT * FROM token_market_snapshots
            WHERE token_id = ?
            ORDER BY received_at_ms DESC
            LIMIT 1
            """,
            (token_id,),
        ).fetchone()
        return dict(row) if row else None

    def aliases_for_symbol(self, symbol: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT token_id FROM token_aliases
            WHERE symbol = ?
            ORDER BY token_id
            """,
            (_normalize_symbol(symbol),),
        ).fetchall()
        return [str(row["token_id"]) for row in rows]

    def resolve_symbol(self, symbol: str) -> TokenIdentity:
        normalized = _normalize_symbol(symbol)
        aliases = self.aliases_for_symbol(normalized)
        if len(aliases) == 1:
            token = self.get_token(aliases[0])
            return TokenIdentity(
                token_id=aliases[0],
                identity_status="resolved_alias",
                chain=token.get("chain") if token else None,
                address=token.get("address") if token else None,
                symbol=normalized,
                candidate_token_ids=aliases,
            )
        if len(aliases) > 1:
            return TokenIdentity(
                token_id=None,
                identity_status="ambiguous_symbol",
                symbol=normalized,
                candidate_token_ids=aliases,
            )
        return TokenIdentity(token_id=None, identity_status="unresolved_symbol", symbol=normalized)

    def _upsert_alias(self, *, snapshot: TokenSnapshot, token_id: str, now_ms: int) -> None:
        self.conn.execute(
            """
            INSERT INTO token_aliases(
              alias_id, symbol, token_id, chain, address, source, confidence, created_at_ms, updated_at_ms
            )
            VALUES (?, ?, ?, ?, ?, 'gmgn_token_payload', 1.0, ?, ?)
            ON CONFLICT(symbol, token_id) DO UPDATE SET
              chain = excluded.chain,
              address = excluded.address,
              confidence = excluded.confidence,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                _alias_id(snapshot.symbol, token_id),
                snapshot.symbol,
                token_id,
                snapshot.chain,
                snapshot.address,
                now_ms,
                now_ms,
            ),
        )

    def _upsert_market_snapshot(
        self,
        *,
        event_id: str,
        token_id: str,
        snapshot: TokenSnapshot,
        received_at_ms: int,
        source_channel: str,
        now_ms: int,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO token_market_snapshots(
              snapshot_id, token_id, event_id, price, previous_price, market_cap,
              source_channel, received_at_ms, raw_json, created_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(token_id, event_id) DO UPDATE SET
              price = excluded.price,
              previous_price = excluded.previous_price,
              market_cap = excluded.market_cap,
              source_channel = excluded.source_channel,
              received_at_ms = excluded.received_at_ms,
              raw_json = excluded.raw_json
            """,
            (
                _snapshot_id(token_id, event_id),
                token_id,
                event_id,
                snapshot.price,
                snapshot.previous_price,
                snapshot.market_cap,
                source_channel,
                received_at_ms,
                json.dumps(snapshot.raw, ensure_ascii=False, sort_keys=True),
                now_ms,
            ),
        )

    def _upsert_openapi_alias(self, *, info: GmgnTokenInfo, token_id: str, now_ms: int) -> None:
        self.conn.execute(
            """
            INSERT INTO token_aliases(
              alias_id, symbol, token_id, chain, address, source, confidence, created_at_ms, updated_at_ms
            )
            VALUES (?, ?, ?, ?, ?, 'gmgn_openapi_token_info', 1.0, ?, ?)
            ON CONFLICT(symbol, token_id) DO UPDATE SET
              chain = excluded.chain,
              address = excluded.address,
              confidence = excluded.confidence,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                _alias_id(info.symbol, token_id),
                info.symbol,
                token_id,
                info.chain,
                info.address,
                now_ms,
                now_ms,
            ),
        )

    def _upsert_openapi_market_snapshot(
        self,
        *,
        event_id: str,
        token_id: str,
        info: GmgnTokenInfo,
        received_at_ms: int,
        source_channel: str,
        now_ms: int,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO token_market_snapshots(
              snapshot_id, token_id, event_id, price, previous_price, market_cap,
              source_channel, received_at_ms, raw_json, created_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(token_id, event_id) DO UPDATE SET
              price = excluded.price,
              previous_price = excluded.previous_price,
              market_cap = excluded.market_cap,
              source_channel = excluded.source_channel,
              received_at_ms = excluded.received_at_ms,
              raw_json = excluded.raw_json
            """,
            (
                _snapshot_id(token_id, event_id),
                token_id,
                event_id,
                info.price,
                info.previous_price,
                info.market_cap,
                source_channel,
                received_at_ms,
                json.dumps(info.raw, ensure_ascii=False, sort_keys=True),
                now_ms,
            ),
        )


def _normalize_symbol(symbol: str) -> str:
    text = symbol.strip().lstrip("$")
    return text.upper() if text.isascii() else text


def _token_id(chain: str, address: str) -> str:
    return f"token:{chain}:{address}"


def _alias_id(symbol: str, token_id: str) -> str:
    return _id("alias", _normalize_symbol(symbol), token_id)


def _snapshot_id(token_id: str, event_id: str) -> str:
    return _id("market", token_id, event_id)


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)
