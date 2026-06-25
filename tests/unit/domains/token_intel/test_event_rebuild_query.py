from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.token_intel.queries.event_rebuild_query import EventRebuildQuery


def test_event_rebuild_query_recent_events_allows_zero_limit_with_explicit_sql_limit() -> None:
    conn = FakeConn(rows=[])

    rows = EventRebuildQuery(conn).recent_events(since_ms=1_700_000_000_000, limit=0)

    assert rows == []
    assert "LIMIT %s" in conn.sql
    assert conn.params == (1_700_000_000_000, 0)


@pytest.mark.parametrize("limit", [-1, True, "10"])
def test_event_rebuild_query_recent_events_rejects_malformed_limit_before_sql(limit: object) -> None:
    conn = FakeConn(rows=[])

    with pytest.raises(ValueError, match="event_rebuild_recent_events_limit_required"):
        EventRebuildQuery(conn).recent_events(
            since_ms=1_700_000_000_000,
            limit=limit,  # type: ignore[arg-type]
        )

    assert conn.sqls == []


class FakeConn:
    def __init__(self, *, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.sql = ""
        self.sqls: list[str] = []
        self.params: Any = None

    def execute(self, sql: str, params: Any = None) -> FakeConn:
        self.sql = str(sql)
        self.sqls.append(self.sql)
        self.params = params
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows
