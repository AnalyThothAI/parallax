from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.token_intel._constants import TOKEN_RADAR_PROJECTION_VERSION

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
    }


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
