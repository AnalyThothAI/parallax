from __future__ import annotations

import pytest

from parallax.domains.token_intel._constants import TOKEN_RADAR_RESOLVER_POLICY_VERSION
from parallax.domains.token_intel.queries.token_radar_rank_source_query import (
    TokenRadarFeatureSourceRequest,
    TokenRadarRankSourceQuery,
    TokenRadarSourceEdgeRequest,
)
from parallax.domains.token_intel.repositories.token_radar_rank_source_repository import (
    TokenRadarRankSourceRepository,
)


class FakeConn:
    def __init__(self, rows=None, *, rowcount: object = 0, omit_rowcount: bool = False):
        self.rows = rows or []
        self.sql = ""
        self.sqls = []
        self.params = None
        self.execute_count = 0
        self.commit_count = 0
        if not omit_rowcount:
            self.rowcount = rowcount
        self.transaction_enter_count = 0
        self.transaction_exit_count = 0
        self.transaction_depth = 0
        self.execute_depths = []

    def execute(self, sql, params=None):
        self.sql = str(sql)
        self.sqls.append(self.sql)
        self.params = params
        self.execute_count += 1
        self.execute_depths.append(self.transaction_depth)
        return self

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def commit(self):
        raise AssertionError("manual commit should not be used")

    def transaction(self):
        conn = self

        class Transaction:
            def __enter__(self):
                conn.transaction_enter_count += 1
                conn.transaction_depth += 1
                return self

            def __exit__(self, exc_type, exc, tb):
                conn.transaction_depth -= 1
                conn.transaction_exit_count += 1
                return False

        return Transaction()


class NoTransactionConn(FakeConn):
    def __init__(self, rows=None, *, rowcount: object = 0):
        super().__init__(rows=rows, rowcount=rowcount)
        self.transaction = None


def _feature_request(request_key: str = "request-1") -> TokenRadarFeatureSourceRequest:
    return TokenRadarFeatureSourceRequest(
        request_key=request_key,
        target_type_key="Asset",
        identity_id="asset-1",
        window="1h",
        scope="all",
        venue="bsc",
        analysis_since_ms=1,
        score_since_ms=2,
        now_ms=3,
    )


def test_rank_source_query_loads_feature_rows_from_narrow_source_edges() -> None:
    conn = FakeConn(rows=[{"request_key": "request-1", "event_id": "event-1"}])

    rows = TokenRadarRankSourceQuery(conn).load_rows_for_requests([_feature_request()])

    assert rows == {"request-1": [{"request_key": "request-1", "event_id": "event-1"}]}
    assert "token_radar_rank_source_events" in conn.sql
    assert "jsonb_to_recordset" in conn.sql
    assert "venue text" in conn.sql
    assert "rank_source.event_received_at_ms >= requested.analysis_since_ms" in conn.sql
    assert "source_kind = 'event'" in conn.sql


def test_rank_source_query_populates_windowless_event_edges() -> None:
    conn = FakeConn(rows=[{"upserted_count": 3, "deleted_count": 1}])

    changed = TokenRadarRankSourceRepository(conn).populate_edges_for_event_ids(
        [TokenRadarSourceEdgeRequest(source_event_id="event-1")],
        projected_at_ms=4,
        commit=True,
    )

    assert changed == 4
    assert "requested_event_ids" in conn.sql
    assert "SELECT DISTINCT ON (projection_version, target_type_key, identity_id, source_kind, source_id)" in conn.sql
    assert "INSERT INTO token_radar_rank_source_events" in conn.sql
    assert "ON CONFLICT(projection_version, target_type_key, identity_id, source_kind, source_id)" in conn.sql
    assert '"window"' not in conn.sql
    assert "source_payload_json" not in conn.sql
    assert "account_profiles" not in conn.sql
    assert "market_tick_current" not in conn.sql
    assert "row_number() OVER" not in conn.sql
    assert "sha256(" not in conn.sql
    assert conn.commit_count == 0
    assert conn.transaction_enter_count == 1
    assert conn.transaction_exit_count == 1
    assert conn.execute_depths == [1]


def test_rank_source_query_deletes_stale_edges_for_requested_event_ids_only() -> None:
    conn = FakeConn(rows=[{"upserted_count": 0, "deleted_count": 1}])

    changed = TokenRadarRankSourceQuery(conn).populate_edges_for_event_ids(
        ["event-1"],
        projected_at_ms=4,
    )

    assert changed == 1
    assert "DELETE FROM token_radar_rank_source_events stale_edges" in conn.sql
    assert "USING requested_event_ids requested" in conn.sql
    assert "stale_edges.source_id = requested.source_event_id" in conn.sql
    assert "NOT EXISTS" in conn.sql
    assert "fresh.source_id = stale_edges.source_id" in conn.sql


