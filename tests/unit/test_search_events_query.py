from __future__ import annotations

from typing import Any

from parallax.domains.token_intel.queries.search_events_query import SearchEventsQuery


def test_resolve_symbols_batches_symbol_targets_with_keyset_sql() -> None:
    conn = FakeConn(
        rows=[
            {
                "target_type": "CexToken",
                "target_id": "cex_token:BTC",
                "symbol": "BTC",
                "chain_id": None,
                "address": None,
                "status": "resolved",
                "source": "cex_token",
                "reason": "CONFIRMED_CEX_TOKEN",
            }
        ]
    )

    result = SearchEventsQuery(conn).resolve_symbols(["BTC", "ETH", "BTC"])

    assert result[0]["target_id"] == "cex_token:BTC"
    assert len(conn.calls) == 1
    sql, params = conn.calls[0]
    assert "WITH input_symbols AS" in sql
    assert "unnest(%s::text[]) WITH ORDINALITY" in sql
    assert "distinct_symbols AS" in sql
    assert "PARTITION BY distinct_symbols.symbol" in sql
    assert params == (["BTC", "ETH", "BTC"],)


class FakeConn:
    def __init__(self, *, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...]) -> FakeCursor:
        self.calls.append((sql, params))
        return FakeCursor(self.rows)


class FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows
