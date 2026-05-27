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

    def publish_board(
        self,
        *,
        rows: list[dict[str, Any]],
        computed_at_ms: int,
        period: str,
        status: str,
        notes: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> int:
        board_period = str(period)
        computed_at = int(computed_at_ms)
        frontier_ms = _source_frontier_ms(rows, default=computed_at)
        latest_error = _latest_attempt_error(status=status, notes=notes)

        self.conn.execute(
            """
            INSERT INTO cex_oi_radar_publication_state(
              board_key, provider, exchange, quote_symbol, contract_type, period,
              current_published_at_ms, current_source_frontier_ms, current_row_count,
              latest_attempt_status, latest_attempt_started_at_ms, latest_attempt_finished_at_ms,
              latest_attempt_error, updated_at_ms
            )
            VALUES (
              %s, %s, %s, %s, %s, %s,
              %s, %s, %s,
              %s, %s, %s,
              %s, %s
            )
            ON CONFLICT(board_key) DO UPDATE SET
              current_published_at_ms = excluded.current_published_at_ms,
              current_source_frontier_ms = excluded.current_source_frontier_ms,
              current_row_count = excluded.current_row_count,
              latest_attempt_status = excluded.latest_attempt_status,
              latest_attempt_started_at_ms = excluded.latest_attempt_started_at_ms,
              latest_attempt_finished_at_ms = excluded.latest_attempt_finished_at_ms,
              latest_attempt_error = excluded.latest_attempt_error,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                _board_key(board_period),
                "binance",
                "binance",
                "USDT",
                "PERPETUAL",
                board_period,
                computed_at,
                frontier_ms,
                len(rows),
                status,
                computed_at,
                computed_at,
                latest_error,
                computed_at,
            ),
        )
        self.conn.execute(
            """
            DELETE FROM cex_oi_radar_rows
            WHERE board_provider = 'binance'
              AND board_exchange = 'binance'
              AND board_quote_symbol = 'USDT'
              AND board_contract_type = 'PERPETUAL'
              AND period = %s
            """,
            (board_period,),
        )

        written = 0
        for row in rows:
            self.conn.execute(
                """
                INSERT INTO cex_oi_radar_rows(
                  row_id, period, board_provider, board_exchange, board_quote_symbol, board_contract_type,
                  rank, target_id, pricefeed_id, native_market_id, base_symbol, quote_symbol,
                  open_interest_usd, open_interest_change_pct_1h, volume_24h_usd, funding_rate,
                  mark_price, score, score_components_json, observed_at_ms, computed_at_ms
                )
                VALUES (
                  %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s,
                  %s, %s, %s, %s, %s
                )
                ON CONFLICT(row_id) DO UPDATE SET
                  rank = excluded.rank,
                  pricefeed_id = excluded.pricefeed_id,
                  native_market_id = excluded.native_market_id,
                  base_symbol = excluded.base_symbol,
                  quote_symbol = excluded.quote_symbol,
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
                    _row_id(board_period, str(row["target_id"])),
                    board_period,
                    "binance",
                    "binance",
                    "USDT",
                    "PERPETUAL",
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
                    int(row.get("observed_at_ms") or computed_at),
                    computed_at,
                ),
            )
            written += 1

        if commit:
            self.conn.commit()
        return written

    def record_attempt_failure(
        self,
        *,
        computed_at_ms: int,
        period: str,
        notes: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> None:
        board_period = str(period)
        computed_at = int(computed_at_ms)
        latest_error = _latest_attempt_error(status="failed", notes=notes)

        self.conn.execute(
            """
            INSERT INTO cex_oi_radar_publication_state(
              board_key, provider, exchange, quote_symbol, contract_type, period,
              current_published_at_ms, current_source_frontier_ms, current_row_count,
              latest_attempt_status, latest_attempt_started_at_ms, latest_attempt_finished_at_ms,
              latest_attempt_error, updated_at_ms
            )
            VALUES (
              %s, %s, %s, %s, %s, %s,
              NULL, NULL, 0,
              'failed', %s, %s,
              %s, %s
            )
            ON CONFLICT(board_key) DO UPDATE SET
              latest_attempt_status = excluded.latest_attempt_status,
              latest_attempt_started_at_ms = excluded.latest_attempt_started_at_ms,
              latest_attempt_finished_at_ms = excluded.latest_attempt_finished_at_ms,
              latest_attempt_error = excluded.latest_attempt_error,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                _board_key(board_period),
                "binance",
                "binance",
                "USDT",
                "PERPETUAL",
                board_period,
                computed_at,
                computed_at,
                latest_error,
                computed_at,
            ),
        )
        if commit:
            self.conn.commit()

    def latest_board(self, *, limit: int) -> dict[str, Any]:
        state = self.conn.execute(
            """
            SELECT *
            FROM cex_oi_radar_publication_state
            WHERE provider = 'binance'
              AND exchange = 'binance'
              AND quote_symbol = 'USDT'
              AND contract_type = 'PERPETUAL'
            ORDER BY current_published_at_ms DESC NULLS LAST, updated_at_ms DESC
            LIMIT 1
            """
        ).fetchone()
        if state is None:
            return {"state": None, "publication": None, "rows": []}

        state_payload = dict(state)
        rows = self.conn.execute(
            """
            SELECT *
            FROM cex_oi_radar_rows
            WHERE board_provider = 'binance'
              AND board_exchange = 'binance'
              AND board_quote_symbol = 'USDT'
              AND board_contract_type = 'PERPETUAL'
              AND period = %s
            ORDER BY rank ASC, score DESC, native_market_id ASC
            LIMIT %s
            """,
            (state_payload["period"], max(1, int(limit))),
        ).fetchall()
        return {
            "state": state_payload,
            "publication": _publication_payload(state_payload),
            "rows": [dict(row) for row in rows],
        }


def _board_key(period: str) -> str:
    return f"binance:USDT:PERPETUAL:{period}"


def _row_id(period: str, target_id: str) -> str:
    digest = hashlib.sha256(f"binance|binance|USDT|PERPETUAL|{period}|{target_id}".encode()).hexdigest()[:32]
    return f"cex-oi-radar-row:{digest}"


def _source_frontier_ms(rows: list[dict[str, Any]], *, default: int) -> int:
    observed_values = [int(row["observed_at_ms"]) for row in rows if row.get("observed_at_ms") is not None]
    if not observed_values:
        return default
    return max(observed_values)


def _latest_attempt_error(*, status: str, notes: dict[str, Any] | None) -> str | None:
    if status != "failed":
        return None
    reason = (notes or {}).get("reason")
    return str(reason) if reason else status


def _publication_payload(state: dict[str, Any]) -> dict[str, Any]:
    payload = dict(state)
    payload["status"] = payload.get("latest_attempt_status")
    payload["published_at_ms"] = payload.get("current_published_at_ms")
    payload["source_frontier_ms"] = payload.get("current_source_frontier_ms")
    payload["row_count"] = payload.get("current_row_count")
    return payload
