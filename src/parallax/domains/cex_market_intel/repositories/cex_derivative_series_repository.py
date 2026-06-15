from __future__ import annotations

import hashlib
from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Any, cast

from psycopg.types.json import Jsonb


class CexDerivativeSeriesRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_open_interest_points(
        self,
        *,
        provider: str,
        exchange: str,
        native_market_id: str,
        base_symbol: str,
        quote_symbol: str,
        period: str,
        points: list[dict[str, Any]],
        commit: bool = True,
    ) -> int:
        if commit:
            with _transaction(self.conn):
                return self.upsert_open_interest_points(
                    provider=provider,
                    exchange=exchange,
                    native_market_id=native_market_id,
                    base_symbol=base_symbol,
                    quote_symbol=quote_symbol,
                    period=period,
                    points=points,
                    commit=False,
                )

        series_provider = _required_series_text(provider, "provider").lower()
        series_exchange = _required_series_text(exchange, "exchange").lower()
        series_native_market_id = _required_series_text(native_market_id, "native_market_id").upper()
        series_period = _required_series_text(period, "period").lower()
        written = 0
        for point in points:
            observed_at_ms = int(point["observed_at_ms"])
            series_id = _series_id(
                series_provider,
                series_native_market_id,
                "open_interest",
                series_period,
                observed_at_ms,
            )
            cursor = self.conn.execute(
                """
                INSERT INTO cex_derivative_series(
                  series_id, provider, exchange, native_market_id, base_symbol, quote_symbol,
                  metric, period, observed_at_ms, value_numeric, value_usd, raw_payload_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'open_interest', %s, %s, %s, %s, %s)
                ON CONFLICT(series_id) DO UPDATE SET
                  value_numeric = excluded.value_numeric,
                  value_usd = excluded.value_usd,
                  raw_payload_json = excluded.raw_payload_json
                WHERE cex_derivative_series.value_numeric IS DISTINCT FROM excluded.value_numeric
                   OR cex_derivative_series.value_usd IS DISTINCT FROM excluded.value_usd
                   OR cex_derivative_series.raw_payload_json IS DISTINCT FROM excluded.raw_payload_json
                """,
                (
                    series_id,
                    series_provider,
                    series_exchange,
                    series_native_market_id,
                    base_symbol,
                    quote_symbol,
                    series_period,
                    observed_at_ms,
                    point.get("value_numeric"),
                    point.get("value_usd"),
                    Jsonb(_required_raw_payload(point)),
                ),
            )
            written += _cursor_rowcount(cursor)
        return written


def _series_id(provider: str, native_market_id: str, metric: str, period: str, observed_at_ms: int) -> str:
    series_provider = _required_series_text(provider, "provider").lower()
    series_native_market_id = _required_series_text(native_market_id, "native_market_id").upper()
    series_metric = _required_series_text(metric, "metric").lower()
    series_period = _required_series_text(period, "period").lower()
    digest = hashlib.sha256(
        "|".join(
            [
                series_provider,
                series_native_market_id,
                series_metric,
                series_period,
                str(observed_at_ms),
            ]
        ).encode("utf-8")
    ).hexdigest()[:32]
    return f"cex-derivative-series:{digest}"


def _required_series_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"cex_derivative_series_identity_required:{field}")
    return text


def _required_raw_payload(point: dict[str, Any]) -> dict[Any, Any]:
    value = point.get("raw_payload")
    if value is None:
        raise ValueError("cex_derivative_series_raw_payload_required")
    if not isinstance(value, Mapping):
        raise ValueError("cex_derivative_series_raw_payload_invalid")
    return dict(value)


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise TypeError("cex_derivative_series_transaction_required") from exc
    if not callable(transaction):
        raise TypeError("cex_derivative_series_transaction_required")
    return cast(AbstractContextManager[Any], transaction())


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("cex_derivative_series_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int):
        raise TypeError("cex_derivative_series_rowcount_invalid")
    if rowcount < 0:
        raise TypeError("cex_derivative_series_rowcount_invalid")
    return rowcount
