from __future__ import annotations

import hashlib
from typing import Any

# Inlined to avoid circular import: asset_market.interfaces → token_intel.interfaces → asset_market.interfaces
# This string must stay in sync with TOKEN_RADAR_RESOLVER_POLICY_VERSION in token_intel/interfaces.py
TOKEN_RADAR_RESOLVER_POLICY_VERSION = "token_radar_v5_identity_resolver"

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
              asset_identity_current.canonical_symbol AS symbol,
              asset_identity_current.canonical_name AS name,
              asset_identity_current.decimals,
              asset_identity_current.identity_confidence,
              latest_price.price_usd,
              latest_price.observed_at_ms AS observed_at_ms,
              latest_price.observed_at_ms AS price_observed_at_ms,
              latest_price.provider AS price_provider,
              market_cap.market_cap_usd,
              market_cap.observed_at_ms AS market_cap_observed_at_ms,
              market_cap.provider AS market_cap_provider,
              liquidity.liquidity_usd,
              liquidity.observed_at_ms AS liquidity_observed_at_ms,
              liquidity.provider AS liquidity_provider,
              latest_price.volume_24h_usd,
              holders.holders,
              holders.observed_at_ms AS holders_observed_at_ms,
              holders.provider AS holders_provider
            FROM registry_assets
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_observations
              WHERE price_observations.subject_type = 'Asset'
                AND price_observations.subject_id = registry_assets.asset_id
                AND price_observations.provider IN ('gmgn_payload', 'okx_dex_search', 'okx_dex_price')
                AND price_observations.price_usd IS NOT NULL
              ORDER BY observed_at_ms DESC, observation_id DESC
              LIMIT 1
            ) latest_price ON true
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_observations
              WHERE price_observations.subject_type = 'Asset'
                AND price_observations.subject_id = registry_assets.asset_id
                AND price_observations.provider IN ('gmgn_payload', 'okx_dex_search')
                AND price_observations.market_cap_usd IS NOT NULL
              ORDER BY observed_at_ms DESC, observation_id DESC
              LIMIT 1
            ) market_cap ON true
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_observations
              WHERE price_observations.subject_type = 'Asset'
                AND price_observations.subject_id = registry_assets.asset_id
                AND price_observations.provider IN ('gmgn_payload', 'okx_dex_search')
                AND price_observations.liquidity_usd IS NOT NULL
              ORDER BY observed_at_ms DESC, observation_id DESC
              LIMIT 1
            ) liquidity ON true
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_observations
              WHERE price_observations.subject_type = 'Asset'
                AND price_observations.subject_id = registry_assets.asset_id
                AND price_observations.provider IN ('gmgn_payload', 'okx_dex_search')
                AND price_observations.holders IS NOT NULL
              ORDER BY observed_at_ms DESC, observation_id DESC
              LIMIT 1
            ) holders ON true
            JOIN asset_identity_current
              ON asset_identity_current.asset_id = registry_assets.asset_id
            WHERE asset_identity_current.canonical_symbol = %s
              AND registry_assets.status IN ('candidate', 'canonical')
            ORDER BY market_cap.market_cap_usd DESC NULLS LAST, registry_assets.asset_id
            """,
            (_symbol(symbol),),
        ).fetchall()
        return [_with_resolution_field_statuses(dict(row)) for row in rows]

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
              asset_identity_current.canonical_symbol AS symbol,
              asset_identity_current.canonical_name AS name,
              asset_identity_current.decimals,
              asset_identity_current.identity_confidence,
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
            LEFT JOIN asset_identity_current
              ON asset_identity_current.asset_id = registry_assets.asset_id
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

    def chain_assets_needing_radar_price_refresh(
        self,
        *,
        stale_before_ms: int,
        radar_since_ms: int,
        hot_since_ms: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH candidate_mentions AS (
              SELECT
                token_intent_resolutions.target_id AS asset_id,
                MAX(events.received_at_ms) AS latest_candidate_received_at_ms,
                COUNT(DISTINCT events.event_id) AS candidate_event_count
              FROM token_intent_resolutions
              JOIN events ON events.event_id = token_intent_resolutions.event_id
              WHERE token_intent_resolutions.is_current = true
                AND token_intent_resolutions.resolver_policy_version = %s
                AND token_intent_resolutions.target_type = 'Asset'
                AND token_intent_resolutions.target_id IS NOT NULL
                AND events.received_at_ms >= %s
              GROUP BY token_intent_resolutions.target_id
            )
            SELECT
              registry_assets.*,
              asset_identity_current.canonical_symbol AS symbol,
              asset_identity_current.canonical_name AS name,
              asset_identity_current.decimals,
              asset_identity_current.identity_confidence,
              latest_price.observed_at_ms AS latest_price_observed_at_ms,
              latest_price.market_cap_usd,
              latest_price.liquidity_usd,
              latest_price.volume_24h_usd,
              latest_price.open_interest_usd,
              latest_price.holders,
              candidate_mentions.latest_candidate_received_at_ms,
              candidate_mentions.candidate_event_count
            FROM candidate_mentions
            JOIN registry_assets ON registry_assets.asset_id = candidate_mentions.asset_id
            LEFT JOIN asset_identity_current
              ON asset_identity_current.asset_id = registry_assets.asset_id
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
            ORDER BY
              CASE WHEN candidate_mentions.latest_candidate_received_at_ms >= %s THEN 0 ELSE 1 END,
              candidate_mentions.latest_candidate_received_at_ms DESC,
              COALESCE(latest_price.observed_at_ms, 0) ASC,
              registry_assets.updated_at_ms DESC,
              registry_assets.asset_id
            LIMIT %s
            """,
            (
                TOKEN_RADAR_RESOLVER_POLICY_VERSION,
                int(radar_since_ms),
                int(stale_before_ms),
                int(hot_since_ms),
                max(0, int(limit)),
            ),
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


def _with_resolution_field_statuses(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "market_cap_status": _resolution_field_status(row, "market_cap"),
        "liquidity_status": _resolution_field_status(row, "liquidity"),
        "holders_status": _resolution_field_status(row, "holders"),
    }


def _resolution_field_status(row: dict[str, Any], key: str) -> str:
    observed_at_ms = row.get(f"{key}_observed_at_ms")
    value = row.get(f"{key}_usd") if key in {"market_cap", "liquidity"} else row.get(key)
    if value is None or observed_at_ms is None:
        return "missing"
    return "fresh"
