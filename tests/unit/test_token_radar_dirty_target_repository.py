from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_dirty_target_repository import (
    TokenRadarDirtyTargetRepository,
)


def test_enqueue_targets_coalesces_by_identity_and_preserves_first_dirty_time() -> None:
    conn = _ScriptedConnection([])

    count = TokenRadarDirtyTargetRepository(conn).enqueue_targets(
        [
            {"target_type_key": "Asset", "identity_id": "asset-1", "source_event_ids": ["event-1"]},
            {"target_type": "Asset", "target_id": "asset-1", "source_event_ids_json": ["event-1", "event-2"]},
            {"target_type_key": "", "identity_id": ""},
        ],
        reason="ingest_resolution",
        now_ms=1_700_000_000_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert count == 1
    assert "INSERT INTO token_radar_dirty_targets" in sql
    assert "ON CONFLICT(target_type_key, identity_id) DO UPDATE SET" in sql
    assert "first_dirty_at_ms = token_radar_dirty_targets.first_dirty_at_ms" in sql
    assert "source_event_ids_json" in sql
    assert conn.params[-1]["target_type_keys"] == ["Asset"]
    assert conn.params[-1]["identity_ids"] == ["asset-1"]
    assert conn.params[-1]["dirty_reason"] == "ingest_resolution"
    assert conn.params[-1]["due_at_ms"] == 1_700_000_000_000


def test_claim_due_uses_skip_locked_and_claims_stale_leases() -> None:
    conn = _ScriptedConnection([[{"target_type_key": "Asset", "identity_id": "asset-1", "payload_hash": "hash-1"}]])

    rows = TokenRadarDirtyTargetRepository(conn).claim_due(
        limit=25,
        lease_ms=60_000,
        now_ms=1_700_000_000_000,
        lease_owner="worker-a",
        commit=False,
    )

    sql = conn.sql[-1]
    assert rows == [{"target_type_key": "Asset", "identity_id": "asset-1", "payload_hash": "hash-1"}]
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s" in sql
    assert "attempt_count = token_radar_dirty_targets.attempt_count + 1" in sql
    assert conn.params[-1]["leased_until_ms"] == 1_700_000_060_000
    assert conn.params[-1]["lease_owner"] == "worker-a"


def test_mark_done_deletes_only_matching_claim_payload_hash() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 1

    deleted = TokenRadarDirtyTargetRepository(conn).mark_done(
        [
            {
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "payload_hash": "claim-hash",
                "lease_owner": "worker-a",
                "attempt_count": 2,
            }
        ],
        now_ms=1_700_000_010_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert deleted == 1
    assert "DELETE FROM token_radar_dirty_targets queue" in sql
    assert "queue.payload_hash = done.payload_hash" in sql
    assert "queue.lease_owner = done.lease_owner" in sql
    assert "queue.attempt_count = done.attempt_count" in sql
    assert "done.payload_hash = ''" not in sql
    assert "done.lease_owner = ''" not in sql
    assert conn.params[-1]["payload_hashes"] == ["claim-hash"]
    assert conn.params[-1]["lease_owners"] == ["worker-a"]
    assert conn.params[-1]["attempt_counts"] == [2]


def test_mark_error_releases_lease_without_overwriting_newer_dirty_payload() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 1

    updated = TokenRadarDirtyTargetRepository(conn).mark_error(
        [
            {
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "payload_hash": "claim-hash",
                "lease_owner": "worker-a",
                "attempt_count": 2,
            }
        ],
        error="projection failed",
        retry_ms=30_000,
        now_ms=1_700_000_010_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert updated == 1
    assert "SET due_at_ms = %(due_at_ms)s" in sql
    assert "leased_until_ms = NULL" in sql
    assert "queue.payload_hash = failed.payload_hash" in sql
    assert "queue.lease_owner = failed.lease_owner" in sql
    assert "queue.attempt_count = failed.attempt_count" in sql
    assert "failed.payload_hash = ''" not in sql
    assert conn.params[-1]["due_at_ms"] == 1_700_000_040_000
    assert conn.params[-1]["last_error"] == "projection failed"


def test_mark_done_rejects_keys_without_claim_payload_hash() -> None:
    conn = _ScriptedConnection([])

    try:
        TokenRadarDirtyTargetRepository(conn).mark_done(
            [{"target_type_key": "Asset", "identity_id": "asset-1"}],
            now_ms=1_700_000_010_000,
            commit=False,
        )
    except ValueError as exc:
        assert "payload_hash" in str(exc)
    else:
        raise AssertionError("expected mark_done to require claimed payload_hash")

    assert conn.sql == []


def test_enqueue_market_targets_maps_market_key_to_radar_identity_in_db() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 2

    count = TokenRadarDirtyTargetRepository(conn).enqueue_market_targets(
        [
            ("chain_token", "eip155:1:0xabc"),
            {"target_type": "cex_symbol", "target_id": "binance:BTC-USDT"},
        ],
        reason="market_tick_current_changed",
        now_ms=1_700_000_000_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert count == 2
    assert "JOIN registry_assets" in sql
    assert "JOIN price_feeds" in sql
    assert "INSERT INTO token_radar_dirty_targets" in sql
    assert "ON CONFLICT(target_type_key, identity_id) DO UPDATE SET" in sql
    assert conn.params[-1]["target_types"] == ["chain_token", "cex_symbol"]
    assert conn.params[-1]["target_ids"] == ["eip155:1:0xabc", "binance:BTC-USDT"]


def test_enqueue_market_targets_uses_stable_hash_and_coalesces_fresh_targets() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 1

    TokenRadarDirtyTargetRepository(conn).enqueue_market_targets(
        [("chain_token", "eip155:1:0xabc")],
        reason="market_tick_current_changed",
        now_ms=1_700_000_000_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert "%(now_ms)s::text" not in sql
    assert "MAX(features.latest_market_observed_at_ms)" in sql
    assert "token_radar_target_projection_coverage" not in sql
    assert "latest_market_observed_at_ms" in sql
    assert "features.projection_version = %(projection_version)s" in sql
    assert "%(market_dirty_min_interval_ms)s" in sql
    assert "payload_hash IS DISTINCT FROM EXCLUDED.payload_hash" in sql
    assert "token_radar_dirty_targets.due_at_ms > EXCLUDED.due_at_ms" in sql
    assert "leased_until_ms = NULL" in sql
    assert "lease_owner = NULL" in sql
    assert "token_radar_dirty_targets.last_error IS NOT NULL" in sql
    assert conn.params[-1]["projection_version"] == "token-radar-v13-social-attention"
    assert conn.params[-1]["market_dirty_min_interval_ms"] == 60_000


def test_enqueue_recent_resolved_targets_is_bounded_freshness_gated_catch_up() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 10

    count = TokenRadarDirtyTargetRepository(conn).enqueue_recent_resolved_targets(
        since_ms=1_700_000_000_000,
        now_ms=1_700_000_060_000,
        limit=10,
        reason="projection_catch_up",
        commit=False,
    )

    sql = conn.sql[-1]
    assert count == 10
    assert "INSERT INTO token_radar_dirty_targets" in sql
    assert "LIMIT %(limit)s" in sql
    assert "token_intent_resolutions.target_type IN ('Asset', 'CexToken')" in sql
    assert "token_intent_resolutions.target_id IS NOT NULL" in sql
    assert "MAX(events.received_at_ms) AS source_max_received_at_ms" in sql
    assert "token_radar_target_features" in sql
    assert "token_radar_target_projection_coverage" not in sql
    assert "MAX(features.latest_event_received_at_ms)" in sql
    assert "eligible.source_max_received_at_ms::text" in sql
    assert "payload_hash IS DISTINCT FROM EXCLUDED.payload_hash" in sql
    assert "token_radar_dirty_targets.last_error IS NOT NULL" in sql
    assert conn.params[-1]["since_ms"] == 1_700_000_000_000
    assert conn.params[-1]["now_ms"] == 1_700_000_060_000
    assert conn.params[-1]["limit"] == 10
    assert conn.params[-1]["projection_version"] == "token-radar-v13-social-attention"


def test_recent_resolved_target_candidate_counts_reuse_bounded_fact_query() -> None:
    conn = _ScriptedConnection([[{"count": 8}], [{"count": 5}]])

    candidates = TokenRadarDirtyTargetRepository(conn).count_recent_resolved_target_candidates(
        since_ms=1_700_000_000_000,
        now_ms=1_700_000_060_000,
        limit=10,
    )
    enqueueable = TokenRadarDirtyTargetRepository(conn).count_recent_resolved_target_enqueue_candidates(
        since_ms=1_700_000_000_000,
        now_ms=1_700_000_060_000,
        limit=10,
    )

    assert candidates == 8
    assert enqueueable == 5
    assert "token_intent_resolutions.target_type IN ('Asset', 'CexToken')" in conn.sql[0]
    assert "INSERT INTO token_radar_dirty_targets" not in conn.sql[0]
    assert "latest_feature" not in conn.sql[0]
    assert "latest_feature" in conn.sql[1]
    assert "target_coverage" not in conn.sql[1]
    assert conn.params[0]["since_ms"] == 1_700_000_000_000
    assert conn.params[1]["projection_version"] == "token-radar-v13-social-attention"


def test_market_current_target_enqueue_maps_persisted_current_rows_since_watermark() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 4

    enqueued = TokenRadarDirtyTargetRepository(conn).enqueue_market_current_targets(
        since_ms=123,
        now_ms=1_700_000_060_000,
        limit=25,
        reason="ops_market_current_repair",
        commit=False,
    )

    sql = conn.sql[-1]
    assert enqueued == 4
    assert "FROM market_tick_current" in sql
    assert "GREATEST(current_row.tick_observed_at_ms, current_row.updated_at_ms) >= %(since_ms)s" in sql
    assert "JOIN registry_assets" in sql
    assert "JOIN price_feeds" in sql
    assert "INSERT INTO token_radar_dirty_targets" in sql
    assert conn.params[-1]["since_ms"] == 123
    assert conn.params[-1]["limit"] == 25
    assert conn.params[-1]["dirty_reason"] == "ops_market_current_repair"


def test_market_current_target_candidate_counts_are_read_only() -> None:
    conn = _ScriptedConnection([[{"count": 6}], [{"count": 4}]])

    candidates = TokenRadarDirtyTargetRepository(conn).count_market_current_target_candidates(
        since_ms=123,
        now_ms=1_700_000_060_000,
        limit=25,
    )
    enqueueable = TokenRadarDirtyTargetRepository(conn).count_market_current_target_enqueue_candidates(
        since_ms=123,
        now_ms=1_700_000_060_000,
        limit=25,
    )

    assert candidates == 6
    assert enqueueable == 4
    assert "FROM market_tick_current" in conn.sql[0]
    assert "INSERT INTO token_radar_dirty_targets" not in conn.sql[0]
    assert "latest_feature" not in conn.sql[0]
    assert "latest_feature" in conn.sql[1]
    assert "target_coverage" not in conn.sql[1]
    assert conn.params[0]["since_ms"] == 123
    assert conn.params[1]["projection_version"] == "token-radar-v13-social-attention"


def test_repository_session_exposes_token_radar_dirty_targets() -> None:
    session = repositories_for_connection(_ScriptedConnection([]))

    assert isinstance(session.token_radar_dirty_targets, TokenRadarDirtyTargetRepository)


class _ScriptedConnection:
    def __init__(self, results: list[list[dict[str, Any]] | None]) -> None:
        self.results = list(results)
        self.sql: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.rowcount = 0
        self.commits = 0

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _ScriptedConnection:
        self.sql.append(str(sql))
        self.params.append(params or {})
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        if not self.results:
            return []
        result = self.results.pop(0)
        assert isinstance(result, list)
        return result

    def fetchone(self) -> dict[str, Any] | None:
        rows = self.fetchall()
        return rows[0] if rows else None

    def commit(self) -> None:
        self.commits += 1
