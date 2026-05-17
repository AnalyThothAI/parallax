from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger(__name__)


def fetch_target_recent_tweets(pool: Any, *, target_id: str, limit: int) -> dict[str, Any]:
    target = str(target_id or "").strip()
    if not target:
        return {"target_id": "", "tweets": []}

    try:
        with pool.connection() as conn:
            cur = conn.execute(
                """
                SELECT
                  e.event_id,
                  e.author_handle,
                  COALESCE(e.author_followers, 0) AS author_followers,
                  e.received_at_ms,
                  e.text_clean,
                  e.tweet_id,
                  tir.resolution_status,
                  COALESCE(tir.confidence, 0.0) AS confidence
                FROM events e
                JOIN token_intent_resolutions tir
                  ON tir.event_id = e.event_id
                 AND tir.is_current = true
                WHERE tir.target_id = %s
                  AND e.received_at_ms >= (
                    extract(epoch from now() - interval '24 hours') * 1000
                  )::bigint
                ORDER BY
                  CASE tir.resolution_status
                    WHEN 'EXACT' THEN 0
                    WHEN 'UNIQUE_BY_CONTEXT' THEN 1
                    WHEN 'AMBIGUOUS' THEN 2
                    ELSE 3
                  END,
                  COALESCE(tir.confidence, 0.0) DESC,
                  e.received_at_ms DESC
                LIMIT %s
                """,
                (target, int(limit)),
            )
            rows = cur.fetchall()
    except Exception as exc:
        return {"error": str(exc)[:300]}

    tweets: list[dict[str, Any]] = []
    for row in rows:
        event_id = str(row["event_id"]) if row.get("event_id") is not None else ""
        if not event_id:
            continue
        handle = row.get("author_handle") or ""
        tweet_id = row.get("tweet_id")
        confidence = float(row.get("confidence") or 0.0)
        weight = _resolution_weight(row.get("resolution_status"))
        tweets.append(
            {
                "event_id": event_id,
                "author_handle": handle,
                "author_followers": int(row.get("author_followers") or 0),
                "received_at_ms": int(row.get("received_at_ms") or 0),
                "text_clean": row.get("text_clean") or "",
                "tweet_url": _build_tweet_url(handle, str(tweet_id) if tweet_id else None),
                "resolution_status": row.get("resolution_status") or "",
                "attribution_weight": round(weight * (confidence if confidence > 0 else 1.0), 4),
            }
        )
    return {"target_id": target, "tweets": tweets}


def fetch_target_price_action(pool: Any, *, target_id: str, hours: int) -> dict[str, Any]:
    target = str(target_id or "").strip()
    bounded_hours = int(hours)
    if not target:
        return {"target_id": "", "hours": bounded_hours, "candles_count": 0}

    window_ms = bounded_hours * 3600 * 1000
    try:
        with pool.connection() as conn:
            cur = conn.execute(
                """
                WITH window_ticks AS (
                  SELECT
                    price_usd,
                    liquidity_usd,
                    volume_24h_usd,
                    market_cap_usd,
                    holders,
                    observed_at_ms
                  FROM market_ticks
                  WHERE target_id = %s
                    AND observed_at_ms >= (
                      (extract(epoch from now()) * 1000)::bigint - %s
                    )
                )
                SELECT
                  count(*) AS candles_count,
                  min(observed_at_ms) AS first_seen_ms,
                  max(observed_at_ms) AS latest_seen_ms,
                  max(price_usd) AS price_max,
                  min(price_usd) AS price_min,
                  max(liquidity_usd) AS liquidity_peak_usd,
                  max(volume_24h_usd) AS volume_24h_peak_usd,
                  max(holders) AS holders_peak
                FROM window_ticks
                """,
                (target, window_ms),
            )
            agg = cur.fetchone() or {}

            cur = conn.execute(
                """
                SELECT price_usd, liquidity_usd, volume_24h_usd, market_cap_usd,
                       holders, observed_at_ms
                FROM market_ticks
                WHERE target_id = %s
                  AND observed_at_ms >= (
                    (extract(epoch from now()) * 1000)::bigint - %s
                  )
                ORDER BY observed_at_ms ASC
                LIMIT 1
                """,
                (target, window_ms),
            )
            first = cur.fetchone()

            cur = conn.execute(
                """
                SELECT price_usd, liquidity_usd, volume_24h_usd, market_cap_usd,
                       holders, observed_at_ms
                FROM market_ticks
                WHERE target_id = %s
                ORDER BY observed_at_ms DESC
                LIMIT 1
                """,
                (target,),
            )
            latest = cur.fetchone()
    except Exception as exc:
        return {"error": str(exc)[:300]}

    candles_count = int((agg.get("candles_count") if agg else 0) or 0)
    first_price = float(first["price_usd"]) if first and first.get("price_usd") is not None else None
    latest_price = float(latest["price_usd"]) if latest and latest.get("price_usd") is not None else None
    return {
        "target_id": target,
        "hours": bounded_hours,
        "candles_count": candles_count,
        "first_seen_ms": _opt_int(agg.get("first_seen_ms")) if agg else None,
        "latest_seen_ms": _opt_int(agg.get("latest_seen_ms")) if agg else None,
        "current_price_usd": latest_price,
        "first_price_usd": first_price,
        "price_change_window_pct": _pct_change(first_price, latest_price),
        "price_min_usd": _opt_float(agg.get("price_min")) if agg else None,
        "price_max_usd": _opt_float(agg.get("price_max")) if agg else None,
        "liquidity_usd": _opt_float(latest.get("liquidity_usd")) if latest else None,
        "liquidity_peak_usd": _opt_float(agg.get("liquidity_peak_usd")) if agg else None,
        "volume_24h_usd": _opt_float(latest.get("volume_24h_usd")) if latest else None,
        "volume_24h_peak_usd": _opt_float(agg.get("volume_24h_peak_usd")) if agg else None,
        "market_cap_usd": _opt_float(latest.get("market_cap_usd")) if latest else None,
        "holders": _opt_int(latest.get("holders")) if latest else None,
        "holders_peak": _opt_int(agg.get("holders_peak")) if agg else None,
    }


