from __future__ import annotations

import hashlib
from typing import Any

from psycopg.types.json import Jsonb


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
        observed_at_ms: int,
        project_id: str | None = None,
        token_standard: str | None = None,
        status: str = "candidate",
        commit: bool = True,
    ) -> dict[str, Any]:
        normalized_chain = _chain(chain_id)
        normalized_address = _address(address)
        standard = token_standard or ("erc20" if normalized_chain.startswith("eip155:") else "token")
        asset_id = f"asset:{normalized_chain}:{standard}:{normalized_address}"
        self.conn.execute(
            """
            INSERT INTO registry_assets(
              asset_id, project_id, chain_id, token_standard, address, status, first_seen_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(asset_id) DO UPDATE SET
              project_id = COALESCE(excluded.project_id, registry_assets.project_id),
              status = CASE
                WHEN registry_assets.status = 'demoted_search' THEN 'candidate'
                ELSE registry_assets.status
              END,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                asset_id,
                project_id,
                normalized_chain,
                standard,
                normalized_address,
                status,
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

    def upsert_us_equity_symbol(
        self,
        *,
        symbol: str,
        exchange: str | None,
        security_name: str | None,
        instrument_type: str,
        source: str,
        source_updated_at_ms: int,
        raw_payload: dict[str, Any] | None,
        observed_at_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        normalized_symbol = _symbol(symbol)
        market_instrument_id = f"market_instrument:us_equity:{normalized_symbol}"
        self.conn.execute(
            """
            INSERT INTO us_equity_symbols(
              symbol, market_instrument_id, exchange, security_name, instrument_type, status, source,
              source_updated_at_ms, raw_payload_json, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, 'active', %s, %s, %s, %s, %s)
            ON CONFLICT(symbol) DO UPDATE SET
              market_instrument_id = excluded.market_instrument_id,
              exchange = excluded.exchange,
              security_name = excluded.security_name,
              instrument_type = excluded.instrument_type,
              status = 'active',
              source = excluded.source,
              source_updated_at_ms = excluded.source_updated_at_ms,
              raw_payload_json = excluded.raw_payload_json,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                normalized_symbol,
                market_instrument_id,
                _optional_text(exchange),
                _optional_text(security_name),
                str(instrument_type or "equity").strip().lower() or "equity",
                source,
                int(source_updated_at_ms),
                Jsonb(raw_payload or {}),
                int(observed_at_ms),
                int(observed_at_ms),
            ),
        )
        if commit:
            self.conn.commit()
        return self._row_by_id("us_equity_symbols", "symbol", normalized_symbol) or {}

    def find_us_equity_symbol(self, symbol: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM us_equity_symbols
            WHERE symbol = %s AND status = 'active'
            """,
            (_symbol(symbol),),
        ).fetchone()
        return dict(row) if row else None

    def deactivate_missing_us_equity_symbols(
        self,
        *,
        source: str,
        active_symbols: set[str],
        observed_at_ms: int,
        commit: bool = True,
    ) -> int:
        normalized_symbols = sorted({_symbol(symbol) for symbol in active_symbols if _symbol(symbol)})
        if normalized_symbols:
            row = self.conn.execute(
                """
                UPDATE us_equity_symbols
                SET status = 'inactive', updated_at_ms = %s
                WHERE source = %s
                  AND status = 'active'
                  AND NOT (symbol = ANY(%s))
                RETURNING symbol
                """,
                (int(observed_at_ms), source, normalized_symbols),
            ).fetchall()
        else:
            row = self.conn.execute(
                """
                UPDATE us_equity_symbols
                SET status = 'inactive', updated_at_ms = %s
                WHERE source = %s
                  AND status = 'active'
                RETURNING symbol
                """,
                (int(observed_at_ms), source),
            ).fetchall()
        if commit:
            self.conn.commit()
        return len(row)

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

    def find_assets_by_symbol_with_identity_metadata(self, symbol: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              registry_assets.*,
              asset_identity_current.canonical_symbol AS symbol,
              asset_identity_current.canonical_name AS name,
              asset_identity_current.decimals,
              asset_identity_current.identity_confidence,
              identity_metadata.raw_payload_json AS identity_raw_payload_json,
              identity_metadata.observed_at_ms AS observed_at_ms,
              identity_metadata.observed_at_ms AS identity_metadata_observed_at_ms,
              identity_metadata.provider AS identity_metadata_provider
            FROM registry_assets
            LEFT JOIN LATERAL (
              SELECT raw_payload_json, observed_at_ms, provider
              FROM asset_identity_evidence
              WHERE asset_identity_evidence.asset_id = registry_assets.asset_id
                AND asset_identity_evidence.provider = 'okx'
                AND asset_identity_evidence.lookup_mode IN ('symbol_search', 'exact_address')
              ORDER BY observed_at_ms DESC, evidence_id DESC
              LIMIT 1
            ) identity_metadata ON true
            JOIN asset_identity_current
              ON asset_identity_current.asset_id = registry_assets.asset_id
            WHERE asset_identity_current.canonical_symbol = %s
              AND registry_assets.status IN ('candidate', 'canonical')
            ORDER BY registry_assets.asset_id
            """,
            (_symbol(symbol),),
        ).fetchall()
        assets = [_with_identity_metadata(dict(row)) for row in rows]
        return sorted(assets, key=_identity_metadata_sort_key)

    def active_live_market_targets(
        self,
        *,
        projection_version: str,
        since_ms: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH active_targets AS (
              SELECT DISTINCT ON (token_radar_rows.target_type, token_radar_rows.target_id)
                token_radar_rows.target_type,
                token_radar_rows.target_id,
                token_radar_rows.pricefeed_id,
                token_radar_rows.computed_at_ms,
                token_radar_rows.source_max_received_at_ms
              FROM token_radar_rows
              WHERE token_radar_rows.projection_version = %s
                AND token_radar_rows.target_type IN ('Asset', 'CexToken')
                AND token_radar_rows.target_id IS NOT NULL
                AND token_radar_rows.computed_at_ms >= %s
              ORDER BY token_radar_rows.target_type, token_radar_rows.target_id, token_radar_rows.computed_at_ms DESC
            ),
            live_targets AS (
              SELECT
                'Asset' AS target_type,
                active_targets.target_id,
                registry_assets.chain_id,
                registry_assets.address,
                NULL::text AS native_market_id,
                NULL::text AS quote_symbol,
                'okx' AS provider,
                active_targets.computed_at_ms,
                active_targets.source_max_received_at_ms
              FROM active_targets
              JOIN registry_assets ON registry_assets.asset_id = active_targets.target_id
              WHERE active_targets.target_type = 'Asset'
                AND registry_assets.status IN ('candidate', 'canonical')
                AND registry_assets.chain_id IS NOT NULL
                AND registry_assets.address IS NOT NULL
              UNION ALL
              SELECT
                'CexToken' AS target_type,
                active_targets.target_id,
                NULL::text AS chain_id,
                NULL::text AS address,
                COALESCE(selected_pricefeed.native_market_id, preferred_pricefeed.native_market_id) AS native_market_id,
                COALESCE(selected_pricefeed.quote_symbol, preferred_pricefeed.quote_symbol) AS quote_symbol,
                COALESCE(selected_pricefeed.provider, preferred_pricefeed.provider, 'okx') AS provider,
                active_targets.computed_at_ms,
                active_targets.source_max_received_at_ms
              FROM active_targets
              JOIN cex_tokens ON cex_tokens.cex_token_id = active_targets.target_id
              LEFT JOIN price_feeds selected_pricefeed
                ON selected_pricefeed.pricefeed_id = active_targets.pricefeed_id
               AND selected_pricefeed.subject_type = 'CexToken'
               AND selected_pricefeed.subject_id = active_targets.target_id
              LEFT JOIN LATERAL (
                SELECT *
                FROM price_feeds
                WHERE price_feeds.subject_type = 'CexToken'
                  AND price_feeds.subject_id = active_targets.target_id
                  AND price_feeds.feed_type LIKE 'cex_%%'
                  AND price_feeds.status IN ('candidate', 'canonical')
                ORDER BY
                  CASE
                    WHEN price_feeds.feed_type = 'cex_spot' THEN 0
                    WHEN price_feeds.feed_type = 'cex_swap' THEN 1
                    ELSE 2
                  END,
                  CASE
                    WHEN price_feeds.quote_symbol = 'USDT' THEN 0
                    WHEN price_feeds.quote_symbol = 'USD' THEN 1
                    WHEN price_feeds.quote_symbol = 'USDC' THEN 2
                    ELSE 9
                  END,
                  price_feeds.updated_at_ms DESC,
                  price_feeds.native_market_id ASC
                LIMIT 1
              ) preferred_pricefeed ON true
              WHERE active_targets.target_type = 'CexToken'
                AND cex_tokens.status IN ('candidate', 'canonical')
            )
            SELECT
              target_type,
              target_id,
              chain_id,
              address,
              native_market_id,
              quote_symbol,
              provider,
              computed_at_ms,
              source_max_received_at_ms
            FROM live_targets
            WHERE target_type = 'Asset' OR native_market_id IS NOT NULL
            ORDER BY computed_at_ms DESC, target_type, target_id
            LIMIT %s
            """,
            (projection_version, int(since_ms), max(0, int(limit))),
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
    return (
        "pricefeed:"
        + hashlib.sha256(
            "|".join([feed_type, provider, native_market_id or "", chain_id or "", address or ""]).encode("utf-8")
        ).hexdigest()
    )


def _symbol(value: str | None) -> str:
    return str(value or "").strip().lstrip("$").upper()


def _optional_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


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


def _with_identity_metadata(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.pop("identity_raw_payload_json", None) or {}
    observed_at_ms = row.get("identity_metadata_observed_at_ms")
    provider = row.get("identity_metadata_provider")
    market_cap_usd = _metadata_number(
        payload,
        "market_cap_usd",
        "marketCapUsd",
        "marketCapUSD",
        "marketCap",
        "market_cap",
        "mcap",
    )
    liquidity_usd = _metadata_number(
        payload,
        "liquidity_usd",
        "liquidityUsd",
        "liquidityUSD",
        "liquidity",
    )
    holders = _metadata_int(payload, "holders", "holderCount", "holder_count")
    provider_rank = _metadata_int(payload, "provider_rank")
    return {
        **row,
        "price_usd": _metadata_number(payload, "price_usd", "priceUsd", "priceUSD", "price"),
        "price_observed_at_ms": observed_at_ms,
        "price_provider": provider,
        "market_cap_usd": market_cap_usd,
        "market_cap_observed_at_ms": observed_at_ms if market_cap_usd is not None else None,
        "market_cap_provider": provider if market_cap_usd is not None else None,
        "liquidity_usd": liquidity_usd,
        "liquidity_observed_at_ms": observed_at_ms if liquidity_usd is not None else None,
        "liquidity_provider": provider if liquidity_usd is not None else None,
        "volume_24h_usd": _metadata_number(payload, "volume_24h_usd", "volume24hUsd", "volume24hUSD", "volume24h"),
        "holders": holders,
        "holders_observed_at_ms": observed_at_ms if holders is not None else None,
        "holders_provider": provider if holders is not None else None,
        "provider_rank": provider_rank,
        "provider_rank_observed_at_ms": observed_at_ms if provider_rank is not None else None,
        "market_cap_status": _identity_metadata_status(market_cap_usd, observed_at_ms),
        "liquidity_status": _identity_metadata_status(liquidity_usd, observed_at_ms),
        "holders_status": _identity_metadata_status(holders, observed_at_ms),
    }


def _identity_metadata_status(value: Any, observed_at_ms: Any) -> str:
    return "fresh" if value is not None and observed_at_ms is not None else "missing"


def _identity_metadata_sort_key(row: dict[str, Any]) -> tuple[float, str]:
    return (-_metadata_float(row.get("market_cap_usd")), str(row.get("asset_id") or ""))


def _metadata_number(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _metadata_int(payload: dict[str, Any], *keys: str) -> int | None:
    value = _metadata_number(payload, *keys)
    return int(value) if value is not None else None


def _metadata_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
