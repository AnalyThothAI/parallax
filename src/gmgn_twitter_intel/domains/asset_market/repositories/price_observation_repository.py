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
        source_event_id: str | None = None,
        source_intent_id: str | None = None,
        source_resolution_id: str | None = None,
        observation_kind: str = "refresh",
        event_received_at_ms: int | None = None,
        raw_payload: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        observation_lag_ms = (
            max(0, int(observed_at_ms) - int(event_received_at_ms)) if event_received_at_ms is not None else None
        )
        observation_id = _observation_id(
            provider=provider,
            pricefeed_id=pricefeed_id,
            observed_at_ms=int(observed_at_ms),
            subject_type=subject_type,
            subject_id=subject_id,
            source_event_id=source_event_id,
            source_intent_id=source_intent_id,
            source_resolution_id=source_resolution_id,
            observation_kind=observation_kind,
        )
        self.conn.execute(
            """
            INSERT INTO price_observations(
              observation_id, pricefeed_id, provider, observed_at_ms, subject_type, subject_id,
              price_usd, price_quote, quote_symbol, price_basis, market_cap_usd, liquidity_usd,
              volume_24h_usd, open_interest_usd, holders, source_event_id, source_intent_id,
              source_resolution_id, observation_kind, event_received_at_ms, observation_lag_ms,
              raw_payload_json, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
              source_event_id = excluded.source_event_id,
              source_intent_id = excluded.source_intent_id,
              source_resolution_id = excluded.source_resolution_id,
              observation_kind = excluded.observation_kind,
              event_received_at_ms = excluded.event_received_at_ms,
              observation_lag_ms = excluded.observation_lag_ms,
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
                source_event_id,
                source_intent_id,
                source_resolution_id,
                observation_kind,
                int(event_received_at_ms) if event_received_at_ms is not None else None,
                observation_lag_ms,
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
        return self.latest_for_subject_at_or_before(
            subject_type=subject_type,
            subject_id=subject_id,
            at_or_before_ms=at_or_before_ms,
        )

    def first_for_subject(self, *, subject_type: str, subject_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM price_observations
            WHERE subject_type = %s AND subject_id = %s
            ORDER BY observed_at_ms ASC, observation_id ASC
            LIMIT 1
            """,
            (subject_type, subject_id),
        ).fetchone()
        return dict(row) if row else None

    def latest_for_subject_at_or_before(
        self,
        *,
        subject_type: str,
        subject_id: str,
        at_or_before_ms: int,
    ) -> dict[str, Any] | None:
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

    def latest_message_for_event(
        self,
        *,
        event_id: str,
        subject_type: str,
        subject_id: str,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM price_observations
            WHERE source_event_id = %s
              AND subject_type = %s
              AND subject_id = %s
              AND observation_kind IN ('message_payload', 'message_quote')
            ORDER BY
              CASE WHEN observation_kind = 'message_payload' THEN 0 ELSE 1 END,
              observed_at_ms DESC,
              observation_id DESC
            LIMIT 1
            """,
            (event_id, subject_type, subject_id),
        ).fetchone()
        return dict(row) if row else None


def _observation_id(
    *,
    provider: str,
    pricefeed_id: str | None,
    observed_at_ms: int,
    subject_type: str,
    subject_id: str,
    source_event_id: str | None,
    source_intent_id: str | None,
    source_resolution_id: str | None,
    observation_kind: str,
) -> str:
    if observation_kind == "refresh" and not (source_event_id or source_intent_id or source_resolution_id):
        return _stable_id(
            "price-observation",
            provider,
            pricefeed_id or "",
            subject_type,
            subject_id,
            str(observed_at_ms),
        )
    return _stable_id(
        "price-observation",
        observation_kind,
        source_event_id or "",
        source_intent_id or "",
        source_resolution_id or "",
        provider,
        pricefeed_id or "",
        subject_type,
        subject_id,
        str(observed_at_ms),
    )


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
