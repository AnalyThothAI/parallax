from __future__ import annotations

import hashlib
import time
from typing import Any

from ..retrieval.discussion_quality_scoring import discussion_quality_score
from ..retrieval.opportunity_scoring import opportunity_score
from ..retrieval.propagation_scoring import propagation_score
from ..retrieval.social_heat_scoring import social_heat_score
from ..retrieval.timing_scoring import timing_score
from ..retrieval.tradeability_scoring import tradeability_score
from ..storage.projection_repository import ProjectionRepository
from .token_radar_contract import (
    TOKEN_RADAR_PROJECTION_NAME,
    TOKEN_RADAR_PROJECTION_VERSION,
    TOKEN_RADAR_RESOLVER_POLICY_VERSION,
    TOKEN_RADAR_SOURCE_TABLE,
)
from .token_radar_feature_builder import BASELINE_SLOT_COUNT, build_radar_features

WINDOW_MS = {
    "5m": 5 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
}
MARKET_FRESH_MS = 5 * 60 * 1000
ATTENTION_HISTORY_MS = 24 * 60 * 60 * 1000
PROJECTION_VERSION = TOKEN_RADAR_PROJECTION_VERSION
STALE_RUNNING_PROJECTION_MS = 10 * 60 * 1000


class TokenRadarProjection:
    def __init__(self, *, repos):
        self.repos = repos

    def rebuild(self, *, window: str, scope: str, now_ms: int | None = None, limit: int = 100) -> dict[str, Any]:
        computed_at_ms = int(now_ms or time.time() * 1000)
        window_ms = WINDOW_MS.get(window, WINDOW_MS["1h"])
        score_since_ms = computed_at_ms - window_ms
        analysis_since_ms = _analysis_since_ms(computed_at_ms=computed_at_ms, window_ms=window_ms)
        source_rows = self._source_rows(since_ms=analysis_since_ms, scope=scope, now_ms=computed_at_ms)
        grouped = self._group_rows(source_rows)
        total_window_events = len(
            {
                str(row["event_id"])
                for row in source_rows
                if int(row.get("received_at_ms") or 0) >= score_since_ms
            }
        )
        projected = [
            row
            for group in grouped.values()
            if (row := _project_group(
                group,
                now_ms=computed_at_ms,
                window=window,
                scope=scope,
                score_since_ms=score_since_ms,
                window_ms=window_ms,
                total_window_events=total_window_events,
            ))
        ]
        resolved = [row for row in projected if row["lane"] == "resolved"]
        attention = [row for row in projected if row["lane"] == "attention"]
        resolved.sort(key=_rank_key)
        attention.sort(key=_rank_key)
        rows = []
        for lane_rows in (resolved, attention):
            for rank, row in enumerate(lane_rows[:limit], start=1):
                rows.append({**row, "rank": rank})
        source_max_received_at_ms = max(
            (int(row.get("source_max_received_at_ms") or 0) for row in rows),
            default=0,
        )
        projection_repo = ProjectionRepository(self.repos.conn)
        projection_repo.mark_stale_running_runs(
            projection_name=TOKEN_RADAR_PROJECTION_NAME,
            projection_version=PROJECTION_VERSION,
            stale_before_ms=computed_at_ms - STALE_RUNNING_PROJECTION_MS,
            finished_at_ms=computed_at_ms,
            commit=False,
        )
        run = projection_repo.start_run(
            projection_name=TOKEN_RADAR_PROJECTION_NAME,
            projection_version=PROJECTION_VERSION,
            mode="rebuild",
            source_start_ms=analysis_since_ms,
            source_end_ms=computed_at_ms,
            commit=False,
        )
        rows_replaced = self.repos.token_radar.replace_rows(
            projection_version=PROJECTION_VERSION,
            window=window,
            scope=scope,
            computed_at_ms=computed_at_ms,
            rows=rows,
            commit=False,
        )
        if not rows_replaced:
            projection_repo.finish_run(
                run_id=str(run["run_id"]),
                status="stale_skipped",
                rows_read=len(source_rows),
                rows_written=0,
                dirty_ranges_written=0,
                error="newer_projection_exists",
                commit=True,
            )
            return {
                "rows_written": 0,
                "source_rows": len(source_rows),
                "computed_at_ms": computed_at_ms,
                "status": "stale_skipped",
            }
        projection_repo.advance_offset(
            projection_name=TOKEN_RADAR_PROJECTION_NAME,
            projection_version=PROJECTION_VERSION,
            source_table=TOKEN_RADAR_SOURCE_TABLE,
            source_max_received_at_ms=source_max_received_at_ms,
            source_max_id=str(rows[0]["row_id"]) if rows else "",
            last_run_id=str(run["run_id"]),
            lag_ms=max(0, computed_at_ms - source_max_received_at_ms) if source_max_received_at_ms else 0,
            status="ready",
            commit=False,
        )
        projection_repo.finish_run(
            run_id=str(run["run_id"]),
            status="ready",
            rows_read=len(source_rows),
            rows_written=len(rows),
            dirty_ranges_written=0,
            commit=True,
        )
        return {
            "rows_written": len(rows),
            "source_rows": len(source_rows),
            "computed_at_ms": computed_at_ms,
            "status": "ready",
        }

    def _source_rows(self, *, since_ms: int, scope: str, now_ms: int) -> list[dict[str, Any]]:
        watched_clause = "AND events.is_watched = true" if scope == "matched" else ""
        rows = self.repos.conn.execute(
            f"""
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
              discovery.discovery_results AS discovery_results_json,
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
              registry_assets.symbol AS asset_symbol,
              registry_assets.name AS asset_name,
              registry_assets.status AS asset_registry_status,
              cex_tokens.base_symbol AS cex_base_symbol,
              cex_tokens.status AS cex_token_status,
              price_feeds.feed_type,
              price_feeds.provider AS pricefeed_provider,
              price_feeds.native_market_id,
              price_feeds.base_symbol AS pricefeed_base_symbol,
              price_feeds.quote_symbol AS pricefeed_quote_symbol,
              price_feeds.status AS pricefeed_status,
              latest_price.provider AS market_provider,
              latest_price.observed_at_ms AS market_observed_at_ms,
              latest_price.price_usd AS market_price_usd,
              latest_price.price_quote AS market_price_quote,
              latest_price.quote_symbol AS market_quote_symbol,
              latest_price.price_basis AS market_price_basis,
              latest_price.market_cap_usd AS market_market_cap_usd,
              latest_price.liquidity_usd AS market_liquidity_usd,
              latest_price.volume_24h_usd AS market_volume_24h_usd,
              latest_price.open_interest_usd AS market_open_interest_usd,
              latest_price.holders AS market_holders,
              first_price.observed_at_ms AS first_price_observed_at_ms,
              first_price.price_usd AS first_price_usd,
              first_price.price_quote AS first_price_quote,
              first_price.quote_symbol AS first_price_quote_symbol,
              first_price.price_basis AS first_price_basis,
              event_price.observation_id AS event_price_observation_id,
              event_price.observation_kind AS event_price_observation_kind,
              event_price.provider AS event_price_provider,
              event_price.observed_at_ms AS event_price_observed_at_ms,
              event_price.price_usd AS event_price_usd,
              event_price.price_quote AS event_price_quote,
              event_price.quote_symbol AS event_price_quote_symbol,
              event_price.price_basis AS event_price_basis,
              before_event_price.observed_at_ms AS before_event_price_observed_at_ms,
              before_event_price.price_usd AS before_event_price_usd,
              before_event_price.price_quote AS before_event_price_quote,
              before_event_price.quote_symbol AS before_event_price_quote_symbol,
              before_event_price.price_basis AS before_event_price_basis
            FROM token_intents
            JOIN token_intent_resolutions
              ON token_intent_resolutions.intent_id = token_intents.intent_id
             AND token_intent_resolutions.is_current = true
             AND token_intent_resolutions.resolver_policy_version = %s
            JOIN events ON events.event_id = token_intents.event_id
            LEFT JOIN account_profiles ap ON ap.handle = LOWER(events.author_handle)
            LEFT JOIN social_event_extractions see ON see.event_id = events.event_id
            LEFT JOIN registry_assets
              ON token_intent_resolutions.target_type = 'Asset'
             AND registry_assets.asset_id = token_intent_resolutions.target_id
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
              SELECT jsonb_agg(
                jsonb_build_object(
                  'lookup_key', token_discovery_results.lookup_key,
                  'lookup_type', token_discovery_results.lookup_type,
                  'status', token_discovery_results.status,
                  'candidate_count', token_discovery_results.candidate_count,
                  'last_lookup_at_ms', token_discovery_results.last_lookup_at_ms,
                  'next_refresh_at_ms', token_discovery_results.next_refresh_at_ms,
                  'last_error', token_discovery_results.last_error,
                  'error_count', token_discovery_results.error_count
                )
                ORDER BY token_discovery_results.lookup_key
              ) AS discovery_results
              FROM token_discovery_results
              WHERE token_discovery_results.provider = 'okx_dex_search'
                AND token_discovery_results.lookup_key IN (
                  SELECT jsonb_array_elements_text(token_intent_resolutions.lookup_keys_json)
                )
            ) discovery ON true
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_observations
              WHERE price_observations.observed_at_ms <= %s
                AND (
                  (
                    COALESCE(token_intent_resolutions.pricefeed_id, preferred_price_feed.pricefeed_id) IS NOT NULL
                    AND price_observations.pricefeed_id = COALESCE(
                      token_intent_resolutions.pricefeed_id,
                      preferred_price_feed.pricefeed_id
                    )
                  )
                  OR (
                    token_intent_resolutions.target_type IS NOT NULL
                    AND token_intent_resolutions.target_id IS NOT NULL
                    AND price_observations.subject_type = token_intent_resolutions.target_type
                    AND price_observations.subject_id = token_intent_resolutions.target_id
                  )
                )
              ORDER BY
                CASE
                  WHEN price_observations.pricefeed_id = COALESCE(
                    token_intent_resolutions.pricefeed_id,
                    preferred_price_feed.pricefeed_id
                  ) THEN 0
                  ELSE 1
                END,
                observed_at_ms DESC,
                observation_id DESC
              LIMIT 1
            ) latest_price ON true
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_observations
              WHERE token_intent_resolutions.target_type IS NOT NULL
                AND token_intent_resolutions.target_id IS NOT NULL
                AND price_observations.subject_type = token_intent_resolutions.target_type
                AND price_observations.subject_id = token_intent_resolutions.target_id
              ORDER BY observed_at_ms ASC, observation_id ASC
              LIMIT 1
            ) first_price ON true
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_observations
              WHERE token_intent_resolutions.target_type IS NOT NULL
                AND token_intent_resolutions.target_id IS NOT NULL
                AND (
                  (
                    price_observations.source_resolution_id = token_intent_resolutions.resolution_id
                    AND price_observations.subject_type = token_intent_resolutions.target_type
                    AND price_observations.subject_id = token_intent_resolutions.target_id
                    AND price_observations.observation_kind IN ('message_payload', 'message_quote')
                  )
                  OR (
                    price_observations.subject_type = token_intent_resolutions.target_type
                    AND price_observations.subject_id = token_intent_resolutions.target_id
                    AND price_observations.observed_at_ms <= events.received_at_ms
                  )
                )
              ORDER BY
                CASE
                  WHEN price_observations.source_resolution_id = token_intent_resolutions.resolution_id
                    AND price_observations.observation_kind = 'message_payload' THEN 0
                  WHEN price_observations.source_resolution_id = token_intent_resolutions.resolution_id
                    AND price_observations.observation_kind = 'message_quote' THEN 1
                  ELSE 2
                END,
                observed_at_ms DESC,
                observation_id DESC
              LIMIT 1
            ) event_price ON true
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_observations
              WHERE token_intent_resolutions.target_type IS NOT NULL
                AND token_intent_resolutions.target_id IS NOT NULL
                AND price_observations.subject_type = token_intent_resolutions.target_type
                AND price_observations.subject_id = token_intent_resolutions.target_id
                AND price_observations.observed_at_ms < events.received_at_ms - 300000
              ORDER BY observed_at_ms DESC, observation_id DESC
              LIMIT 1
            ) before_event_price ON true
            WHERE events.received_at_ms >= %s {watched_clause}
            """,
            (TOKEN_RADAR_RESOLVER_POLICY_VERSION, now_ms, since_ms),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _group_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = (
                f"{row.get('target_type')}:{row.get('target_id')}"
                if row.get("target_type") and row.get("target_id")
                else str(row.get("intent_id"))
            )
            grouped.setdefault(key, []).append(row)
        return grouped


def _analysis_since_ms(*, computed_at_ms: int, window_ms: int) -> int:
    score_since_ms = computed_at_ms - window_ms
    baseline_since_ms = score_since_ms - BASELINE_SLOT_COUNT * window_ms
    attention_since_ms = computed_at_ms - ATTENTION_HISTORY_MS
    return min(baseline_since_ms, attention_since_ms)


def _project_group(
    rows: list[dict[str, Any]],
    *,
    now_ms: int,
    window: str,
    scope: str,
    score_since_ms: int | None = None,
    window_ms: int | None = None,
    total_window_events: int | None = None,
) -> dict[str, Any] | None:
    resolved_window_ms = window_ms or WINDOW_MS.get(window, WINDOW_MS["1h"])
    resolved_score_since_ms = score_since_ms if score_since_ms is not None else min(
        int(row.get("received_at_ms") or 0) for row in rows
    )
    window_rows = [
        row for row in rows
        if int(row.get("received_at_ms") or 0) >= resolved_score_since_ms
    ]
    if not window_rows:
        return None
    previous_rows = [
        row for row in rows
        if resolved_score_since_ms - resolved_window_ms <= int(row.get("received_at_ms") or 0) < resolved_score_since_ms
    ]
    latest = max(window_rows, key=lambda row: int(row.get("received_at_ms") or 0))
    event_ids = sorted({str(row["event_id"]) for row in window_rows})
    latest_seen_ms = max(int(row.get("received_at_ms") or 0) for row in rows)
    resolution_status = str(latest.get("resolution_status") or "NIL")
    target_type = str(latest.get("target_type") or "") or None
    target_id = str(latest.get("target_id") or "") or None
    resolved = _has_resolved_target(latest)
    lane = "resolved" if resolved else "attention"
    target = _target(latest)
    market = _market(window_rows, resolved=resolved, now_ms=now_ms)
    scored_window_rows = [{**row, **_market_prefix_for_features(market)} for row in window_rows]
    features = build_radar_features(
        window_rows=scored_window_rows,
        context_rows=rows,
        previous_rows=previous_rows,
        now_ms=now_ms,
        window_ms=resolved_window_ms,
        total_window_events=total_window_events or len(event_ids),
    )
    score = _score(features)
    decision = str(score["opportunity"].get("decision") or "discard")
    return {
        "row_id": _stable_id(
            "token-radar-row",
            window,
            scope,
            str(target_id or latest.get("intent_id")),
            str(now_ms),
        ),
        "source_max_received_at_ms": latest_seen_ms,
        "lane": lane,
        "rank": 0,
        "intent_id": latest["intent_id"],
        "event_id": latest["event_id"],
        "target_type": target_type,
        "target_id": target_id,
        "pricefeed_id": latest.get("pricefeed_id"),
        "intent_json": {
            "intent_id": latest["intent_id"],
            "display_symbol": _real_symbol(latest.get("display_symbol")),
            "display_name": latest.get("display_name"),
            "evidence": [],
        },
        "asset_json": target if target_type == "Asset" else {},
        "target_json": target,
        "primary_venue_json": None,
        "attention_json": {
            **features.attention,
            "latest_seen_ms": latest_seen_ms,
        },
        "resolution_json": {
            "status": resolution_status,
            "target_type": target_type,
            "target_id": target_id,
            "pricefeed_id": latest.get("pricefeed_id"),
            "reason_codes": latest.get("reason_codes_json") or [],
            "candidate_ids": latest.get("candidate_ids_json") or [],
            "lookup_keys": latest.get("lookup_keys_json") or [],
            "discovery": _resolution_discovery(latest),
        },
        "market_json": market,
        "price_json": market,
        "score_json": score,
        "decision": decision,
        "data_health_json": {
            "identity": resolution_status,
            "market": market["market_observation_status"],
            "coverage": "public_stream",
        },
        "source_event_ids_json": event_ids,
        "created_at_ms": now_ms,
    }


def _has_resolved_target(row: dict[str, Any]) -> bool:
    return bool(row.get("target_id")) and str(row.get("resolution_status") or "") in {
        "EXACT",
        "UNIQUE_BY_CONTEXT",
    }


def _resolution_discovery(row: dict[str, Any]) -> list[dict[str, Any]]:
    lookup_keys = _discovery_lookup_keys(row.get("lookup_keys_json") or [])
    existing = [
        _discovery_result(item)
        for item in row.get("discovery_results_json") or []
        if isinstance(item, dict) and item.get("lookup_key")
    ]
    existing_by_key = {str(item["lookup_key"]): item for item in existing}
    out: list[dict[str, Any]] = []
    for key in lookup_keys:
        out.append(existing_by_key.get(key) or _not_searched_discovery(key))
    seen = {str(item["lookup_key"]) for item in out}
    out.extend(item for item in existing if str(item["lookup_key"]) not in seen)
    return out


def _discovery_lookup_keys(raw_keys: list[Any]) -> list[str]:
    out: list[str] = []
    for raw_key in raw_keys:
        key = str(raw_key or "")
        if key.startswith("symbol:") or key.startswith("address:"):
            out.append(key)
    return sorted(set(out))


def _discovery_result(item: dict[str, Any]) -> dict[str, Any]:
    lookup_key = str(item.get("lookup_key") or "")
    return {
        "lookup_key": lookup_key,
        "lookup_type": item.get("lookup_type") or _lookup_type(lookup_key),
        "status": item.get("status") or "unknown",
        "candidate_count": int(item.get("candidate_count") or 0),
        "last_lookup_at_ms": item.get("last_lookup_at_ms"),
        "next_refresh_at_ms": item.get("next_refresh_at_ms"),
        "last_error": item.get("last_error"),
        "error_count": int(item.get("error_count") or 0),
    }


def _not_searched_discovery(lookup_key: str) -> dict[str, Any]:
    return {
        "lookup_key": lookup_key,
        "lookup_type": _lookup_type(lookup_key),
        "status": "not_searched",
        "candidate_count": 0,
        "last_lookup_at_ms": None,
        "next_refresh_at_ms": None,
        "last_error": None,
        "error_count": 0,
    }


def _lookup_type(lookup_key: str) -> str:
    if lookup_key.startswith("symbol:"):
        return "dex_symbol_lookup"
    if lookup_key.startswith("address:"):
        return "address_lookup"
    return "unknown_lookup"


def _target(row: dict[str, Any]) -> dict[str, Any]:
    target_type = row.get("target_type")
    target_id = row.get("target_id")
    if not target_type or not target_id:
        return {
            "target_type": None,
            "target_id": None,
            "symbol": _display_symbol(row),
            "status": str(row.get("resolution_status") or "NIL"),
        }
    if target_type == "CexToken":
        return {
            "target_type": "CexToken",
            "target_id": target_id,
            "symbol": _display_symbol(row),
            "status": row.get("cex_token_status"),
            "pricefeed_id": row.get("pricefeed_id"),
            "native_market_id": row.get("native_market_id"),
            "quote_symbol": row.get("pricefeed_quote_symbol"),
            "feed_type": row.get("feed_type"),
            "provider": row.get("pricefeed_provider"),
        }
    return {
        "target_type": "Asset",
        "target_id": target_id,
        "symbol": _display_symbol(row),
        "name": row.get("asset_name"),
        "chain_id": row.get("asset_chain_id"),
        "token_standard": row.get("asset_token_standard"),
        "address": row.get("asset_address"),
        "status": row.get("asset_registry_status"),
        "pricefeed_id": row.get("pricefeed_id"),
    }


def _market(window_rows: list[dict[str, Any]], *, resolved: bool, now_ms: int) -> dict[str, Any]:
    if not resolved:
        return _missing_market("no_resolved_target")
    if not window_rows:
        return _missing_market("pending_refresh")
    latest = max(window_rows, key=lambda item: int(item.get("received_at_ms") or 0))
    social_start = min(window_rows, key=lambda item: int(item.get("received_at_ms") or 0))
    observed_at_ms = _int_or_none(latest.get("market_observed_at_ms"))
    if observed_at_ms is not None:
        snapshot_age_ms = max(0, int(now_ms) - observed_at_ms)
        fresh = snapshot_age_ms <= MARKET_FRESH_MS
        reference_value, social_value, social_basis = _comparable_price(
            _price_values(latest, "market"),
            _price_values(social_start, "event"),
        )
        social_for_before, before_value, before_basis = _comparable_price(
            _price_values(social_start, "event"),
            _price_values(social_start, "before_event"),
        )
        reference_for_first, first_value, first_basis = _comparable_price(
            _price_values(latest, "market"),
            _price_values(latest, "first"),
        )
        price_change_status = (
            "ready" if reference_value is not None and social_value is not None else "insufficient_history"
        )
        if social_basis == "basis_mismatch":
            price_change_status = "basis_mismatch"
        return {
            "market_status": "fresh" if fresh else "stale",
            "market_observation_status": "ready" if fresh else "stale",
            "price_change_status": price_change_status,
            "provider": latest.get("market_provider"),
            "pricefeed_id": latest.get("pricefeed_id"),
            "price_usd": latest.get("market_price_usd"),
            "price_quote": latest.get("market_price_quote"),
            "quote_symbol": latest.get("market_quote_symbol") or latest.get("pricefeed_quote_symbol"),
            "price_basis": latest.get("market_price_basis"),
            "market_cap_usd": latest.get("market_market_cap_usd"),
            "liquidity_usd": latest.get("market_liquidity_usd"),
            "volume_24h_usd": latest.get("market_volume_24h_usd"),
            "open_interest_usd": latest.get("market_open_interest_usd"),
            "holders": latest.get("market_holders"),
            "snapshot_age_ms": snapshot_age_ms,
            "snapshot_observed_at_ms": observed_at_ms,
            "social_signal_start_ms": social_start.get("received_at_ms"),
            "price_at_social_start": social_value,
            "price_at_reference": reference_value,
            "price_change_since_social_pct": _pct_change(reference_value, social_value),
            "price_change_basis": social_basis,
            "price_before_social_start": before_value,
            "price_change_before_social_pct": _pct_change(social_for_before, before_value)
            if before_basis != "basis_mismatch"
            else None,
            "price_at_first_snapshot": first_value,
            "first_snapshot_observed_at_ms": latest.get("first_price_observed_at_ms"),
            "price_change_since_first_snapshot_pct": _pct_change(reference_for_first, first_value)
            if first_basis != "basis_mismatch"
            else None,
        }
    missing = _missing_market("pending_refresh")
    missing["social_signal_start_ms"] = min((int(row.get("received_at_ms") or 0) for row in window_rows), default=None)
    return missing


def _missing_market(status: str) -> dict[str, Any]:
    return {
        "market_status": "missing",
        "market_observation_status": status,
        "price_change_status": status,
        "provider": None,
        "pricefeed_id": None,
        "price_usd": None,
        "price_quote": None,
        "quote_symbol": None,
        "price_basis": None,
        "market_cap_usd": None,
        "liquidity_usd": None,
        "volume_24h_usd": None,
        "open_interest_usd": None,
        "holders": None,
        "snapshot_age_ms": None,
        "snapshot_observed_at_ms": None,
        "social_signal_start_ms": None,
        "price_at_social_start": None,
        "price_at_reference": None,
        "price_before_social_start": None,
        "price_at_first_snapshot": None,
        "first_snapshot_observed_at_ms": None,
        "price_change_since_social_pct": None,
        "price_change_before_social_pct": None,
        "price_change_since_first_snapshot_pct": None,
    }


def _score(features) -> dict[str, Any]:
    components = {
        "heat": social_heat_score(features.heat),
        "quality": discussion_quality_score(features.quality),
        "propagation": propagation_score(features.propagation),
        "tradeability": tradeability_score(features.tradeability),
        "timing": timing_score(features.timing),
    }
    return {**components, "opportunity": opportunity_score(components)}


def _market_prefix_for_features(market: dict[str, Any]) -> dict[str, Any]:
    return {
        "market_status": market.get("market_status"),
        "market_observation_status": market.get("market_observation_status"),
        "price_change_since_social_pct": market.get("price_change_since_social_pct"),
        "price_change_before_social_pct": market.get("price_change_before_social_pct"),
    }


def _price_values(row: dict[str, Any], prefix: str) -> dict[str, Any]:
    if prefix == "market":
        return {
            "price_usd": row.get("market_price_usd"),
            "price_quote": row.get("market_price_quote"),
            "quote_symbol": row.get("market_quote_symbol") or row.get("pricefeed_quote_symbol"),
            "price_basis": row.get("market_price_basis"),
        }
    return {
        "price_usd": row.get(f"{prefix}_price_usd"),
        "price_quote": row.get(f"{prefix}_price_quote"),
        "quote_symbol": row.get(f"{prefix}_price_quote_symbol"),
        "price_basis": row.get(f"{prefix}_price_basis"),
    }


def _comparable_price(current: dict[str, Any], base: dict[str, Any]) -> tuple[Any, Any, str]:
    if current.get("price_usd") is not None and base.get("price_usd") is not None:
        return current["price_usd"], base["price_usd"], "usd"
    current_quote = current.get("quote_symbol")
    base_quote = base.get("quote_symbol")
    if current_quote and base_quote and current_quote == base_quote:
        return current.get("price_quote"), base.get("price_quote"), f"quote:{current_quote}"
    return None, None, "basis_mismatch"


def _pct_change(current: Any, base: Any) -> float | None:
    current_value = _float_or_none(current)
    base_value = _float_or_none(base)
    if current_value is None or base_value is None or base_value == 0:
        return None
    return round(current_value / base_value - 1.0, 6)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _display_symbol(row: dict[str, Any]) -> str | None:
    for value in (
        row.get("display_symbol"),
        row.get("cex_base_symbol"),
        row.get("asset_symbol"),
        row.get("pricefeed_base_symbol"),
    ):
        symbol = _real_symbol(value)
        if symbol:
            return symbol
    return None


def _real_symbol(value: Any) -> str | None:
    if value is None:
        return None
    symbol = str(value).strip().lstrip("$")
    if not symbol:
        return None
    if _is_address_like_symbol(symbol):
        return None
    return symbol


def _is_address_like_symbol(symbol: str) -> bool:
    value = symbol.strip().upper()
    if value.startswith("0X") and len(value) >= 22:
        return all(char in "0123456789ABCDEF" for char in value[2:])
    if len(value) < 32:
        return False
    if value.endswith("PUMP"):
        value = value[:-4]
    return all(char.isdigit() or ("A" <= char <= "Z") for char in value)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rank_key(row: dict[str, Any]) -> tuple[int, int, int, int]:
    attention = row["attention_json"]
    score = row.get("score_json") if isinstance(row.get("score_json"), dict) else {}
    decision_priority = {"driver": 0, "watch": 1, "investigate": 2, "discard": 3}
    opportunity = score.get("opportunity") if isinstance(score.get("opportunity"), dict) else {}
    heat = score.get("heat") if isinstance(score.get("heat"), dict) else {}
    return (
        decision_priority.get(str(row.get("decision") or "discard"), 3),
        -int(opportunity.get("score") or 0),
        -int(heat.get("score") or 0),
        -int(attention["latest_seen_ms"]),
    )


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