@pytest.mark.parametrize(
    ("rows", "error"),
    [
        pytest.param([], "token_radar_rank_source_write_count_required:result", id="missing-row"),
        pytest.param(
            [{"deleted_count": 0}],
            "token_radar_rank_source_write_count_required:upserted_count",
            id="missing-upserted",
        ),
        pytest.param(
            [{"upserted_count": 0}],
            "token_radar_rank_source_write_count_required:deleted_count",
            id="missing-deleted",
        ),
        pytest.param(
            [{"upserted_count": "not-a-count", "deleted_count": 0}],
            "token_radar_rank_source_write_count_invalid:upserted_count",
            id="invalid-upserted",
        ),
        pytest.param(
            [{"upserted_count": 0, "deleted_count": -1}],
            "token_radar_rank_source_write_count_invalid:deleted_count",
            id="negative-deleted",
        ),
        pytest.param(
            [{"upserted_count": True, "deleted_count": 0}],
            "token_radar_rank_source_write_count_invalid:upserted_count",
            id="bool-upserted",
        ),
    ],
)
def test_rank_source_query_populate_edges_for_events_requires_sql_count_evidence(
    rows: list[dict[str, object]],
    error: str,
) -> None:
    conn = FakeConn(rows=rows)

    with pytest.raises(TypeError, match=error):
        TokenRadarRankSourceQuery(conn).populate_edges_for_event_ids(
            ["event-1"],
            projected_at_ms=4,
        )


def test_rank_source_query_populates_edges_for_repair_targets() -> None:
    conn = FakeConn(rows=[{"upserted_count": 2, "deleted_count": 1}])

    changed = TokenRadarRankSourceQuery(conn).populate_edges_for_targets(
        [{"target_type_key": "Asset", "identity_id": "asset-1"}],
        projected_at_ms=4,
        analysis_since_ms=2,
    )

    assert changed == 3
    assert "requested_targets AS" in conn.sql
    assert "token_intent_resolutions.target_type = requested_targets.target_type_key" in conn.sql
    assert "token_intent_resolutions.target_id = requested_targets.identity_id" in conn.sql
    assert "DELETE FROM token_radar_rank_source_events stale_edges" in conn.sql
    assert "USING requested_targets requested" in conn.sql
    assert "stale_edges.target_type_key = requested.target_type_key" in conn.sql
    assert "stale_edges.identity_id = requested.identity_id" in conn.sql
    assert "events.received_at_ms >= %s" in conn.sql
    assert "stale_edges.event_received_at_ms >= %s" in conn.sql
    assert '"window"' not in conn.sql
    assert conn.params[1:] == (
        "token-radar-v13-social-attention",
        4,
        TOKEN_RADAR_RESOLVER_POLICY_VERSION,
        2,
        "token-radar-v13-social-attention",
        2,
    )
    assert conn.commit_count == 0


@pytest.mark.parametrize(
    ("rows", "error"),
    [
        pytest.param([], "token_radar_rank_source_write_count_required:result", id="missing-row"),
        pytest.param(
            [{"deleted_count": 0}],
            "token_radar_rank_source_write_count_required:upserted_count",
            id="missing-upserted",
        ),
        pytest.param(
            [{"upserted_count": 0}],
            "token_radar_rank_source_write_count_required:deleted_count",
            id="missing-deleted",
        ),
        pytest.param(
            [{"upserted_count": "not-a-count", "deleted_count": 0}],
            "token_radar_rank_source_write_count_invalid:upserted_count",
            id="invalid-upserted",
        ),
        pytest.param(
            [{"upserted_count": 0, "deleted_count": -1}],
            "token_radar_rank_source_write_count_invalid:deleted_count",
            id="negative-deleted",
        ),
        pytest.param(
            [{"upserted_count": True, "deleted_count": 0}],
            "token_radar_rank_source_write_count_invalid:upserted_count",
            id="bool-upserted",
        ),
    ],
)
def test_rank_source_query_populate_edges_for_targets_requires_sql_count_evidence(
    rows: list[dict[str, object]],
    error: str,
) -> None:
    conn = FakeConn(rows=rows)

    with pytest.raises(TypeError, match=error):
        TokenRadarRankSourceQuery(conn).populate_edges_for_targets(
            [{"target_type_key": "Asset", "identity_id": "asset-1"}],
            projected_at_ms=4,
            analysis_since_ms=2,
        )


