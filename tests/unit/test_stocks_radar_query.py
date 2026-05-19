from __future__ import annotations

from gmgn_twitter_intel.domains.token_intel._constants import TOKEN_RADAR_RESOLVER_POLICY_VERSION
from gmgn_twitter_intel.domains.token_intel.queries.stocks_radar_query import StocksRadarQuery


def test_stock_rows_materializes_recent_intents_before_resolution_lookup() -> None:
    conn = RecordingConn()

    assert StocksRadarQuery(conn).stock_rows(since_ms=1000, now_ms=2000, scope="all", limit=25) == []

    sql = conn.sql
    assert "WITH recent_intents AS MATERIALIZED" in sql
    assert "FROM events e" in sql
    assert "JOIN token_intents ti ON ti.event_id = e.event_id" in sql
    assert sql.index("WITH recent_intents AS MATERIALIZED") < sql.index("JOIN token_intent_resolutions tir")
    assert conn.params == (1000, 2000, TOKEN_RADAR_RESOLVER_POLICY_VERSION, 25)


class RecordingConn:
    def __init__(self) -> None:
        self.sql = ""
        self.params: tuple[object, ...] = ()

    def execute(self, sql: str, params: tuple[object, ...]) -> RecordingCursor:
        self.sql = sql
        self.params = params
        return RecordingCursor()


class RecordingCursor:
    def fetchall(self) -> list[dict[str, object]]:
        return []
