from __future__ import annotations

import hashlib
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, cast

from psycopg.types.json import Jsonb

from parallax.platform.current_read_model_payload_hash import stable_current_payload_hash

_OBSERVED_AT_SOURCE_VALUES = frozenset({"provider", "computed"})


@dataclass(frozen=True, slots=True)
class CexBoardPublicationResult:
    board_changed: bool
    board_rows_written: int


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
        result = self.publish_board_with_result(
            rows=rows,
            computed_at_ms=computed_at_ms,
            period=period,
            status=status,
            notes=notes,
            commit=commit,
        )
        return result.board_rows_written

    def publish_board_with_result(
        self,
        *,
        rows: list[dict[str, Any]],
        computed_at_ms: int,
        period: str,
        status: str,
        notes: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> CexBoardPublicationResult:
        if commit:
            with _transaction(self.conn):
                return self.publish_board_with_result(
                    rows=rows,
                    computed_at_ms=computed_at_ms,
                    period=period,
                    status=status,
                    notes=notes,
                    commit=False,
                )

        board_period = _required_board_text(period, "period")
        computed_at = int(computed_at_ms)
        board_key = _board_key(board_period)
        frontier_ms = _source_frontier_ms(rows, default=computed_at)
        latest_error = _latest_attempt_error(status=status, notes=notes)

        if status not in {"success", "partial"}:
            self._record_attempt_without_publication(
                computed_at_ms=computed_at,
                period=board_period,
                status=status,
                latest_error=latest_error,
                commit=False,
            )
            return CexBoardPublicationResult(board_changed=False, board_rows_written=0)

        current_payload_hash = _board_payload_hash(
            rows=rows,
            period=board_period,
            source_frontier_ms=frontier_ms,
        )
        existing_state = self.conn.execute(
            """
            SELECT current_payload_hash
            FROM cex_oi_radar_publication_state
            WHERE board_key = %s
            """,
            (board_key,),
        ).fetchone()
        existing_payload_hash = dict(existing_state).get("current_payload_hash") if existing_state else None
        if existing_payload_hash == current_payload_hash:
            self._record_attempt_without_publication(
                computed_at_ms=computed_at,
                period=board_period,
                status=status,
                latest_error=latest_error,
                commit=False,
            )
            return CexBoardPublicationResult(board_changed=False, board_rows_written=0)

        self.conn.execute(
            """
            INSERT INTO cex_oi_radar_publication_state(
              board_key, provider, exchange, quote_symbol, contract_type, period,
              current_published_at_ms, current_source_frontier_ms, current_row_count, current_payload_hash,
              latest_attempt_status, latest_attempt_started_at_ms, latest_attempt_finished_at_ms,
              latest_attempt_error, updated_at_ms
            )
            VALUES (
              %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s,
              %s, %s, %s,
              %s, %s
            )
            ON CONFLICT(board_key) DO UPDATE SET
              current_published_at_ms = excluded.current_published_at_ms,
              current_source_frontier_ms = excluded.current_source_frontier_ms,
              current_row_count = excluded.current_row_count,
              current_payload_hash = excluded.current_payload_hash,
              latest_attempt_status = excluded.latest_attempt_status,
              latest_attempt_started_at_ms = excluded.latest_attempt_started_at_ms,
              latest_attempt_finished_at_ms = excluded.latest_attempt_finished_at_ms,
              latest_attempt_error = excluded.latest_attempt_error,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                board_key,
                "binance",
                "binance",
                "USDT",
                "PERPETUAL",
                board_period,
                computed_at,
                frontier_ms,
                len(rows),
                current_payload_hash,
                status,
                computed_at,
                computed_at,
                latest_error,
                computed_at,
            ),
        )
        incoming_row_ids = [_row_id(board_period, _required_board_row_text(row, "target_id")) for row in rows]
        if incoming_row_ids:
            delete_cursor = self.conn.execute(
                """
                DELETE FROM cex_oi_radar_rows
                WHERE board_provider = 'binance'
                  AND board_exchange = 'binance'
                  AND board_quote_symbol = 'USDT'
                  AND board_contract_type = 'PERPETUAL'
                  AND period = %s
                  AND NOT (row_id = ANY(%s::text[]))
                """,
                (board_period, incoming_row_ids),
            )
        else:
            delete_cursor = self.conn.execute(
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

        written = _cursor_rowcount(delete_cursor)
        for row, row_id in zip(rows, incoming_row_ids, strict=True):
            row_target_id = _required_board_row_text(row, "target_id")
            row_native_market_id = _required_board_row_text(row, "native_market_id")
            row_base_symbol = _required_board_row_text(row, "base_symbol")
            row_quote_symbol = _required_board_row_text(row, "quote_symbol")
            upsert_cursor = self.conn.execute(
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
                WHERE cex_oi_radar_rows.rank IS DISTINCT FROM excluded.rank
                   OR cex_oi_radar_rows.pricefeed_id IS DISTINCT FROM excluded.pricefeed_id
                   OR cex_oi_radar_rows.native_market_id IS DISTINCT FROM excluded.native_market_id
                   OR cex_oi_radar_rows.base_symbol IS DISTINCT FROM excluded.base_symbol
                   OR cex_oi_radar_rows.quote_symbol IS DISTINCT FROM excluded.quote_symbol
                   OR cex_oi_radar_rows.open_interest_usd IS DISTINCT FROM excluded.open_interest_usd
                   OR cex_oi_radar_rows.open_interest_change_pct_1h
                      IS DISTINCT FROM excluded.open_interest_change_pct_1h
                   OR cex_oi_radar_rows.volume_24h_usd IS DISTINCT FROM excluded.volume_24h_usd
                   OR cex_oi_radar_rows.funding_rate IS DISTINCT FROM excluded.funding_rate
                   OR cex_oi_radar_rows.mark_price IS DISTINCT FROM excluded.mark_price
                   OR cex_oi_radar_rows.score IS DISTINCT FROM excluded.score
                   OR cex_oi_radar_rows.score_components_json IS DISTINCT FROM excluded.score_components_json
                   OR cex_oi_radar_rows.observed_at_ms IS DISTINCT FROM excluded.observed_at_ms
                """,
                (
                    row_id,
                    board_period,
                    "binance",
                    "binance",
                    "USDT",
                    "PERPETUAL",
                    int(row["rank"]),
                    row_target_id,
                    row.get("pricefeed_id"),
                    row_native_market_id,
                    row_base_symbol,
                    row_quote_symbol,
                    row.get("open_interest_usd"),
                    row.get("open_interest_change_pct_1h"),
                    row.get("volume_24h_usd"),
                    row.get("funding_rate"),
                    row.get("mark_price"),
                    row["score"],
                    Jsonb(_required_score_components(row)),
                    _required_observed_at_ms(row),
                    computed_at,
                ),
            )
            written += _cursor_rowcount(upsert_cursor)

        return CexBoardPublicationResult(board_changed=True, board_rows_written=written)

    def record_attempt_failure(
        self,
        *,
        computed_at_ms: int,
        period: str,
        notes: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> None:
        board_period = _required_board_text(period, "period")
        computed_at = int(computed_at_ms)
        latest_error = _latest_attempt_error(status="failed", notes=notes)

        self._record_attempt_without_publication(
            computed_at_ms=computed_at,
            period=board_period,
            status="failed",
            latest_error=latest_error,
            commit=commit,
        )

    def _record_attempt_without_publication(
        self,
        *,
        computed_at_ms: int,
        period: str,
        status: str,
        latest_error: str | None,
        commit: bool,
    ) -> None:
        if commit:
            with _transaction(self.conn):
                self._record_attempt_without_publication(
                    computed_at_ms=computed_at_ms,
                    period=period,
                    status=status,
                    latest_error=latest_error,
                    commit=False,
                )
            return

        board_period = _required_board_text(period, "period")
        computed_at = int(computed_at_ms)

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
              %s, %s, %s,
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
                status,
                computed_at,
                computed_at,
                latest_error,
                computed_at,
            ),
        )

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
    board_period = _required_board_text(period, "period")
    return f"binance:USDT:PERPETUAL:{board_period}"


