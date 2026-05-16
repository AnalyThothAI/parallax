from __future__ import annotations

from decimal import Decimal
from typing import Any

from gmgn_twitter_intel.domains.asset_market.repositories.token_capture_tier_repository import (
    TokenCaptureTierRepository,
)


def test_upsert_tier_updates_only_token_capture_tier_projection() -> None:
    conn = _ScriptedConnection([])

    TokenCaptureTierRepository(conn).upsert_tier(
        target_type="chain_token",
        target_id="solana:abc",
        tier=1,
        reason="ws_subscribed",
        score=Decimal("9.5"),
        updated_at_ms=1_700_000_000_000,
    )

    sql = "\n".join(conn.sql)
    assert "INSERT INTO token_capture_tier" in sql
    assert "ON CONFLICT(target_type, target_id) DO UPDATE SET" in sql
    assert "UPDATE market_ticks" not in sql
    assert "UPDATE enriched_events" not in sql
    assert conn.commits == 0
    assert conn.params[-1]["tier"] == 1
    assert conn.params[-1]["score"] == Decimal("9.5")


def test_list_by_tier_prioritizes_missing_or_incomplete_market_ticks() -> None:
    conn = _ScriptedConnection([[{"target_id": "solana:abc"}]])

    rows = TokenCaptureTierRepository(conn).list_by_tier(1, limit=50)

    assert rows == [{"target_id": "solana:abc"}]
    sql = conn.sql[-1]
    assert "FROM token_capture_tier" in sql
    assert "LEFT JOIN LATERAL" in sql
    assert "latest_tick.tick_id IS NULL" in sql
    assert "latest_tick.market_cap_usd IS NULL" in sql
    assert "latest_tick.received_at_ms ASC NULLS FIRST" in sql
    assert "tier = %(tier)s" in sql
    assert "score DESC" in sql
    assert "LIMIT %(limit)s" in sql
    assert conn.params[-1] == {"tier": 1, "limit": 50}


def test_get_selects_exact_target() -> None:
    conn = _ScriptedConnection([{"target_type": "chain_token", "target_id": "solana:abc"}])

    row = TokenCaptureTierRepository(conn).get("chain_token", "solana:abc")

    assert row == {"target_type": "chain_token", "target_id": "solana:abc"}
    sql = conn.sql[-1]
    assert "target_type = %(target_type)s" in sql
    assert "target_id = %(target_id)s" in sql
    assert conn.params[-1] == {"target_type": "chain_token", "target_id": "solana:abc"}


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
