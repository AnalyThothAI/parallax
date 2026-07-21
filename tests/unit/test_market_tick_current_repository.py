from __future__ import annotations

from typing import Any

import pytest

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.asset_market.repositories.market_tick_current_repository import (
    MarketTickCurrentRepository,
)


def test_get_reads_durable_current_row_by_stable_product_key() -> None:
    conn = _ScriptedConnection([[{"tick_id": "tick-3"}]])

    row = MarketTickCurrentRepository(conn).get(
        target_type="chain_token",
        target_id="solana:abc",
    )

    assert row == {"tick_id": "tick-3"}
    assert "FROM market_tick_current" in conn.sql[-1]
    assert conn.params[-1] == ("chain_token", "solana:abc")


def test_upsert_current_is_monotonic_and_writes_no_duplicate_raw_payload() -> None:
    conn = _ScriptedConnection([[{"changed": True}], []])
    repo = MarketTickCurrentRepository(conn)
    tick = _tick_row(tick_id="tick-1")

    assert repo.upsert_current_from_tick(tick) is True
    assert repo.upsert_current_from_tick(tick) is False

    sql = conn.sql[0]
    assert "INSERT INTO market_tick_current" in sql
    assert "ON CONFLICT(target_type, target_id) DO UPDATE SET" in sql
    assert "EXCLUDED.tick_observed_at_ms,\n              EXCLUDED.updated_at_ms,\n              EXCLUDED.tick_id" in sql
    assert "IS DISTINCT FROM ROW(" in sql
    assert "raw_payload_json" not in sql
    assert "payload_hash" not in sql
    assert conn.params[0]["updated_at_ms"] == tick["received_at_ms"]
    assert conn.params[0]["created_at_ms"] == tick["created_at_ms"]


def test_upsert_current_does_not_accept_runtime_timestamp_override() -> None:
    repo = MarketTickCurrentRepository(_ScriptedConnection([]))

    with pytest.raises(TypeError):
        repo.upsert_current_from_tick(_tick_row(tick_id="tick-1"), now_ms=123)  # type: ignore[call-arg]


def test_upsert_current_returning_changed_requires_cursor_rowcount() -> None:
    conn = _CurrentRowcountConnection(row={"changed": True}, omit_rowcount=True)

    with pytest.raises(TypeError, match="market_tick_current_repository_rowcount_invalid"):
        MarketTickCurrentRepository(conn).upsert_current_from_tick(_tick_row(tick_id="tick-rowcount-missing"))


@pytest.mark.parametrize("rowcount", ["bad", True, -1])
def test_upsert_current_rejects_invalid_cursor_rowcount(rowcount: object) -> None:
    conn = _CurrentRowcountConnection(row={"changed": True}, rowcount=rowcount)

    with pytest.raises(TypeError, match="market_tick_current_repository_rowcount_invalid"):
        MarketTickCurrentRepository(conn).upsert_current_from_tick(_tick_row(tick_id="tick-rowcount-invalid"))


@pytest.mark.parametrize(
    ("rowcount", "row"),
    [
        (0, {"changed": True}),
        (1, None),
        (2, {"changed": True}),
    ],
)
def test_upsert_current_rejects_rowcount_returning_mismatch(
    rowcount: object,
    row: dict[str, Any] | None,
) -> None:
    conn = _CurrentRowcountConnection(row=row, rowcount=rowcount)

    with pytest.raises(TypeError, match="market_tick_current_repository_rowcount_invalid"):
        MarketTickCurrentRepository(conn).upsert_current_from_tick(_tick_row(tick_id="tick-rowcount-mismatch"))


def test_repository_session_exposes_only_surviving_market_current_repository() -> None:
    session = repositories_for_connection(
        _ScriptedConnection([]),
        notification_delivery_running_timeout_ms=300_000,
        notification_delivery_stale_running_terminalization_batch_size=100,
    )

    assert isinstance(session.market_tick_current, MarketTickCurrentRepository)
    assert not hasattr(session, "market_tick_current_dirty_targets")


def _tick_row(*, tick_id: str) -> dict[str, Any]:
    return {
        "target_type": "chain_token",
        "target_id": "solana:abc",
        "observed_at_ms": 1_700_000_000_000,
        "received_at_ms": 1_700_000_000_001,
        "tick_id": tick_id,
        "source_tier": "tier1_ws",
        "source_provider": "okx_dex_ws",
        "chain": "solana",
        "token_address": "abc",
        "exchange": None,
        "instrument": None,
        "pricefeed_id": None,
        "price_usd": "1.23",
        "liquidity_usd": "1000",
        "volume_24h_usd": "2000",
        "open_interest_usd": None,
        "market_cap_usd": "3000",
        "holders": 42,
        "created_at_ms": 1_700_000_000_002,
    }


class _ScriptedConnection:
    def __init__(self, results: list[list[dict[str, Any]] | None]) -> None:
        self.results = list(results)
        self.sql: list[str] = []
        self.params: list[Any] = []
        self.rowcount = 0

    def execute(self, sql: str, params: Any | None = None) -> _ScriptedConnection:
        self.sql.append(str(sql))
        self.params.append(params or {})
        return self

    def fetchone(self) -> dict[str, Any] | None:
        if not self.results:
            self.rowcount = 0
            return None
        result = self.results.pop(0)
        if not result:
            self.rowcount = 0
            return None
        self.rowcount = 1
        return result[0]


class _CurrentRowcountConnection:
    def __init__(
        self,
        *,
        row: dict[str, Any] | None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self.row = row
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount

    def execute(self, sql: str, params: Any | None = None) -> _CurrentRowcountCursor:
        return _CurrentRowcountCursor(row=self.row, rowcount=self.rowcount, omit_rowcount=self.omit_rowcount)


class _CurrentRowcountCursor:
    def __init__(self, *, row: dict[str, Any] | None, rowcount: object, omit_rowcount: bool) -> None:
        self.row = row
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self.row
