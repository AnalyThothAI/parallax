from __future__ import annotations

from parallax.domains.token_intel._constants import TOKEN_RADAR_RESOLVER_POLICY_VERSION
from parallax.domains.token_intel.queries.stocks_radar_query import StocksRadarQuery


def test_stock_rows_materializes_recent_intents_before_resolution_lookup() -> None:
    conn = RecordingConn()

    assert StocksRadarQuery(conn).stock_rows(since_ms=1000, now_ms=2000, scope="all", limit=25) == []

    sql = conn.sql
    assert "WITH recent_intents AS MATERIALIZED" in sql
    assert "FROM events e" in sql
    assert "JOIN token_intents ti ON ti.event_id = e.event_id" in sql
    assert sql.index("WITH recent_intents AS MATERIALIZED") < sql.index("JOIN token_intent_resolutions tir")
    assert "ranked AS MATERIALIZED" in sql
    assert sql.index("ranked AS MATERIALIZED") < sql.index("COALESCE(e.text_clean, e.text) AS latest_text")
    assert conn.params == (1000, 2000, TOKEN_RADAR_RESOLVER_POLICY_VERSION, 25, 25)


def test_stock_rows_bounds_source_event_id_aggregation_per_symbol() -> None:
    conn = RecordingConn()

    StocksRadarQuery(conn).stock_rows(since_ms=1000, now_ms=2000, scope="all", limit=25)

    assert "ranked_mentions AS MATERIALIZED" in conn.sql
    assert "row_number() OVER (" in conn.sql
    assert "FILTER (WHERE event_rank <= %s)" in conn.sql
    assert "ARRAY_AGG(event_id ORDER BY received_at_ms DESC, event_id DESC) AS source_event_ids" not in conn.sql


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
