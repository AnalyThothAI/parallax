from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

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


def test_search_events_route_hits_allows_zero_route_limit_without_sql() -> None:
    conn = FakeConn(rows=[])

    rows = SearchEventsQuery(conn).route_hits(
        intent=SimpleNamespace(kind="handle", handle="alice", lexical_query=None, normalized_text="alice"),
        target_candidates=[],
        watched_only=False,
        route_limit=0,
        since_ms=1,
    )

    assert rows == []
    assert conn.calls == []


@pytest.mark.parametrize("route_limit", [-1, True, "10"])
def test_search_events_route_hits_rejects_malformed_limit_before_sql(route_limit: object) -> None:
    conn = FakeConn(rows=[])

    with pytest.raises(ValueError, match="search_events_route_limit_required"):
        SearchEventsQuery(conn).route_hits(
            intent=SimpleNamespace(kind="handle", handle="alice", lexical_query=None, normalized_text="alice"),
            target_candidates=[],
            watched_only=False,
            route_limit=route_limit,  # type: ignore[arg-type]
            since_ms=1,
        )

    assert conn.calls == []


def test_search_events_target_hits_page_allows_zero_limit_without_sql() -> None:
    conn = FakeConn(rows=[])

    rows = SearchEventsQuery(conn).target_hits_page(
        [{"target_type": "CexToken", "target_id": "cex_token:BTC", "symbol": "BTC", "status": "resolved"}],
        watched_only=False,
        limit=0,
        after=None,
        since_ms=1,
    )

    assert rows == []
    assert conn.calls == []


@pytest.mark.parametrize("limit", [-1, True, "10"])
def test_search_events_target_hits_page_rejects_malformed_limit_before_sql(limit: object) -> None:
    conn = FakeConn(rows=[])

    with pytest.raises(ValueError, match="search_events_target_page_limit_required"):
        SearchEventsQuery(conn).target_hits_page(
            [{"target_type": "CexToken", "target_id": "cex_token:BTC", "symbol": "BTC", "status": "resolved"}],
            watched_only=False,
            limit=limit,  # type: ignore[arg-type]
            after=None,
            since_ms=1,
        )

    assert conn.calls == []


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
