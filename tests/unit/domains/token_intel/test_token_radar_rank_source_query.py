from __future__ import annotations

from gmgn_twitter_intel.domains.token_intel.queries.token_radar_rank_source_query import (
    TokenRadarRankSourceQuery,
    TokenRadarSourceRequest,
)
from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_rank_source_repository import (
    TokenRadarRankSourceRepository,
)


class FakeConn:
    def __init__(self, rows=None, *, rowcount: int = 0):
        self.rows = rows or []
        self.sql = ""
        self.params = None
        self.execute_count = 0
        self.commit_count = 0
        self.rowcount = rowcount

    def execute(self, sql, params=None):
        self.sql = str(sql)
        self.params = params
        self.execute_count += 1
        return self

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def commit(self):
        self.commit_count += 1


def test_rank_source_query_reads_compact_rank_source_events_without_legacy_source_scan():
    conn = FakeConn(rows=[{"request_key": "request-1", "event_id": "event-1"}])

    rows = TokenRadarRankSourceQuery(conn).load_rows_for_requests(
        [
            TokenRadarSourceRequest(
                request_key="request-1",
                target_type_key="Asset",
                identity_id="asset-1",
                window="1h",
                scope="all",
                analysis_since_ms=1,
                score_since_ms=2,
                now_ms=3,
            )
        ]
    )

    assert rows == {"request-1": [{"request_key": "request-1", "event_id": "event-1"}]}
    assert "token_radar_rank_source_events" in conn.sql
    assert "WITH request_targets AS" not in conn.sql
    assert "token_intents" not in conn.sql
    assert "token_intent_resolutions" not in conn.sql
    assert "events.text" not in conn.sql
    assert "events.text_clean" not in conn.sql
    assert "events.reference_json" not in conn.sql
    assert "raw_payload_json" not in conn.sql
    assert "audit_json" not in conn.sql
    assert "source_kind = 'event'" in conn.sql
    assert conn.execute_count == 1


def test_rank_source_query_populates_compact_edges_without_event_text_or_legacy_cte():
    conn = FakeConn(rows=[{"upserted_count": 3, "deleted_count": 1}])

    changed = TokenRadarRankSourceQuery(conn).populate_edges_for_requests(
        [
            TokenRadarSourceRequest(
                request_key="request-1",
                target_type_key="CexToken",
                identity_id="cex_token:BTC",
                window="1h",
                scope="matched",
                analysis_since_ms=1,
                score_since_ms=2,
                now_ms=3,
            )
        ],
        projected_at_ms=4,
        commit=True,
    )

    assert changed == 4
    assert "INSERT INTO token_radar_rank_source_events" in conn.sql
    assert "ON CONFLICT" in conn.sql
    assert "WITH request_targets AS" not in conn.sql
    assert "events.text" not in conn.sql
    assert "events.text_clean" not in conn.sql
    assert "events.reference_json" not in conn.sql
    assert "raw_payload_json" not in conn.sql
    assert "audit_json" not in conn.sql
    assert "price_feeds.provider = 'binance'" in conn.sql
    assert "price_feeds.feed_type = 'cex_swap'" in conn.sql
    assert "price_feeds.quote_symbol = 'USDT'" in conn.sql
    assert conn.commit_count == 1


def test_rank_source_query_dedupes_event_sources_before_upsert():
    conn = FakeConn(rows=[{"upserted_count": 1, "deleted_count": 0}])

    TokenRadarRankSourceQuery(conn).populate_edges_for_requests(
        [
            TokenRadarSourceRequest(
                request_key="request-1",
                target_type_key="Asset",
                identity_id="asset-1",
                window="1h",
                scope="all",
                analysis_since_ms=1,
                score_since_ms=2,
                now_ms=3,
            )
        ],
        projected_at_ms=4,
        commit=False,
    )

    normalized_sql = " ".join(conn.sql.split())
    assert "deduped_source AS" in conn.sql
    assert 'PARTITION BY "window", scope, target_type_key, identity_id, event_id' in conn.sql
    assert "resolution_confidence DESC NULLS LAST" in conn.sql
    assert "CASE WHEN event_price_capture_id IS NOT NULL THEN 0 ELSE 1 END" in conn.sql
    assert "event_price_tick_lag_ms ASC NULLS LAST" in conn.sql
    assert "event_source_choice_rank = 1" in conn.sql
    assert "FROM deduped_source" in conn.sql
    assert normalized_sql.index("deduped_source AS") < normalized_sql.index("ranked_source AS")
    assert normalized_sql.index("FROM deduped_source") < normalized_sql.index("INSERT INTO")


