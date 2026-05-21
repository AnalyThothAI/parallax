from __future__ import annotations

import hashlib
from typing import Any

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
        written = 0
        for point in points:
            observed_at_ms = int(point["observed_at_ms"])
            series_id = _series_id(provider, native_market_id, "open_interest", period, observed_at_ms)
            self.conn.execute(
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
                """,
                (
                    series_id,
                    provider,
                    exchange,
                    native_market_id,
                    base_symbol,
                    quote_symbol,
                    period,
                    observed_at_ms,
                    point.get("value_numeric"),
                    point.get("value_usd"),
                    Jsonb(point.get("raw_payload") or {}),
                ),
            )
            written += 1
        if commit:
            self.conn.commit()
        return written


def _series_id(provider: str, native_market_id: str, metric: str, period: str, observed_at_ms: int) -> str:
    digest = hashlib.sha256(
        "|".join(
            [
                provider.strip().lower(),
                native_market_id.strip().upper(),
                metric.strip().lower(),
                period.strip().lower(),
                str(observed_at_ms),
            ]
        ).encode("utf-8")
    ).hexdigest()[:32]
    return f"cex-derivative-series:{digest}"
