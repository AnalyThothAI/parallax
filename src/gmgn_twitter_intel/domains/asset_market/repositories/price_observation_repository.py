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
        if provider == "gmgn_payload":
            raise ValueError("GMGN payload token snapshots are identity evidence only, not market observations")
        if observation_kind != "message_anchor":
            raise ValueError("price observations are anchor-only; live/refresh prices are not persisted")
        if not source_event_id or not source_intent_id or not source_resolution_id or event_received_at_ms is None:
            raise ValueError("message_anchor observations require event, intent, resolution, and event time")
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
        self._upsert_token_market_price_baseline(
            resolution_id=source_resolution_id,
            event_id=source_event_id,
            target_type=subject_type,
            target_id=subject_id,
            event_received_at_ms=int(event_received_at_ms),
            observation_id=observation_id,
            observation_kind=observation_kind,
            provider=provider,
            observed_at_ms=int(observed_at_ms),
            price_usd=price_usd,
            price_quote=price_quote,
            quote_symbol=quote_symbol,
            price_basis=price_basis,
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
              AND observation_kind = 'message_anchor'
            ORDER BY
              observed_at_ms DESC,
              observation_id DESC
            LIMIT 1
            """,
            (event_id, subject_type, subject_id),
        ).fetchone()
        return dict(row) if row else None

    def backfill_token_price_baselines(self, *, limit: int = 1000) -> dict[str, int]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM price_observations
            WHERE source_resolution_id IS NOT NULL
              AND source_event_id IS NOT NULL
              AND event_received_at_ms IS NOT NULL
              AND observation_kind = 'message_anchor'
            ORDER BY event_received_at_ms DESC, observation_id DESC
            LIMIT %s
            """,
            (max(0, int(limit)),),
        ).fetchall()
        for row in rows:
            self._upsert_token_market_price_baseline(
                resolution_id=str(row["source_resolution_id"]),
                event_id=str(row["source_event_id"]),
                target_type=str(row["subject_type"]),
                target_id=str(row["subject_id"]),
                event_received_at_ms=int(row["event_received_at_ms"]),
                observation_id=str(row["observation_id"]),
                observation_kind=str(row["observation_kind"]),
                provider=str(row["provider"]),
                observed_at_ms=int(row["observed_at_ms"]),
                price_usd=row.get("price_usd"),
                price_quote=row.get("price_quote"),
                quote_symbol=row.get("quote_symbol"),
                price_basis=row.get("price_basis"),
            )
        self.conn.commit()
        return {"baselines_written": len(rows)}

    def _upsert_token_market_price_baseline(
        self,
        *,
        resolution_id: str,
        event_id: str,
        target_type: str,
        target_id: str,
        event_received_at_ms: int,
        observation_id: str,
        observation_kind: str,
        provider: str,
        observed_at_ms: int,
        price_usd: Any,
        price_quote: Any,
        quote_symbol: str | None,
        price_basis: str | None,
    ) -> None:
        first = self.first_for_subject(subject_type=target_type, subject_id=target_id)
        before = self._latest_for_subject_before_event(
            subject_type=target_type,
            subject_id=target_id,
            at_or_before_ms=event_received_at_ms,
            exclude_observation_id=observation_id,
        )
        self.conn.execute(
            """
            INSERT INTO token_market_price_baselines(
              resolution_id, event_id, target_type, target_id, event_received_at_ms,
              first_price_observed_at_ms, first_price_usd, first_price_quote,
              first_price_quote_symbol, first_price_basis,
              event_price_observation_id, event_price_observation_kind, event_price_provider,
              event_price_observed_at_ms, event_price_usd, event_price_quote,
              event_price_quote_symbol, event_price_basis,
              before_event_price_observed_at_ms, before_event_price_usd, before_event_price_quote,
              before_event_price_quote_symbol, before_event_price_basis, updated_at_ms
            )
            VALUES (
              %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT(resolution_id) DO UPDATE SET
              event_id = excluded.event_id,
              target_type = excluded.target_type,
              target_id = excluded.target_id,
              event_received_at_ms = excluded.event_received_at_ms,
              first_price_observed_at_ms = excluded.first_price_observed_at_ms,
              first_price_usd = excluded.first_price_usd,
              first_price_quote = excluded.first_price_quote,
              first_price_quote_symbol = excluded.first_price_quote_symbol,
              first_price_basis = excluded.first_price_basis,
              event_price_observation_id = excluded.event_price_observation_id,
              event_price_observation_kind = excluded.event_price_observation_kind,
              event_price_provider = excluded.event_price_provider,
              event_price_observed_at_ms = excluded.event_price_observed_at_ms,
              event_price_usd = excluded.event_price_usd,
              event_price_quote = excluded.event_price_quote,
              event_price_quote_symbol = excluded.event_price_quote_symbol,
              event_price_basis = excluded.event_price_basis,
              before_event_price_observed_at_ms = excluded.before_event_price_observed_at_ms,
              before_event_price_usd = excluded.before_event_price_usd,
              before_event_price_quote = excluded.before_event_price_quote,
              before_event_price_quote_symbol = excluded.before_event_price_quote_symbol,
              before_event_price_basis = excluded.before_event_price_basis,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                resolution_id,
                event_id,
                target_type,
                target_id,
                event_received_at_ms,
                _row_int(first, "observed_at_ms"),
                _row_value(first, "price_usd"),
                _row_value(first, "price_quote"),
                _row_value(first, "quote_symbol"),
                _row_value(first, "price_basis"),
                observation_id,
                observation_kind,
                provider,
                observed_at_ms,
                price_usd,
                price_quote,
                quote_symbol,
                price_basis,
                _row_int(before, "observed_at_ms"),
                _row_value(before, "price_usd"),
                _row_value(before, "price_quote"),
                _row_value(before, "quote_symbol"),
                _row_value(before, "price_basis"),
                observed_at_ms,
            ),
        )

    def _latest_for_subject_before_event(
        self,
        *,
        subject_type: str,
        subject_id: str,
        at_or_before_ms: int,
        exclude_observation_id: str,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM price_observations
            WHERE subject_type = %s
              AND subject_id = %s
              AND observed_at_ms <= %s
              AND observation_id <> %s
            ORDER BY observed_at_ms DESC, observation_id DESC
            LIMIT 1
            """,
            (subject_type, subject_id, int(at_or_before_ms), exclude_observation_id),
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


def _row_value(row: dict[str, Any] | None, key: str) -> Any:
    return row.get(key) if row else None


def _row_int(row: dict[str, Any] | None, key: str) -> int | None:
    value = _row_value(row, key)
    return int(value) if value is not None else None