def fetch_official_token_profile(pool: Any, *, target_id: str) -> dict[str, Any]:
    target = str(target_id or "").strip()
    if not target:
        return {}

    try:
        with pool.connection() as conn:
            cur = conn.execute(
                """
                SELECT
                  asset_id,
                  provider,
                  symbol,
                  name,
                  description,
                  website_url,
                  twitter_username,
                  twitter_url,
                  telegram_url,
                  logo_url,
                  banner_url,
                  updated_at_ms
                FROM asset_profiles
                WHERE asset_id = %s
                  AND status = 'ready'
                ORDER BY updated_at_ms DESC
                LIMIT 1
                """,
                (target,),
            )
            row = cur.fetchone()
    except Exception as exc:
        return {"error": str(exc)[:300]}

    if not row:
        return {}

    description_raw = row.get("description")
    description_value = description_raw.strip() if isinstance(description_raw, str) else None
    description_has_text = bool(description_value)
    return {
        "target_id": target,
        "provider": row.get("provider") or "",
        "symbol": row.get("symbol") or "",
        "name": row.get("name") or "",
        "website": row.get("website_url") or None,
        "twitter_username": row.get("twitter_username") or None,
        "twitter_url": row.get("twitter_url") or None,
        "telegram": row.get("telegram_url") or None,
        "description": description_value if description_has_text else None,
        "description_source_available": description_has_text,
        "logo_url": row.get("logo_url") or None,
        "banner_url": row.get("banner_url") or None,
    }


def fetch_evidence_event_urls(pool: Any, *, event_ids: list[str]) -> dict[str, str]:
    if not event_ids:
        return {}
    placeholders = ",".join(["%s"] * len(event_ids))
    try:
        with pool.connection() as conn:
            cur = conn.execute(
                f"""
                SELECT
                  event_id,
                  author_handle,
                  tweet_id,
                  canonical_url
                FROM events
                WHERE event_id IN ({placeholders})
                """,
                tuple(event_ids),
            )
            rows = cur.fetchall()
    except Exception as exc:
        _logger.warning("fetch_evidence_event_urls_failed err=%s", str(exc)[:300])
        return {}
    urls: dict[str, str] = {}
    for row in rows:
        event_id = row.get("event_id")
        canonical_url = row.get("canonical_url")
        url = canonical_url.strip() if isinstance(canonical_url, str) else ""
        if not url:
            url = _build_tweet_url(row.get("author_handle"), row.get("tweet_id")) or ""
        if event_id and url:
            urls[str(event_id)] = url
    return urls


def _build_tweet_url(handle: str | None, tweet_id: str | None) -> str | None:
    if not handle or not tweet_id:
        return None
    cleaned = str(handle).lstrip("@")
    if not cleaned:
        return None
    return f"https://x.com/{cleaned}/status/{tweet_id}"


def _resolution_weight(status: str | None) -> float:
    if status == "EXACT":
        return 1.0
    if status == "UNIQUE_BY_CONTEXT":
        return 0.9
    if status == "AMBIGUOUS":
        return 0.45
    return 0.1


def _pct_change(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    try:
        s = float(start)
        e = float(end)
    except (TypeError, ValueError):
        return None
    if s == 0:
        return None
    return round((e - s) / s * 100.0, 4)


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _opt_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "fetch_evidence_event_urls",
    "fetch_official_token_profile",
    "fetch_target_price_action",
    "fetch_target_recent_tweets",
]
