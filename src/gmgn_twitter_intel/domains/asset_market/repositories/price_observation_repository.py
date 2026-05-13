from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.asset_market.types import (
    MarketObservation,
    MarketTargetRef,
    market_observation_from_row,
)

MARKET_OBSERVATION_KINDS = frozenset({"event_anchor", "decision_latest"})


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
        observation_kind: str = "event_anchor",
        event_received_at_ms: int | None = None,
        raw_payload: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        observation = MarketObservation(
            target=MarketTargetRef(target_type=subject_type, target_id=subject_id),
            observed_at_ms=int(observed_at_ms),
            received_at_ms=int(observed_at_ms),
            source=observation_kind,
            provider=provider,
            pricefeed_id=pricefeed_id,
            price_usd=_optional_float(price_usd),
            price_quote=_optional_float(price_quote),
            quote_symbol=quote_symbol,
            price_basis=price_basis,
            market_cap_usd=_optional_float(market_cap_usd),
            liquidity_usd=_optional_float(liquidity_usd),
            holders=int(holders) if holders is not None else None,
            volume_24h_usd=_optional_float(volume_24h_usd),
            open_interest_usd=_optional_float(open_interest_usd),
            raw_payload_hash=_raw_payload_hash(raw_payload),
        )
        observation_id = self.insert_market_observation(
            observation,
            observation_kind=observation_kind,
            source_event_id=source_event_id,
            source_intent_id=source_intent_id,
            source_resolution_id=source_resolution_id,
            event_received_at_ms=event_received_at_ms,
            commit=commit,
        )
        return self.get(observation_id) or {}

    def insert_market_observation(
        self,
        observation: MarketObservation,
        *,
        observation_kind: str,
        source_event_id: str | None = None,
        source_intent_id: str | None = None,
        source_resolution_id: str | None = None,
        event_received_at_ms: int | None = None,
        commit: bool = True,
    ) -> str:
        if observation.provider == "gmgn_payload":
            raise ValueError("GMGN payload token snapshots are identity evidence only, not market observations")
        if observation_kind not in MARKET_OBSERVATION_KINDS:
            raise ValueError("price observations must be event_anchor or decision_latest")
        if observation_kind == "event_anchor" and (
            not source_event_id or not source_intent_id or not source_resolution_id or event_received_at_ms is None
        ):
            raise ValueError("event_anchor observations require event, intent, resolution, and event time")

        observation_id = _observation_id(
            provider=observation.provider or "",
            pricefeed_id=observation.pricefeed_id,
            observed_at_ms=observation.observed_at_ms,
            subject_type=observation.target.target_type,
            subject_id=observation.target.target_id,
            source_event_id=source_event_id,
            source_intent_id=source_intent_id,
            source_resolution_id=source_resolution_id,
            observation_kind=observation_kind,
        )
        existing_id = (
            self._event_anchor_observation_id(source_resolution_id) if observation_kind == "event_anchor" else None
        )
        stored_observation_id = (
            self._update_market_observation(
                existing_id,
                observation,
                observation_kind=observation_kind,
                source_event_id=source_event_id,
                source_intent_id=source_intent_id,
                source_resolution_id=source_resolution_id,
                event_received_at_ms=event_received_at_ms,
            )
            if existing_id
            else self._insert_market_observation(
                observation_id,
                observation,
                observation_kind=observation_kind,
                source_event_id=source_event_id,
                source_intent_id=source_intent_id,
                source_resolution_id=source_resolution_id,
                event_received_at_ms=event_received_at_ms,
            )
        )
        if commit:
            self.conn.commit()
        return stored_observation_id

    def get(self, observation_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM price_observations WHERE observation_id = %s",
            (observation_id,),
        ).fetchone()
        return dict(row) if row else None

    def event_anchor_for_resolution(self, *, resolution_id: str) -> MarketObservation | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM price_observations
            WHERE source_resolution_id = %s
              AND observation_kind = 'event_anchor'
            ORDER BY observed_at_ms DESC, observation_id DESC
            LIMIT 1
            """,
            (resolution_id,),
        ).fetchone()
        return market_observation_from_row(row) if row else None

    def latest_for_target(
        self,
        *,
        target_type: str,
        target_id: str,
        now_ms: int,
        max_age_ms: int | None,
    ) -> MarketObservation | None:
        min_observed_at_ms = int(now_ms) - int(max_age_ms) if max_age_ms is not None else None
        row = self.conn.execute(
            """
            SELECT *
            FROM price_observations
            WHERE subject_type = %s
              AND subject_id = %s
              AND observation_kind = 'decision_latest'
              AND (%s IS NULL OR observed_at_ms >= %s)
              AND observed_at_ms <= %s
            ORDER BY observed_at_ms DESC, observation_id DESC
            LIMIT 1
            """,
            (target_type, target_id, min_observed_at_ms, min_observed_at_ms, int(now_ms)),
        ).fetchone()
        return market_observation_from_row(row) if row else None

    def first_after(self, *, target_type: str, target_id: str, at_ms: int) -> MarketObservation | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM price_observations
            WHERE subject_type = %s
              AND subject_id = %s
              AND observed_at_ms >= %s
            ORDER BY observed_at_ms ASC, observation_id ASC
            LIMIT 1
            """,
            (target_type, target_id, int(at_ms)),
        ).fetchone()
        return market_observation_from_row(row) if row else None

    def latest_before(self, *, target_type: str, target_id: str, at_ms: int) -> MarketObservation | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM price_observations
            WHERE subject_type = %s
              AND subject_id = %s
              AND observed_at_ms <= %s
            ORDER BY observed_at_ms DESC, observation_id DESC
            LIMIT 1
            """,
            (target_type, target_id, int(at_ms)),
        ).fetchone()
        return market_observation_from_row(row) if row else None

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

    def latest_price_for_subject_at_or_before(
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
            WHERE subject_type = %s
              AND subject_id = %s
              AND observed_at_ms <= %s
              AND price_usd IS NOT NULL
            ORDER BY observed_at_ms DESC, observation_id DESC
            LIMIT 1
            """,
            (subject_type, subject_id, int(at_or_before_ms)),
        ).fetchone()
        return dict(row) if row else None

    def first_for_subject_at_or_after(
        self,
        *,
        subject_type: str,
        subject_id: str,
        at_or_after_ms: int,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM price_observations
            WHERE subject_type = %s
              AND subject_id = %s
              AND observed_at_ms >= %s
              AND price_usd IS NOT NULL
            ORDER BY observed_at_ms ASC, observation_id ASC
            LIMIT 1
            """,
            (subject_type, subject_id, int(at_or_after_ms)),
        ).fetchone()
        return dict(row) if row else None

    def first_price_for_subject_between(
        self,
        *,
        subject_type: str,
        subject_id: str,
        at_or_after_ms: int,
        at_or_before_ms: int,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM price_observations
            WHERE subject_type = %s
              AND subject_id = %s
              AND observed_at_ms >= %s
              AND observed_at_ms <= %s
              AND price_usd IS NOT NULL
            ORDER BY observed_at_ms ASC, observation_id ASC
            LIMIT 1
            """,
            (subject_type, subject_id, int(at_or_after_ms), int(at_or_before_ms)),
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
              AND observation_kind = 'event_anchor'
            ORDER BY
              observed_at_ms DESC,
              observation_id DESC
            LIMIT 1
            """,
            (event_id, subject_type, subject_id),
        ).fetchone()
        return dict(row) if row else None

    def _event_anchor_observation_id(self, source_resolution_id: str | None) -> str | None:
        if not source_resolution_id:
            return None
        row = self.conn.execute(
            """
            SELECT observation_id
            FROM price_observations
            WHERE source_resolution_id = %s
              AND observation_kind = 'event_anchor'
            ORDER BY observed_at_ms DESC, observation_id DESC
            LIMIT 1
            """,
            (source_resolution_id,),
        ).fetchone()
        return str(row["observation_id"]) if row else None

    def _insert_market_observation(
        self,
        observation_id: str,
        observation: MarketObservation,
        *,
        observation_kind: str,
        source_event_id: str | None,
        source_intent_id: str | None,
        source_resolution_id: str | None,
        event_received_at_ms: int | None,
    ) -> str:
        stored = self.conn.execute(
            """
            INSERT INTO price_observations(
              observation_id, pricefeed_id, provider, observed_at_ms, subject_type, subject_id,
              price_usd, price_quote, quote_symbol, price_basis, market_cap_usd, liquidity_usd,
              volume_24h_usd, open_interest_usd, holders, source_event_id, source_intent_id,
              source_resolution_id, observation_kind, event_received_at_ms, observation_lag_ms,
              raw_payload_json, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING observation_id
            """,
            _row_params(
                observation_id,
                observation,
                observation_kind=observation_kind,
                source_event_id=source_event_id,
                source_intent_id=source_intent_id,
                source_resolution_id=source_resolution_id,
                event_received_at_ms=event_received_at_ms,
            ),
        ).fetchone()
        return str((stored or {}).get("observation_id") or observation_id)

    def _update_market_observation(
        self,
        observation_id: str,
        observation: MarketObservation,
        *,
        observation_kind: str,
        source_event_id: str | None,
        source_intent_id: str | None,
        source_resolution_id: str | None,
        event_received_at_ms: int | None,
    ) -> str:
        stored = self.conn.execute(
            """
            UPDATE price_observations
            SET pricefeed_id = %s,
                provider = %s,
                observed_at_ms = %s,
                subject_type = %s,
                subject_id = %s,
                price_usd = %s,
                price_quote = %s,
                quote_symbol = %s,
                price_basis = %s,
                market_cap_usd = %s,
                liquidity_usd = %s,
                volume_24h_usd = %s,
                open_interest_usd = %s,
                holders = %s,
                source_event_id = %s,
                source_intent_id = %s,
                source_resolution_id = %s,
                observation_kind = %s,
                event_received_at_ms = %s,
                observation_lag_ms = %s,
                raw_payload_json = %s,
                created_at_ms = %s
            WHERE observation_id = %s
            RETURNING observation_id
            """,
            (
                *_row_params(
                    observation_id,
                    observation,
                    observation_kind=observation_kind,
                    source_event_id=source_event_id,
                    source_intent_id=source_intent_id,
                    source_resolution_id=source_resolution_id,
                    event_received_at_ms=event_received_at_ms,
                )[1:],
                observation_id,
            ),
        ).fetchone()
        return str((stored or {}).get("observation_id") or observation_id)


def _row_params(
    observation_id: str,
    observation: MarketObservation,
    *,
    observation_kind: str,
    source_event_id: str | None,
    source_intent_id: str | None,
    source_resolution_id: str | None,
    event_received_at_ms: int | None,
) -> tuple[Any, ...]:
    observed_at_ms = int(observation.observed_at_ms)
    observation_lag_ms = (
        max(0, observed_at_ms - int(event_received_at_ms)) if event_received_at_ms is not None else None
    )
    created_at_ms = int(observation.received_at_ms if observation.received_at_ms is not None else observed_at_ms)
    return (
        observation_id,
        observation.pricefeed_id,
        observation.provider,
        observed_at_ms,
        observation.target.target_type,
        observation.target.target_id,
        observation.price_usd,
        observation.price_quote,
        observation.quote_symbol,
        observation.price_basis or "unavailable",
        observation.market_cap_usd,
        observation.liquidity_usd,
        observation.volume_24h_usd,
        observation.open_interest_usd,
        observation.holders,
        source_event_id,
        source_intent_id,
        source_resolution_id,
        observation_kind,
        int(event_received_at_ms) if event_received_at_ms is not None else None,
        observation_lag_ms,
        Jsonb(_raw_payload_json(observation)),
        created_at_ms,
    )


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


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _raw_payload_hash(raw_payload: Mapping[str, Any] | None) -> str | None:
    if not raw_payload:
        return None
    value = raw_payload.get("raw_payload_hash")
    return str(value) if value is not None else None


def _raw_payload_json(observation: MarketObservation) -> dict[str, Any]:
    return {"raw_payload_hash": observation.raw_payload_hash} if observation.raw_payload_hash else {}
