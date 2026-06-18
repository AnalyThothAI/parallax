from __future__ import annotations

from decimal import Decimal
from typing import Any

from parallax.domains.asset_market.repositories.token_capture_tier_repository import (
    TokenCaptureTierRepository,
)


def test_token_capture_tier_upsert_returns_false_when_payload_unchanged() -> None:
    conn = _ScriptedConnection([{"changed": True}, None])
    repo = TokenCaptureTierRepository(conn)

    first = repo.upsert_tier(
        target_type="chain_token",
        target_id="sol:abc",
        tier=1,
        reason="ranked",
        score=Decimal("1"),
        updated_at_ms=1_000,
    )
    second = repo.upsert_tier(
        target_type="chain_token",
        target_id="sol:abc",
        tier=1,
        reason="ranked",
        score=Decimal("1"),
        updated_at_ms=2_000,
    )

    sql = conn.sql[-1]
    assert first is True
    assert second is False
    assert "RETURNING true AS changed" in sql
    assert "WHERE token_capture_tier.tier IS DISTINCT FROM EXCLUDED.tier" in sql
    assert "OR token_capture_tier.reason IS DISTINCT FROM EXCLUDED.reason" in sql
    assert "OR token_capture_tier.score IS DISTINCT FROM EXCLUDED.score" in sql
    assert "updated_at_ms IS DISTINCT FROM" not in sql


class _ScriptedConnection:
    def __init__(self, results: list[dict[str, Any] | None]) -> None:
        self.results = list(results)
        self.sql: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.rowcount = 0

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _ScriptedConnection:
        self.sql.append(str(sql))
        self.params.append(params or {})
        self.rowcount = 1 if self.results and self.results[0] is not None else 0
        return self

    def fetchone(self) -> dict[str, Any] | None:
        if not self.results:
            return None
        return self.results.pop(0)
