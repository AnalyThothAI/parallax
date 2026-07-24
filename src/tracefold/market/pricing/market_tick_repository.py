from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any, cast

from psycopg.types.json import Jsonb

from tracefold.market.pricing.market_tick import MarketTick
from tracefold.market.pricing.market_tick_id import market_tick_id
from tracefold.platform.postgres.json_safety import postgres_safe_json
from tracefold.platform.postgres.write_contract import returning_mutation_count
from tracefold.platform.validation import require_positive_int


def _optional_returning_row(cursor: Any, row: Any | None) -> dict[str, Any] | None:
    returning_mutation_count(cursor, row, error_code="market_tick_repository_rowcount_invalid")
    if row is None:
        return None
    return dict(row)


class MarketTickRepository:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def insert_ticks_returning_rows(self, ticks: Iterable[MarketTick]) -> list[dict[str, Any]]:
        inserted: list[dict[str, Any]] = []
        for tick in ticks:
            inserted_row = self._insert_tick_returning_row(tick)
            if inserted_row is not None:
                inserted.append(inserted_row)
        return inserted

    def latest_target_ticks_after(
        self,
        *,
        after: tuple[str, str] | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        parsed_limit = require_positive_int(limit, error_code="market_tick_rebuild_limit_required")
        if after is None:
            after_target_type = None
            after_target_id = None
        else:
            after_target_type = str(after[0]).strip()
            after_target_id = str(after[1]).strip()
            if not after_target_type or not after_target_id:
                raise ValueError("market_tick_rebuild_cursor_required")
        rows = self._conn.execute(
            """
            WITH RECURSIVE targets(target_type, target_id, position) AS (
              (
                SELECT target_type, target_id, 1::bigint
                FROM market_ticks
                WHERE %(after_target_type)s::text IS NULL
                   OR (target_type, target_id) > (
                     %(after_target_type)s::text,
                     %(after_target_id)s::text
                   )
                ORDER BY target_type, target_id
                LIMIT 1
              )
              UNION ALL
              SELECT next_target.target_type, next_target.target_id, targets.position + 1
              FROM targets
              CROSS JOIN LATERAL (
                SELECT ticks.target_type, ticks.target_id
                FROM market_ticks AS ticks
                WHERE (ticks.target_type, ticks.target_id) > (targets.target_type, targets.target_id)
                ORDER BY ticks.target_type, ticks.target_id
                LIMIT 1
              ) AS next_target
              WHERE targets.position < %(limit)s
            )
            SELECT
              latest.tick_id,
              latest.target_type,
              latest.target_id,
              latest.chain,
              latest.token_address,
              latest.exchange,
              latest.instrument,
              latest.pricefeed_id,
              latest.source_tier,
              latest.source_provider,
              latest.observed_at_ms,
              latest.received_at_ms,
              latest.price_usd,
              latest.liquidity_usd,
              latest.volume_24h_usd,
              latest.open_interest_usd,
              latest.market_cap_usd,
              latest.holders,
              latest.created_at_ms
            FROM targets
            CROSS JOIN LATERAL (
              SELECT ticks.*
              FROM market_ticks AS ticks
              WHERE ticks.target_type = targets.target_type
                AND ticks.target_id = targets.target_id
              ORDER BY ticks.observed_at_ms DESC, ticks.received_at_ms DESC, ticks.tick_id DESC
              LIMIT 1
            ) AS latest
            ORDER BY latest.target_type, latest.target_id
            """,
            {
                "after_target_type": after_target_type,
                "after_target_id": after_target_id,
                "limit": parsed_limit,
            },
        ).fetchall()
        return [dict(row) for row in rows]

    def _insert_tick_returning_row(self, tick: MarketTick) -> dict[str, Any] | None:
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
        cursor = self._conn.execute(
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
            RETURNING
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
                created_at_ms
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
        )
        row = cursor.fetchone()
        return _optional_returning_row(cursor, row)

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


def _payload_hash(payload: Any) -> str:
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
