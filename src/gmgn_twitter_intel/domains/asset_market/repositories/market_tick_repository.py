from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any, cast

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.asset_market.types import MarketTick, market_tick_id
from gmgn_twitter_intel.platform.db.json_safety import postgres_safe_json


class MarketTickRepository:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def insert_tick(self, tick: MarketTick) -> str:
        self._insert_tick_returning_id(tick)
        return tick.tick_id

    def insert_ticks(self, ticks: Iterable[MarketTick]) -> int:
        return len(self.insert_ticks_returning_ids(ticks))

    def insert_ticks_returning_ids(self, ticks: Iterable[MarketTick]) -> list[str]:
        inserted: list[str] = []
        for tick in ticks:
            inserted_id = self._insert_tick_returning_id(tick)
            if inserted_id is not None:
                inserted.append(inserted_id)
        return inserted

    def _insert_tick_returning_id(self, tick: MarketTick) -> str | None:
        expected_id = market_tick_id(
            target_type=tick.target_type,
            target_id=tick.target_id,
            source_provider=tick.source_provider,
            observed_at_ms=tick.observed_at_ms,
        )
        if tick.tick_id != expected_id:
            raise ValueError(
                "market tick id must be deterministic for (target_type, target_id, source_provider, observed_at_ms)"
            )

        safe_payload = postgres_safe_json(tick.raw_payload_json)
        payload_hash = _payload_hash(safe_payload)
        row = self._conn.execute(
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
                open_interest_usd,
                market_cap_usd,
                holders,
                raw_payload_json,
                payload_hash,
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
                %(open_interest_usd)s,
                %(market_cap_usd)s,
                %(holders)s,
                %(raw_payload_json)s,
                %(payload_hash)s,
                %(created_at_ms)s
            )
            ON CONFLICT(observed_at_ms, target_type, target_id, source_provider) DO NOTHING
            RETURNING tick_id
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
                "open_interest_usd": tick.open_interest_usd,
                "market_cap_usd": tick.market_cap_usd,
                "holders": tick.holders,
                "raw_payload_json": Jsonb(safe_payload),
                "payload_hash": payload_hash,
                "created_at_ms": tick.created_at_ms,
            },
        ).fetchone()
        if row is None:
            return None
        return str(row["tick_id"])

    def latest_at_or_before(
        self,
        *,
        target_type: str,
        target_id: str,
        at_ms: int,
        max_lag_ms: int,
    ) -> dict[str, Any] | None:
        row = self._conn.execute(
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
        return cast("dict[str, Any] | None", row)

    def nearest_around(
        self,
        *,
        target_type: str,
        target_id: str,
        at_ms: int,
        max_lag_ms: int,
    ) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM market_ticks
            WHERE target_type = %(target_type)s
              AND target_id = %(target_id)s
              AND observed_at_ms >= %(min_observed_at_ms)s
              AND observed_at_ms <= %(max_observed_at_ms)s
            ORDER BY ABS(observed_at_ms - %(at_ms)s) ASC,
                     observed_at_ms ASC,
                     received_at_ms ASC,
                     tick_id ASC
            LIMIT 1
            """,
            {
                "target_type": target_type,
                "target_id": target_id,
                "at_ms": int(at_ms),
                "min_observed_at_ms": int(at_ms) - int(max_lag_ms),
                "max_observed_at_ms": int(at_ms) + int(max_lag_ms),
            },
        ).fetchone()
        return cast("dict[str, Any] | None", row)

    def latest_for_target(
        self,
        *,
        target_type: str,
        target_id: str,
        max_age_ms: int,
        now_ms: int,
    ) -> dict[str, Any] | None:
        row = self._conn.execute(
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
        return cast("dict[str, Any] | None", row)

    def latest_for_targets(
        self,
        *,
        targets: list[dict[str, str]],
        max_age_ms: int,
        now_ms: int,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        if not targets:
            return {}
        values_sql = ",".join(["(%s, %s)"] * len(targets))
        params: list[Any] = []
        for target in targets:
            params.extend([str(target["target_type"]), str(target["target_id"])])
        params.append(int(now_ms) - int(max_age_ms))
        rows = self._conn.execute(
            f"""
            WITH requested(target_type, target_id) AS (VALUES {values_sql}),
            ranked AS (
              SELECT mt.*,
                     row_number() OVER (
                       PARTITION BY mt.target_type, mt.target_id
                       ORDER BY mt.observed_at_ms DESC, mt.received_at_ms DESC, mt.tick_id DESC
                     ) AS rn
              FROM requested r
              JOIN market_ticks mt
                ON mt.target_type = r.target_type
               AND mt.target_id = r.target_id
              WHERE mt.received_at_ms >= %s
            )
            SELECT *
            FROM ranked
            WHERE rn = 1
            """,
            params,
        ).fetchall()
        return {(str(row["target_type"]), str(row["target_id"])): dict(row) for row in rows}

    def first_between(
        self,
        *,
        target_type: str,
        target_id: str,
        start_ms: int,
        end_ms: int,
    ) -> dict[str, Any] | None:
        row = self._conn.execute(
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
        return cast("dict[str, Any] | None", row)


def _payload_hash(payload: Any) -> str:
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
