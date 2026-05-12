from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_RESOLVER_POLICY_VERSION


class StocksRadarQuery:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def stock_rows(self, *, since_ms: int, now_ms: int, scope: str, limit: int) -> list[dict[str, Any]]:
        watched_clause = "AND events.is_watched = true" if scope == "matched" else ""
        rows = self.conn.execute(
            f"""
            WITH stock_mentions AS MATERIALIZED (
              SELECT
                tir.target_id,
                ues.symbol,
                ues.security_name,
                ues.exchange,
                ues.instrument_type,
                events.event_id,
                events.author_handle,
                events.is_watched,
                events.received_at_ms,
                COALESCE(events.text_clean, events.text) AS event_text
              FROM events
              JOIN token_intents ti ON ti.event_id = events.event_id
              JOIN token_intent_resolutions tir
                ON tir.intent_id = ti.intent_id
               AND tir.is_current = true
               AND tir.resolver_policy_version = %s
               AND tir.target_type = 'MarketInstrument'
               AND tir.resolution_status = 'NON_CRYPTO'
               AND tir.reason_codes_json @> '["CONFIRMED_US_EQUITY"]'::jsonb
              JOIN us_equity_symbols ues
                ON ues.market_instrument_id = tir.target_id
               AND ues.status = 'active'
              WHERE events.received_at_ms >= %s
                AND events.received_at_ms <= %s {watched_clause}
            )
            SELECT
              target_id,
              symbol,
              security_name,
              exchange,
              instrument_type,
              COUNT(*)::int AS mentions,
              COUNT(DISTINCT NULLIF(LOWER(author_handle), ''))::int AS unique_authors,
              SUM(CASE WHEN is_watched THEN 1 ELSE 0 END)::int AS watched_mentions,
              MAX(received_at_ms)::bigint AS latest_seen_ms,
              (ARRAY_AGG(event_id ORDER BY received_at_ms DESC, event_id DESC))[1] AS latest_event_id,
              (ARRAY_AGG(author_handle ORDER BY received_at_ms DESC, event_id DESC))[1] AS latest_author_handle,
              (ARRAY_AGG(event_text ORDER BY received_at_ms DESC, event_id DESC))[1] AS latest_text,
              ARRAY_AGG(event_id ORDER BY received_at_ms DESC, event_id DESC) AS source_event_ids
            FROM stock_mentions
            GROUP BY target_id, symbol, security_name, exchange, instrument_type
            ORDER BY mentions DESC, watched_mentions DESC, latest_seen_ms DESC, symbol ASC
            LIMIT %s
            """,
            (
                TOKEN_RADAR_RESOLVER_POLICY_VERSION,
                int(since_ms),
                int(now_ms),
                int(limit),
            ),
        ).fetchall()
        return [dict(row) for row in rows]