def _row_id(period: str, target_id: str) -> str:
    board_period = _required_board_text(period, "period")
    target = _required_board_text(target_id, "target_id")
    digest = hashlib.sha256(f"binance|binance|USDT|PERPETUAL|{board_period}|{target}".encode()).hexdigest()[:32]
    return f"cex-oi-radar-row:{digest}"


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("cex_oi_radar_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int):
        raise TypeError("cex_oi_radar_rowcount_invalid")
    if rowcount < 0:
        raise TypeError("cex_oi_radar_rowcount_invalid")
    return rowcount


def _source_frontier_ms(rows: list[dict[str, Any]], *, default: int) -> int:
    observed_values = [
        provider_observed_at_ms
        for row in rows
        if (provider_observed_at_ms := _provider_observed_at_ms(row)) is not None
    ]
    if not observed_values:
        return default
    return max(observed_values)


def _latest_attempt_error(*, status: str, notes: dict[str, Any] | None) -> str | None:
    if status != "failed":
        return None
    reason = (notes or {}).get("reason")
    return str(reason) if reason else status


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise TypeError("cex_oi_radar_transaction_required") from exc
    if not callable(transaction):
        raise TypeError("cex_oi_radar_transaction_required")
    return cast(AbstractContextManager[Any], transaction())


def _board_payload_hash(*, rows: list[dict[str, Any]], period: str, source_frontier_ms: int) -> str:
    board_period = _required_board_text(period, "period")
    return stable_current_payload_hash(
        {
            "provider": "binance",
            "exchange": "binance",
            "quote_symbol": "USDT",
            "contract_type": "PERPETUAL",
            "period": board_period,
            "source_frontier_ms": _board_hash_source_frontier_ms(
                rows=rows,
                source_frontier_ms=source_frontier_ms,
            ),
            "rows": [
                _board_row_payload(row)
                for row in sorted(
                    rows,
                    key=lambda item: (int(item["rank"]), _required_board_row_text(item, "target_id")),
                )
            ],
        }
    )


def _board_row_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": int(row["rank"]),
        "target_id": _required_board_row_text(row, "target_id"),
        "pricefeed_id": row.get("pricefeed_id"),
        "native_market_id": _required_board_row_text(row, "native_market_id"),
        "base_symbol": _required_board_row_text(row, "base_symbol"),
        "quote_symbol": _required_board_row_text(row, "quote_symbol"),
        "open_interest_usd": row.get("open_interest_usd"),
        "open_interest_change_pct_1h": row.get("open_interest_change_pct_1h"),
        "volume_24h_usd": row.get("volume_24h_usd"),
        "funding_rate": row.get("funding_rate"),
        "mark_price": row.get("mark_price"),
        "score": row["score"],
        "score_components": _required_score_components(row),
        "observed_at_ms": _provider_observed_at_ms(row),
    }


