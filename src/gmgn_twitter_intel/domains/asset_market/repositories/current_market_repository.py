from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.asset_market.market_field_facts import (
    CEX_MARKET_CAPABLE_PROVIDERS,
    DEFAULT_MARKET_METADATA_FRESH_MS,
    DEFAULT_PRICE_FRESH_MS,
    DEX_METADATA_CAPABLE_PROVIDERS,
    PRICE_CAPABLE_PROVIDERS,
    VOLUME_24H_CAPABLE_PROVIDERS,
    aggregate_market_status,
    field_fact,
)


def _sql_values(values: frozenset[str]) -> str:
    return ", ".join(f"'{value}'" for value in sorted(values))


PRICE_PROVIDER_SQL = _sql_values(PRICE_CAPABLE_PROVIDERS)
DEX_METADATA_PROVIDER_SQL = _sql_values(DEX_METADATA_CAPABLE_PROVIDERS)
VOLUME_24H_PROVIDER_SQL = _sql_values(VOLUME_24H_CAPABLE_PROVIDERS)
OPEN_INTEREST_PROVIDER_SQL = _sql_values(CEX_MARKET_CAPABLE_PROVIDERS)


class CurrentMarketRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def current_for_subjects(
        self,
        subjects: list[dict[str, Any]],
        *,
        now_ms: int,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        normalized = _subjects(subjects)
        if not normalized:
            return {}
        values_sql = ",".join(["(%s, %s)"] * len(normalized))
        params: list[Any] = []
        for subject_type, subject_id in normalized:
            params.extend([subject_type, subject_id])
        params.append(int(now_ms))
        rows = self.conn.execute(
            f"""
            WITH requested(subject_type, subject_id) AS (VALUES {values_sql}),
                 clock(now_ms) AS (VALUES (%s))
            SELECT
              requested.subject_type,
              requested.subject_id,
              price.observation_id AS price_observation_id,
              price.provider AS price_provider,
              price.observed_at_ms AS price_observed_at_ms,
              price.price_usd,
              price.price_quote,
              price.quote_symbol,
              price.price_basis,
              market_cap.observation_id AS market_cap_observation_id,
              market_cap.provider AS market_cap_provider,
              market_cap.observed_at_ms AS market_cap_observed_at_ms,
              market_cap.market_cap_usd,
              liquidity.observation_id AS liquidity_observation_id,
              liquidity.provider AS liquidity_provider,
              liquidity.observed_at_ms AS liquidity_observed_at_ms,
              liquidity.liquidity_usd,
              holders.observation_id AS holders_observation_id,
              holders.provider AS holders_provider,
              holders.observed_at_ms AS holders_observed_at_ms,
              holders.holders,
              volume_24h.observation_id AS volume_24h_observation_id,
              volume_24h.provider AS volume_24h_provider,
              volume_24h.observed_at_ms AS volume_24h_observed_at_ms,
              volume_24h.volume_24h_usd,
              open_interest.observation_id AS open_interest_observation_id,
              open_interest.provider AS open_interest_provider,
              open_interest.observed_at_ms AS open_interest_observed_at_ms,
              open_interest.open_interest_usd
            FROM requested
            CROSS JOIN clock
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_observations
              WHERE subject_type = requested.subject_type
                AND subject_id = requested.subject_id
                AND observed_at_ms <= clock.now_ms
                AND provider IN ({PRICE_PROVIDER_SQL})
                AND (price_usd IS NOT NULL OR price_quote IS NOT NULL)
              ORDER BY observed_at_ms DESC, observation_id DESC
              LIMIT 1
            ) price ON true
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_observations
              WHERE subject_type = requested.subject_type
                AND subject_id = requested.subject_id
                AND observed_at_ms <= clock.now_ms
                AND provider IN ({DEX_METADATA_PROVIDER_SQL})
                AND market_cap_usd IS NOT NULL
              ORDER BY observed_at_ms DESC, observation_id DESC
              LIMIT 1
            ) market_cap ON true
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_observations
              WHERE subject_type = requested.subject_type
                AND subject_id = requested.subject_id
                AND observed_at_ms <= clock.now_ms
                AND provider IN ({DEX_METADATA_PROVIDER_SQL})
                AND liquidity_usd IS NOT NULL
              ORDER BY observed_at_ms DESC, observation_id DESC
              LIMIT 1
            ) liquidity ON true
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_observations
              WHERE subject_type = requested.subject_type
                AND subject_id = requested.subject_id
                AND observed_at_ms <= clock.now_ms
                AND provider IN ({DEX_METADATA_PROVIDER_SQL})
                AND holders IS NOT NULL
              ORDER BY observed_at_ms DESC, observation_id DESC
              LIMIT 1
            ) holders ON true
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_observations
              WHERE subject_type = requested.subject_type
                AND subject_id = requested.subject_id
                AND observed_at_ms <= clock.now_ms
                AND provider IN ({VOLUME_24H_PROVIDER_SQL})
                AND volume_24h_usd IS NOT NULL
              ORDER BY observed_at_ms DESC, observation_id DESC
              LIMIT 1
            ) volume_24h ON true
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_observations
              WHERE subject_type = requested.subject_type
                AND subject_id = requested.subject_id
                AND observed_at_ms <= clock.now_ms
                AND provider IN ({OPEN_INTEREST_PROVIDER_SQL})
                AND open_interest_usd IS NOT NULL
              ORDER BY observed_at_ms DESC, observation_id DESC
              LIMIT 1
            ) open_interest ON true
            """,
            params,
        ).fetchall()
        return {_key(row): _snapshot(row, now_ms=now_ms) for row in rows}


def _subjects(subjects: list[dict[str, Any]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    normalized: list[tuple[str, str]] = []
    for subject in subjects:
        subject_type = str(subject.get("target_type") or subject.get("subject_type") or "").strip()
        subject_id = str(subject.get("target_id") or subject.get("subject_id") or "").strip()
        if not subject_type or not subject_id:
            continue
        key = (subject_type, subject_id)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return normalized


def _key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row["subject_type"]), str(row["subject_id"]))


def _snapshot(row: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
    target_type, target_id = _key(row)
    fields = {
        "price_usd": field_fact(
            value=row.get("price_usd"),
            observed_at_ms=row.get("price_observed_at_ms"),
            now_ms=now_ms,
            provider=row.get("price_provider"),
            observation_id=row.get("price_observation_id"),
            fresh_ms=DEFAULT_PRICE_FRESH_MS,
        ),
        "price_quote": field_fact(
            value=row.get("price_quote"),
            observed_at_ms=row.get("price_observed_at_ms"),
            now_ms=now_ms,
            provider=row.get("price_provider"),
            observation_id=row.get("price_observation_id"),
            fresh_ms=DEFAULT_PRICE_FRESH_MS,
        ),
        "quote_symbol": field_fact(
            value=row.get("quote_symbol"),
            observed_at_ms=row.get("price_observed_at_ms"),
            now_ms=now_ms,
            provider=row.get("price_provider"),
            observation_id=row.get("price_observation_id"),
            fresh_ms=DEFAULT_PRICE_FRESH_MS,
        ),
        "price_basis": field_fact(
            value=row.get("price_basis"),
            observed_at_ms=row.get("price_observed_at_ms"),
            now_ms=now_ms,
            provider=row.get("price_provider"),
            observation_id=row.get("price_observation_id"),
            fresh_ms=DEFAULT_PRICE_FRESH_MS,
        ),
        "market_cap_usd": field_fact(
            value=row.get("market_cap_usd"),
            observed_at_ms=row.get("market_cap_observed_at_ms"),
            now_ms=now_ms,
            provider=row.get("market_cap_provider"),
            observation_id=row.get("market_cap_observation_id"),
            fresh_ms=DEFAULT_MARKET_METADATA_FRESH_MS,
        ),
        "liquidity_usd": field_fact(
            value=row.get("liquidity_usd"),
            observed_at_ms=row.get("liquidity_observed_at_ms"),
            now_ms=now_ms,
            provider=row.get("liquidity_provider"),
            observation_id=row.get("liquidity_observation_id"),
            fresh_ms=DEFAULT_MARKET_METADATA_FRESH_MS,
        ),
        "holders": field_fact(
            value=row.get("holders"),
            observed_at_ms=row.get("holders_observed_at_ms"),
            now_ms=now_ms,
            provider=row.get("holders_provider"),
            observation_id=row.get("holders_observation_id"),
            fresh_ms=DEFAULT_MARKET_METADATA_FRESH_MS,
        ),
        "volume_24h_usd": field_fact(
            value=row.get("volume_24h_usd"),
            observed_at_ms=row.get("volume_24h_observed_at_ms"),
            now_ms=now_ms,
            provider=row.get("volume_24h_provider"),
            observation_id=row.get("volume_24h_observation_id"),
            fresh_ms=DEFAULT_MARKET_METADATA_FRESH_MS,
        ),
        "open_interest_usd": field_fact(
            value=row.get("open_interest_usd"),
            observed_at_ms=row.get("open_interest_observed_at_ms"),
            now_ms=now_ms,
            provider=row.get("open_interest_provider"),
            observation_id=row.get("open_interest_observation_id"),
            fresh_ms=DEFAULT_MARKET_METADATA_FRESH_MS,
        ),
    }
    return {
        "target_type": target_type,
        "target_id": target_id,
        "market_status": aggregate_market_status(target_type=target_type, fields=fields),
        "fields": fields,
    }
