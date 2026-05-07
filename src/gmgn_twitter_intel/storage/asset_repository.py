from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

MARKET_DATA_CLAUSE = """
(
  price_usd IS NOT NULL
  OR market_cap_usd IS NOT NULL
  OR liquidity_usd IS NOT NULL
  OR volume_24h_usd IS NOT NULL
  OR open_interest_usd IS NOT NULL
  OR holders IS NOT NULL
)
"""
ADDRESS_LIKE_SYMBOL_SQL_RE = r"(^0X[0-9A-F]{20,}$)|(^[A-Z0-9]{32,}(PUMP)?$)"


@dataclass(frozen=True, slots=True)
class AssetResolutionResult:
    asset: dict[str, Any]
    venue: dict[str, Any] | None = None
    aliases: list[dict[str, Any]] = field(default_factory=list)


class AssetRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_cex_instrument(
        self,
        *,
        exchange: str,
        inst_type: str,
        inst_id: str,
        base_symbol: str,
        quote_symbol: str,
        observed_at_ms: int,
        source_payload_hash: str | None = None,
        commit: bool = True,
    ) -> AssetResolutionResult:
        normalized_exchange = _normalize_key(exchange)
        normalized_inst_type = _normalize_symbol(inst_type)
        normalized_inst_id = inst_id.strip().upper()
        normalized_base = _normalize_symbol(base_symbol)
        normalized_quote = _normalize_symbol(quote_symbol)
        asset_id = f"asset:cex:{normalized_base}"
        venue_id = f"venue:cex:{normalized_exchange}:{normalized_inst_type}:{normalized_inst_id}"
        asset = self._upsert_asset(
            asset_id=asset_id,
            asset_type="cex_asset",
            canonical_symbol=normalized_base,
            display_name=normalized_base,
            identity_status="resolved",
            confidence=0.95,
            primary_source=f"{normalized_exchange}_cex",
            first_seen_event_id=None,
            first_seen_at_ms=observed_at_ms,
        )
        self.conn.execute(
            """
            INSERT INTO asset_venues(
              venue_id, asset_id, venue_type, provider, exchange, chain, address,
              inst_id, base_symbol, quote_symbol, inst_type, is_active, confidence,
              source_payload_hash, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, 'cex', %s, %s, NULL, NULL, %s, %s, %s, %s, true, 0.95, %s, %s, %s)
            ON CONFLICT(venue_id) DO UPDATE SET
              is_active = true,
              confidence = excluded.confidence,
              source_payload_hash = COALESCE(excluded.source_payload_hash, asset_venues.source_payload_hash),
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                venue_id,
                asset_id,
                normalized_exchange,
                normalized_exchange,
                normalized_inst_id,
                normalized_base,
                normalized_quote,
                normalized_inst_type,
                source_payload_hash,
                int(observed_at_ms),
                _now_ms(),
            ),
        )
        alias = self._upsert_alias(
            asset_id=asset_id,
            alias_type="symbol",
            alias_value=normalized_base,
            normalized_alias=normalized_base,
            source=f"{normalized_exchange}_cex_instrument",
            confidence=0.95,
            created_at_ms=observed_at_ms,
        )
        if commit:
            self.conn.commit()
        return AssetResolutionResult(asset=asset, venue=self.get_venue(venue_id), aliases=[alias])

    def upsert_dex_asset(
        self,
        *,
        chain: str,
        address: str,
        symbol: str | None,
        observed_at_ms: int,
        event_id: str | None = None,
        provider: str = "deterministic",
        source_payload_hash: str | None = None,
        commit: bool = True,
    ) -> AssetResolutionResult:
        normalized_chain = _normalize_key(chain)
        normalized_address = _normalize_address(address) or address
        normalized_symbol = _normalize_symbol(symbol) if symbol else ""
        asset_id = f"asset:dex:{normalized_chain}:{normalized_address.lower()}"
        venue_id = f"venue:dex:{normalized_chain}:{normalized_address.lower()}"
        incoming_symbol_is_address_like = not normalized_symbol or _is_address_like_symbol(normalized_symbol)
        current_asset = self.get_asset(asset_id)
        if current_asset and incoming_symbol_is_address_like:
            current_symbol = str(current_asset.get("canonical_symbol") or "")
            if current_symbol and not _is_address_like_symbol(current_symbol):
                normalized_symbol = _normalize_symbol(current_symbol)
                incoming_symbol_is_address_like = False
        canonical_symbol = normalized_symbol if not incoming_symbol_is_address_like else normalized_address
        asset = self._upsert_asset(
            asset_id=asset_id,
            asset_type="dex_asset",
            canonical_symbol=canonical_symbol,
            display_name=normalized_symbol if not incoming_symbol_is_address_like else None,
            identity_status="resolved",
            confidence=0.95,
            primary_source=provider,
            first_seen_event_id=event_id,
            first_seen_at_ms=observed_at_ms,
        )
        self.conn.execute(
            """
            INSERT INTO asset_venues(
              venue_id, asset_id, venue_type, provider, exchange, chain, address,
              inst_id, base_symbol, quote_symbol, inst_type, is_active, confidence,
              source_payload_hash, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, 'dex', %s, NULL, %s, %s, NULL, NULL, NULL, NULL, true, 0.95, %s, %s, %s)
            ON CONFLICT(venue_id) DO UPDATE SET
              is_active = true,
              confidence = excluded.confidence,
              source_payload_hash = COALESCE(excluded.source_payload_hash, asset_venues.source_payload_hash),
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                venue_id,
                asset_id,
                provider,
                normalized_chain,
                normalized_address,
                source_payload_hash,
                int(observed_at_ms),
                _now_ms(),
            ),
        )
        aliases = []
        if normalized_symbol and not incoming_symbol_is_address_like:
            aliases.append(
                self._upsert_alias(
                    asset_id=asset_id,
                    alias_type="symbol",
                    alias_value=normalized_symbol,
                    normalized_alias=normalized_symbol,
                    source=provider,
                    confidence=0.95,
                    created_at_ms=observed_at_ms,
                )
            )
        aliases.append(
            self._upsert_alias(
                asset_id=asset_id,
                alias_type="ca",
                alias_value=normalized_address,
                normalized_alias=normalized_address.lower(),
                source=provider,
                confidence=1.0,
                created_at_ms=observed_at_ms,
            )
        )
        if commit:
            self.conn.commit()
        return AssetResolutionResult(asset=asset, venue=self.get_venue(venue_id), aliases=aliases)

    def get_asset(self, asset_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM assets WHERE asset_id = %s", (asset_id,)).fetchone()
        return dict(row) if row else None

    def get_venue(self, venue_id: str | None) -> dict[str, Any] | None:
        if not venue_id:
            return None
        row = self.conn.execute("SELECT * FROM asset_venues WHERE venue_id = %s", (venue_id,)).fetchone()
        return dict(row) if row else None

    def candidates_for_symbol(self, symbol: str) -> list[dict[str, Any]]:
        normalized = _normalize_symbol(symbol)
        rows = self.conn.execute(
            """
            SELECT
              assets.asset_id,
              assets.asset_type,
              assets.canonical_symbol,
              assets.display_name,
              assets.identity_status,
              assets.confidence AS asset_confidence,
              assets.primary_source,
              asset_aliases.alias_id,
              asset_aliases.alias_type,
              asset_aliases.source AS alias_source,
              asset_aliases.confidence AS alias_confidence,
              asset_venues.venue_id,
              asset_venues.venue_type,
              asset_venues.provider AS venue_provider,
              asset_venues.exchange,
              asset_venues.chain,
              asset_venues.address,
              asset_venues.inst_id,
              asset_venues.base_symbol,
              asset_venues.quote_symbol,
              asset_venues.inst_type,
              asset_venues.is_active
            FROM asset_aliases
            JOIN assets ON assets.asset_id = asset_aliases.asset_id
            LEFT JOIN asset_venues
              ON asset_venues.asset_id = assets.asset_id AND asset_venues.is_active = true
            WHERE asset_aliases.alias_type = 'symbol'
              AND asset_aliases.normalized_alias = %s
            ORDER BY
              asset_aliases.confidence DESC,
              assets.confidence DESC,
              CASE asset_venues.venue_type WHEN 'cex' THEN 0 WHEN 'dex' THEN 1 ELSE 2 END,
              CASE
                WHEN asset_venues.venue_type = 'cex'
                  AND asset_venues.inst_type = 'SPOT'
                  AND asset_venues.quote_symbol = 'USDT' THEN 0
                WHEN asset_venues.venue_type = 'cex'
                  AND asset_venues.inst_type = 'SPOT'
                  AND asset_venues.quote_symbol = 'USD' THEN 1
                WHEN asset_venues.venue_type = 'cex'
                  AND asset_venues.inst_type = 'SPOT'
                  AND asset_venues.quote_symbol = 'USDC' THEN 2
                WHEN asset_venues.venue_type = 'cex'
                  AND asset_venues.inst_type = 'SWAP'
                  AND asset_venues.quote_symbol = 'USDT' THEN 3
                WHEN asset_venues.venue_type = 'cex' THEN 4
                ELSE 5
              END,
              asset_venues.inst_id NULLS LAST,
              asset_venues.chain NULLS LAST
            """,
            (normalized,),
        ).fetchall()
        return [dict(row) for row in rows]

    def candidates_for_ca(self, *, chain: str | None, address: str) -> list[dict[str, Any]]:
        normalized_chain = _normalize_key(chain) if chain and chain != "evm_unknown" else None
        normalized_address = (_normalize_address(address) or address).lower()
        clauses = ["asset_venues.venue_type = 'dex'", "lower(asset_venues.address) = %s"]
        params: list[Any] = [normalized_address]
        if normalized_chain:
            clauses.append("asset_venues.chain = %s")
            params.append(normalized_chain)
        rows = self.conn.execute(
            f"""
            SELECT
              assets.asset_id,
              assets.asset_type,
              assets.canonical_symbol,
              assets.display_name,
              assets.identity_status,
              assets.confidence AS asset_confidence,
              assets.primary_source,
              asset_venues.venue_id,
              asset_venues.venue_type,
              asset_venues.provider AS venue_provider,
              asset_venues.exchange,
              asset_venues.chain,
              asset_venues.address,
              asset_venues.inst_id,
              asset_venues.base_symbol,
              asset_venues.quote_symbol,
              asset_venues.inst_type,
              asset_venues.is_active
            FROM asset_venues
            JOIN assets ON assets.asset_id = asset_venues.asset_id
            WHERE {' AND '.join(clauses)}
              AND asset_venues.is_active = true
            ORDER BY asset_venues.confidence DESC, assets.confidence DESC
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def venue_for_cex_instrument(self, *, exchange: str, inst_type: str, inst_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT asset_venues.*, assets.canonical_symbol, assets.identity_status
            FROM asset_venues
            JOIN assets ON assets.asset_id = asset_venues.asset_id
            WHERE asset_venues.venue_type = 'cex'
              AND asset_venues.exchange = %s
              AND asset_venues.inst_type = %s
              AND asset_venues.inst_id = %s
              AND asset_venues.is_active = true
            """,
            (_normalize_key(exchange), _normalize_symbol(inst_type), inst_id.strip().upper()),
        ).fetchone()
        return dict(row) if row else None

    def insert_market_snapshot(
        self,
        *,
        asset_id: str,
        venue_id: str,
        provider: str,
        observed_at_ms: int,
        price_usd: float | None = None,
        market_cap_usd: float | None = None,
        liquidity_usd: float | None = None,
        volume_24h_usd: float | None = None,
        open_interest_usd: float | None = None,
        holders: int | None = None,
        price_change_5m_pct: float | None = None,
        price_change_1h_pct: float | None = None,
        price_change_24h_pct: float | None = None,
        source_payload_hash: str | None = None,
        raw_observation_id: str | None = None,
        created_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        snapshot_id = _stable_id("asset-market", asset_id, venue_id, provider, str(observed_at_ms))
        self.conn.execute(
            """
            INSERT INTO asset_market_snapshots(
              snapshot_id, asset_id, venue_id, provider, observed_at_ms, price_usd,
              market_cap_usd, liquidity_usd, volume_24h_usd, open_interest_usd,
              holders, price_change_5m_pct, price_change_1h_pct, price_change_24h_pct,
              source_payload_hash, raw_observation_id, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(snapshot_id) DO UPDATE SET
              price_usd = excluded.price_usd,
              market_cap_usd = excluded.market_cap_usd,
              liquidity_usd = excluded.liquidity_usd,
              volume_24h_usd = excluded.volume_24h_usd,
              open_interest_usd = excluded.open_interest_usd,
              holders = excluded.holders,
              source_payload_hash = COALESCE(excluded.source_payload_hash, asset_market_snapshots.source_payload_hash)
            """,
            (
                snapshot_id,
                asset_id,
                venue_id,
                provider,
                int(observed_at_ms),
                price_usd,
                market_cap_usd,
                liquidity_usd,
                volume_24h_usd,
                open_interest_usd,
                holders,
                price_change_5m_pct,
                price_change_1h_pct,
                price_change_24h_pct,
                source_payload_hash,
                raw_observation_id,
                int(created_at_ms or _now_ms()),
            ),
        )
        if commit:
            self.conn.commit()
        return self._row_by_id("asset_market_snapshots", "snapshot_id", snapshot_id) or {}

    def market_snapshot_at_or_before(self, asset_id: str | None, observed_at_ms: int) -> dict[str, Any] | None:
        if not asset_id:
            return None
        row = self.conn.execute(
            f"""
            SELECT *
            FROM asset_market_snapshots
            WHERE asset_id = %s AND observed_at_ms <= %s
              AND {MARKET_DATA_CLAUSE}
            ORDER BY observed_at_ms DESC, snapshot_id DESC
            LIMIT 1
            """,
            (asset_id, int(observed_at_ms)),
        ).fetchone()
        return dict(row) if row else None

    def market_snapshot_at_or_after(self, asset_id: str | None, observed_at_ms: int) -> dict[str, Any] | None:
        if not asset_id:
            return None
        row = self.conn.execute(
            f"""
            SELECT *
            FROM asset_market_snapshots
            WHERE asset_id = %s AND observed_at_ms >= %s
              AND {MARKET_DATA_CLAUSE}
            ORDER BY observed_at_ms ASC, snapshot_id ASC
            LIMIT 1
            """,
            (asset_id, int(observed_at_ms)),
        ).fetchone()
        return dict(row) if row else None

    def market_snapshots_between(self, asset_id: str | None, *, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
        if not asset_id:
            return []
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM asset_market_snapshots
            WHERE asset_id = %s AND observed_at_ms BETWEEN %s AND %s
              AND {MARKET_DATA_CLAUSE}
            ORDER BY observed_at_ms ASC, snapshot_id ASC
            """,
            (asset_id, int(start_ms), int(end_ms)),
        ).fetchall()
        return [dict(row) for row in rows]

    def nearest_market_snapshot(
        self,
        asset_id: str | None,
        *,
        target_ms: int,
        tolerance_ms: int,
    ) -> dict[str, Any] | None:
        if not asset_id:
            return None
        row = self.conn.execute(
            f"""
            SELECT *,
                   ABS(observed_at_ms - %s) AS distance_ms
            FROM asset_market_snapshots
            WHERE asset_id = %s
              AND observed_at_ms BETWEEN %s AND %s
              AND {MARKET_DATA_CLAUSE}
            ORDER BY distance_ms ASC, observed_at_ms ASC, snapshot_id ASC
            LIMIT 1
            """,
            (int(target_ms), asset_id, int(target_ms - tolerance_ms), int(target_ms + tolerance_ms)),
        ).fetchone()
        return dict(row) if row else None

    def _upsert_asset(
        self,
        *,
        asset_id: str,
        asset_type: str,
        canonical_symbol: str,
        display_name: str | None,
        identity_status: str,
        confidence: float,
        primary_source: str,
        first_seen_event_id: str | None,
        first_seen_at_ms: int,
    ) -> dict[str, Any]:
        self.conn.execute(
            """
            INSERT INTO assets(
              asset_id, asset_type, canonical_symbol, display_name, identity_status,
              confidence, primary_source, first_seen_event_id, first_seen_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(asset_id) DO UPDATE SET
              canonical_symbol = excluded.canonical_symbol,
              display_name = COALESCE(excluded.display_name, assets.display_name),
              identity_status = excluded.identity_status,
              confidence = GREATEST(assets.confidence, excluded.confidence),
              primary_source = CASE
                WHEN excluded.confidence >= assets.confidence THEN excluded.primary_source
                ELSE assets.primary_source
              END,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                asset_id,
                asset_type,
                _normalize_symbol(canonical_symbol),
                display_name,
                identity_status,
                float(confidence),
                primary_source,
                first_seen_event_id,
                int(first_seen_at_ms),
                _now_ms(),
            ),
        )
        return self.get_asset(asset_id) or {}

    def _upsert_alias(
        self,
        *,
        asset_id: str,
        alias_type: str,
        alias_value: str,
        normalized_alias: str,
        source: str,
        confidence: float,
        created_at_ms: int,
    ) -> dict[str, Any]:
        alias_id = _stable_id("asset-alias", alias_type, normalized_alias, asset_id, source)
        self.conn.execute(
            """
            INSERT INTO asset_aliases(
              alias_id, asset_id, alias_type, alias_value, normalized_alias,
              source, confidence, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(alias_type, normalized_alias, asset_id, source) DO UPDATE SET
              alias_value = excluded.alias_value,
              confidence = GREATEST(asset_aliases.confidence, excluded.confidence)
            """,
            (
                alias_id,
                asset_id,
                alias_type,
                alias_value,
                normalized_alias,
                source,
                float(confidence),
                int(created_at_ms),
            ),
        )
        return self._row_by_id("asset_aliases", "alias_id", alias_id) or {}

    def _row_by_id(self, table: str, column: str, value: str) -> dict[str, Any] | None:
        row = self.conn.execute(f"SELECT * FROM {table} WHERE {column} = %s", (value,)).fetchone()
        return dict(row) if row else None


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _is_address_like_symbol(symbol: str | None) -> bool:
    if not symbol:
        return False
    value = symbol.strip().upper()
    if value.startswith("0X") and len(value) >= 22:
        return all(char in "0123456789ABCDEF" for char in value[2:])
    if len(value) < 32:
        return False
    if value.endswith("PUMP"):
        value = value[:-4]
    return all(char.isdigit() or ("A" <= char <= "Z") for char in value)


def _normalize_key(value: str) -> str:
    return value.strip().lower()


def _normalize_address(address: str | None) -> str | None:
    if not address:
        return None
    return address.strip()


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _stable_id(prefix: str, *parts: str) -> str:
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _field(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value[name]
    return getattr(value, name)