def test_rank_source_query_dedupes_duplicate_populate_requests_to_widest_range():
    conn = FakeConn(rows=[{"upserted_count": 1, "deleted_count": 0}])

    TokenRadarRankSourceQuery(conn).populate_edges_for_requests(
        [
            TokenRadarSourceRequest(
                request_key="narrow",
                target_type_key="Asset",
                identity_id="asset-1",
                window="1h",
                scope="all",
                analysis_since_ms=100,
                score_since_ms=200,
                now_ms=300,
            ),
            TokenRadarSourceRequest(
                request_key="wide",
                target_type_key="Asset",
                identity_id="asset-1",
                window="1h",
                scope="all",
                analysis_since_ms=10,
                score_since_ms=20,
                now_ms=400,
            ),
        ],
        projected_at_ms=4,
        commit=False,
    )

    normalized_sql = " ".join(conn.sql.split())
    assert "raw_requested AS" in conn.sql
    assert 'SELECT DISTINCT ON ("window", scope, target_type_key, identity_id)' in conn.sql
    assert "FROM raw_requested" in conn.sql
    assert "analysis_since_ms ASC" in conn.sql
    assert "score_since_ms ASC" in conn.sql
    assert "now_ms DESC" in conn.sql
    assert normalized_sql.index("raw_requested AS") < normalized_sql.index("requested AS")
    assert normalized_sql.index("requested AS") < normalized_sql.index("source_intents AS")


def test_rank_source_query_deletes_stale_edges_inside_requested_window_only():
    conn = FakeConn(rows=[{"upserted_count": 3, "deleted_count": 1}])

    changed = TokenRadarRankSourceQuery(conn).populate_edges_for_requests(
        [
            TokenRadarSourceRequest(
                request_key="request-1",
                target_type_key="Asset",
                identity_id="asset-1",
                window="1h",
                scope="all",
                analysis_since_ms=1,
                score_since_ms=2,
                now_ms=3,
            )
        ],
        projected_at_ms=4,
        commit=False,
    )

    assert changed == 4
    assert "DELETE FROM token_radar_rank_source_events stale_edges" in conn.sql
    assert "USING requested" in conn.sql
    assert 'stale_edges."window" = requested."window"' in conn.sql
    assert "stale_edges.scope = requested.scope" in conn.sql
    assert "stale_edges.target_type_key = requested.target_type_key" in conn.sql
    assert "stale_edges.identity_id = requested.identity_id" in conn.sql
    assert "stale_edges.event_received_at_ms >= requested.analysis_since_ms" in conn.sql
    assert "stale_edges.event_received_at_ms <= requested.now_ms" in conn.sql
    assert "NOT EXISTS" in conn.sql
    assert "fresh.event_id = stale_edges.source_id" in conn.sql


def test_rank_source_query_prunes_edges_by_projection_window_scope_and_cutoff():
    conn = FakeConn(rowcount=5)

    deleted = TokenRadarRankSourceQuery(conn).prune_edges(
        projection_version="token-radar-v13-social-attention",
        window="5m",
        scope="matched",
        event_received_before_ms=1_777_800_000_000,
        commit=False,
    )

    assert deleted == 5
    assert "DELETE FROM token_radar_rank_source_events" in conn.sql
    assert 'AND "window" = %s' in conn.sql
    assert "AND scope = %s" in conn.sql
    assert "AND event_received_at_ms < %s" in conn.sql
    assert "events " not in conn.sql
    assert "token_intents" not in conn.sql
    assert conn.params == (
        "token-radar-v13-social-attention",
        "5m",
        "matched",
        1_777_800_000_000,
    )
    assert conn.commit_count == 0


