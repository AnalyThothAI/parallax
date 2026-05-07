from __future__ import annotations

import hashlib
from typing import Any

from psycopg.types.json import Jsonb


class PriceObservationRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def insert_observation(
        self,
        *,
        provider: str,
        pricefeed_id: str | None,
        observed_at_ms: int,
        subject_type: str,
        subject_id: str,
        price_usd: Any = None,
        price_quote: Any = None,
        quote_symbol: str | None = None,
        price_basis: str = "unavailable",
        market_cap_usd: Any = None,
        liquidity_usd: Any = None,
        volume_24h_usd: Any = None,
        open_interest_usd: Any = None,
        holders: int | None = None,
        raw_payload: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        observation_id = _stable_id(
            "price-observation",
            provider,
            pricefeed_id or "",
            subject_type,
            subject_id,
            str(observed_at_ms),
        )
        self.conn.execute(
            """
            INSERT INTO price_observations(
              observation_id, pricefeed_id, provider, observed_at_ms, subject_type, subject_id,
              price_usd, price_quote, quote_symbol, price_basis, market_cap_usd, liquidity_usd,
              volume_24h_usd, open_interest_usd, holders, raw_payload_json, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(observation_id) DO UPDATE SET
              price_usd = excluded.price_usd,
              price_quote = excluded.price_quote,
              quote_symbol = excluded.quote_symbol,
              price_basis = excluded.price_basis,
              market_cap_usd = excluded.market_cap_usd,
              liquidity_usd = excluded.liquidity_usd,
              volume_24h_usd = excluded.volume_24h_usd,
              open_interest_usd = excluded.open_interest_usd,
              holders = excluded.holders,
              raw_payload_json = excluded.raw_payload_json
            """,
            (
                observation_id,
                pricefeed_id,
                provider,
                int(observed_at_ms),
                subject_type,
                subject_id,
                price_usd,
                price_quote,
                quote_symbol,
                price_basis,
                market_cap_usd,
                liquidity_usd,
                volume_24h_usd,
                open_interest_usd,
                holders,
                Jsonb(raw_payload or {}),
                int(observed_at_ms),
            ),
        )
        if commit:
            self.conn.commit()
        return self.get(observation_id) or {}

    def get(self, observation_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM price_observations WHERE observation_id = %s",
            (observation_id,),
        ).fetchone()
        return dict(row) if row else None

    def latest_for_subject(self, *, subject_type: str, subject_id: str, at_or_before_ms: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM price_observations
            WHERE subject_type = %s AND subject_id = %s AND observed_at_ms <= %s
            ORDER BY observed_at_ms DESC, observation_id DESC
            LIMIT 1
            """,
            (subject_type, subject_id, int(at_or_before_ms)),
        ).fetchone()
        return dict(row) if row else None


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
