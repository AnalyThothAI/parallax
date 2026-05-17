from __future__ import annotations

from typing import Any, cast

from gmgn_twitter_intel.domains.asset_market.types import EnrichedEventCapture


class EnrichedEventRepository:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def insert_capture(self, capture: EnrichedEventCapture) -> None:
        self._conn.execute(
            """
            INSERT INTO enriched_events(
                event_id,
                intent_id,
                resolution_id,
                target_type,
                target_id,
                t_event_ms,
                tick_id,
                tick_lag_ms,
                capture_method,
                capture_reason,
                created_at_ms
            )
            VALUES (
                %(event_id)s,
                %(intent_id)s,
                %(resolution_id)s,
                %(target_type)s,
                %(target_id)s,
                %(t_event_ms)s,
                %(tick_id)s,
                %(tick_lag_ms)s,
                %(capture_method)s,
                %(capture_reason)s,
                %(created_at_ms)s
            )
            ON CONFLICT(event_id, intent_id) DO NOTHING
            """,
            {
                "event_id": capture.event_id,
                "intent_id": capture.intent_id,
                "resolution_id": capture.resolution_id,
                "target_type": capture.target_type,
                "target_id": capture.target_id,
                "t_event_ms": capture.t_event_ms,
                "tick_id": capture.tick_id,
                "tick_lag_ms": capture.tick_lag_ms,
                "capture_method": capture.capture_method,
                "capture_reason": capture.capture_reason,
                "created_at_ms": capture.created_at_ms,
            },
        )

    def list_by_event_id(self, event_id: str) -> list[dict[str, Any]]:
        return list(
            self._conn.execute(
                f"""
                {self._joined_select()}
                WHERE ee.event_id = %(event_id)s
                ORDER BY ee.intent_id ASC
                """,
                {"event_id": event_id},
            ).fetchall()
        )

    def by_event_intent(self, event_id: str, intent_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            f"""
            {self._joined_select()}
            WHERE ee.event_id = %(event_id)s
              AND ee.intent_id = %(intent_id)s
            """,
            {"event_id": event_id, "intent_id": intent_id},
        ).fetchone()
        return cast("dict[str, Any] | None", row)

    def latest_for_target(self, *, target_type: str, target_id: str, limit: int) -> list[dict[str, Any]]:
        return list(
            self._conn.execute(
                f"""
                {self._joined_select()}
                WHERE ee.target_type = %(target_type)s
                  AND ee.target_id = %(target_id)s
                ORDER BY ee.t_event_ms DESC, ee.event_id DESC, ee.intent_id DESC
                LIMIT %(limit)s
                """,
                {"target_type": target_type, "target_id": target_id, "limit": limit},
            ).fetchall()
        )

    def attach_backfill_capture(self, capture: EnrichedEventCapture) -> bool:
        cursor = self._conn.execute(
            """
            UPDATE enriched_events
            SET tick_id = %(tick_id)s,
                tick_lag_ms = %(tick_lag_ms)s,
                capture_method = %(capture_method)s,
                capture_reason = %(capture_reason)s
            WHERE event_id = %(event_id)s
              AND intent_id = %(intent_id)s
              AND capture_method = 'unavailable'
              AND capture_reason = 'pending_backfill'
              AND tick_id IS NULL
            """,
            {
                "event_id": capture.event_id,
                "intent_id": capture.intent_id,
                "tick_id": capture.tick_id,
                "tick_lag_ms": capture.tick_lag_ms,
                "capture_method": capture.capture_method,
                "capture_reason": capture.capture_reason,
            },
        )
        return int(getattr(cursor, "rowcount", 0) or 0) == 1

    def mark_backfill_terminal(self, *, event_id: str, intent_id: str, reason: str) -> bool:
        cursor = self._conn.execute(
            """
            UPDATE enriched_events
            SET capture_method = 'unavailable',
                capture_reason = %(reason)s
            WHERE event_id = %(event_id)s
              AND intent_id = %(intent_id)s
              AND capture_method = 'unavailable'
              AND capture_reason = 'pending_backfill'
              AND tick_id IS NULL
              AND tick_lag_ms IS NULL
            """,
            {
                "event_id": event_id,
                "intent_id": intent_id,
                "reason": reason,
            },
        )
        return int(getattr(cursor, "rowcount", 0) or 0) == 1

    def _joined_select(self) -> str:
        return """
            SELECT
                ee.*,
                mt.tick_id AS market_tick_id,
                mt.chain AS market_tick_chain,
                mt.token_address AS market_tick_token_address,
                mt.exchange AS market_tick_exchange,
                mt.instrument AS market_tick_instrument,
                mt.pricefeed_id AS market_tick_pricefeed_id,
                mt.source_tier AS market_tick_source_tier,
                mt.source_provider AS market_tick_source_provider,
                mt.observed_at_ms AS market_tick_observed_at_ms,
                mt.received_at_ms AS market_tick_received_at_ms,
                mt.price_usd AS market_tick_price_usd,
                mt.liquidity_usd AS market_tick_liquidity_usd,
                mt.volume_24h_usd AS market_tick_volume_24h_usd,
                mt.market_cap_usd AS market_tick_market_cap_usd,
                mt.raw_payload_json AS market_tick_raw_payload_json,
                mt.created_at_ms AS market_tick_created_at_ms
            FROM enriched_events ee
            LEFT JOIN market_ticks mt ON mt.tick_id = ee.tick_id
        """
