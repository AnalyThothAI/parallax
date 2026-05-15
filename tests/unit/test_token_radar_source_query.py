from __future__ import annotations

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
    assert "price_observations" not in sql
    assert "event_anchor" not in sql
    assert "decision_latest" not in sql
    assert "event_price_capture" in sql
    assert "event_price_tick" in sql
    assert "latest_price" in sql


class _Conn:
    def __init__(self) -> None:
        self.sqls: list[str] = []

    def execute(self, sql, params=None):
        self.sqls.append(str(sql))
        return _Result()


class _Result:
    def fetchall(self):
        return []

    def fetchone(self):
        return {"value": 0}
