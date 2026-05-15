from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_RESOLVER_POLICY_VERSION


class TokenRadarSourceQuery:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def source_rows(
        self,
        *,
        since_ms: int,
        scope: str,
        now_ms: int,
    ) -> list[dict[str, Any]]:
        watched_clause = "AND events.is_watched = true" if scope == "matched" else ""
        rows = self.conn.execute(
            f"""
            WITH window_events AS MATERIALIZED (
              SELECT
                events.event_id,
                events.author_handle,
                events.is_watched,
                events.received_at_ms,
                events.text,
                events.text_clean,
                events.reference_json,
                events.author_followers
              FROM events
              WHERE events.received_at_ms >= %s
                AND events.received_at_ms <= %s {watched_clause}
              ORDER BY events.received_at_ms ASC, events.event_id ASC
            )
            SELECT
              token_intents.*,
              token_intent_resolutions.resolution_id,
              token_intent_resolutions.target_type,
              token_intent_resolutions.target_id,
              COALESCE(token_intent_resolutions.pricefeed_id, preferred_price_feed.pricefeed_id) AS pricefeed_id,
              token_intent_resolutions.resolution_status,
              token_intent_resolutions.reason_codes_json,
              token_intent_resolutions.candidate_ids_json,
              token_intent_resolutions.lookup_keys_json,
              NULL AS discovery_results_json,
              token_intent_resolutions.decision_time_ms,
              events.author_handle,
              events.is_watched,
              events.received_at_ms,
              events.text,
              events.text_clean,
              events.reference_json,
              events.author_followers AS ws_author_followers,
              ap.gmgn_platform_followers AS gmgn_platform_followers,
              ap.gmgn_user_tags AS gmgn_user_tags,
              ap.first_seen_ms AS account_profile_first_seen_ms,
              see.direction_hint AS llm_direction_hint,
              see.impact_hint AS llm_impact_hint,
              see.semantic_novelty_hint AS llm_semantic_novelty_hint,
              see.confidence AS llm_label_confidence,
              registry_assets.chain_id AS asset_chain_id,
              registry_assets.token_standard AS asset_token_standard,
              registry_assets.address AS asset_address,
              asset_identity_current.canonical_symbol AS asset_symbol,
              asset_identity_current.canonical_name AS asset_name,
              asset_identity_current.identity_confidence AS asset_identity_confidence,
              asset_identity_current.selection_reason_codes_json AS asset_identity_reason_codes,
              asset_identity_current.conflict_count AS asset_identity_conflict_count,
              registry_assets.status AS asset_registry_status,
              cex_tokens.base_symbol AS cex_base_symbol,
              cex_tokens.status AS cex_token_status,
              price_feeds.feed_type,
              price_feeds.provider AS pricefeed_provider,
              price_feeds.native_market_id,
              price_feeds.base_symbol AS pricefeed_base_symbol,
              price_feeds.quote_symbol AS pricefeed_quote_symbol,
              price_feeds.status AS pricefeed_status,
              first_price_tick.observed_at_ms AS first_price_observed_at_ms,
              first_price_tick.price_usd AS first_price_usd,
              NULL::numeric AS first_price_quote,
              NULL::text AS first_price_quote_symbol,
              NULL::text AS first_price_basis,
              event_price_capture.tick_id AS event_price_capture_id,
              event_price_capture.capture_method AS event_price_capture_method,
              event_price_capture.capture_reason AS event_price_capture_reason,
              event_price_capture.tick_lag_ms AS event_price_tick_lag_ms,
              event_price_tick.source_provider AS event_price_provider,
              event_price_tick.source_tier AS event_price_source_tier,
              event_price_tick.pricefeed_id AS event_price_pricefeed_id,
              event_price_tick.observed_at_ms AS event_price_observed_at_ms,
              event_price_tick.created_at_ms AS event_price_received_at_ms,
              event_price_tick.price_usd AS event_price_usd,
              NULL::numeric AS event_price_quote,
              NULL::text AS event_price_quote_symbol,
              NULL::text AS event_price_basis,
              event_price_tick.market_cap_usd AS event_price_market_cap_usd,
              event_price_tick.liquidity_usd AS event_price_liquidity_usd,
              event_price_tick.volume_24h_usd AS event_price_volume_24h_usd,
              NULL::numeric AS event_price_open_interest_usd,
              event_price_tick.holders AS event_price_holders,
              latest_price_tick.tick_id AS latest_price_tick_id,
              latest_price_tick.source_provider AS latest_price_provider,
              latest_price_tick.source_tier AS latest_price_source_tier,
              latest_price_tick.pricefeed_id AS latest_price_pricefeed_id,
              latest_price_tick.observed_at_ms AS latest_price_observed_at_ms,
              latest_price_tick.created_at_ms AS latest_price_received_at_ms,
              latest_price_tick.price_usd AS latest_price_usd,
              NULL::numeric AS latest_price_quote,
              NULL::text AS latest_price_quote_symbol,
              NULL::text AS latest_price_basis,
              latest_price_tick.market_cap_usd AS latest_price_market_cap_usd,
              latest_price_tick.liquidity_usd AS latest_price_liquidity_usd,
              latest_price_tick.volume_24h_usd AS latest_price_volume_24h_usd,
              NULL::numeric AS latest_price_open_interest_usd,
              latest_price_tick.holders AS latest_price_holders,
              NULL::bigint AS before_event_price_observed_at_ms,
              NULL::numeric AS before_event_price_usd,
              NULL::numeric AS before_event_price_quote,
              NULL::text AS before_event_price_quote_symbol,
              NULL::text AS before_event_price_basis
            FROM window_events events
            JOIN token_intents ON token_intents.event_id = events.event_id
            JOIN LATERAL (
              SELECT *
              FROM token_intent_resolutions
              WHERE token_intent_resolutions.intent_id = token_intents.intent_id
                AND token_intent_resolutions.is_current = true
                AND token_intent_resolutions.resolver_policy_version = %s
                AND COALESCE(token_intent_resolutions.target_type, 'Asset') IN ('Asset', 'CexToken')
              LIMIT 1
            ) token_intent_resolutions ON true
            LEFT JOIN account_profiles ap ON ap.handle = LOWER(events.author_handle)
            LEFT JOIN social_event_extractions see ON see.event_id = events.event_id
            LEFT JOIN registry_assets
              ON token_intent_resolutions.target_type = 'Asset'
             AND registry_assets.asset_id = token_intent_resolutions.target_id
            LEFT JOIN asset_identity_current
              ON token_intent_resolutions.target_type = 'Asset'
             AND asset_identity_current.asset_id = token_intent_resolutions.target_id
            LEFT JOIN cex_tokens
              ON token_intent_resolutions.target_type = 'CexToken'
             AND cex_tokens.cex_token_id = token_intent_resolutions.target_id
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_feeds
              WHERE token_intent_resolutions.target_type = 'CexToken'
                AND price_feeds.subject_type = 'CexToken'
                AND price_feeds.subject_id = token_intent_resolutions.target_id
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
              ON price_feeds.pricefeed_id = COALESCE(
                token_intent_resolutions.pricefeed_id,
                preferred_price_feed.pricefeed_id
              )
            LEFT JOIN LATERAL (
              SELECT
                CASE
                  WHEN token_intent_resolutions.target_type = 'Asset'
                    AND registry_assets.chain_id IS NOT NULL
                    AND registry_assets.address IS NOT NULL
                    THEN 'chain_token'
                  WHEN token_intent_resolutions.target_type = 'CexToken'
                    AND price_feeds.provider IS NOT NULL
                    AND price_feeds.native_market_id IS NOT NULL
                    THEN 'cex_symbol'
                  ELSE NULL
                END AS target_type,
                CASE
                  WHEN token_intent_resolutions.target_type = 'Asset'
                    AND registry_assets.chain_id IS NOT NULL
                    AND registry_assets.address IS NOT NULL
                    THEN registry_assets.chain_id || ':' || registry_assets.address
                  WHEN token_intent_resolutions.target_type = 'CexToken'
                    AND price_feeds.provider IS NOT NULL
                    AND price_feeds.native_market_id IS NOT NULL
                    THEN price_feeds.provider || ':' || price_feeds.native_market_id
                  ELSE NULL
                END AS target_id
            ) market_target ON true
            LEFT JOIN LATERAL (
              SELECT
                enriched_events.tick_id,
                enriched_events.capture_method,
                enriched_events.capture_reason,
                enriched_events.tick_lag_ms,
                enriched_events.created_at_ms
              FROM enriched_events
              WHERE enriched_events.event_id = events.event_id
                AND enriched_events.intent_id = token_intents.intent_id
                AND enriched_events.resolution_id = token_intent_resolutions.resolution_id
              ORDER BY enriched_events.created_at_ms DESC
              LIMIT 1
            ) event_price_capture ON true
            LEFT JOIN market_ticks event_price_tick
              ON event_price_tick.tick_id = event_price_capture.tick_id
            LEFT JOIN LATERAL (
              SELECT *
              FROM market_ticks
              WHERE market_ticks.target_type = market_target.target_type
                AND market_ticks.target_id = market_target.target_id
                AND market_ticks.observed_at_ms <= %s
              ORDER BY market_ticks.observed_at_ms DESC, market_ticks.tick_id DESC
              LIMIT 1
            ) latest_price_tick ON true
            LEFT JOIN LATERAL (
              SELECT *
              FROM market_ticks
              WHERE market_ticks.target_type = market_target.target_type
                AND market_ticks.target_id = market_target.target_id
              ORDER BY market_ticks.observed_at_ms ASC, market_ticks.tick_id ASC
              LIMIT 1
            ) first_price_tick ON true
            ORDER BY events.received_at_ms ASC, events.event_id ASC
            """,
            (
                since_ms,
                now_ms,
                TOKEN_RADAR_RESOLVER_POLICY_VERSION,
                now_ms,
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def source_count(self, *, since_ms: int, scope: str) -> int:
        watched_clause = "AND events.is_watched = true" if scope == "matched" else ""
        row = self.conn.execute(
            f"""
            SELECT COUNT(*) AS value
            FROM token_intents
            JOIN token_intent_resolutions
              ON token_intent_resolutions.intent_id = token_intents.intent_id
             AND token_intent_resolutions.is_current = true
             AND token_intent_resolutions.resolver_policy_version = %s
             AND COALESCE(token_intent_resolutions.target_type, 'Asset') IN ('Asset', 'CexToken')
            JOIN events ON events.event_id = token_intents.event_id
            WHERE events.received_at_ms >= %s {watched_clause}
            """,
            (TOKEN_RADAR_RESOLVER_POLICY_VERSION, since_ms),
        ).fetchone()
        return int(row["value"] or 0) if row else 0

    def max_resolution_ms(self) -> int | None:
        row = self.conn.execute(
            "SELECT MAX(decision_time_ms) AS value FROM token_intent_resolutions WHERE is_current = true"
        ).fetchone()
        value = row["value"] if row else None
        return int(value) if value is not None else None

    def max_price_observed_at_ms(self) -> int | None:
        row = self.conn.execute("SELECT MAX(observed_at_ms) AS value FROM market_ticks").fetchone()
        value = row["value"] if row else None
        return int(value) if value is not None else None