def test_rank_source_query_conflict_update_refreshes_consumed_market_columns():
    conn = FakeConn(rows=[{"upserted_count": 1, "deleted_count": 0}])

    TokenRadarRankSourceQuery(conn).populate_edges_for_requests(
        [
            TokenRadarSourceRequest(
                request_key="request-1",
                target_type_key="Asset",
                identity_id="asset-1",
                window="1h",
                scope="all",
                analysis_since_ms=1,
                score_since_ms=2,
                now_ms=3,
            )
        ],
        projected_at_ms=4,
        commit=False,
    )

    assert "latest_price_market_cap_usd = excluded.latest_price_market_cap_usd" in conn.sql
    assert "latest_price_liquidity_usd = excluded.latest_price_liquidity_usd" in conn.sql
    assert "latest_price_volume_24h_usd = excluded.latest_price_volume_24h_usd" in conn.sql
    assert "latest_price_open_interest_usd = excluded.latest_price_open_interest_usd" in conn.sql
    assert "latest_price_holders = excluded.latest_price_holders" in conn.sql
    assert "event_price_market_cap_usd = excluded.event_price_market_cap_usd" in conn.sql
    assert "event_price_liquidity_usd = excluded.event_price_liquidity_usd" in conn.sql
    assert "event_price_volume_24h_usd = excluded.event_price_volume_24h_usd" in conn.sql
    assert "event_price_open_interest_usd = excluded.event_price_open_interest_usd" in conn.sql
    assert "event_price_holders = excluded.event_price_holders" in conn.sql


def test_rank_source_query_uses_source_payload_hash_noop_gate():
    conn = FakeConn(rows=[{"upserted_count": 1, "deleted_count": 0}])

    TokenRadarRankSourceQuery(conn).populate_edges_for_requests(
        [
            TokenRadarSourceRequest(
                request_key="request-1",
                target_type_key="Asset",
                identity_id="asset-1",
                window="1h",
                scope="all",
                analysis_since_ms=1,
                score_since_ms=2,
                now_ms=3,
            )
        ],
        projected_at_ms=4,
        commit=False,
    )

    normalized_sql = " ".join(conn.sql.split())
    assert "source_payload_hash" in conn.sql
    assert "sha256(" in conn.sql
    assert "convert_to(" in conn.sql
    assert "source_payload_hash = excluded.source_payload_hash" in conn.sql
    assert (
        "WHERE token_radar_rank_source_events.source_payload_hash IS DISTINCT FROM "
        "excluded.source_payload_hash"
    ) in normalized_sql
    assert "projected_at_ms = excluded.projected_at_ms" in conn.sql


def test_rank_source_query_groups_rows_by_request_and_chunks():
    conn = FakeConn(
        rows=[
            {"request_key": "request-1", "event_id": "event-1"},
            {"request_key": "request-2", "event_id": "event-2"},
        ]
    )
    requests = [
        TokenRadarSourceRequest(
            request_key=f"request-{index}",
            target_type_key="Asset",
            identity_id=f"asset-{index}",
            window="1h",
            scope="all",
            analysis_since_ms=1,
            score_since_ms=2,
            now_ms=3,
        )
        for index in (1, 2)
    ]

    rows = TokenRadarRankSourceQuery(conn, chunk_size=1).load_rows_for_requests(requests)

    assert list(rows) == ["request-1", "request-2"]
    assert conn.execute_count == 2


def test_rank_source_repository_uses_compact_query():
    conn = FakeConn(rows=[{"request_key": "request-1", "event_id": "event-1"}])

    rows = TokenRadarRankSourceRepository(conn).load_rows_for_requests(
        [
            TokenRadarSourceRequest(
                request_key="request-1",
                target_type_key="Asset",
                identity_id="asset-1",
                window="1h",
                scope="all",
                analysis_since_ms=1,
                score_since_ms=2,
                now_ms=3,
            )
        ]
    )

    assert rows["request-1"][0]["event_id"] == "event-1"
    assert "token_radar_rank_source_events" in conn.sql


def test_rank_source_repository_populates_compact_edges():
    conn = FakeConn(rows=[{"upserted_count": 1, "deleted_count": 0}])

    changed = TokenRadarRankSourceRepository(conn).populate_edges_for_requests(
        [
            TokenRadarSourceRequest(
                request_key="request-1",
                target_type_key="Asset",
                identity_id="asset-1",
                window="1h",
                scope="all",
                analysis_since_ms=1,
                score_since_ms=2,
                now_ms=3,
            )
        ],
        projected_at_ms=4,
        commit=False,
    )

    assert changed == 1
    assert "INSERT INTO token_radar_rank_source_events" in conn.sql
    assert conn.commit_count == 0


def test_rank_source_repository_prunes_edges_through_compact_query():
    conn = FakeConn(rowcount=4)

    deleted = TokenRadarRankSourceRepository(conn).prune_edges(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        event_received_before_ms=1_777_000_000_000,
        commit=False,
    )

    assert deleted == 4
    assert "DELETE FROM token_radar_rank_source_events" in conn.sql
    assert conn.params == (
        "token-radar-v13-social-attention",
        "1h",
        "all",
        1_777_000_000_000,
    )
