from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.token_intel._constants import (
    TOKEN_RADAR_PROJECTION_VERSION,
    TOKEN_RADAR_RESOLVER_POLICY_VERSION,
)

TOKEN_RADAR_RANK_SOURCE_REQUEST_CHUNK_SIZE = 200


@dataclass(frozen=True)
class TokenRadarSourceRequest:
    request_key: str
    target_type_key: str
    identity_id: str
    window: str
    scope: str
    analysis_since_ms: int
    score_since_ms: int
    now_ms: int
    source_event_ids: tuple[str, ...] = ()


class TokenRadarRankSourceQuery:
    def __init__(self, conn: Any, *, chunk_size: int = TOKEN_RADAR_RANK_SOURCE_REQUEST_CHUNK_SIZE) -> None:
        self.conn = conn
        self.chunk_size = max(1, int(chunk_size))

    def load_rows_for_requests(
        self,
        requests: Sequence[TokenRadarSourceRequest],
    ) -> dict[str, list[dict[str, Any]]]:
        rows_by_request: dict[str, list[dict[str, Any]]] = {str(request.request_key): [] for request in requests}
        for chunk in _chunks(tuple(requests), self.chunk_size):
            rows = self.conn.execute(
                _RANK_SOURCE_ROWS_FOR_REQUESTS_SQL,
                (Jsonb([_request_payload(r) for r in chunk]), TOKEN_RADAR_PROJECTION_VERSION),
            ).fetchall()
            for row in rows:
                payload = dict(row)
                request_key = str(payload.get("request_key") or "")
                rows_by_request.setdefault(request_key, []).append(payload)
        return rows_by_request

    def latest_market_context_for_targets(
        self,
        targets: Sequence[Mapping[str, Any]],
    ) -> dict[tuple[str, str], dict[str, Any]]:
        rows_by_target: dict[tuple[str, str], dict[str, Any]] = {}
        target_payloads = _target_payloads(targets)
        if not target_payloads:
            return rows_by_target
        rows = self.conn.execute(
            _LATEST_MARKET_CONTEXT_FOR_TARGETS_SQL,
            (Jsonb(target_payloads),),
        ).fetchall()
        for row in rows:
            payload = dict(row)
            target_key = (str(payload.get("target_type_key") or ""), str(payload.get("identity_id") or ""))
            rows_by_target[target_key] = payload
        return rows_by_target

    def populate_edges_for_event_ids(
        self,
        requests: Sequence[TokenRadarSourceRequest],
        *,
        projected_at_ms: int,
        commit: bool = True,
    ) -> int:
        changed = 0
        for chunk in _chunks(tuple(requests), self.chunk_size):
            row = self.conn.execute(
                _POPULATE_RANK_SOURCE_EDGES_FOR_EVENT_IDS_SQL,
                (
                    Jsonb([_request_payload(r) for r in chunk]),
                    TOKEN_RADAR_RESOLVER_POLICY_VERSION,
                    TOKEN_RADAR_PROJECTION_VERSION,
                    int(projected_at_ms),
                    TOKEN_RADAR_PROJECTION_VERSION,
                ),
            ).fetchone()
            changed += int((row or {}).get("upserted_count") or 0)
            changed += int((row or {}).get("deleted_count") or 0)
        if commit:
            self.conn.commit()
        return changed

    def prune_edges(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
        event_received_before_ms: int,
        commit: bool = True,
    ) -> int:
        cursor = self.conn.execute(
            """
            DELETE FROM token_radar_rank_source_events
            WHERE projection_version = %s
              AND "window" = %s
              AND scope = %s
              AND event_received_at_ms < %s
            """,
            (projection_version, window, scope, int(event_received_before_ms)),
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)


def _chunks(
    requests: tuple[TokenRadarSourceRequest, ...],
    chunk_size: int,
) -> Sequence[tuple[TokenRadarSourceRequest, ...]]:
    return tuple(requests[index : index + chunk_size] for index in range(0, len(requests), chunk_size))


def _request_payload(request: TokenRadarSourceRequest) -> dict[str, Any]:
    return {
        "request_key": str(request.request_key),
        "target_type_key": str(request.target_type_key),
        "identity_id": str(request.identity_id),
        "window": str(request.window),
        "scope": str(request.scope),
        "analysis_since_ms": int(request.analysis_since_ms),
        "score_since_ms": int(request.score_since_ms),
        "now_ms": int(request.now_ms),
        "source_event_ids_json": list(request.source_event_ids),
    }