def _board_hash_source_frontier_ms(
    *,
    rows: list[dict[str, Any]],
    source_frontier_ms: int,
) -> int | None:
    provider_observed_values = [
        provider_observed_at_ms
        for row in rows
        if (provider_observed_at_ms := _provider_observed_at_ms(row)) is not None
    ]
    if provider_observed_values:
        return max(provider_observed_values)
    if not rows or any(_observed_at_source(row) == "computed" for row in rows):
        return None
    return source_frontier_ms


def _provider_observed_at_ms(row: dict[str, Any]) -> int | None:
    observed_at_ms = _required_observed_at_ms(row)
    source = _observed_at_source(row)
    if source == "provider":
        return observed_at_ms
    if source == "computed":
        return None
    raise ValueError("cex_oi_radar_observation_invalid:observed_at_source")


def _observed_at_source(row: dict[str, Any]) -> str:
    return _required_observed_at_source(row)


def _required_observed_at_ms(row: dict[str, Any]) -> int:
    value = row.get("observed_at_ms")
    if value is None:
        raise ValueError("cex_oi_radar_observation_required:observed_at_ms")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("cex_oi_radar_observation_invalid:observed_at_ms") from exc


def _required_observed_at_source(row: dict[str, Any]) -> str:
    value = row.get("observed_at_source")
    if value is None:
        raise ValueError("cex_oi_radar_observation_required:observed_at_source")
    source = str(value).strip().lower()
    if not source:
        raise ValueError("cex_oi_radar_observation_required:observed_at_source")
    if source not in _OBSERVED_AT_SOURCE_VALUES:
        raise ValueError("cex_oi_radar_observation_invalid:observed_at_source")
    return source


def _required_score_components(row: dict[str, Any]) -> dict[Any, Any]:
    value = row.get("score_components")
    if value is None:
        raise ValueError("cex_oi_radar_score_components_required")
    if not isinstance(value, Mapping):
        raise ValueError("cex_oi_radar_score_components_invalid")
    return dict(value)


def _required_board_row_text(row: dict[str, Any], field: str) -> str:
    return _required_board_text(row.get(field), field)


def _required_board_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"cex_oi_radar_identity_required:{field}")
    return text


def _publication_payload(state: dict[str, Any]) -> dict[str, Any]:
    payload = dict(state)
    payload["status"] = payload.get("latest_attempt_status")
    payload["published_at_ms"] = payload.get("current_published_at_ms")
    payload["source_frontier_ms"] = payload.get("current_source_frontier_ms")
    payload["row_count"] = payload.get("current_row_count")
    return payload
