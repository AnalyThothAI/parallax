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
              price_baselines.first_price_observed_at_ms,
              price_baselines.first_price_usd,
              price_baselines.first_price_quote,
              price_baselines.first_price_quote_symbol,
              price_baselines.first_price_basis,
              price_baselines.event_price_observation_id,
              price_baselines.event_price_observation_kind,
              price_baselines.event_price_provider,
              price_baselines.event_price_observed_at_ms,
              price_baselines.event_price_usd,
              price_baselines.event_price_quote,
              price_baselines.event_price_quote_symbol,
              price_baselines.event_price_basis,
              price_baselines.before_event_price_observed_at_ms,
              price_baselines.before_event_price_usd,
              price_baselines.before_event_price_quote,
              price_baselines.before_event_price_quote_symbol,
              price_baselines.before_event_price_basis
            FROM window_events events
            JOIN token_intents ON token_intents.event_id = events.event_id
            JOIN LATERAL (
              SELECT *
              FROM token_intent_resolutions
              WHERE token_intent_resolutions.intent_id = token_intents.intent_id
                AND token_intent_resolutions.is_current = true
                AND token_intent_resolutions.resolver_policy_version = %s
              LIMIT 1
            ) token_intent_resolutions ON true
            LEFT JOIN token_market_price_baselines price_baselines
              ON price_baselines.resolution_id = token_intent_resolutions.resolution_id
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
            ORDER BY events.received_at_ms ASC, events.event_id ASC
            """,
            (
                since_ms,
                now_ms,
                TOKEN_RADAR_RESOLVER_POLICY_VERSION,
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
        row = self.conn.execute("SELECT MAX(observed_at_ms) AS value FROM price_observations").fetchone()
        value = row["value"] if row else None
        return int(value) if value is not None else None
