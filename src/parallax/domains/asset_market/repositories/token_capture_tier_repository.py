from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from psycopg.types.json import Jsonb


class TokenCaptureTierRepository:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def upsert_tier(
        self,
        *,
        target_type: str,
        target_id: str,
        tier: int,
        reason: str,
        score: Decimal,
        updated_at_ms: int,
    ) -> bool:
        row = self._conn.execute(
            """
            INSERT INTO token_capture_tier(
                target_type,
                target_id,
                tier,
                reason,
                score,
                updated_at_ms
            )
            VALUES (
                %(target_type)s,
                %(target_id)s,
                %(tier)s,
                %(reason)s,
                %(score)s,
                %(updated_at_ms)s
            )
            ON CONFLICT(target_type, target_id) DO UPDATE SET
                tier = EXCLUDED.tier,
                reason = EXCLUDED.reason,
                score = EXCLUDED.score,
                updated_at_ms = EXCLUDED.updated_at_ms
            WHERE token_capture_tier.tier IS DISTINCT FROM EXCLUDED.tier
               OR token_capture_tier.reason IS DISTINCT FROM EXCLUDED.reason
               OR token_capture_tier.score IS DISTINCT FROM EXCLUDED.score
            RETURNING true AS changed
            """,
            {
                "target_type": target_type,
                "target_id": target_id,
                "tier": tier,
                "reason": reason,
                "score": score,
                "updated_at_ms": updated_at_ms,
            },
        ).fetchone()
        return row is not None and bool(row.get("changed", True))

    def list_by_tier(
        self,
        tier: int,
        limit: int,
        *,
        exclude_keys: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"tier": tier, "limit": limit}
        exclude_filter = ""
        if exclude_keys:
            params["exclude_keys"] = Jsonb(list(exclude_keys))
            exclude_filter = """
                  AND NOT EXISTS (
                    SELECT 1
                    FROM jsonb_to_recordset(%(exclude_keys)s::jsonb)
                      AS excluded(target_type text, target_id text)
                    WHERE excluded.target_type = token_capture_tier.target_type
                      AND excluded.target_id = token_capture_tier.target_id
                  )
            """
        return list(
            self._conn.execute(
                f"""
                SELECT token_capture_tier.*
                FROM token_capture_tier
                LEFT JOIN LATERAL (
                  SELECT market_ticks.tick_id,
                         market_ticks.market_cap_usd,
                         market_ticks.liquidity_usd,
                         market_ticks.volume_24h_usd,
                         market_ticks.holders,
                         market_ticks.received_at_ms
                  FROM market_ticks
                  WHERE market_ticks.target_type = token_capture_tier.target_type
                    AND market_ticks.target_id = token_capture_tier.target_id
                  ORDER BY market_ticks.observed_at_ms DESC, market_ticks.tick_id DESC
                  LIMIT 1
                ) latest_tick ON true
                WHERE token_capture_tier.tier = %(tier)s
                {exclude_filter}
                  ORDER BY
                  CASE
                    WHEN latest_tick.tick_id IS NOT NULL
                      AND (
                        latest_tick.market_cap_usd IS NULL
                        OR latest_tick.liquidity_usd IS NULL
                        OR latest_tick.volume_24h_usd IS NULL
                        OR latest_tick.holders IS NULL
                      )
                      THEN 0
                    WHEN latest_tick.tick_id IS NULL THEN 1
                    ELSE 2
                  END ASC,
                  latest_tick.received_at_ms ASC NULLS FIRST,
                  token_capture_tier.score DESC,
                  token_capture_tier.updated_at_ms DESC,
                  token_capture_tier.target_id ASC
                LIMIT %(limit)s
                """,
                params,
            ).fetchall()
        )

    def get(self, target_type: str, target_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM token_capture_tier
            WHERE target_type = %(target_type)s
              AND target_id = %(target_id)s
            """,
            {"target_type": target_type, "target_id": target_id},
        ).fetchone()
        return cast("dict[str, Any] | None", row)

    def demote_hot_rows_outside_rank_set(
        self,
        *,
        active_keys: list[dict[str, str]],
        updated_at_ms: int,
    ) -> int:
        cursor = self._conn.execute(
            """
            WITH active_keys AS (
              SELECT target_type, target_id
              FROM jsonb_to_recordset(%(active_keys)s::jsonb)
                AS x(target_type text, target_id text)
            )
            UPDATE token_capture_tier AS t
            SET tier = 3,
                reason = 'inline_only',
                updated_at_ms = %(updated_at_ms)s
            WHERE t.tier IN (1, 2)
              AND NOT EXISTS (
                SELECT 1
                FROM active_keys k
                WHERE k.target_type = t.target_type
                  AND k.target_id = t.target_id
              )
            """,
            {"active_keys": Jsonb(list(active_keys)), "updated_at_ms": int(updated_at_ms)},
        )
        return int(getattr(cursor, "rowcount", 0) or 0)

    def live_target_rows(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT
              token_capture_tier.target_type,
              token_capture_tier.target_id,
              token_capture_tier.tier,
              token_capture_tier.score,
              CASE
                WHEN token_capture_tier.target_type = 'chain_token'
                  THEN split_part(token_capture_tier.target_id, ':', 1)
                ELSE NULL
              END AS chain_id,
              CASE
                WHEN token_capture_tier.target_type = 'chain_token'
                  THEN split_part(token_capture_tier.target_id, ':', 2)
                ELSE NULL
              END AS address,
              split_part(token_capture_tier.target_id, ':', 1) AS provider,
              split_part(token_capture_tier.target_id, ':', 2) AS native_market_id,
              CASE
                WHEN token_capture_tier.target_type = 'cex_symbol' THEN 'USDT'
                ELSE NULL
              END AS quote_symbol
            FROM token_capture_tier
            WHERE token_capture_tier.tier IN (1, 2)
            ORDER BY token_capture_tier.tier ASC,
                     token_capture_tier.score DESC,
                     token_capture_tier.updated_at_ms DESC,
                     token_capture_tier.target_type ASC,
                     token_capture_tier.target_id ASC
            LIMIT %(limit)s
            """,
            {"limit": max(0, int(limit))},
        ).fetchall()
        return [dict(row) for row in rows]
