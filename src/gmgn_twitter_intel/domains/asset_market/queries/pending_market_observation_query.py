from __future__ import annotations

from typing import Any

# Inlined to avoid circular import; must stay in sync with TOKEN_RADAR_RESOLVER_POLICY_VERSION
_RESOLVER_POLICY_VERSION = "token_radar_v5_identity_resolver"

_MESSAGE_MARKET_HOT_LOOKBACK_MS = 60 * 60 * 1000


class PendingMarketObservationQuery:
    """Selects token intent resolutions that need a market price observation."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def pending_rows(self, *, now_ms: int, limit: int) -> list[dict[str, Any]]:
        hot_since_ms = int(now_ms) - _MESSAGE_MARKET_HOT_LOOKBACK_MS
        rows = self.conn.execute(
            """
            SELECT
              tir.resolution_id,
              tir.intent_id,
              tir.event_id,
              tir.target_type,
              tir.target_id,
              COALESCE(tir.pricefeed_id, preferred_price_feed.pricefeed_id) AS pricefeed_id,
              events.received_at_ms AS event_received_at_ms,
              registry_assets.chain_id AS asset_chain_id,
              registry_assets.address AS asset_address,
              asset_identity_current.canonical_symbol AS asset_symbol,
              asset_identity_current.identity_confidence AS asset_identity_confidence,
              latest_subject_price.market_cap_usd AS asset_market_cap_usd,
              latest_subject_price.liquidity_usd AS asset_liquidity_usd,
              latest_subject_price.holders AS asset_holders,
              cex_tokens.base_symbol AS cex_base_symbol,
              price_feeds.feed_type,
              price_feeds.provider AS pricefeed_provider,
              price_feeds.native_market_id,
              price_feeds.base_symbol AS pricefeed_base_symbol,
              price_feeds.quote_symbol AS pricefeed_quote_symbol
            FROM token_intent_resolutions tir
            JOIN events ON events.event_id = tir.event_id
            LEFT JOIN registry_assets
              ON tir.target_type = 'Asset'
             AND registry_assets.asset_id = tir.target_id
            LEFT JOIN asset_identity_current
              ON tir.target_type = 'Asset'
             AND asset_identity_current.asset_id = tir.target_id
            LEFT JOIN cex_tokens
              ON tir.target_type = 'CexToken'
             AND cex_tokens.cex_token_id = tir.target_id
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_feeds
              WHERE tir.target_type = 'CexToken'
                AND price_feeds.subject_type = 'CexToken'
                AND price_feeds.subject_id = tir.target_id
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
            ) preferred_price_feed ON true
            LEFT JOIN price_feeds
              ON price_feeds.pricefeed_id = COALESCE(tir.pricefeed_id, preferred_price_feed.pricefeed_id)
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_observations
              WHERE price_observations.subject_type = tir.target_type
                AND price_observations.subject_id = tir.target_id
              ORDER BY observed_at_ms DESC, observation_id DESC
              LIMIT 1
            ) latest_subject_price ON true
            WHERE tir.is_current = true
              AND tir.resolver_policy_version = %s
              AND tir.target_type IN ('Asset', 'CexToken')
              AND tir.target_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1
                FROM price_observations po
                WHERE po.source_resolution_id = tir.resolution_id
                  AND po.subject_type = tir.target_type
                  AND po.subject_id = tir.target_id
                  AND (
                    COALESCE(tir.pricefeed_id, preferred_price_feed.pricefeed_id) IS NULL
                    OR po.pricefeed_id = COALESCE(tir.pricefeed_id, preferred_price_feed.pricefeed_id)
                  )
                  AND po.observation_kind IN ('message_payload', 'message_quote')
              )
            ORDER BY
              CASE WHEN events.received_at_ms >= %s THEN 0 ELSE 1 END,
              events.received_at_ms DESC,
              tir.resolution_id ASC
            LIMIT %s
            """,
            (_RESOLVER_POLICY_VERSION, hot_since_ms, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]