def _target_payloads(targets: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    payloads: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for target in targets:
        target_type_key = str(target.get("target_type_key") or target.get("target_type") or "").strip()
        identity_id = str(target.get("identity_id") or target.get("target_id") or "").strip()
        target_key = (target_type_key, identity_id)
        if not target_type_key or not identity_id or target_key in seen:
            continue
        seen.add(target_key)
        payloads.append({"target_type_key": target_type_key, "identity_id": identity_id})
    return payloads


_LATEST_MARKET_CONTEXT_FOR_TARGETS_SQL = """
WITH requested AS (
  SELECT DISTINCT target_type_key, identity_id
  FROM jsonb_to_recordset(%s::jsonb) AS r(
    target_type_key text,
    identity_id text
  )
),
asset_market AS (
  SELECT
    requested.target_type_key,
    requested.identity_id,
    current_row.tick_id AS latest_price_tick_id,
    current_row.source_provider AS latest_price_provider,
    current_row.source_tier AS latest_price_source_tier,
    current_row.pricefeed_id AS latest_price_pricefeed_id,
    current_row.tick_observed_at_ms AS latest_price_observed_at_ms,
    current_row.updated_at_ms AS latest_price_received_at_ms,
    current_row.price_usd AS latest_price_usd,
    NULL::numeric AS latest_price_quote,
    NULL::text AS latest_price_quote_symbol,
    NULL::text AS latest_price_basis,
    current_row.market_cap_usd AS latest_price_market_cap_usd,
    current_row.liquidity_usd AS latest_price_liquidity_usd,
    current_row.volume_24h_usd AS latest_price_volume_24h_usd,
    current_row.open_interest_usd AS latest_price_open_interest_usd,
    current_row.holders AS latest_price_holders
  FROM requested
  JOIN registry_assets
    ON requested.target_type_key = 'Asset'
   AND registry_assets.asset_id = requested.identity_id
  JOIN market_tick_current current_row
    ON current_row.target_type = 'chain_token'
   AND lower(current_row.target_id) = lower(registry_assets.chain_id || ':' || registry_assets.address)
),
cex_market AS (
  SELECT
    requested.target_type_key,
    requested.identity_id,
    current_row.tick_id AS latest_price_tick_id,
    current_row.source_provider AS latest_price_provider,
    current_row.source_tier AS latest_price_source_tier,
    current_row.pricefeed_id AS latest_price_pricefeed_id,
    current_row.tick_observed_at_ms AS latest_price_observed_at_ms,
    current_row.updated_at_ms AS latest_price_received_at_ms,
    current_row.price_usd AS latest_price_usd,
    NULL::numeric AS latest_price_quote,
    NULL::text AS latest_price_quote_symbol,
    NULL::text AS latest_price_basis,
    current_row.market_cap_usd AS latest_price_market_cap_usd,
    current_row.liquidity_usd AS latest_price_liquidity_usd,
    current_row.volume_24h_usd AS latest_price_volume_24h_usd,
    current_row.open_interest_usd AS latest_price_open_interest_usd,
    current_row.holders AS latest_price_holders
  FROM requested
  JOIN LATERAL (
    SELECT *
    FROM price_feeds
    WHERE requested.target_type_key = 'CexToken'
      AND price_feeds.subject_type = 'CexToken'
      AND price_feeds.subject_id = requested.identity_id
      AND price_feeds.provider = 'binance'
      AND price_feeds.feed_type = 'cex_swap'
      AND price_feeds.quote_symbol = 'USDT'
      AND price_feeds.status = 'canonical'
    ORDER BY price_feeds.updated_at_ms DESC, price_feeds.native_market_id ASC
    LIMIT 1
  ) price_feeds ON true
  JOIN market_tick_current current_row
    ON current_row.target_type = 'cex_symbol'
   AND current_row.target_id = price_feeds.provider || ':' || price_feeds.native_market_id
)
SELECT *
FROM asset_market
UNION ALL
SELECT *
FROM cex_market
"""


_RANK_SOURCE_ROWS_FOR_REQUESTS_SQL = """
WITH requested AS (
  SELECT *
  FROM jsonb_to_recordset(%s::jsonb) AS r(
    request_key text,
    target_type_key text,
    identity_id text,
    "window" text,
    scope text,
    analysis_since_ms bigint,
    score_since_ms bigint,
    now_ms bigint
  )
)
SELECT
  requested.request_key,
  requested."window",
  requested.scope,
  requested.score_since_ms,
  rank_source.source_payload_hash,
  rank_source.intent_id,
  rank_source.event_id,
  rank_source.intent_key,
  rank_source.construction_policy,
  rank_source.primary_evidence_id,
  rank_source.display_symbol,
  rank_source.display_name,
  rank_source.chain_hint,
  rank_source.address_hint,
  rank_source.intent_status,
  rank_source.intent_created_at_ms AS created_at_ms,
  rank_source.intent_updated_at_ms AS updated_at_ms,
  rank_source.resolution_id,
  rank_source.target_type,
  rank_source.target_id,
  rank_source.pricefeed_id,
  rank_source.resolution_status,
  rank_source.reason_codes_json,
  rank_source.candidate_ids_json,
  rank_source.lookup_keys_json,
  NULL AS discovery_results_json,
  rank_source.decision_time_ms,
  rank_source.author_handle,
  rank_source.is_watched,
  rank_source.event_received_at_ms AS received_at_ms,
  rank_source.text_fingerprint,
  rank_source.post_quality_score,
  rank_source.post_informative,
  rank_source.post_has_market_context,
  rank_source.ws_author_followers,
  rank_source.gmgn_platform_followers,
  rank_source.gmgn_user_tags,
  rank_source.account_profile_first_seen_ms,
  rank_source.llm_direction_hint,
  rank_source.llm_impact_hint,
  rank_source.llm_semantic_novelty_hint,
  rank_source.llm_label_confidence,
  rank_source.asset_chain_id,
  rank_source.asset_token_standard,
  rank_source.asset_address,
  rank_source.asset_symbol,
  rank_source.asset_name,
  rank_source.asset_identity_confidence,
  rank_source.asset_identity_reason_codes,
  rank_source.asset_identity_conflict_count,
  rank_source.asset_registry_status,
  rank_source.cex_base_symbol,
  rank_source.cex_token_status,
  rank_source.feed_type,
  rank_source.pricefeed_provider,
  rank_source.native_market_id,
  rank_source.pricefeed_base_symbol,
  rank_source.pricefeed_quote_symbol,
  rank_source.pricefeed_status,
  rank_source.first_price_observed_at_ms,
  rank_source.first_price_usd,
  rank_source.first_price_quote,
  rank_source.first_price_quote_symbol,
  rank_source.first_price_basis,
  rank_source.event_price_capture_id,
  rank_source.event_price_capture_method,
  rank_source.event_price_capture_reason,
  rank_source.event_price_tick_lag_ms,
  rank_source.event_price_provider,
  rank_source.event_price_source_tier,
  rank_source.event_price_pricefeed_id,
  rank_source.event_price_observed_at_ms,
  rank_source.event_price_received_at_ms,
  rank_source.event_price_usd,
  rank_source.event_price_quote,
  rank_source.event_price_quote_symbol,
  rank_source.event_price_basis,
  rank_source.event_price_market_cap_usd,
  rank_source.event_price_liquidity_usd,
  rank_source.event_price_volume_24h_usd,
  rank_source.event_price_open_interest_usd,
  rank_source.event_price_holders,
  rank_source.latest_price_tick_id,
  rank_source.latest_price_provider,
  rank_source.latest_price_source_tier,
  rank_source.latest_price_pricefeed_id,
  rank_source.latest_price_observed_at_ms,
  rank_source.latest_price_received_at_ms,
  rank_source.latest_price_usd,
  rank_source.latest_price_quote,
  rank_source.latest_price_quote_symbol,
  rank_source.latest_price_basis,
  rank_source.latest_price_market_cap_usd,
  rank_source.latest_price_liquidity_usd,
  rank_source.latest_price_volume_24h_usd,
  rank_source.latest_price_open_interest_usd,
  rank_source.latest_price_holders,
  rank_source.before_event_price_observed_at_ms,
  rank_source.before_event_price_usd,
  rank_source.before_event_price_quote,
  rank_source.before_event_price_quote_symbol,
  rank_source.before_event_price_basis,
  rank_source.first_seen_global_24h
FROM requested
JOIN token_radar_rank_source_events rank_source
  ON rank_source.projection_version = %s
 AND rank_source."window" = requested."window"
 AND rank_source.scope = requested.scope
 AND rank_source.target_type_key = requested.target_type_key
 AND rank_source.identity_id = requested.identity_id
WHERE rank_source.source_kind = 'event'
  AND rank_source.event_received_at_ms >= requested.analysis_since_ms
  AND rank_source.event_received_at_ms <= requested.now_ms
  AND CASE WHEN requested.scope = 'matched' THEN rank_source.is_watched = true ELSE true END
ORDER BY
  requested.request_key ASC,
  rank_source.source_rank ASC,
  rank_source.event_received_at_ms ASC,
  rank_source.event_id ASC
"""


_POPULATE_RANK_SOURCE_EDGES_FOR_EVENT_IDS_SQL = """
WITH raw_requested AS (
  SELECT *
  FROM jsonb_to_recordset(%s::jsonb) AS r(
    request_key text,
    target_type_key text,
    identity_id text,
    "window" text,
    scope text,
    analysis_since_ms bigint,
    score_since_ms bigint,
    now_ms bigint,
    source_event_ids_json jsonb
  )
),
requested_event_ids AS (
  SELECT DISTINCT
    request_key,
    target_type_key,
    identity_id,
    "window",
    scope,
    analysis_since_ms,
    score_since_ms,
    now_ms,
    source_ids.source_event_id
  FROM raw_requested
  CROSS JOIN LATERAL jsonb_array_elements_text(
    COALESCE(raw_requested.source_event_ids_json, '[]'::jsonb)
  ) AS source_ids(source_event_id)
  WHERE source_ids.source_event_id <> ''
),
source_intents AS (
  SELECT
    requested_event_ids."window",
    requested_event_ids.scope,
    requested_event_ids.target_type_key,
    requested_event_ids.identity_id,
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
    token_intents.created_at_ms AS intent_created_at_ms,
    token_intents.updated_at_ms AS intent_updated_at_ms,
    token_intent_resolutions.resolution_id,
    token_intent_resolutions.target_type,
    token_intent_resolutions.target_id,
    CASE
      WHEN token_intent_resolutions.target_type = 'CexToken'
        THEN preferred_price_feed.pricefeed_id
      ELSE token_intent_resolutions.pricefeed_id
    END AS pricefeed_id,
    token_intent_resolutions.resolution_status,
    token_intent_resolutions.confidence AS resolution_confidence,
    token_intent_resolutions.reason_codes_json,
    token_intent_resolutions.candidate_ids_json,
    token_intent_resolutions.lookup_keys_json,
    token_intent_resolutions.decision_time_ms,
    events.author_handle,
    events.is_watched,
    events.received_at_ms AS event_received_at_ms,
    md5(COALESCE(events.search_tsv::text, '')) AS text_fingerprint,
    CASE
      WHEN events.search_tsv IS NULL THEN NULL
      WHEN events.search_tsv @@ websearch_to_tsquery('simple', 'price OR liquidity OR volume OR holders OR mcap OR fdv')
        THEN 80
      WHEN events.is_watched THEN 65
      ELSE 55
    END AS post_quality_score,
    CASE WHEN events.search_tsv IS NULL THEN NULL ELSE true END AS post_informative,
    CASE
      WHEN events.search_tsv IS NULL THEN NULL
      ELSE events.search_tsv @@ websearch_to_tsquery('simple', 'price OR liquidity OR volume OR holders OR mcap OR fdv')
    END AS post_has_market_context,
    events.author_followers AS ws_author_followers,
    ap.gmgn_platform_followers,
    COALESCE(ap.gmgn_user_tags, ARRAY[]::TEXT[]) AS gmgn_user_tags,
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
    NULL::text AS before_event_price_basis,
    false AS first_seen_global_24h
  FROM requested_event_ids
  JOIN token_intents
    ON token_intents.event_id = requested_event_ids.source_event_id
  JOIN events
    ON events.event_id = requested_event_ids.source_event_id
  JOIN token_intent_resolutions
    ON token_intent_resolutions.intent_id = token_intents.intent_id
   AND token_intent_resolutions.event_id = requested_event_ids.source_event_id
   AND token_intent_resolutions.target_type = requested_event_ids.target_type_key
   AND token_intent_resolutions.target_id = requested_event_ids.identity_id
  LEFT JOIN account_profiles ap
    ON events.received_at_ms >= requested_event_ids.score_since_ms
   AND ap.handle = LOWER(events.author_handle)
  LEFT JOIN social_event_extractions see
    ON events.received_at_ms >= requested_event_ids.score_since_ms
   AND see.event_id = token_intents.event_id
  LEFT JOIN registry_assets
    ON events.received_at_ms >= requested_event_ids.score_since_ms
   AND token_intent_resolutions.target_type = 'Asset'
   AND registry_assets.asset_id = token_intent_resolutions.target_id
  LEFT JOIN asset_identity_current
    ON events.received_at_ms >= requested_event_ids.score_since_ms
   AND token_intent_resolutions.target_type = 'Asset'
   AND asset_identity_current.asset_id = token_intent_resolutions.target_id
  LEFT JOIN cex_tokens
    ON events.received_at_ms >= requested_event_ids.score_since_ms
   AND token_intent_resolutions.target_type = 'CexToken'
   AND cex_tokens.cex_token_id = token_intent_resolutions.target_id
  LEFT JOIN LATERAL (
    SELECT *
    FROM price_feeds
    WHERE token_intent_resolutions.target_type = 'CexToken'
      AND price_feeds.subject_type = 'CexToken'
      AND price_feeds.subject_id = token_intent_resolutions.target_id
      AND price_feeds.provider = 'binance'
      AND price_feeds.feed_type = 'cex_swap'
      AND price_feeds.quote_symbol = 'USDT'
      AND price_feeds.status = 'canonical'
    ORDER BY price_feeds.updated_at_ms DESC, price_feeds.native_market_id ASC
    LIMIT 1
  ) preferred_price_feed ON events.received_at_ms >= requested_event_ids.score_since_ms
  LEFT JOIN price_feeds
    ON events.received_at_ms >= requested_event_ids.score_since_ms
   AND price_feeds.pricefeed_id = CASE
      WHEN token_intent_resolutions.target_type = 'CexToken'
        THEN preferred_price_feed.pricefeed_id
      ELSE token_intent_resolutions.pricefeed_id
    END
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
  ) market_target ON events.received_at_ms >= requested_event_ids.score_since_ms
  LEFT JOIN LATERAL (
    SELECT
      enriched_events.tick_observed_at_ms,
      enriched_events.tick_id,
      enriched_events.capture_method,
      enriched_events.capture_reason,
      enriched_events.tick_lag_ms,
      enriched_events.created_at_ms
    FROM enriched_events
    WHERE events.received_at_ms >= requested_event_ids.score_since_ms
      AND enriched_events.event_id = token_intents.event_id
      AND enriched_events.intent_id = token_intents.intent_id
      AND enriched_events.resolution_id = token_intent_resolutions.resolution_id
    ORDER BY enriched_events.created_at_ms DESC
    LIMIT 1
  ) event_price_capture ON true
  LEFT JOIN market_ticks event_price_tick
    ON event_price_tick.observed_at_ms = event_price_capture.tick_observed_at_ms
   AND event_price_tick.tick_id = event_price_capture.tick_id
   AND event_price_tick.target_type = market_target.target_type
   AND event_price_tick.target_id = market_target.target_id
   AND event_price_tick.source_provider = CASE
      WHEN token_intent_resolutions.target_type = 'CexToken' THEN 'binance_cex_rest'
      ELSE event_price_tick.source_provider
    END
  LEFT JOIN market_tick_current latest_price_tick
    ON latest_price_tick.target_type = market_target.target_type
   AND latest_price_tick.target_id = market_target.target_id
  WHERE events.received_at_ms >= requested_event_ids.analysis_since_ms
    AND events.received_at_ms <= requested_event_ids.now_ms
    AND token_intent_resolutions.is_current = true
    AND token_intent_resolutions.resolver_policy_version = %s
    AND token_intent_resolutions.target_type IN ('Asset', 'CexToken')
    AND token_intent_resolutions.target_id IS NOT NULL
    AND CASE WHEN requested_event_ids.scope = 'matched' THEN events.is_watched = true ELSE true END
),
deduped_source AS (
  SELECT *
  FROM (
    SELECT
      source_intents.*,
      row_number() OVER (
        PARTITION BY "window", scope, target_type_key, identity_id, event_id
        ORDER BY
          CASE
            WHEN resolution_status = 'EXACT' THEN 0
            WHEN resolution_status = 'UNIQUE_BY_CONTEXT' THEN 1
            WHEN resolution_status = 'AMBIGUOUS' THEN 2
            ELSE 3
          END,
          resolution_confidence DESC NULLS LAST,
          CASE WHEN event_price_capture_id IS NOT NULL THEN 0 ELSE 1 END,
          event_price_tick_lag_ms ASC NULLS LAST,
          decision_time_ms DESC NULLS LAST,
          intent_updated_at_ms DESC NULLS LAST,
          event_price_observed_at_ms DESC NULLS LAST,
          event_price_received_at_ms DESC NULLS LAST,
          latest_price_observed_at_ms DESC NULLS LAST,
          latest_price_received_at_ms DESC NULLS LAST,
          resolution_id DESC NULLS LAST,
          intent_id DESC
      ) AS event_source_choice_rank
    FROM source_intents
  ) source_choices
  WHERE event_source_choice_rank = 1
),
ranked_source AS (
  SELECT
    deduped_source.*,
    (row_number() OVER (
      PARTITION BY "window", scope, target_type_key, identity_id
      ORDER BY event_received_at_ms ASC, event_id ASC
  ) - 1)::integer AS source_rank
  FROM deduped_source
),
hashed_source AS (
  SELECT
    ranked_source.*,
    encode(
      sha256(
        convert_to(
          (
            to_jsonb(ranked_source)
            - 'resolution_confidence'
            - 'event_source_choice_rank'
            - 'latest_price_tick_id'
            - 'latest_price_provider'
            - 'latest_price_source_tier'
            - 'latest_price_pricefeed_id'
            - 'latest_price_observed_at_ms'
            - 'latest_price_received_at_ms'
            - 'latest_price_usd'
            - 'latest_price_quote'
            - 'latest_price_quote_symbol'
            - 'latest_price_basis'
            - 'latest_price_market_cap_usd'
            - 'latest_price_liquidity_usd'
            - 'latest_price_volume_24h_usd'
            - 'latest_price_open_interest_usd'
            - 'latest_price_holders'
          )::text,
          'UTF8'
        )
      ),
      'hex'
    ) AS source_payload_hash
  FROM ranked_source
),
upserted AS (
  INSERT INTO token_radar_rank_source_events(
    projection_version, "window", scope, lane, target_type_key, identity_id,
    source_kind, source_id, event_received_at_ms, source_rank, projected_at_ms,
    source_payload_hash, intent_id, event_id, intent_key, construction_policy, primary_evidence_id,
    display_symbol, display_name, chain_hint, address_hint, intent_status,
    intent_created_at_ms, intent_updated_at_ms, resolution_id, target_type, target_id,
    pricefeed_id, resolution_status, reason_codes_json, candidate_ids_json,
    lookup_keys_json, decision_time_ms, author_handle, is_watched, text_fingerprint,
    post_quality_score, post_informative, post_has_market_context, ws_author_followers,
    gmgn_platform_followers, gmgn_user_tags, account_profile_first_seen_ms,
    llm_direction_hint, llm_impact_hint, llm_semantic_novelty_hint, llm_label_confidence,
    asset_chain_id, asset_token_standard, asset_address, asset_symbol, asset_name,
    asset_identity_confidence, asset_identity_reason_codes, asset_identity_conflict_count,
    asset_registry_status, cex_base_symbol, cex_token_status, feed_type, pricefeed_provider,
    native_market_id, pricefeed_base_symbol, pricefeed_quote_symbol, pricefeed_status,
    first_price_observed_at_ms, first_price_usd, first_price_quote, first_price_quote_symbol,
    first_price_basis, event_price_capture_id, event_price_capture_method,
    event_price_capture_reason, event_price_tick_lag_ms, event_price_provider,
    event_price_source_tier, event_price_pricefeed_id, event_price_observed_at_ms,
    event_price_received_at_ms, event_price_usd, event_price_quote, event_price_quote_symbol,
    event_price_basis, event_price_market_cap_usd, event_price_liquidity_usd,
    event_price_volume_24h_usd, event_price_open_interest_usd, event_price_holders,
    latest_price_tick_id, latest_price_provider, latest_price_source_tier,
    latest_price_pricefeed_id, latest_price_observed_at_ms, latest_price_received_at_ms,
    latest_price_usd, latest_price_quote, latest_price_quote_symbol, latest_price_basis,
    latest_price_market_cap_usd, latest_price_liquidity_usd, latest_price_volume_24h_usd,
    latest_price_open_interest_usd, latest_price_holders, before_event_price_observed_at_ms,
    before_event_price_usd, before_event_price_quote, before_event_price_quote_symbol,
    before_event_price_basis, first_seen_global_24h
  )
  SELECT
    %s,
    ranked_source."window",
    ranked_source.scope,
    'resolved',
    ranked_source.target_type_key,
    ranked_source.identity_id,
    'event',
    ranked_source.event_id,
    ranked_source.event_received_at_ms,
    ranked_source.source_rank,
    %s,
    ranked_source.source_payload_hash,
    ranked_source.intent_id,
    ranked_source.event_id,
    ranked_source.intent_key,
    ranked_source.construction_policy,
    ranked_source.primary_evidence_id,
    ranked_source.display_symbol,
    ranked_source.display_name,
    ranked_source.chain_hint,
    ranked_source.address_hint,
    ranked_source.intent_status,
    ranked_source.intent_created_at_ms,
    ranked_source.intent_updated_at_ms,
    ranked_source.resolution_id,
    ranked_source.target_type,
    ranked_source.target_id,
    ranked_source.pricefeed_id,
    ranked_source.resolution_status,
    COALESCE(ranked_source.reason_codes_json, '[]'::jsonb),
    COALESCE(ranked_source.candidate_ids_json, '[]'::jsonb),
    COALESCE(ranked_source.lookup_keys_json, '[]'::jsonb),
    ranked_source.decision_time_ms,
    ranked_source.author_handle,
    ranked_source.is_watched,
    ranked_source.text_fingerprint,
    ranked_source.post_quality_score,
    ranked_source.post_informative,
    ranked_source.post_has_market_context,
    ranked_source.ws_author_followers,
    ranked_source.gmgn_platform_followers,
    ranked_source.gmgn_user_tags,
    ranked_source.account_profile_first_seen_ms,
    ranked_source.llm_direction_hint,
    ranked_source.llm_impact_hint,
    ranked_source.llm_semantic_novelty_hint,
    ranked_source.llm_label_confidence,
    ranked_source.asset_chain_id,
    ranked_source.asset_token_standard,
    ranked_source.asset_address,
    ranked_source.asset_symbol,
    ranked_source.asset_name,
    ranked_source.asset_identity_confidence,
    COALESCE(ranked_source.asset_identity_reason_codes, '[]'::jsonb),
    COALESCE(ranked_source.asset_identity_conflict_count, 0),
    ranked_source.asset_registry_status,
    ranked_source.cex_base_symbol,
    ranked_source.cex_token_status,
    ranked_source.feed_type,
    ranked_source.pricefeed_provider,
    ranked_source.native_market_id,
    ranked_source.pricefeed_base_symbol,
    ranked_source.pricefeed_quote_symbol,
    ranked_source.pricefeed_status,
    ranked_source.first_price_observed_at_ms,
    ranked_source.first_price_usd,
    ranked_source.first_price_quote,
    ranked_source.first_price_quote_symbol,
    ranked_source.first_price_basis,
    ranked_source.event_price_capture_id,
    ranked_source.event_price_capture_method,
    ranked_source.event_price_capture_reason,
    ranked_source.event_price_tick_lag_ms,
    ranked_source.event_price_provider,
    ranked_source.event_price_source_tier,
    ranked_source.event_price_pricefeed_id,
    ranked_source.event_price_observed_at_ms,
    ranked_source.event_price_received_at_ms,
    ranked_source.event_price_usd,
    ranked_source.event_price_quote,
    ranked_source.event_price_quote_symbol,
    ranked_source.event_price_basis,
    ranked_source.event_price_market_cap_usd,
    ranked_source.event_price_liquidity_usd,
    ranked_source.event_price_volume_24h_usd,
    ranked_source.event_price_open_interest_usd,
    ranked_source.event_price_holders,
    ranked_source.latest_price_tick_id,
    ranked_source.latest_price_provider,
    ranked_source.latest_price_source_tier,
    ranked_source.latest_price_pricefeed_id,
    ranked_source.latest_price_observed_at_ms,
    ranked_source.latest_price_received_at_ms,
    ranked_source.latest_price_usd,
    ranked_source.latest_price_quote,
    ranked_source.latest_price_quote_symbol,
    ranked_source.latest_price_basis,
    ranked_source.latest_price_market_cap_usd,
    ranked_source.latest_price_liquidity_usd,
    ranked_source.latest_price_volume_24h_usd,
    ranked_source.latest_price_open_interest_usd,
    ranked_source.latest_price_holders,
    ranked_source.before_event_price_observed_at_ms,
    ranked_source.before_event_price_usd,
    ranked_source.before_event_price_quote,
    ranked_source.before_event_price_quote_symbol,
    ranked_source.before_event_price_basis,
    ranked_source.first_seen_global_24h
  FROM hashed_source AS ranked_source
  ON CONFLICT(projection_version, "window", scope, lane, target_type_key, identity_id, source_kind, source_id)
  DO UPDATE SET
    event_received_at_ms = excluded.event_received_at_ms,
    source_rank = excluded.source_rank,
    projected_at_ms = excluded.projected_at_ms,
    source_payload_hash = excluded.source_payload_hash,
    intent_id = excluded.intent_id,
    event_id = excluded.event_id,
    intent_key = excluded.intent_key,
    construction_policy = excluded.construction_policy,
    primary_evidence_id = excluded.primary_evidence_id,
    display_symbol = excluded.display_symbol,
    display_name = excluded.display_name,
    chain_hint = excluded.chain_hint,
    address_hint = excluded.address_hint,
    intent_status = excluded.intent_status,
    intent_created_at_ms = excluded.intent_created_at_ms,
    intent_updated_at_ms = excluded.intent_updated_at_ms,
    resolution_id = excluded.resolution_id,
    target_type = excluded.target_type,
    target_id = excluded.target_id,
    pricefeed_id = excluded.pricefeed_id,
    resolution_status = excluded.resolution_status,
    reason_codes_json = excluded.reason_codes_json,
    candidate_ids_json = excluded.candidate_ids_json,
    lookup_keys_json = excluded.lookup_keys_json,
    decision_time_ms = excluded.decision_time_ms,
    author_handle = excluded.author_handle,
    is_watched = excluded.is_watched,
    text_fingerprint = excluded.text_fingerprint,
    post_quality_score = excluded.post_quality_score,
    post_informative = excluded.post_informative,
    post_has_market_context = excluded.post_has_market_context,
    ws_author_followers = excluded.ws_author_followers,
    gmgn_platform_followers = excluded.gmgn_platform_followers,
    gmgn_user_tags = excluded.gmgn_user_tags,
    account_profile_first_seen_ms = excluded.account_profile_first_seen_ms,
    llm_direction_hint = excluded.llm_direction_hint,
    llm_impact_hint = excluded.llm_impact_hint,
    llm_semantic_novelty_hint = excluded.llm_semantic_novelty_hint,
    llm_label_confidence = excluded.llm_label_confidence,
    asset_chain_id = excluded.asset_chain_id,
    asset_token_standard = excluded.asset_token_standard,
    asset_address = excluded.asset_address,
    asset_symbol = excluded.asset_symbol,
    asset_name = excluded.asset_name,
    asset_identity_confidence = excluded.asset_identity_confidence,
    asset_identity_reason_codes = excluded.asset_identity_reason_codes,
    asset_identity_conflict_count = excluded.asset_identity_conflict_count,
    asset_registry_status = excluded.asset_registry_status,
    cex_base_symbol = excluded.cex_base_symbol,
    cex_token_status = excluded.cex_token_status,
    feed_type = excluded.feed_type,
    pricefeed_provider = excluded.pricefeed_provider,
    native_market_id = excluded.native_market_id,
    pricefeed_base_symbol = excluded.pricefeed_base_symbol,
    pricefeed_quote_symbol = excluded.pricefeed_quote_symbol,
    pricefeed_status = excluded.pricefeed_status,
    first_price_observed_at_ms = excluded.first_price_observed_at_ms,
    first_price_usd = excluded.first_price_usd,
    first_price_quote = excluded.first_price_quote,
    first_price_quote_symbol = excluded.first_price_quote_symbol,
    first_price_basis = excluded.first_price_basis,
    event_price_capture_id = excluded.event_price_capture_id,
    event_price_capture_method = excluded.event_price_capture_method,
    event_price_capture_reason = excluded.event_price_capture_reason,
    event_price_tick_lag_ms = excluded.event_price_tick_lag_ms,
    event_price_provider = excluded.event_price_provider,
    event_price_source_tier = excluded.event_price_source_tier,
    event_price_pricefeed_id = excluded.event_price_pricefeed_id,
    event_price_observed_at_ms = excluded.event_price_observed_at_ms,
    event_price_received_at_ms = excluded.event_price_received_at_ms,
    event_price_usd = excluded.event_price_usd,
    event_price_quote = excluded.event_price_quote,
    event_price_quote_symbol = excluded.event_price_quote_symbol,
    event_price_basis = excluded.event_price_basis,
    event_price_market_cap_usd = excluded.event_price_market_cap_usd,
    event_price_liquidity_usd = excluded.event_price_liquidity_usd,
    event_price_volume_24h_usd = excluded.event_price_volume_24h_usd,
    event_price_open_interest_usd = excluded.event_price_open_interest_usd,
    event_price_holders = excluded.event_price_holders,
    latest_price_tick_id = excluded.latest_price_tick_id,
    latest_price_provider = excluded.latest_price_provider,
    latest_price_source_tier = excluded.latest_price_source_tier,
    latest_price_pricefeed_id = excluded.latest_price_pricefeed_id,
    latest_price_observed_at_ms = excluded.latest_price_observed_at_ms,
    latest_price_received_at_ms = excluded.latest_price_received_at_ms,
    latest_price_usd = excluded.latest_price_usd,
    latest_price_quote = excluded.latest_price_quote,
    latest_price_quote_symbol = excluded.latest_price_quote_symbol,
    latest_price_basis = excluded.latest_price_basis,
    latest_price_market_cap_usd = excluded.latest_price_market_cap_usd,
    latest_price_liquidity_usd = excluded.latest_price_liquidity_usd,
    latest_price_volume_24h_usd = excluded.latest_price_volume_24h_usd,
    latest_price_open_interest_usd = excluded.latest_price_open_interest_usd,
    latest_price_holders = excluded.latest_price_holders,
    before_event_price_observed_at_ms = excluded.before_event_price_observed_at_ms,
    before_event_price_usd = excluded.before_event_price_usd,
    before_event_price_quote = excluded.before_event_price_quote,
    before_event_price_quote_symbol = excluded.before_event_price_quote_symbol,
    before_event_price_basis = excluded.before_event_price_basis,
    first_seen_global_24h = excluded.first_seen_global_24h
  WHERE token_radar_rank_source_events.source_payload_hash IS DISTINCT FROM excluded.source_payload_hash
  RETURNING 1
),
deleted AS (
  DELETE FROM token_radar_rank_source_events stale_edges
  USING requested_event_ids requested
  WHERE stale_edges.projection_version = %s
    AND stale_edges."window" = requested."window"
    AND stale_edges.scope = requested.scope
    AND stale_edges.lane = 'resolved'
    AND stale_edges.target_type_key = requested.target_type_key
    AND stale_edges.identity_id = requested.identity_id
    AND stale_edges.source_kind = 'event'
    AND stale_edges.source_id = requested.source_event_id
    AND NOT EXISTS (
      SELECT 1
      FROM ranked_source fresh
      WHERE fresh."window" = stale_edges."window"
        AND fresh.scope = stale_edges.scope
        AND fresh.target_type_key = stale_edges.target_type_key
        AND fresh.identity_id = stale_edges.identity_id
        AND fresh.event_id = stale_edges.source_id
    )
  RETURNING 1
)
SELECT
  (SELECT COUNT(*) FROM upserted) AS upserted_count,
  (SELECT COUNT(*) FROM deleted) AS deleted_count
"""
