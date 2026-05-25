from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_RESOLVER_POLICY_VERSION


class TokenRadarTargetFeatureQuery:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def source_rows(
        self,
        *,
        target_type_key: str,
        identity_id: str,
        since_ms: int,
        score_since_ms: int | None,
        scope: str,
        now_ms: int,
    ) -> list[dict[str, Any]]:
        resolved_score_since_ms = int(since_ms if score_since_ms is None else score_since_ms)
        watched_clause = "AND events.is_watched = true" if scope == "matched" else ""
        rows = self.conn.execute(
            f"""
            WITH source_intents AS MATERIALIZED (
              SELECT
                token_intents.intent_id,
                token_intents.event_id,
                token_intents.intent_key,
                token_intents.construction_policy,
                token_intents.primary_evidence_id,
                token_intents.display_symbol,
                token_intents.display_name,
                token_intents.chain_hint,
                token_intents.address_hint,
                token_intents.intent_status,
                token_intents.created_at_ms,
                token_intents.updated_at_ms,
                token_intent_resolutions.resolution_id,
                token_intent_resolutions.target_type,
                token_intent_resolutions.target_id,
                token_intent_resolutions.pricefeed_id AS resolution_pricefeed_id,
                token_intent_resolutions.resolution_status,
                token_intent_resolutions.reason_codes_json,
                token_intent_resolutions.candidate_ids_json,
                token_intent_resolutions.lookup_keys_json,
                token_intent_resolutions.decision_time_ms,
                events.author_handle,
                events.is_watched,
                events.received_at_ms,
                events.text,
                events.text_clean,
                events.reference_json,
                events.author_followers
              FROM token_intent_resolutions
              JOIN token_intents ON token_intents.intent_id = token_intent_resolutions.intent_id
              JOIN events ON events.event_id = token_intents.event_id
              WHERE token_intent_resolutions.target_type = %s
                AND token_intent_resolutions.target_id = %s
                AND events.received_at_ms >= %s
                AND events.received_at_ms <= %s
                AND token_intent_resolutions.is_current = true
                AND token_intent_resolutions.resolver_policy_version = %s
                AND token_intent_resolutions.target_type IN ('Asset', 'CexToken')
                AND token_intent_resolutions.target_id IS NOT NULL
                {watched_clause}
            )
            SELECT
              source_intents.intent_id,
              source_intents.event_id,
              source_intents.intent_key,
              source_intents.construction_policy,
              source_intents.primary_evidence_id,
              source_intents.display_symbol,
              source_intents.display_name,
              source_intents.chain_hint,
              source_intents.address_hint,
              source_intents.intent_status,
              source_intents.created_at_ms,
              source_intents.updated_at_ms,
              source_intents.resolution_id,
              source_intents.target_type,
              source_intents.target_id,
              CASE
                WHEN source_intents.target_type = 'CexToken'
                  THEN preferred_price_feed.pricefeed_id
                ELSE source_intents.resolution_pricefeed_id
              END AS pricefeed_id,
              source_intents.resolution_status,
              source_intents.reason_codes_json,
              source_intents.candidate_ids_json,
              source_intents.lookup_keys_json,
              NULL AS discovery_results_json,
              source_intents.decision_time_ms,
              source_intents.author_handle,
              source_intents.is_watched,
              source_intents.received_at_ms,
              source_intents.text,
              source_intents.text_clean,
              source_intents.reference_json,
              source_intents.author_followers AS ws_author_followers,
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
              NULL::bigint AS first_price_observed_at_ms,
              NULL::numeric AS first_price_usd,
              NULL::numeric AS first_price_quote,
              NULL::text AS first_price_quote_symbol,
              NULL::text AS first_price_basis,
              CASE WHEN event_price_tick.tick_id IS NOT NULL THEN event_price_capture.tick_id ELSE NULL END
                AS event_price_capture_id,
              CASE WHEN event_price_tick.tick_id IS NOT NULL THEN event_price_capture.capture_method ELSE NULL END
                AS event_price_capture_method,
              CASE WHEN event_price_tick.tick_id IS NOT NULL THEN event_price_capture.capture_reason ELSE NULL END
                AS event_price_capture_reason,
              CASE WHEN event_price_tick.tick_id IS NOT NULL THEN event_price_capture.tick_lag_ms ELSE NULL END
                AS event_price_tick_lag_ms,
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
              event_price_tick.open_interest_usd AS event_price_open_interest_usd,
              event_price_tick.holders AS event_price_holders,
              latest_price_tick.tick_id AS latest_price_tick_id,
              latest_price_tick.source_provider AS latest_price_provider,
              latest_price_tick.source_tier AS latest_price_source_tier,
              latest_price_tick.pricefeed_id AS latest_price_pricefeed_id,
              latest_price_tick.tick_observed_at_ms AS latest_price_observed_at_ms,
              latest_price_tick.updated_at_ms AS latest_price_received_at_ms,
              latest_price_tick.price_usd AS latest_price_usd,
              NULL::numeric AS latest_price_quote,
              NULL::text AS latest_price_quote_symbol,
              NULL::text AS latest_price_basis,
              latest_price_tick.market_cap_usd AS latest_price_market_cap_usd,
              latest_price_tick.liquidity_usd AS latest_price_liquidity_usd,
              latest_price_tick.volume_24h_usd AS latest_price_volume_24h_usd,
              latest_price_tick.open_interest_usd AS latest_price_open_interest_usd,
              latest_price_tick.holders AS latest_price_holders,
              NULL::bigint AS before_event_price_observed_at_ms,
              NULL::numeric AS before_event_price_usd,
              NULL::numeric AS before_event_price_quote,
              NULL::text AS before_event_price_quote_symbol,
              NULL::text AS before_event_price_basis
            FROM source_intents
            LEFT JOIN account_profiles ap
              ON source_intents.received_at_ms >= %s
             AND ap.handle = LOWER(source_intents.author_handle)
            LEFT JOIN social_event_extractions see
              ON source_intents.received_at_ms >= %s
             AND see.event_id = source_intents.event_id
            LEFT JOIN registry_assets
              ON source_intents.received_at_ms >= %s
             AND source_intents.target_type = 'Asset'
             AND registry_assets.asset_id = source_intents.target_id
            LEFT JOIN asset_identity_current
              ON source_intents.received_at_ms >= %s
             AND source_intents.target_type = 'Asset'
             AND asset_identity_current.asset_id = source_intents.target_id
            LEFT JOIN cex_tokens
              ON source_intents.received_at_ms >= %s
             AND source_intents.target_type = 'CexToken'
             AND cex_tokens.cex_token_id = source_intents.target_id
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_feeds
              WHERE source_intents.target_type = 'CexToken'
                AND price_feeds.subject_type = 'CexToken'
                AND price_feeds.subject_id = source_intents.target_id
                AND price_feeds.provider = 'binance'
                AND price_feeds.feed_type = 'cex_swap'
                AND price_feeds.quote_symbol = 'USDT'
                AND price_feeds.status = 'canonical'
              ORDER BY price_feeds.updated_at_ms DESC, price_feeds.native_market_id ASC
              LIMIT 1
            ) preferred_price_feed ON source_intents.received_at_ms >= %s
            LEFT JOIN price_feeds
              ON source_intents.received_at_ms >= %s
             AND price_feeds.pricefeed_id = CASE
                WHEN source_intents.target_type = 'CexToken'
                  THEN preferred_price_feed.pricefeed_id
                ELSE source_intents.resolution_pricefeed_id
              END
            LEFT JOIN LATERAL (
              SELECT
                CASE
                  WHEN source_intents.target_type = 'Asset'
                    AND registry_assets.chain_id IS NOT NULL
                    AND registry_assets.address IS NOT NULL
                    THEN 'chain_token'
                  WHEN source_intents.target_type = 'CexToken'
                    AND price_feeds.provider IS NOT NULL
                    AND price_feeds.native_market_id IS NOT NULL
                    THEN 'cex_symbol'
                  ELSE NULL
                END AS target_type,
                CASE
                  WHEN source_intents.target_type = 'Asset'
                    AND registry_assets.chain_id IS NOT NULL
                    AND registry_assets.address IS NOT NULL
                    THEN registry_assets.chain_id || ':' || registry_assets.address
                  WHEN source_intents.target_type = 'CexToken'
                    AND price_feeds.provider IS NOT NULL
                    AND price_feeds.native_market_id IS NOT NULL
                    THEN price_feeds.provider || ':' || price_feeds.native_market_id
                  ELSE NULL
                END AS target_id
            ) market_target ON source_intents.received_at_ms >= %s
            LEFT JOIN LATERAL (
              SELECT
                enriched_events.tick_observed_at_ms,
                enriched_events.tick_id,
                enriched_events.capture_method,
                enriched_events.capture_reason,
                enriched_events.tick_lag_ms,
                enriched_events.created_at_ms
              FROM enriched_events
              WHERE source_intents.received_at_ms >= %s
                AND enriched_events.event_id = source_intents.event_id
                AND enriched_events.intent_id = source_intents.intent_id
                AND enriched_events.resolution_id = source_intents.resolution_id
              ORDER BY enriched_events.created_at_ms DESC
              LIMIT 1
            ) event_price_capture ON true
            LEFT JOIN market_ticks event_price_tick
              ON event_price_tick.observed_at_ms = event_price_capture.tick_observed_at_ms
             AND event_price_tick.tick_id = event_price_capture.tick_id
             AND event_price_tick.target_type = market_target.target_type
             AND event_price_tick.target_id = market_target.target_id
             AND event_price_tick.source_provider = CASE
                WHEN source_intents.target_type = 'CexToken' THEN 'binance_cex_rest'
                ELSE event_price_tick.source_provider
              END
            LEFT JOIN market_tick_current latest_price_tick
              ON latest_price_tick.target_type = market_target.target_type
             AND latest_price_tick.target_id = market_target.target_id
            ORDER BY source_intents.received_at_ms ASC, source_intents.event_id ASC
            """,
            (
                target_type_key,
                identity_id,
                int(since_ms),
                int(now_ms),
                TOKEN_RADAR_RESOLVER_POLICY_VERSION,
                resolved_score_since_ms,
                resolved_score_since_ms,
                resolved_score_since_ms,
                resolved_score_since_ms,
                resolved_score_since_ms,
                resolved_score_since_ms,
                resolved_score_since_ms,
                resolved_score_since_ms,
                resolved_score_since_ms,
            ),
        ).fetchall()
        return [dict(row) for row in rows]
