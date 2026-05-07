from __future__ import annotations

import hashlib
from typing import Any


class RegistryRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_cex_token(
        self,
        *,
        base_symbol: str,
        project_id: str | None,
        source: str,
        observed_at_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        symbol = _symbol(base_symbol)
        cex_token_id = f"cex_token:{symbol}"
        self.conn.execute(
            """
            INSERT INTO cex_tokens(
              cex_token_id, project_id, base_symbol, status, evidence_level,
              first_seen_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, 'canonical', %s, %s, %s)
            ON CONFLICT(cex_token_id) DO UPDATE SET
              project_id = COALESCE(excluded.project_id, cex_tokens.project_id),
              base_symbol = excluded.base_symbol,
              status = 'canonical',
              evidence_level = excluded.evidence_level,
              updated_at_ms = excluded.updated_at_ms
            """,
            (cex_token_id, project_id, symbol, source, int(observed_at_ms), int(observed_at_ms)),
        )
        if commit:
            self.conn.commit()
        return self._row_by_id("cex_tokens", "cex_token_id", cex_token_id) or {}

    def upsert_chain_asset(
        self,
        *,
        chain_id: str,
        address: str,
        symbol: str | None,
        name: str | None,
        decimals: int | None,
        source: str,
        observed_at_ms: int,
        project_id: str | None = None,
        token_standard: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        normalized_chain = _chain(chain_id)
        normalized_address = _address(address)
        standard = token_standard or ("erc20" if normalized_chain.startswith("eip155:") else "token")
        asset_id = f"asset:{normalized_chain}:{standard}:{normalized_address}"
        self.conn.execute(
            """
            INSERT INTO registry_assets(
              asset_id, project_id, chain_id, token_standard, address, symbol, name, decimals,
              status, evidence_level, primary_source, first_seen_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'candidate', 'price_observation', %s, %s, %s)
            ON CONFLICT(asset_id) DO UPDATE SET
              project_id = COALESCE(excluded.project_id, registry_assets.project_id),
              symbol = COALESCE(excluded.symbol, registry_assets.symbol),
              name = COALESCE(excluded.name, registry_assets.name),
              decimals = COALESCE(excluded.decimals, registry_assets.decimals),
              evidence_level = excluded.evidence_level,
              primary_source = excluded.primary_source,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                asset_id,
                project_id,
                normalized_chain,
                standard,
                normalized_address,
                _symbol(symbol) if symbol else None,
                name,
                decimals,
                source,
                int(observed_at_ms),
                int(observed_at_ms),
            ),
        )
        if commit:
            self.conn.commit()
        return self._row_by_id("registry_assets", "asset_id", asset_id) or {}

    def upsert_pricefeed(
        self,
        *,
        feed_type: str,
        provider: str,
        subject_type: str,
        subject_id: str,
        observed_at_ms: int,
        native_market_id: str | None = None,
        chain_id: str | None = None,
        address: str | None = None,
        base_asset_id: str | None = None,
        base_cex_token_id: str | None = None,
        base_project_id: str | None = None,
        base_symbol: str | None = None,
        quote_symbol: str | None = None,
        multiplier: Any = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        normalized_feed_type = feed_type.strip().lower()
        normalized_provider = provider.strip().lower()
        normalized_market = native_market_id.strip().upper() if native_market_id else None
        normalized_chain = _chain(chain_id) if chain_id else None
        normalized_address = _address(address) if address else None
        pricefeed_id = _pricefeed_id(
            feed_type=normalized_feed_type,
            provider=normalized_provider,
            native_market_id=normalized_market,
            chain_id=normalized_chain,
            address=normalized_address,
        )
        self.conn.execute(
            """
            INSERT INTO price_feeds(
              pricefeed_id, feed_type, provider, subject_type, subject_id, chain_id, address,
              native_market_id, base_asset_id, base_cex_token_id, base_project_id, base_symbol,
              quote_symbol, multiplier, status, evidence_level, first_seen_at_ms, updated_at_ms
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              'canonical', 'price_observation', %s, %s
            )
            ON CONFLICT(pricefeed_id) DO UPDATE SET
              subject_type = excluded.subject_type,
              subject_id = excluded.subject_id,
              base_asset_id = COALESCE(excluded.base_asset_id, price_feeds.base_asset_id),
              base_cex_token_id = COALESCE(excluded.base_cex_token_id, price_feeds.base_cex_token_id),
              base_project_id = COALESCE(excluded.base_project_id, price_feeds.base_project_id),
              base_symbol = COALESCE(excluded.base_symbol, price_feeds.base_symbol),
              quote_symbol = COALESCE(excluded.quote_symbol, price_feeds.quote_symbol),
              multiplier = COALESCE(excluded.multiplier, price_feeds.multiplier),
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                pricefeed_id,
                normalized_feed_type,
                normalized_provider,
                subject_type,
                subject_id,
                normalized_chain,
                normalized_address,
                normalized_market,
                base_asset_id,
                base_cex_token_id,
                base_project_id,
                _symbol(base_symbol) if base_symbol else None,
                quote_symbol.upper() if quote_symbol else None,
                multiplier,
                int(observed_at_ms),
                int(observed_at_ms),
            ),
        )
        if commit:
            self.conn.commit()
        return self._row_by_id("price_feeds", "pricefeed_id", pricefeed_id) or {}

    def find_cex_token(self, base_symbol: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM cex_tokens
            WHERE base_symbol = %s AND status IN ('candidate', 'canonical')
            """,
            (_symbol(base_symbol),),
        ).fetchone()
        return dict(row) if row else None

    def find_assets_by_address(self, *, chain_id: str | None, address: str) -> list[dict[str, Any]]:
        clauses = ["lower(address) = %s", "status IN ('candidate', 'canonical')"]
        params: list[Any] = [_address_lookup(address)]
        if chain_id:
            clauses.append("chain_id = %s")
            params.append(_chain(chain_id))
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM registry_assets
            WHERE {" AND ".join(clauses)}
            ORDER BY updated_at_ms DESC, asset_id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def find_assets_by_symbol_with_latest_observation(self, symbol: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              registry_assets.*,
              latest_price.price_usd,
              latest_price.market_cap_usd,
              latest_price.liquidity_usd,
              latest_price.volume_24h_usd,
              latest_price.holders,
              latest_price.observed_at_ms
            FROM registry_assets
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_observations
              WHERE price_observations.subject_type = 'Asset'
                AND price_observations.subject_id = registry_assets.asset_id
              ORDER BY observed_at_ms DESC, observation_id DESC
              LIMIT 1
            ) latest_price ON true
            WHERE registry_assets.symbol = %s
              AND registry_assets.status IN ('candidate', 'canonical')
            ORDER BY latest_price.market_cap_usd DESC NULLS LAST, registry_assets.asset_id
            """,
            (_symbol(symbol),),
        ).fetchall()
        return [dict(row) for row in rows]

    def find_cex_pricefeed(self, *, exchange: str, native_market_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM price_feeds
            WHERE provider = %s AND native_market_id = %s AND feed_type LIKE 'cex_%%'
            ORDER BY updated_at_ms DESC
            LIMIT 1
            """,
            (exchange.strip().lower(), native_market_id.strip().upper()),
        ).fetchone()
        return dict(row) if row else None

    def find_preferred_cex_pricefeed(self, base_symbol: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM price_feeds
            WHERE subject_type = 'CexToken'
              AND base_symbol = %s
              AND feed_type LIKE 'cex_%%'
              AND status IN ('candidate', 'canonical')
            ORDER BY
              CASE
                WHEN feed_type = 'cex_spot' THEN 0
                WHEN feed_type = 'cex_swap' THEN 1
                ELSE 2
              END,
              CASE
                WHEN quote_symbol = 'USDT' THEN 0
                WHEN quote_symbol = 'USD' THEN 1
                WHEN quote_symbol = 'USDC' THEN 2
                ELSE 9
              END,
              updated_at_ms DESC,
              native_market_id ASC
            LIMIT 1
            """,
            (_symbol(base_symbol),),
        ).fetchone()
        return dict(row) if row else None

    def chain_assets_needing_price_refresh(self, *, stale_before_ms: int, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              registry_assets.*,
              latest_price.observed_at_ms AS latest_price_observed_at_ms,
              latest_price.market_cap_usd,
              latest_price.liquidity_usd,
              latest_price.volume_24h_usd,
              latest_price.open_interest_usd,
              latest_price.holders
            FROM registry_assets
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_observations
              WHERE price_observations.subject_type = 'Asset'
                AND price_observations.subject_id = registry_assets.asset_id
              ORDER BY observed_at_ms DESC, observation_id DESC
              LIMIT 1
            ) latest_price ON true
            WHERE registry_assets.status IN ('candidate', 'canonical')
              AND (
                latest_price.observed_at_ms IS NULL
                OR latest_price.observed_at_ms < %s
              )
            ORDER BY COALESCE(latest_price.observed_at_ms, 0) ASC, registry_assets.updated_at_ms DESC
            LIMIT %s
            """,
            (int(stale_before_ms), max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def _row_by_id(self, table: str, key: str, value: str) -> dict[str, Any] | None:
        row = self.conn.execute(f"SELECT * FROM {table} WHERE {key} = %s", (value,)).fetchone()
        return dict(row) if row else None


def _pricefeed_id(
    *,
    feed_type: str,
    provider: str,
    native_market_id: str | None,
    chain_id: str | None,
    address: str | None,
) -> str:
    if native_market_id:
        market_type = feed_type.removeprefix("cex_")
        return f"pricefeed:cex:{provider}:{market_type}:{native_market_id}"
    if chain_id and address:
        return f"pricefeed:dex-token:{provider}:{chain_id}:{address}"
    return "pricefeed:" + hashlib.sha256(
        "|".join([feed_type, provider, native_market_id or "", chain_id or "", address or ""]).encode("utf-8")
    ).hexdigest()


def _symbol(value: str | None) -> str:
    return str(value or "").strip().lstrip("$").upper()


def _chain(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"eth", "ethereum"}:
        return "eip155:1"
    if normalized in {"base"}:
        return "eip155:8453"
    if normalized in {"bsc", "bnb"}:
        return "eip155:56"
    if normalized in {"sol", "solana"}:
        return "solana"
    return normalized


def _address(value: str) -> str:
    text = value.strip()
    return text.lower() if text.startswith(("0x", "0X")) else text


def _address_lookup(value: str) -> str:
    return value.strip().lower()
