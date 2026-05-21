from __future__ import annotations

import hashlib
from typing import Any

from psycopg.types.json import Jsonb


class CexOiRadarRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def binance_usdt_perp_universe(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              pricefeed_id,
              subject_id AS cex_token_id,
              native_market_id,
              base_symbol,
              quote_symbol,
              provider,
              feed_type,
              updated_at_ms
            FROM price_feeds
            WHERE subject_type = 'CexToken'
              AND provider = 'binance'
              AND feed_type = 'cex_swap'
              AND quote_symbol = 'USDT'
              AND status = 'canonical'
              AND native_market_id IS NOT NULL
            ORDER BY updated_at_ms DESC, native_market_id ASC
            LIMIT %s
            """,
            (max(1, int(limit)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def start_run(
        self,
        *,
        run_id: str,
        started_at_ms: int,
        universe_count: int,
        period: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO cex_oi_radar_runs(
              run_id, provider, exchange, quote_symbol, contract_type, period, status,
              started_at_ms, universe_count, processed_count, failed_count, notes_json
            )
            VALUES (
              %s, 'binance', 'binance', 'USDT', 'PERPETUAL', %s, 'running',
              %s, %s, 0, 0, '{}'::jsonb
            )
            ON CONFLICT(run_id) DO NOTHING
            """,
            (run_id, period, int(started_at_ms), int(universe_count)),
        )

    def insert_rows(self, *, run_id: str, rows: list[dict[str, Any]], computed_at_ms: int) -> int:
        written = 0
        for row in rows:
            row_id = _row_id(run_id, str(row["target_id"]))
            self.conn.execute(
                """
                INSERT INTO cex_oi_radar_rows(
                  row_id, run_id, rank, target_id, pricefeed_id, native_market_id, base_symbol, quote_symbol,
                  open_interest_usd, open_interest_change_pct_1h, volume_24h_usd, funding_rate,
                  mark_price, score, score_components_json, observed_at_ms, computed_at_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(row_id) DO UPDATE SET
                  rank = excluded.rank,
                  open_interest_usd = excluded.open_interest_usd,
                  open_interest_change_pct_1h = excluded.open_interest_change_pct_1h,
                  volume_24h_usd = excluded.volume_24h_usd,
                  funding_rate = excluded.funding_rate,
                  mark_price = excluded.mark_price,
                  score = excluded.score,
                  score_components_json = excluded.score_components_json,
                  observed_at_ms = excluded.observed_at_ms,
                  computed_at_ms = excluded.computed_at_ms
                """,
                (
                    row_id,
                    run_id,
                    int(row["rank"]),
                    row["target_id"],
                    row.get("pricefeed_id"),
                    row["native_market_id"],
                    row["base_symbol"],
                    row["quote_symbol"],
                    row.get("open_interest_usd"),
                    row.get("open_interest_change_pct_1h"),
                    row.get("volume_24h_usd"),
                    row.get("funding_rate"),
                    row.get("mark_price"),
                    row["score"],
                    Jsonb(row.get("score_components") or {}),
                    int(row.get("observed_at_ms") or computed_at_ms),
                    int(computed_at_ms),
                ),
            )
            written += 1
        return written

    def finish_run(
        self,
        *,
        run_id: str,
        status: str,
        finished_at_ms: int,
        processed_count: int,
        failed_count: int,
        notes: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            UPDATE cex_oi_radar_runs
            SET status = %s,
                finished_at_ms = %s,
                processed_count = %s,
                failed_count = %s,
                notes_json = %s
            WHERE run_id = %s
            """,
            (
                status,
                int(finished_at_ms),
                int(processed_count),
                int(failed_count),
                Jsonb(notes or {}),
                run_id,
            ),
        )
        if commit:
            self.conn.commit()

    def latest_board(self, *, limit: int) -> dict[str, Any]:
        run = self.conn.execute(
            """
            SELECT *
            FROM cex_oi_radar_runs
            WHERE provider = 'binance'
              AND exchange = 'binance'
              AND quote_symbol = 'USDT'
              AND contract_type = 'PERPETUAL'
              AND status IN ('success', 'partial')
            ORDER BY finished_at_ms DESC NULLS LAST, started_at_ms DESC
            LIMIT 1
            """
        ).fetchone()
        if run is None:
            return {"run": None, "rows": []}
        rows = self.conn.execute(
            """
            SELECT *
            FROM cex_oi_radar_rows
            WHERE run_id = %s
            ORDER BY rank ASC, score DESC, native_market_id ASC
            LIMIT %s
            """,
            (run["run_id"], max(1, int(limit))),
        ).fetchall()
        return {"run": dict(run), "rows": [dict(row) for row in rows]}


def oi_radar_run_id(*, started_at_ms: int) -> str:
    return f"cex-oi-radar:binance-usdt-perp:{int(started_at_ms)}"


def _row_id(run_id: str, target_id: str) -> str:
    digest = hashlib.sha256(f"{run_id}|{target_id}".encode()).hexdigest()[:32]
    return f"cex-oi-radar-row:{digest}"
