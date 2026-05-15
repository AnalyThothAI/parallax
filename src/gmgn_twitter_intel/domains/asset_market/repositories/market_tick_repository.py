from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.asset_market.types import MarketTick, market_tick_id


class MarketTickRepository:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def insert_tick(self, tick: MarketTick) -> str:
        expected_id = market_tick_id(
            target_type=tick.target_type,
            target_id=tick.target_id,
            source_provider=tick.source_provider,
            observed_at_ms=tick.observed_at_ms,
        )
        if tick.tick_id != expected_id:
            raise ValueError(
                "market tick id must be deterministic for "
                "(target_type, target_id, source_provider, observed_at_ms)"
            )

        self._conn.execute(
            """
            INSERT INTO market_ticks(
                tick_id,
                target_type,
                target_id,
                chain,
                token_address,
                exchange,
                instrument,
                pricefeed_id,
                source_tier,
                source_provider,
                observed_at_ms,
                received_at_ms,
                price_usd,
                liquidity_usd,
                volume_24h_usd,
                market_cap_usd,
                holders,
                raw_payload_json,
                created_at_ms
            )
            VALUES (
                %(tick_id)s,
                %(target_type)s,
                %(target_id)s,
                %(chain)s,
                %(token_address)s,
                %(exchange)s,
                %(instrument)s,
                %(pricefeed_id)s,
                %(source_tier)s,
                %(source_provider)s,
                %(observed_at_ms)s,
                %(received_at_ms)s,
                %(price_usd)s,
                %(liquidity_usd)s,
                %(volume_24h_usd)s,
                %(market_cap_usd)s,
                %(holders)s,
                %(raw_payload_json)s,
                %(created_at_ms)s
            )
            ON CONFLICT(target_type, target_id, source_provider, observed_at_ms) DO NOTHING
            """,
            {
                "tick_id": tick.tick_id,
                "target_type": tick.target_type,
                "target_id": tick.target_id,
                "chain": tick.chain,
                "token_address": tick.token_address,
                "exchange": tick.exchange,
                "instrument": tick.instrument,
                "pricefeed_id": tick.pricefeed_id,
                "source_tier": tick.source_tier,
                "source_provider": tick.source_provider,
                "observed_at_ms": tick.observed_at_ms,
                "received_at_ms": tick.received_at_ms,
                "price_usd": tick.price_usd,
                "liquidity_usd": tick.liquidity_usd,
                "volume_24h_usd": tick.volume_24h_usd,
                "market_cap_usd": tick.market_cap_usd,
                "holders": tick.holders,
                "raw_payload_json": Jsonb(tick.raw_payload_json),
                "created_at_ms": tick.created_at_ms,
            },
        )
        return tick.tick_id

    def insert_ticks(self, ticks: Iterable[MarketTick]) -> int:
        count = 0
        for tick in ticks:
            self.insert_tick(tick)
            count += 1
        return count

    def latest_at_or_before(
        self,
        *,
        target_type: str,
        target_id: str,
        at_ms: int,
        max_lag_ms: int,
    ) -> dict[str, Any] | None:
        return self._conn.execute(
            """
            SELECT *
            FROM market_ticks
            WHERE target_type = %(target_type)s
              AND target_id = %(target_id)s
              AND observed_at_ms <= %(at_ms)s
              AND observed_at_ms >= %(min_observed_at_ms)s
            ORDER BY observed_at_ms DESC, received_at_ms DESC, tick_id DESC
            LIMIT 1
            """,
            {
                "target_type": target_type,
                "target_id": target_id,
                "at_ms": at_ms,
                "min_observed_at_ms": at_ms - max_lag_ms,
            },
        ).fetchone()

    def latest_for_target(
        self,
        *,
        target_type: str,
        target_id: str,
        max_age_ms: int,
        now_ms: int,
    ) -> dict[str, Any] | None:
        return self._conn.execute(
            """
            SELECT *
            FROM market_ticks
            WHERE target_type = %(target_type)s
              AND target_id = %(target_id)s
              AND received_at_ms >= %(min_received_at_ms)s
            ORDER BY observed_at_ms DESC, received_at_ms DESC, tick_id DESC
            LIMIT 1
            """,
            {
                "target_type": target_type,
                "target_id": target_id,
                "min_received_at_ms": now_ms - max_age_ms,
            },
        ).fetchone()

    def first_between(
        self,
        *,
        target_type: str,
        target_id: str,
        start_ms: int,
        end_ms: int,
    ) -> dict[str, Any] | None:
        return self._conn.execute(
            """
            SELECT *
            FROM market_ticks
            WHERE target_type = %(target_type)s
              AND target_id = %(target_id)s
              AND observed_at_ms >= %(start_ms)s
              AND observed_at_ms <= %(end_ms)s
            ORDER BY observed_at_ms ASC, received_at_ms ASC, tick_id ASC
            LIMIT 1
            """,
            {
                "target_type": target_type,
                "target_id": target_id,
                "start_ms": start_ms,
                "end_ms": end_ms,
            },
        ).fetchone()
