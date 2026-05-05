from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any

from eth_utils import is_address, to_checksum_address

from ..market.gmgn_openapi_client import GmgnTokenInfo
from ..models import TokenSnapshot

EVM_CHAINS = {
    "eth",
    "ethereum",
    "base",
    "bsc",
    "bnb",
    "arbitrum",
    "optimism",
    "polygon",
    "avalanche",
    "evm",
    "evm_unknown",
}
CHAIN_ALIASES = {
    "ethereum": "eth",
    "bnb": "bsc",
    "sol": "solana",
}


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
        chain = _normalize_chain(snapshot.chain)
        address = _normalize_address(snapshot.address, chain)
        symbol = _normalize_symbol(snapshot.symbol)
        token_id = _token_id(chain, address)
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
                chain,
                address,
                symbol,
                snapshot.icon_url,
                event_id,
                received_at_ms,
                now_ms,
                now_ms,
            ),
        )
        self._upsert_alias(
            symbol=symbol,
            token_id=token_id,
            chain=chain,
            address=address,
            source="gmgn_token_payload",
            confidence=1.0,
            now_ms=now_ms,
        )
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
            chain=chain,
            address=address,
            symbol=symbol,
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
        chain = _normalize_chain(info.chain)
        address = _normalize_address(info.address, chain)
        symbol = _normalize_symbol(info.symbol)
        token_id = _token_id(chain, address)
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
                chain,
                address,
                symbol,
                info.name,
                info.icon_url,
                event_id,
                received_at_ms,
                now_ms,
                now_ms,
            ),
        )
        self._upsert_alias(
            symbol=symbol,
            token_id=token_id,
            chain=chain,
            address=address,
            source="gmgn_openapi_token_info",
            confidence=1.0,
            now_ms=now_ms,
        )
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
            chain=chain,
            address=address,
            symbol=symbol,
            candidate_token_ids=[token_id],
        )

    def get_token(self, token_id: str | None) -> dict[str, Any] | None:
        if not token_id:
            return None
        row = self.conn.execute("SELECT * FROM tokens WHERE token_id = ?", (token_id,)).fetchone()
        return _canonical_token_row(dict(row)) if row else None

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
        normalized_chain = _normalize_chain(chain)
        normalized_address = _normalize_address(address, normalized_chain)
        normalized_symbol = _normalize_symbol(symbol or normalized_address)
        token_id = _token_id(normalized_chain, normalized_address)
        identity_status = "unresolved_chain_ca" if normalized_chain == "evm_unknown" else "resolved_ca"
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
            (
                token_id,
                normalized_chain,
                normalized_address,
                normalized_symbol,
                identity_status,
                event_id,
                received_at_ms,
                now_ms,
                now_ms,
            ),
        )
        if symbol and identity_status == "resolved_ca":
            self._upsert_alias(
                symbol=normalized_symbol,
                token_id=token_id,
                chain=normalized_chain,
                address=normalized_address,
                source="co_occurring_ca_symbol",
                confidence=0.95,
                now_ms=now_ms,
            )
        if commit:
            self.conn.commit()
        return TokenIdentity(
            token_id=token_id,
            identity_status=identity_status,
            chain=normalized_chain,
            address=normalized_address,
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

    def market_snapshot_at_or_before(self, token_id: str | None, received_at_ms: int) -> dict[str, Any] | None:
        if not token_id:
            return None
        row = self.conn.execute(
            """
            SELECT * FROM token_market_snapshots
            WHERE token_id = ?
              AND received_at_ms <= ?
            ORDER BY received_at_ms DESC
            LIMIT 1
            """,
            (token_id, received_at_ms),
        ).fetchone()
        return dict(row) if row else None

    def market_snapshot_at_or_after(self, token_id: str | None, received_at_ms: int) -> dict[str, Any] | None:
        if not token_id:
            return None
        row = self.conn.execute(
            """
            SELECT * FROM token_market_snapshots
            WHERE token_id = ?
              AND received_at_ms >= ?
            ORDER BY received_at_ms ASC
            LIMIT 1
            """,
            (token_id, received_at_ms),
        ).fetchone()
        return dict(row) if row else None

    def market_snapshots_between(
        self,
        token_id: str | None,
        *,
        start_ms: int,
        end_ms: int,
    ) -> list[dict[str, Any]]:
        if not token_id:
            return []
        rows = self.conn.execute(
            """
            SELECT * FROM token_market_snapshots
            WHERE token_id = ?
              AND received_at_ms >= ?
              AND received_at_ms <= ?
            ORDER BY received_at_ms ASC
            """,
            (token_id, int(start_ms), int(end_ms)),
        ).fetchall()
        return [dict(row) for row in rows]

    def nearest_market_snapshot(
        self,
        token_id: str | None,
        *,
        target_ms: int,
        tolerance_ms: int,
    ) -> dict[str, Any] | None:
        if not token_id:
            return None
        row = self.conn.execute(
            """
            SELECT *,
                   abs(received_at_ms - ?) AS distance_ms
            FROM token_market_snapshots
            WHERE token_id = ?
              AND received_at_ms >= ?
              AND received_at_ms <= ?
            ORDER BY distance_ms ASC, received_at_ms ASC
            LIMIT 1
            """,
            (
                int(target_ms),
                token_id,
                int(target_ms) - int(tolerance_ms),
                int(target_ms) + int(tolerance_ms),
            ),
        ).fetchone()
        return dict(row) if row else None

    def market_snapshot_for_event(self, *, token_id: str | None, event_id: str) -> dict[str, Any] | None:
        if not token_id:
            return None
        row = self.conn.execute(
            """
            SELECT * FROM token_market_snapshots
            WHERE token_id = ?
              AND event_id = ?
            LIMIT 1
            """,
            (token_id, event_id),
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
        return sorted({_canonical_token_id_from_token_id(str(row["token_id"])) for row in rows})

    def tokens_for_symbol(self, symbol: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT t.*
            FROM token_aliases ta
            JOIN tokens t ON t.token_id = ta.token_id
            WHERE ta.symbol = ?
            ORDER BY ta.confidence DESC, t.first_seen_ms DESC, t.token_id
            """,
            (_normalize_symbol(symbol),),
        ).fetchall()
        by_id: dict[str, dict[str, Any]] = {}
        for row in rows:
            token = _canonical_token_row(dict(row))
            by_id[str(token["token_id"])] = token
        return list(by_id.values())

    def resolve_symbol(self, symbol: str) -> TokenIdentity:
        normalized = _normalize_symbol(symbol)
        aliases = self.aliases_for_symbol(normalized)
        if len(aliases) == 1:
            return TokenIdentity(
                token_id=None,
                identity_status="symbol_only",
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

    def _upsert_alias(
        self,
        *,
        symbol: str,
        token_id: str,
        chain: str,
        address: str,
        source: str,
        confidence: float,
        now_ms: int,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO token_aliases(
              alias_id, symbol, token_id, chain, address, source, confidence, created_at_ms, updated_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, token_id) DO UPDATE SET
              chain = excluded.chain,
              address = excluded.address,
              confidence = excluded.confidence,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                _alias_id(symbol, token_id),
                symbol,
                token_id,
                chain,
                address,
                source,
                confidence,
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


def _normalize_chain(chain: str) -> str:
    normalized = chain.strip().lower()
    return CHAIN_ALIASES.get(normalized, normalized)


def _normalize_address(address: str, chain: str) -> str:
    text = address.strip()
    if chain in EVM_CHAINS and is_address(text):
        return to_checksum_address(text)
    return text


def _token_id(chain: str, address: str) -> str:
    return f"token:{chain}:{address}"


def _canonical_token_id_from_token_id(token_id: str) -> str:
    parsed = _parse_token_id(token_id)
    if parsed is None:
        return token_id
    chain, address = parsed
    return _token_id(chain, _normalize_address(address, chain))


def _canonical_token_row(row: dict[str, Any]) -> dict[str, Any]:
    chain = _normalize_chain(str(row["chain"]))
    address = _normalize_address(str(row["address"]), chain)
    row["chain"] = chain
    row["address"] = address
    row["token_id"] = _token_id(chain, address)
    row["symbol"] = _normalize_symbol(str(row["symbol"]))
    return row


def _parse_token_id(token_id: str) -> tuple[str, str] | None:
    parts = token_id.split(":", 2)
    if len(parts) != 3 or parts[0] != "token":
        return None
    return (_normalize_chain(parts[1]), parts[2])


def _alias_id(symbol: str, token_id: str) -> str:
    return _id("alias", _normalize_symbol(symbol), token_id)


def _snapshot_id(token_id: str, event_id: str) -> str:
    return _id("market", token_id, event_id)


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)
