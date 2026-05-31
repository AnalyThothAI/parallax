from __future__ import annotations

from typing import Any

from parallax.domains.asset_market.repositories.enriched_event_repository import (
    EnrichedEventRepository,
)
from parallax.domains.asset_market.types import EnrichedEventCapture


def test_insert_enriched_event_is_append_only() -> None:
    conn = _ScriptedConnection([])
    capture = _capture()

    EnrichedEventRepository(conn).insert_capture(capture)

    sql = "\n".join(conn.sql)
    assert "INSERT INTO enriched_events" in sql
    assert "ON CONFLICT(event_id, intent_id) DO NOTHING" in sql
    assert "UPDATE enriched_events" not in sql
    assert conn.commits == 0
    assert conn.params[-1]["event_id"] == "event-1"
    assert conn.params[-1]["tick_observed_at_ms"] == 1_700_000_000_100
    assert conn.params[-1]["tick_id"] == "tick-1"
    assert "tick_observed_at_ms" in sql


def test_list_by_event_id_joins_market_tick_and_orders_by_intent() -> None:
    conn = _ScriptedConnection([[{"event_id": "event-1", "intent_id": "intent-1"}]])

    rows = EnrichedEventRepository(conn).list_by_event_id("event-1")

    assert rows == [{"event_id": "event-1", "intent_id": "intent-1"}]
    sql = conn.sql[-1]
    assert "FROM enriched_events ee" in sql
    assert "mt.observed_at_ms = ee.tick_observed_at_ms" in sql
    assert "mt.tick_id = ee.tick_id" in sql
    assert "ee.event_id = %(event_id)s" in sql
    assert "ORDER BY ee.intent_id ASC" in sql
    assert conn.params[-1] == {"event_id": "event-1"}


def test_by_event_intent_selects_exact_joined_row() -> None:
    conn = _ScriptedConnection([{"event_id": "event-1", "intent_id": "intent-1"}])

    row = EnrichedEventRepository(conn).by_event_intent("event-1", "intent-1")

    assert row == {"event_id": "event-1", "intent_id": "intent-1"}
    sql = conn.sql[-1]
    assert "ee.event_id = %(event_id)s" in sql
    assert "ee.intent_id = %(intent_id)s" in sql
    assert "mt.observed_at_ms = ee.tick_observed_at_ms" in sql
    assert "mt.tick_id = ee.tick_id" in sql
    assert conn.params[-1] == {"event_id": "event-1", "intent_id": "intent-1"}


def test_latest_for_target_orders_by_event_time_and_keys() -> None:
    conn = _ScriptedConnection([[{"event_id": "event-2", "intent_id": "intent-2"}]])

    rows = EnrichedEventRepository(conn).latest_for_target(
        target_type="chain_token",
        target_id="solana:abc",
        limit=25,
    )

    assert rows == [{"event_id": "event-2", "intent_id": "intent-2"}]
    sql = conn.sql[-1]
    assert "ee.target_type = %(target_type)s" in sql
    assert "ee.target_id = %(target_id)s" in sql
    assert "ORDER BY ee.t_event_ms DESC, ee.event_id DESC, ee.intent_id DESC" in sql
    assert "LIMIT %(limit)s" in sql
    assert conn.params[-1] == {"target_type": "chain_token", "target_id": "solana:abc", "limit": 25}


def test_attach_backfill_capture_writes_composite_tick_key() -> None:
    conn = _ScriptedConnection([])
    capture = _capture()

    EnrichedEventRepository(conn).attach_backfill_capture(capture)

    sql = conn.sql[-1]
    assert "SET tick_observed_at_ms = %(tick_observed_at_ms)s" in sql
    assert "tick_id IS NULL" in sql
    assert "tick_observed_at_ms IS NULL" in sql
    assert conn.params[-1]["tick_observed_at_ms"] == 1_700_000_000_100


class _ScriptedConnection:
    def __init__(self, results: list[dict[str, Any] | list[dict[str, Any]] | None]) -> None:
        self.results = list(results)
        self.sql: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.commits = 0

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _ScriptedConnection:
        self.sql.append(str(sql))
        self.params.append(params or {})
        return self

    def fetchone(self) -> dict[str, Any] | None:
        if not self.results:
            return None
        result = self.results.pop(0)
        assert not isinstance(result, list)
        return result

    def fetchall(self) -> list[dict[str, Any]]:
        if not self.results:
            return []
        result = self.results.pop(0)
        assert isinstance(result, list)
        return result

    def commit(self) -> None:
        self.commits += 1


def _capture() -> EnrichedEventCapture:
    return EnrichedEventCapture(
        event_id="event-1",
        intent_id="intent-1",
        resolution_id="resolution-1",
        target_type="chain_token",
        target_id="solana:abc",
        t_event_ms=1_700_000_000_000,
        tick_observed_at_ms=1_700_000_000_100,
        tick_id="tick-1",
        tick_lag_ms=100,
        capture_method="tier1_ws",
        capture_reason="fresh_tick",
        created_at_ms=1_700_000_000_200,
    )