@pytest.mark.parametrize(
    ("field", "aliases"),
    [
        pytest.param("target_type_key", {"target_type": "Asset"}, id="target-type-key"),
        pytest.param("identity_id", {"target_id": "asset-1"}, id="identity-id"),
    ],
)
def test_rank_source_query_populate_edges_for_targets_requires_formal_identity_without_alias_fallback(
    field: str,
    aliases: dict[str, str],
) -> None:
    conn = FakeConn(rows=[{"upserted_count": 2, "deleted_count": 1}])
    target = {"target_type_key": "Asset", "identity_id": "asset-1"}
    target.pop(field)
    target.update(aliases)

    with pytest.raises(ValueError, match=f"token_radar_rank_source_target_identity_required:{field}"):
        TokenRadarRankSourceQuery(conn).populate_edges_for_targets(
            [target],
            projected_at_ms=4,
            analysis_since_ms=2,
        )

    assert conn.sqls == []


@pytest.mark.parametrize(
    ("field", "aliases"),
    [
        pytest.param("target_type_key", {"target_type": "Asset"}, id="target-type-key"),
        pytest.param("identity_id", {"target_id": "asset-1"}, id="identity-id"),
    ],
)
def test_rank_source_query_latest_market_context_requires_formal_identity_without_alias_fallback(
    field: str,
    aliases: dict[str, str],
) -> None:
    conn = FakeConn(rows=[{"target_type_key": "Asset", "identity_id": "asset-1"}])
    target = {"target_type_key": "Asset", "identity_id": "asset-1"}
    target.pop(field)
    target.update(aliases)

    with pytest.raises(ValueError, match=f"token_radar_rank_source_target_identity_required:{field}"):
        TokenRadarRankSourceQuery(conn).latest_market_context_for_targets([target])

    assert conn.sqls == []


def test_rank_source_query_loads_existing_and_current_affected_targets_for_events() -> None:
    conn = FakeConn(
        rows=[
            {"target_type_key": "Asset", "identity_id": "old-asset"},
            {"target_type_key": "Asset", "identity_id": "new-asset"},
        ]
    )

    targets = TokenRadarRankSourceQuery(conn).affected_targets_for_event_ids(["event-1"])

    assert targets == [
        {"target_type_key": "Asset", "identity_id": "old-asset"},
        {"target_type_key": "Asset", "identity_id": "new-asset"},
    ]
    assert "existing_edges AS" in conn.sql
    assert "current_edges AS" in conn.sql
    assert "UNION" in conn.sql


def test_rank_source_query_affected_targets_requires_formal_output_identity_without_silent_skip() -> None:
    conn = FakeConn(rows=[{"target_type_key": "Asset"}])

    with pytest.raises(ValueError, match="token_radar_rank_source_target_identity_required:identity_id"):
        TokenRadarRankSourceQuery(conn).affected_targets_for_event_ids(["event-1"])


def test_rank_source_query_prunes_edges_by_projection_and_cutoff() -> None:
    conn = FakeConn(rowcount=5)

    deleted = TokenRadarRankSourceQuery(conn).prune_edges(
        projection_version="token-radar-v13-social-attention",
        event_received_before_ms=1_777_800_000_000,
        limit=11,
    )

    assert deleted == 5
    assert "DELETE FROM token_radar_rank_source_events" in conn.sql
    assert 'AND "window" = %s' not in conn.sql
    assert "AND scope = %s" not in conn.sql
    assert "AND event_received_at_ms < %s" in conn.sql
    assert "LIMIT %s" in conn.sql
    assert conn.params == ("token-radar-v13-social-attention", 1_777_800_000_000, 11)
    assert conn.commit_count == 0


def test_rank_source_query_prune_edges_requires_cursor_rowcount() -> None:
    conn = FakeConn(omit_rowcount=True)

    with pytest.raises(TypeError, match="token_radar_rank_source_rowcount_required"):
        TokenRadarRankSourceQuery(conn).prune_edges(
            projection_version="token-radar-v13-social-attention",
            event_received_before_ms=1_777_800_000_000,
            limit=11,
        )


@pytest.mark.parametrize("rowcount", [True, -1, "not-a-count", "3"])
def test_rank_source_query_prune_edges_rejects_invalid_cursor_rowcount(rowcount: object) -> None:
    conn = FakeConn(rowcount=rowcount)

    with pytest.raises(TypeError, match="token_radar_rank_source_rowcount_invalid"):
        TokenRadarRankSourceQuery(conn).prune_edges(
            projection_version="token-radar-v13-social-attention",
            event_received_before_ms=1_777_800_000_000,
            limit=11,
        )


def test_rank_source_query_groups_rows_by_request_and_chunks() -> None:
    conn = FakeConn(
        rows=[
            {"request_key": "request-1", "event_id": "event-1"},
            {"request_key": "request-2", "event_id": "event-2"},
        ]
    )
    requests = [_feature_request("request-1"), _feature_request("request-2")]

    rows = TokenRadarRankSourceQuery(conn, chunk_size=1).load_rows_for_requests(requests)

    assert list(rows) == ["request-1", "request-2"]
    assert conn.execute_count == 2


