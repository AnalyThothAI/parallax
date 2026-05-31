from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from psycopg.types.json import Jsonb

from parallax.platform.db.json_safety import postgres_safe_json


class MarketTickCurrentRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def latest_tick_for_target(self, *, target_type: str, target_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM market_ticks
            WHERE target_type = %(target_type)s
              AND target_id = %(target_id)s
            ORDER BY observed_at_ms DESC, received_at_ms DESC, tick_id DESC
            LIMIT 1
            """,
            {"target_type": str(target_type), "target_id": str(target_id)},
        ).fetchone()
        return cast("dict[str, Any] | None", row)

    def upsert_current_from_tick(self, tick_row: Mapping[str, Any], *, now_ms: int) -> bool:
        params = _current_params(tick_row, now_ms=now_ms)
        row = self.conn.execute(
            """
            INSERT INTO market_tick_current(
              target_type,
              target_id,
              tick_observed_at_ms,
              tick_id,
              source_tier,
              source_provider,
              chain,
              token_address,
              exchange,
              instrument,
              pricefeed_id,
              price_usd,
              liquidity_usd,
              volume_24h_usd,
              open_interest_usd,
              market_cap_usd,
              holders,
              raw_payload_json,
              payload_hash,
              updated_at_ms,
              created_at_ms
            )
            VALUES (
              %(target_type)s,
              %(target_id)s,
              %(tick_observed_at_ms)s,
              %(tick_id)s,
              %(source_tier)s,
              %(source_provider)s,
              %(chain)s,
              %(token_address)s,
              %(exchange)s,
              %(instrument)s,
              %(pricefeed_id)s,
              %(price_usd)s,
              %(liquidity_usd)s,
              %(volume_24h_usd)s,
              %(open_interest_usd)s,
              %(market_cap_usd)s,
              %(holders)s,
              %(raw_payload_json)s,
              %(payload_hash)s,
              %(updated_at_ms)s,
              %(created_at_ms)s
            )
            ON CONFLICT(target_type, target_id) DO UPDATE SET
              tick_observed_at_ms = EXCLUDED.tick_observed_at_ms,
              tick_id = EXCLUDED.tick_id,
              source_tier = EXCLUDED.source_tier,
              source_provider = EXCLUDED.source_provider,
              chain = EXCLUDED.chain,
              token_address = EXCLUDED.token_address,
              exchange = EXCLUDED.exchange,
              instrument = EXCLUDED.instrument,
              pricefeed_id = EXCLUDED.pricefeed_id,
              price_usd = EXCLUDED.price_usd,
              liquidity_usd = EXCLUDED.liquidity_usd,
              volume_24h_usd = EXCLUDED.volume_24h_usd,
              open_interest_usd = EXCLUDED.open_interest_usd,
              market_cap_usd = EXCLUDED.market_cap_usd,
              holders = EXCLUDED.holders,
              raw_payload_json = EXCLUDED.raw_payload_json,
              payload_hash = EXCLUDED.payload_hash,
              updated_at_ms = EXCLUDED.updated_at_ms,
              created_at_ms = EXCLUDED.created_at_ms
            WHERE market_tick_current.tick_id IS DISTINCT FROM EXCLUDED.tick_id
               OR market_tick_current.tick_observed_at_ms IS DISTINCT FROM EXCLUDED.tick_observed_at_ms
               OR market_tick_current.source_tier IS DISTINCT FROM EXCLUDED.source_tier
               OR market_tick_current.source_provider IS DISTINCT FROM EXCLUDED.source_provider
               OR market_tick_current.chain IS DISTINCT FROM EXCLUDED.chain
               OR market_tick_current.token_address IS DISTINCT FROM EXCLUDED.token_address
               OR market_tick_current.exchange IS DISTINCT FROM EXCLUDED.exchange
               OR market_tick_current.instrument IS DISTINCT FROM EXCLUDED.instrument
               OR market_tick_current.pricefeed_id IS DISTINCT FROM EXCLUDED.pricefeed_id
               OR market_tick_current.price_usd IS DISTINCT FROM EXCLUDED.price_usd
               OR market_tick_current.liquidity_usd IS DISTINCT FROM EXCLUDED.liquidity_usd
               OR market_tick_current.volume_24h_usd IS DISTINCT FROM EXCLUDED.volume_24h_usd
               OR market_tick_current.open_interest_usd IS DISTINCT FROM EXCLUDED.open_interest_usd
               OR market_tick_current.market_cap_usd IS DISTINCT FROM EXCLUDED.market_cap_usd
               OR market_tick_current.holders IS DISTINCT FROM EXCLUDED.holders
               OR market_tick_current.raw_payload_json IS DISTINCT FROM EXCLUDED.raw_payload_json
               OR market_tick_current.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
               OR market_tick_current.updated_at_ms IS DISTINCT FROM EXCLUDED.updated_at_ms
               OR market_tick_current.created_at_ms IS DISTINCT FROM EXCLUDED.created_at_ms
            RETURNING true AS changed
            """,
            params,
        ).fetchone()
        return bool(row and row["changed"])

    def truncate_current(self) -> None:
        self.conn.execute("TRUNCATE market_tick_current")

    def latest_ticks_for_all_targets(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT ON (target_type, target_id) *
            FROM market_ticks
            ORDER BY target_type ASC,
                     target_id ASC,
                     observed_at_ms DESC,
                     received_at_ms DESC,
                     tick_id DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def _current_params(tick_row: Mapping[str, Any], *, now_ms: int) -> dict[str, Any]:
    return {
        "target_type": str(tick_row["target_type"]),
        "target_id": str(tick_row["target_id"]),
        "tick_observed_at_ms": int(tick_row["observed_at_ms"]),
        "tick_id": str(tick_row["tick_id"]),
        "source_tier": str(tick_row["source_tier"]),
        "source_provider": str(tick_row["source_provider"]),
        "chain": tick_row.get("chain"),
        "token_address": tick_row.get("token_address"),
        "exchange": tick_row.get("exchange"),
        "instrument": tick_row.get("instrument"),
        "pricefeed_id": tick_row.get("pricefeed_id"),
        "price_usd": tick_row.get("price_usd"),
        "liquidity_usd": tick_row.get("liquidity_usd"),
        "volume_24h_usd": tick_row.get("volume_24h_usd"),
        "open_interest_usd": tick_row.get("open_interest_usd"),
        "market_cap_usd": tick_row.get("market_cap_usd"),
        "holders": tick_row.get("holders"),
        "raw_payload_json": Jsonb(postgres_safe_json(tick_row.get("raw_payload_json") or {})),
        "payload_hash": str(tick_row["payload_hash"]),
        "updated_at_ms": int(tick_row["received_at_ms"]),
        "created_at_ms": int(tick_row["created_at_ms"]),
        "now_ms": int(now_ms),
    }
