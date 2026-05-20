from __future__ import annotations

from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_RESOLVER_POLICY_VERSION
from gmgn_twitter_intel.domains.token_intel.queries.token_radar_source_query import TokenRadarSourceQuery


def test_token_radar_source_query_excludes_non_crypto_market_instruments():
    conn = _Conn()
    query = TokenRadarSourceQuery(conn)

    query.source_rows(since_ms=1, scope="all", now_ms=2)
    query.source_count(since_ms=1, scope="all")

    joined_sql = "\n".join(conn.sqls)
    assert "COALESCE(token_intent_resolutions.target_type, 'Asset') IN ('Asset', 'CexToken')" in joined_sql


def test_token_radar_source_query_uses_enriched_events_and_market_ticks_only():
    conn = _Conn()
    query = TokenRadarSourceQuery(conn)

    query.source_rows(since_ms=1, scope="all", now_ms=2)

    sql = conn.sqls[-1]
    assert "enriched_events" in sql
    assert "market_ticks" in sql
    assert _legacy_price_table() not in sql
    assert _public_market_key("event") not in sql
    assert _public_market_key("decision") not in sql
    assert "event_price_capture" in sql
    assert "event_price_tick" in sql
    assert "latest_price" in sql
    assert "event_price_capture.tick_lag_ms AS event_price_tick_lag_ms" in sql
    assert "event_price_tick.holders AS event_price_holders" in sql
    assert "latest_price_tick.holders AS latest_price_holders" in sql


def test_token_radar_source_query_starts_from_intents_and_gates_market_joins_to_score_window():
    conn = _Conn()
    query = TokenRadarSourceQuery(conn)

    query.source_rows(since_ms=1, score_since_ms=2, scope="all", now_ms=3)

    sql = conn.sqls[-1]
    assert "WITH source_intents AS MATERIALIZED" in sql
    assert "WITH window_events AS MATERIALIZED" not in sql
    assert "FROM token_intents" in sql
    assert "JOIN events ON events.event_id = token_intents.event_id" in sql
    assert "source_intents.received_at_ms >= %s" in sql
    params = tuple(conn.params[-1])
    assert params[:3] == (1, 3, TOKEN_RADAR_RESOLVER_POLICY_VERSION)
    assert params.count(2) >= 4
    assert params.count(3) == 2


class _Conn:
    def __init__(self) -> None:
        self.sqls: list[str] = []
        self.params: list[object] = []

    def execute(self, sql, params=None):
        self.sqls.append(str(sql))
        self.params.append(params)
        return _Result()


class _Result:
    def fetchall(self):
        return []

    def fetchone(self):
        return {"value": 0}


def _legacy_price_table() -> str:
    return "_".join(("price", "observations"))


def _public_market_key(prefix: str) -> str:
    suffix = "anchor" if prefix == "event" else "latest"
    return "_".join((prefix, suffix))
