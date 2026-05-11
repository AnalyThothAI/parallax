from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.asset_market.market_field_facts import (
    DEFAULT_MARKET_METADATA_FRESH_MS,
    DEFAULT_PRICE_FRESH_MS,
    aggregate_market_status,
    field_fact,
)

_PRICE_FIELDS = frozenset({"price_usd", "price_quote", "quote_symbol", "price_basis"})
_MARKET_FIELD_KEYS = (
    "price_usd",
    "price_quote",
    "quote_symbol",
    "price_basis",
    "market_cap_usd",
    "liquidity_usd",
    "holders",
    "volume_24h_usd",
    "open_interest_usd",
)


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
                 latest_facts AS (
                   SELECT DISTINCT ON (
                     facts.subject_type, facts.subject_id, facts.field_key
                   )
                     facts.subject_type,
                     facts.subject_id,
                     facts.field_key,
                     facts.value_json,
                     facts.observed_at_ms,
                     facts.provider,
                     facts.source_observation_id
                   FROM current_market_field_facts facts
                   JOIN requested
                     ON requested.subject_type = facts.subject_type
                    AND requested.subject_id = facts.subject_id
                   WHERE facts.observed_at_ms <= %s
                   ORDER BY
                     facts.subject_type,
                     facts.subject_id,
                     facts.field_key,
                     facts.observed_at_ms DESC,
                     facts.source_observation_id DESC
                 )
            SELECT *
            FROM latest_facts
            ORDER BY subject_type, subject_id, field_key
            """,
            params,
        ).fetchall()
        facts_by_subject: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
        for row in rows:
            key = _key(row)
            field_key = str(row["field_key"])
            facts_by_subject.setdefault(key, {})[field_key] = field_fact(
                value=row.get("value_json"),
                observed_at_ms=row.get("observed_at_ms"),
                now_ms=now_ms,
                provider=row.get("provider"),
                observation_id=row.get("source_observation_id"),
                fresh_ms=_fresh_ms(field_key),
            )
        return {
            key: _snapshot(subject_type=key[0], subject_id=key[1], facts=facts)
            for key, facts in facts_by_subject.items()
        }


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


def _snapshot(*, subject_type: str, subject_id: str, facts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    fields = {
        key: facts.get(
            key,
            field_fact(
                value=None,
                observed_at_ms=None,
                now_ms=0,
                provider=None,
                observation_id=None,
                fresh_ms=_fresh_ms(key),
            ),
        )
        for key in _MARKET_FIELD_KEYS
    }
    return {
        "target_type": subject_type,
        "target_id": subject_id,
        "market_status": aggregate_market_status(target_type=subject_type, fields=fields),
        "fields": fields,
    }


def _fresh_ms(field_key: str) -> int:
    return DEFAULT_PRICE_FRESH_MS if field_key in _PRICE_FIELDS else DEFAULT_MARKET_METADATA_FRESH_MS
