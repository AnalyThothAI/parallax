from __future__ import annotations

from typing import Any

import pytest

from gmgn_twitter_intel.domains.asset_market.repositories.price_observation_repository import (
    PriceObservationRepository,
)
from gmgn_twitter_intel.domains.asset_market.types import MarketObservation, MarketTargetRef


def test_event_anchor_insert_updates_existing_resolution_without_baseline_write() -> None:
    conn = _ScriptedConnection(
        [
            {"observation_id": "existing-observation"},
            {"observation_id": "existing-observation"},
        ]
    )
    observation = _observation(source="event_anchor", price_usd=1.1)

    observation_id = PriceObservationRepository(conn).insert_market_observation(
        observation,
        observation_kind="event_anchor",
        source_event_id="event-1",
        source_intent_id="intent-1",
        source_resolution_id="resolution-1",
        event_received_at_ms=1_700_000_000_000,
    )

    sql = "\n".join(conn.sql)
    assert observation_id == "existing-observation"
    assert "UPDATE price_observations" in sql
    assert "ON CONFLICT" not in sql
    assert "token_market_price_baselines" not in sql
    assert conn.commits == 1


def test_decision_latest_insert_does_not_require_source_resolution() -> None:
    conn = _ScriptedConnection([{"observation_id": "live-observation"}])
    observation = _observation(source="decision_latest", price_usd=1.2)

    observation_id = PriceObservationRepository(conn).insert_market_observation(
        observation,
        observation_kind="decision_latest",
    )

    assert observation_id == "live-observation"
    assert any("INSERT INTO price_observations" in sql for sql in conn.sql)


def test_event_anchor_requires_source_context() -> None:
    conn = _ScriptedConnection([])

    with pytest.raises(ValueError, match="event_anchor observations require"):
        PriceObservationRepository(conn).insert_market_observation(
            _observation(source="event_anchor", price_usd=1.0),
            observation_kind="event_anchor",
        )

    assert conn.sql == []


def test_latest_for_target_returns_market_observation_value_type() -> None:
    conn = _ScriptedConnection(
        [
            {
                "subject_type": "Asset",
                "subject_id": "asset-1",
                "observed_at_ms": 1_700_000_010_000,
                "created_at_ms": 1_700_000_010_100,
                "observation_kind": "decision_latest",
                "provider": "okx_dex_ws",
                "pricefeed_id": "pf-1",
                "price_usd": 1.2,
                "price_quote": None,
                "quote_symbol": "USD",
                "price_basis": "last",
                "market_cap_usd": None,
                "liquidity_usd": 5_000.0,
                "holders": 20,
                "volume_24h_usd": None,
                "open_interest_usd": None,
                "raw_payload_json": {"raw_payload_hash": "abc"},
            }
        ]
    )

    observation = PriceObservationRepository(conn).latest_for_target(
        target_type="Asset",
        target_id="asset-1",
        now_ms=1_700_000_020_000,
        max_age_ms=60_000,
    )

    assert observation is not None
    assert observation.target == MarketTargetRef("Asset", "asset-1")
    assert observation.source == "decision_latest"
    assert observation.price_usd == 1.2
    assert observation.raw_payload_hash == "abc"


class _ScriptedConnection:
    def __init__(self, rows: list[dict[str, Any] | None]) -> None:
        self.rows = list(rows)
        self.sql: list[str] = []
        self.params: list[Any] = []
        self.commits = 0

    def execute(self, sql: str, params: Any = None) -> _ScriptedConnection:
        self.sql.append(str(sql))
        self.params.append(params)
        return self

    def fetchone(self) -> dict[str, Any] | None:
        if not self.rows:
            return None
        return self.rows.pop(0)

    def commit(self) -> None:
        self.commits += 1


def _observation(*, source: str, price_usd: float | None) -> MarketObservation:
    return MarketObservation(
        target=MarketTargetRef(target_type="Asset", target_id="asset-1"),
        observed_at_ms=1_700_000_001_000,
        received_at_ms=1_700_000_001_100,
        source=source,
        provider="okx",
        pricefeed_id=None,
        price_usd=price_usd,
        price_quote=None,
        quote_symbol="USD",
        price_basis="last",
        market_cap_usd=None,
        liquidity_usd=None,
        holders=None,
        volume_24h_usd=None,
        open_interest_usd=None,
        raw_payload_hash=None,
    )