def test_rank_source_query_loads_latest_market_context_for_requested_targets() -> None:
    conn = FakeConn(
        rows=[
            {"target_type_key": "Asset", "identity_id": "asset-1", "latest_price_tick_id": "tick-1"},
            {"target_type_key": "CexToken", "identity_id": "cex-token-1", "latest_price_tick_id": "tick-2"},
        ]
    )

    context = TokenRadarRankSourceQuery(conn).latest_market_context_for_targets(
        [
            {"target_type_key": "Asset", "identity_id": "asset-1"},
            {"target_type_key": "CexToken", "identity_id": "cex-token-1"},
        ]
    )

    assert context[("Asset", "asset-1")]["latest_price_tick_id"] == "tick-1"
    assert context[("CexToken", "cex-token-1")]["latest_price_tick_id"] == "tick-2"
    assert "JOIN market_tick_current" in conn.sql
    assert "JOIN registry_assets" in conn.sql
    assert "price_feeds.provider = 'binance'" in conn.sql


def test_rank_source_query_latest_market_context_requires_formal_output_identity_without_empty_key() -> None:
    conn = FakeConn(rows=[{"identity_id": "asset-1", "latest_price_tick_id": "tick-1"}])

    with pytest.raises(ValueError, match="token_radar_rank_source_target_identity_required:target_type_key"):
        TokenRadarRankSourceQuery(conn).latest_market_context_for_targets(
            [{"target_type_key": "Asset", "identity_id": "asset-1"}]
        )


def test_rank_source_repository_uses_query_facade() -> None:
    conn = FakeConn(rows=[{"request_key": "request-1", "event_id": "event-1"}])

    rows = TokenRadarRankSourceRepository(conn).load_rows_for_requests([_feature_request()])

    assert rows["request-1"][0]["event_id"] == "event-1"
    assert "token_radar_rank_source_events" in conn.sql


def test_rank_source_repository_populates_and_prunes_edges() -> None:
    conn = FakeConn(rows=[{"upserted_count": 1, "deleted_count": 0}], rowcount=4)

    changed = TokenRadarRankSourceRepository(conn).populate_edges_for_event_ids(
        [TokenRadarSourceEdgeRequest(source_event_id="event-1")],
        projected_at_ms=4,
        commit=False,
    )
    deleted = TokenRadarRankSourceRepository(conn).prune_edges(
        projection_version="token-radar-v13-social-attention",
        event_received_before_ms=1_777_000_000_000,
        limit=13,
        commit=False,
    )

    assert changed == 1
    assert deleted == 4
    assert conn.params == ("token-radar-v13-social-attention", 1_777_000_000_000, 13)


def test_rank_source_repository_mutations_require_connection_transaction_before_sql_when_committing() -> None:
    operations = (
        lambda repo: repo.populate_edges_for_event_ids(
            [TokenRadarSourceEdgeRequest(source_event_id="event-1")],
            projected_at_ms=4,
        ),
        lambda repo: repo.populate_edges_for_targets(
            [{"target_type_key": "Asset", "identity_id": "asset-1"}],
            projected_at_ms=4,
            analysis_since_ms=2,
        ),
        lambda repo: repo.prune_edges(
            projection_version="token-radar-v13-social-attention",
            event_received_before_ms=1_777_000_000_000,
            limit=10,
        ),
    )

    for operation in operations:
        conn = NoTransactionConn(rows=[{"upserted_count": 1, "deleted_count": 0}], rowcount=1)
        repo = TokenRadarRankSourceRepository(conn)

        try:
            operation(repo)
        except RuntimeError as exc:
            assert str(exc) == "token_radar_rank_source_repository_transaction_required"
        else:
            raise AssertionError("expected missing transaction support to fail")

        assert conn.sqls == []


def test_rank_source_repository_commit_owned_mutations_use_connection_transaction_without_manual_commit() -> None:
    conn = FakeConn(rows=[{"upserted_count": 1, "deleted_count": 1}], rowcount=3)
    repo = TokenRadarRankSourceRepository(conn)

    changed_by_event = repo.populate_edges_for_event_ids(
        [TokenRadarSourceEdgeRequest(source_event_id="event-1")],
        projected_at_ms=4,
    )
    changed_by_target = repo.populate_edges_for_targets(
        [{"target_type_key": "Asset", "identity_id": "asset-1"}],
        projected_at_ms=5,
        analysis_since_ms=2,
    )
    pruned = repo.prune_edges(
        projection_version="token-radar-v13-social-attention",
        event_received_before_ms=1_777_000_000_000,
        limit=10,
    )

    assert (changed_by_event, changed_by_target, pruned) == (2, 2, 3)
    assert conn.commit_count == 0
    assert conn.transaction_enter_count == 3
    assert conn.transaction_exit_count == 3
    assert conn.execute_depths == [1, 1, 1]
