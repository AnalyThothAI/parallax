from __future__ import annotations

from typing import Any

TOKEN_TARGET_RESOLVER_POLICY_VERSION = "token_radar_v4_deterministic_resolver"


class TokenTargetRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def timeline_rows(
        self,
        *,
        target_type: str,
        target_id: str,
        since_ms: int,
        watched_only: bool,
        limit: int,
        cursor: tuple[int, str] | None = None,
    ) -> list[dict[str, Any]]:
        clauses = [
            "tir.target_type = %s",
            "tir.target_id = %s",
            "tir.is_current = true",
            "tir.resolver_policy_version = %s",
            "events.received_at_ms >= %s",
        ]
        params: list[Any] = [target_type, target_id, TOKEN_TARGET_RESOLVER_POLICY_VERSION, int(since_ms)]
        if cursor is not None:
            cursor_ms, cursor_event_id = cursor
            clauses.append("(events.received_at_ms, events.event_id) < (%s, %s)")
            params.extend([int(cursor_ms), str(cursor_event_id)])
        if watched_only:
            clauses.append("events.is_watched = true")
        params.append(max(0, int(limit)))
        rows = self.conn.execute(
            f"""
            SELECT
              events.event_id,
              events.tweet_id,
              events.canonical_url,
              events.author_handle,
              events.text,
              events.text_clean,
              events.reference_json,
              events.is_watched,
              events.received_at_ms,
              tir.target_type,
              tir.target_id,
              tir.resolution_status,
              tir.resolution_status AS attribution_status,
              CASE
                WHEN tir.resolution_status = 'EXACT' THEN 1.0
                WHEN tir.resolution_status = 'UNIQUE_BY_CONTEXT' THEN 0.9
                WHEN tir.resolution_status = 'AMBIGUOUS' THEN 0.45
                ELSE 0.0
              END AS confidence,
              registry_assets.chain_id,
              registry_assets.token_standard,
              registry_assets.address,
              registry_assets.symbol AS asset_symbol,
              registry_assets.name AS asset_name,
              cex_tokens.base_symbol AS cex_base_symbol,
              COALESCE(tir.pricefeed_id, preferred_price_feed.pricefeed_id) AS pricefeed_id,
              price_feeds.provider,
              price_feeds.native_market_id,
              price_feeds.base_symbol AS pricefeed_base_symbol,
              price_feeds.quote_symbol,
              price_feeds.feed_type,
              message_price.observation_id AS price_observation_id,
              message_price.provider AS price_provider,
              message_price.observed_at_ms AS price_observed_at_ms,
              message_price.price_usd,
              message_price.price_quote,
              message_price.quote_symbol AS price_quote_symbol,
              message_price.observation_kind AS price_observation_kind,
              message_price.observation_lag_ms AS price_observation_lag_ms
            FROM token_intent_resolutions tir
            JOIN events ON events.event_id = tir.event_id
            LEFT JOIN registry_assets
              ON tir.target_type = 'Asset'
             AND registry_assets.asset_id = tir.target_id
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
              WHERE price_observations.source_event_id = events.event_id
                AND price_observations.source_resolution_id = tir.resolution_id
                AND price_observations.subject_type = tir.target_type
                AND price_observations.subject_id = tir.target_id
                AND (
                  COALESCE(tir.pricefeed_id, preferred_price_feed.pricefeed_id) IS NULL
                  OR price_observations.pricefeed_id = COALESCE(tir.pricefeed_id, preferred_price_feed.pricefeed_id)
                )
                AND price_observations.observation_kind IN ('message_payload', 'message_quote')
              ORDER BY
                CASE WHEN price_observations.observation_kind = 'message_payload' THEN 0 ELSE 1 END,
                price_observations.observed_at_ms DESC,
                price_observations.observation_id DESC
              LIMIT 1
            ) message_price ON true
            WHERE {' AND '.join(clauses)}
            ORDER BY events.received_at_ms DESC, events.event_id DESC
            LIMIT %s
            """,
            params,
        ).fetchall()
        return [_public_row(dict(row)) for row in rows]


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "symbol": row.get("asset_symbol") or row.get("cex_base_symbol") or row.get("pricefeed_base_symbol"),
    }
