from __future__ import annotations

import json
from typing import Any

from gmgn_twitter_intel.domains.asset_market.interfaces import message_price_payload


class EventTokenProjectionQuery:
    def __init__(self, conn: Any):
        self.conn = conn

    def for_event(self, event_id: str) -> list[dict[str, Any]]:
        return self.for_events((event_id,)).get(str(event_id), [])

    def for_events(self, event_ids: tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
        ids = tuple(dict.fromkeys(str(item).strip() for item in event_ids if str(item or "").strip()))
        if not ids:
            return {}
        rows = self.conn.execute(
            """
            WITH requested_events(event_id, request_rank) AS MATERIALIZED (
              SELECT event_id, request_rank
              FROM unnest(%s::text[]) WITH ORDINALITY AS requested(event_id, request_rank)
            )
            SELECT
              tir.resolution_id,
              tir.intent_id,
              tir.event_id,
              tir.target_type,
              tir.target_id,
              COALESCE(tir.pricefeed_id, preferred_price_feed.pricefeed_id) AS pricefeed_id,
              tir.resolution_status,
              tir.reason_codes_json,
              tir.candidate_ids_json,
              tir.lookup_keys_json,
              COALESCE(
                asset_identity_current.canonical_symbol,
                cex_tokens.base_symbol,
                price_feeds.base_symbol
              ) AS symbol,
              price_feeds.quote_symbol AS quote_symbol,
              COALESCE(event_tick.tick_id, latest_tick.tick_id) AS market_tick_id,
              COALESCE(event_tick.source_provider, latest_tick.source_provider) AS market_tick_provider,
              COALESCE(event_tick.observed_at_ms, latest_tick.observed_at_ms) AS market_tick_observed_at_ms,
              COALESCE(event_tick.price_usd, latest_tick.price_usd) AS price_usd,
              NULL::numeric AS price_quote,
              NULL::text AS price_quote_symbol,
              COALESCE(
                event_market_capture.capture_method,
                CASE WHEN latest_tick.tick_id IS NOT NULL THEN 'latest_market_tick' ELSE NULL END
              ) AS market_capture_method,
              COALESCE(
                event_market_capture.tick_lag_ms,
                CASE
                  WHEN latest_tick.tick_id IS NOT NULL THEN ABS(latest_tick.observed_at_ms - events.received_at_ms)
                  ELSE NULL
                END
              ) AS market_tick_lag_ms
            FROM requested_events
            JOIN token_intent_resolutions tir
              ON tir.event_id = requested_events.event_id
             AND tir.is_current = TRUE
             AND tir.target_type IN ('Asset', 'CexToken')
             AND tir.target_id IS NOT NULL
            JOIN events
              ON events.event_id = tir.event_id
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
            LEFT JOIN enriched_events event_market_capture
              ON event_market_capture.event_id = tir.event_id
             AND event_market_capture.intent_id = tir.intent_id
             AND event_market_capture.resolution_id = tir.resolution_id
            LEFT JOIN market_ticks event_tick
              ON event_tick.tick_id = event_market_capture.tick_id
            LEFT JOIN LATERAL (
              SELECT
                CASE
                  WHEN tir.target_type = 'Asset'
                    AND registry_assets.chain_id IS NOT NULL
                    AND registry_assets.address IS NOT NULL
                    THEN 'chain_token'
                  WHEN tir.target_type = 'CexToken'
                    AND price_feeds.provider IS NOT NULL
                    AND price_feeds.native_market_id IS NOT NULL
                    THEN 'cex_symbol'
                  ELSE NULL
                END AS target_type,
                CASE
                  WHEN tir.target_type = 'Asset'
                    AND registry_assets.chain_id IS NOT NULL
                    AND registry_assets.address IS NOT NULL
                    THEN registry_assets.chain_id || ':' || registry_assets.address
                  WHEN tir.target_type = 'CexToken'
                    AND price_feeds.provider IS NOT NULL
                    AND price_feeds.native_market_id IS NOT NULL
                    THEN price_feeds.provider || ':' || price_feeds.native_market_id
                  ELSE NULL
                END AS target_id
            ) market_target ON true
            LEFT JOIN LATERAL (
              SELECT market_ticks.*
              FROM market_ticks
              WHERE market_ticks.target_type = market_target.target_type
                AND market_ticks.target_id = market_target.target_id
              ORDER BY market_ticks.observed_at_ms DESC, market_ticks.received_at_ms DESC, market_ticks.tick_id DESC
              LIMIT 1
            ) latest_tick ON event_tick.tick_id IS NULL
            ORDER BY requested_events.request_rank, tir.decision_time_ms, tir.resolution_id
            """,
            (list(ids),),
        ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            projected = _project_token_resolution(dict(row))
            if projected is None:
                continue
            grouped.setdefault(str(projected["event_id"]), []).append(projected)
        return grouped


def _project_token_resolution(row: dict[str, Any]) -> dict[str, Any] | None:
    target_type = _clean_text(row.get("target_type"))
    target_id = _clean_text(row.get("target_id"))
    if target_type not in {"Asset", "CexToken"} or not target_id:
        return None
    return {
        "resolution_id": str(row.get("resolution_id") or ""),
        "intent_id": str(row.get("intent_id") or ""),
        "event_id": str(row.get("event_id") or ""),
        "target_type": target_type,
        "target_id": target_id,
        "pricefeed_id": _clean_text(row.get("pricefeed_id")),
        "resolution_status": str(row.get("resolution_status") or ""),
        "reason_codes_json": _loads(row.get("reason_codes_json"), []),
        "candidate_ids_json": _loads(row.get("candidate_ids_json"), []),
        "lookup_keys_json": _loads(row.get("lookup_keys_json"), []),
        "symbol": _resolution_symbol(row, target_type=target_type, target_id=target_id),
        "price": message_price_payload(row),
    }


def _resolution_symbol(row: dict[str, Any], *, target_type: str, target_id: str) -> str | None:
    symbol = _clean_text(row.get("symbol"))
    if symbol:
        return symbol
    if target_type != "CexToken":
        return None
    return target_id.rsplit(":", maxsplit=1)[-1].upper()


def _clean_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    if not value.strip():
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


__all__ = ["EventTokenProjectionQuery"]
