from __future__ import annotations

from gmgn_twitter_intel.domains.token_intel.queries.token_radar_rank_source_query import (
    TokenRadarRankSourceQuery,
    TokenRadarSourceRequest,
)
from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_rank_source_repository import (
    TokenRadarRankSourceRepository,
)


class FakeConn:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.sql = ""
        self.params = None
        self.execute_count = 0

    def execute(self, sql, params=None):
        self.sql = str(sql)
        self.params = params
        self.execute_count += 1
        return self

    def fetchall(self):
        return self.rows


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
