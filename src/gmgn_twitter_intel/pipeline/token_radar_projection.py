from __future__ import annotations

import hashlib
import time
from typing import Any

from ..storage.projection_repository import ProjectionRepository
from .deterministic_token_resolver import RESOLVER_POLICY_VERSION

WINDOW_MS = {
    "5m": 5 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
}
MARKET_FRESH_MS = 5 * 60 * 1000
PROJECTION_VERSION = "token-radar-v4"


class TokenRadarProjection:
    def __init__(self, *, repos):
        self.repos = repos

    def rebuild(self, *, window: str, scope: str, now_ms: int | None = None, limit: int = 100) -> dict[str, Any]:
        computed_at_ms = int(now_ms or time.time() * 1000)
        since_ms = computed_at_ms - WINDOW_MS.get(window, WINDOW_MS["1h"])
        source_rows = self._source_rows(since_ms=since_ms, scope=scope, now_ms=computed_at_ms)
        grouped = self._group_rows(source_rows)
        projected = [
            _project_group(group, now_ms=computed_at_ms, window=window, scope=scope)
            for group in grouped.values()
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
        run = ProjectionRepository(self.repos.conn).start_run(
            projection_name="token-radar",
            projection_version=PROJECTION_VERSION,
            mode="rebuild",
            source_start_ms=since_ms,
            source_end_ms=computed_at_ms,
            commit=False,
        )
        self.repos.token_radar.replace_rows(
            projection_version=PROJECTION_VERSION,
            window=window,
            scope=scope,
            computed_at_ms=computed_at_ms,
            rows=rows,
            commit=False,
        )
        ProjectionRepository(self.repos.conn).advance_offset(
            projection_name="token-radar",
            projection_version=PROJECTION_VERSION,
            source_table="token_intent_resolutions",
            source_max_received_at_ms=source_max_received_at_ms,
            source_max_id=str(rows[0]["row_id"]) if rows else "",
            last_run_id=str(run["run_id"]),
            lag_ms=max(0, computed_at_ms - source_max_received_at_ms) if source_max_received_at_ms else 0,
            status="ready",
            commit=False,
        )
        ProjectionRepository(self.repos.conn).finish_run(
            run_id=str(run["run_id"]),
            status="ready",
            rows_read=len(source_rows),
            rows_written=len(rows),
            dirty_ranges_written=0,
            commit=True,
        )
        return {"rows_written": len(rows), "source_rows": len(source_rows), "computed_at_ms": computed_at_ms}

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
              token_intent_resolutions.decision_time_ms,
              events.author_handle,
              events.is_watched,
              events.received_at_ms,
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
              latest_price.holders AS market_holders
            FROM token_intents
            JOIN token_intent_resolutions
              ON token_intent_resolutions.intent_id = token_intents.intent_id
             AND token_intent_resolutions.is_current = true
             AND token_intent_resolutions.resolver_policy_version = %s
            JOIN events ON events.event_id = token_intents.event_id
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
            WHERE events.received_at_ms >= %s {watched_clause}
            """,
            (RESOLVER_POLICY_VERSION, now_ms, since_ms),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _group_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = str(row.get("target_id") or row.get("intent_id"))
            grouped.setdefault(key, []).append(row)
        return grouped


def _project_group(rows: list[dict[str, Any]], *, now_ms: int, window: str, scope: str) -> dict[str, Any]:
    latest = max(rows, key=lambda row: int(row.get("received_at_ms") or 0))
    event_ids = sorted({str(row["event_id"]) for row in rows})
    authors = {str(row.get("author_handle") or "") for row in rows if row.get("author_handle")}
    watched = sum(1 for row in rows if row.get("is_watched"))
    latest_seen_ms = max(int(row.get("received_at_ms") or 0) for row in rows)
    resolution_status = str(latest.get("resolution_status") or "NIL")
    target_type = str(latest.get("target_type") or "") or None
    target_id = str(latest.get("target_id") or "") or None
    resolved = _has_resolved_target(latest)
    lane = "resolved" if resolved else "attention"
    target = _target(latest)
    market = _market(latest, resolved=resolved, now_ms=now_ms)
    score = _score(mentions=len(event_ids), authors=len(authors), watched=watched, resolved=resolved, market=market)
    decision = _decision(score=score, resolved=resolved, market=market)
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
            "mentions_5m": len(event_ids),
            "mentions_1h": len(event_ids),
            "mentions_window": len(event_ids),
            "unique_authors": len(authors),
            "watched_mentions": watched,
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


def _market(row: dict[str, Any], *, resolved: bool, now_ms: int) -> dict[str, Any]:
    if not resolved:
        return _missing_market("no_resolved_target")
    observed_at_ms = _int_or_none(row.get("market_observed_at_ms"))
    if observed_at_ms is not None:
        snapshot_age_ms = max(0, int(now_ms) - observed_at_ms)
        fresh = snapshot_age_ms <= MARKET_FRESH_MS
        return {
            "market_status": "fresh" if fresh else "stale",
            "market_observation_status": "ready" if fresh else "stale",
            "price_change_status": "insufficient_history",
            "provider": row.get("market_provider"),
            "pricefeed_id": row.get("pricefeed_id"),
            "price_usd": row.get("market_price_usd"),
            "price_quote": row.get("market_price_quote"),
            "quote_symbol": row.get("market_quote_symbol") or row.get("pricefeed_quote_symbol"),
            "price_basis": row.get("market_price_basis"),
            "market_cap_usd": row.get("market_market_cap_usd"),
            "liquidity_usd": row.get("market_liquidity_usd"),
            "volume_24h_usd": row.get("market_volume_24h_usd"),
            "open_interest_usd": row.get("market_open_interest_usd"),
            "holders": row.get("market_holders"),
            "snapshot_age_ms": snapshot_age_ms,
            "snapshot_observed_at_ms": observed_at_ms,
            "price_at_social_start": None,
            "price_at_reference": row.get("market_price_usd") or row.get("market_price_quote"),
            "price_change_since_social_pct": None,
            "price_before_social_start": None,
            "price_change_before_social_pct": None,
        }
    return _missing_market("pending_refresh")


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
        "price_change_since_social_pct": None,
        "price_change_before_social_pct": None,
    }


def _score(*, mentions: int, authors: int, watched: int, resolved: bool, market: dict[str, Any]) -> dict[str, Any]:
    heat = min(100, 30 + mentions * 6 + authors * 8 + watched * 8)
    quality = min(100, 70 + watched * 8) if resolved else min(70, 35 + mentions * 8)
    propagation = min(100, 30 + authors * 14)
    market_usable = _market_usable_for_driver(market)
    market_risks = [] if market_usable else [_market_risk(market)]
    hard_risks = [] if resolved and market_usable else market_risks if resolved else ["unresolved_token_identity"]
    price_health = 80 if resolved and market_usable else 45 if resolved else 20
    timing = 50 if resolved else 35
    opportunity = round(heat * 0.4 + quality * 0.25 + propagation * 0.2 + price_health * 0.1 + timing * 0.05)
    return {
        "heat": _score_block(heat),
        "quality": _score_block(quality),
        "propagation": _score_block(propagation),
        "price_health": _score_block(price_health, hard_risks=hard_risks),
        "timing": _score_block(timing),
        "opportunity": _score_block(opportunity, hard_risks=hard_risks),
    }


def _score_block(score: int, *, hard_risks: list[str] | None = None) -> dict[str, Any]:
    return {
        "score": int(score),
        "score_version": "token_radar_v4",
        "reasons": [],
        "risks": hard_risks or [],
        "hard_risks": hard_risks or [],
        "contributions": [],
        "risk_caps": [],
    }


def _decision(*, score: dict[str, Any], resolved: bool, market: dict[str, Any]) -> str:
    if not resolved:
        return "investigate"
    opportunity = int((score.get("opportunity") or {}).get("score") or 0)
    if not _market_usable_for_driver(market):
        return "watch" if opportunity >= 45 else "discard"
    return "driver" if opportunity >= 75 else "watch" if opportunity >= 45 else "discard"


def _market_usable_for_driver(market: dict[str, Any]) -> bool:
    return str(market.get("market_status") or "") in {"fresh", "ready", "stale"} and str(
        market.get("market_observation_status") or ""
    ) in {"ready", "stale"}


def _market_risk(market: dict[str, Any]) -> str:
    status = str(market.get("market_observation_status") or "missing_market")
    if status == "pending_refresh":
        return "market_pending"
    if status == "no_resolved_target":
        return "unresolved_token_identity"
    return status


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


def _rank_key(row: dict[str, Any]) -> tuple[int, int]:
    attention = row["attention_json"]
    return (-int(attention["mentions_window"]), -int(attention["latest_seen_ms"]))


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
