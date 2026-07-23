from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from psycopg import pq

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.token_intel._constants import TOKEN_RADAR_PROJECTION_VERSION
from parallax.domains.token_intel.repositories.token_radar_dirty_target_repository import (
    TokenRadarDirtyTargetRepository,
    dirty_payload_hash,
)


def test_enqueue_targets_coalesces_by_identity_and_preserves_first_dirty_time() -> None:
    conn = _ScriptedConnection([], rowcount=1)

    count = TokenRadarDirtyTargetRepository(conn).enqueue_targets(
        [
            {"target_type_key": "Asset", "identity_id": "asset-1"},
            {"target_type_key": "Asset", "identity_id": "asset-1"},
        ],
        reason="ops_repair",
        now_ms=1_700_000_000_000,
    )

    sql = conn.sql[-1]
    assert count == 1
    assert "INSERT INTO token_radar_dirty_targets" in sql
    assert "ON CONFLICT(target_type_key, identity_id) DO UPDATE SET" in sql
    assert "first_dirty_at_ms = token_radar_dirty_targets.first_dirty_at_ms" in sql
    assert "source_event_ids_json" not in sql
    assert conn.params[-1]["target_type_keys"] == ["Asset"]
    assert conn.params[-1]["identity_ids"] == ["asset-1"]
    assert conn.params[-1]["dirty_reason"] == "ops_repair"
    assert conn.params[-1]["due_at_ms"] == 1_700_000_000_000


@pytest.mark.parametrize(
    "row",
    [
        pytest.param({"target_type": "Asset", "target_id": "asset-1"}, id="legacy-target-alias"),
        pytest.param({"target_type_key": "Asset", "target_id": "asset-1"}, id="legacy-id-alias"),
        pytest.param({"target_type_key": "Asset", "identity_id": ""}, id="blank-formal-id"),
        pytest.param({"target_type_key": "", "identity_id": "asset-1"}, id="blank-formal-type"),
    ],
)
def test_enqueue_targets_requires_formal_identity_without_alias_fallback(row: dict[str, str]) -> None:
    conn = _ScriptedConnection([])

    with pytest.raises(ValueError, match="token_radar_dirty_target_enqueue_identity_required"):
        TokenRadarDirtyTargetRepository(conn).enqueue_targets(
            [row],
            reason="ops_repair",
            now_ms=1_700_000_000_000,
        )

    assert conn.sql == []


def test_enqueue_targets_unions_dirty_kind_flags_on_conflict() -> None:
    conn = _ScriptedConnection([])

    TokenRadarDirtyTargetRepository(conn).enqueue_targets(
        [{"target_type_key": "Asset", "identity_id": "asset-1"}],
        reason="intent_written",
        now_ms=1_700_000_000_000,
    )

    sql = conn.sql[-1]
    assert "market_dirty" in sql
    assert "repair_dirty" in sql
    assert "market_dirty = token_radar_dirty_targets.market_dirty OR EXCLUDED.market_dirty" in sql
    assert "repair_dirty = token_radar_dirty_targets.repair_dirty OR EXCLUDED.repair_dirty" in sql
    assert "ELSE 'mixed'" in sql
    assert conn.params[-1]["market_dirty"] is False
    assert conn.params[-1]["repair_dirty"] is False


def test_dirty_payload_hash_rejects_legacy_non_string_payload_keys() -> None:
    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        dirty_payload_hash({123: "legacy", "target_type_key": "Asset", "identity_id": "asset-1"})


def test_claim_due_uses_skip_locked_and_claims_stale_leases() -> None:
    conn = _ScriptedConnection(
        [[{"target_type_key": "Asset", "identity_id": "asset-1", "payload_hash": "hash-1"}]],
        rowcount=1,
    )

    rows = TokenRadarDirtyTargetRepository(conn).claim_due(
        limit=25,
        lease_ms=60_000,
        now_ms=1_700_000_000_000,
        lease_owner="worker-a",
    )

    sql = conn.sql[-1]
    assert rows == [{"target_type_key": "Asset", "identity_id": "asset-1", "payload_hash": "hash-1"}]
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s" in sql
    assert "attempt_count = queue.attempt_count + 1" in sql
    assert conn.params[-1]["leased_until_ms"] == 1_700_000_060_000
    assert conn.params[-1]["lease_owner"] == "worker-a"


def test_claim_due_requires_returning_rowcount() -> None:
    conn = _ScriptedConnection(
        [[{"target_type_key": "Asset", "identity_id": "asset-1", "payload_hash": "hash-1"}]],
        omit_rowcount=True,
    )

    with pytest.raises(TypeError, match="token_radar_dirty_target_rowcount_invalid"):
        TokenRadarDirtyTargetRepository(conn).claim_due(
            limit=25,
            lease_ms=60_000,
            now_ms=1_700_000_000_000,
            lease_owner="worker-a",
        )


def test_claim_due_rejects_returning_rowcount_mismatch() -> None:
    conn = _ScriptedConnection(
        [[{"target_type_key": "Asset", "identity_id": "asset-1", "payload_hash": "hash-1"}]],
        rowcount=2,
    )

    with pytest.raises(TypeError, match="token_radar_dirty_target_rowcount_invalid"):
        TokenRadarDirtyTargetRepository(conn).claim_due(
            limit=25,
            lease_ms=60_000,
            now_ms=1_700_000_000_000,
            lease_owner="worker-a",
        )


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        pytest.param({"limit": -1}, "token_radar_dirty_target_claim_limit_required", id="negative-limit"),
        pytest.param({"limit": True}, "token_radar_dirty_target_claim_limit_required", id="bool-limit"),
        pytest.param({"limit": "25"}, "token_radar_dirty_target_claim_limit_required", id="string-limit"),
        pytest.param({"lease_ms": 0}, "token_radar_dirty_target_claim_lease_ms_required", id="zero-lease"),
        pytest.param({"lease_ms": True}, "token_radar_dirty_target_claim_lease_ms_required", id="bool-lease"),
        pytest.param({"lease_ms": "60000"}, "token_radar_dirty_target_claim_lease_ms_required", id="string-lease"),
    ],
)
def test_claim_due_rejects_malformed_parameters_before_transaction(
    overrides: dict[str, object],
    error: str,
) -> None:
    conn = _MissingTransactionConnection()
    params: dict[str, object] = {
        "limit": 25,
        "lease_ms": 60_000,
        "now_ms": 1_700_000_000_000,
        "lease_owner": "worker-a",
    }
    params.update(overrides)

    with pytest.raises(ValueError, match=error):
        TokenRadarDirtyTargetRepository(conn).claim_due(**params)

    assert conn.sql == []
    assert conn.commits == 0


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
        max_attempts=3,
        worker_name="token_radar_projection",
        now_ms=1_700_000_010_000,
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


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        pytest.param({"retry_ms": 0}, "token_radar_dirty_target_retry_ms_required", id="zero-retry"),
        pytest.param({"retry_ms": True}, "token_radar_dirty_target_retry_ms_required", id="bool-retry"),
        pytest.param({"retry_ms": "30000"}, "token_radar_dirty_target_retry_ms_required", id="string-retry"),
        pytest.param({"max_attempts": 0}, "token_radar_dirty_target_max_attempts_required", id="zero-attempts"),
        pytest.param({"max_attempts": True}, "token_radar_dirty_target_max_attempts_required", id="bool-attempts"),
        pytest.param({"max_attempts": "3"}, "token_radar_dirty_target_max_attempts_required", id="string-attempts"),
    ],
)
def test_mark_error_rejects_malformed_retry_policy_before_transaction(
    overrides: dict[str, object],
    error: str,
) -> None:
    conn = _MissingTransactionConnection()
    params: dict[str, object] = {
        "error": "projection failed",
        "retry_ms": 30_000,
        "max_attempts": 3,
        "worker_name": "token_radar_projection",
        "now_ms": 1_700_000_010_000,
    }
    params.update(overrides)

    with pytest.raises(ValueError, match=error):
        TokenRadarDirtyTargetRepository(conn).mark_error([_claim()], **params)

    assert conn.sql == []
    assert conn.commits == 0


def test_mark_error_terminalizes_exhausted_target_dirty_claim() -> None:
    conn = _TerminalizingConnection()
    claim = _claim()

    changed = TokenRadarDirtyTargetRepository(conn).mark_error(
        [claim],
        error="projection failed",
        retry_ms=30_000,
        max_attempts=1,
        worker_name="token_radar_projection",
        now_ms=1_700_000_010_000,
    )

    assert changed == 1
    assert "DELETE FROM token_radar_dirty_targets queue" in conn.sql[0]
    assert any("INSERT INTO worker_queue_terminal_events" in sql for sql in conn.sql)
    assert conn.terminal_params["worker_name"] == "token_radar_projection"
    assert conn.terminal_params["source_table"] == "token_radar_dirty_targets"
    assert conn.terminal_params["target_key"] == "Asset:asset-1"
    assert conn.terminal_params["final_status"] == "terminal"
    assert conn.terminal_params["final_reason"] == "token_radar_projection_retry_budget_exhausted: projection failed"
    assert conn.terminal_params["final_reason_bucket"] == "retry_budget_exhausted"
    assert conn.terminal_params["attempt_count"] == 1
    assert conn.terminal_params["payload_hash"] == "hash-1"


@pytest.mark.parametrize(
    ("operation", "error"),
    [
        pytest.param(
            lambda repo: repo.enqueue_market_product_targets(
                [("Asset", "asset-1")],
                reason="market_tick_current_changed",
                now_ms=1_700_000_000_000,
            ),
            "token_radar_dirty_target_rowcount_invalid",
            id="market-target-rowcount-required",
        ),
        pytest.param(
            lambda repo: repo.mark_done([_claim()], now_ms=1_700_000_060_000),
            "token_radar_dirty_target_rowcount_invalid",
            id="done-rowcount-required",
        ),
        pytest.param(
            lambda repo: repo.mark_error(
                [_claim()],
                error="projection failed",
                retry_ms=30_000,
                max_attempts=3,
                worker_name="token_radar_projection",
                now_ms=1_700_000_060_000,
            ),
            "token_radar_dirty_target_rowcount_invalid",
            id="error-rowcount-required",
        ),
    ],
)
def test_target_dirty_write_counts_require_cursor_rowcount(
    operation: Callable[[TokenRadarDirtyTargetRepository], object],
    error: str,
) -> None:
    conn = _ScriptedConnection([], omit_rowcount=True)

    with pytest.raises(TypeError, match=error):
        operation(TokenRadarDirtyTargetRepository(conn))


@pytest.mark.parametrize("rowcount", ("bad", "1"))
def test_target_dirty_write_counts_reject_invalid_cursor_rowcount(rowcount: object) -> None:
    conn = _ScriptedConnection([], rowcount=rowcount)

    with pytest.raises(TypeError, match="token_radar_dirty_target_rowcount_invalid"):
        TokenRadarDirtyTargetRepository(conn).enqueue_market_current_targets(
            since_ms=123,
            now_ms=1_700_000_060_000,
            limit=25,
            reason="ops_market_current_repair",
        )


def test_target_dirty_generic_enqueue_requires_cursor_rowcount() -> None:
    conn = _ScriptedConnection([], omit_rowcount=True)

    with pytest.raises(TypeError, match="token_radar_dirty_target_rowcount_invalid"):
        TokenRadarDirtyTargetRepository(conn).enqueue_targets(
            [{"target_type_key": "Asset", "identity_id": "asset-1"}],
            reason="intent_written",
            now_ms=1_700_000_000_000,
        )


@pytest.mark.parametrize("rowcount", ("bad", "1", True, -1))
def test_target_dirty_generic_enqueue_rejects_invalid_cursor_rowcount(rowcount: object) -> None:
    conn = _ScriptedConnection([], rowcount=rowcount)

    with pytest.raises(TypeError, match="token_radar_dirty_target_rowcount_invalid"):
        TokenRadarDirtyTargetRepository(conn).enqueue_targets(
            [{"target_type_key": "Asset", "identity_id": "asset-1"}],
            reason="intent_written",
            now_ms=1_700_000_000_000,
        )


@pytest.mark.parametrize(
    "operation",
    [
        lambda repo: repo.enqueue_targets(
            [{"target_type_key": "Asset", "identity_id": "asset-1"}],
            reason="intent_written",
            now_ms=1_700_000_000_000,
        ),
        lambda repo: repo.enqueue_market_product_targets(
            [("Asset", "asset-1")],
            reason="market_tick_current_changed",
            now_ms=1_700_000_000_000,
        ),
        lambda repo: repo.claim_due(
            limit=10,
            lease_ms=60_000,
            now_ms=1_700_000_000_000,
            lease_owner="token_radar_projection",
        ),
        lambda repo: repo.enqueue_recent_resolved_targets(
            since_ms=1_700_000_000_000,
            now_ms=1_700_000_060_000,
            limit=10,
            reason="projection_catch_up",
        ),
        lambda repo: repo.enqueue_market_current_targets(
            since_ms=1_700_000_000_000,
            now_ms=1_700_000_060_000,
            limit=10,
            reason="ops_market_current_repair",
        ),
        lambda repo: repo.mark_done([_claim()], now_ms=1_700_000_060_000),
        lambda repo: repo.mark_error(
            [_claim()],
            error="projection failed",
            retry_ms=30_000,
            max_attempts=3,
            worker_name="token_radar_projection",
            now_ms=1_700_000_060_000,
        ),
    ],
)
def test_target_dirty_mutations_require_explicit_transaction_before_sql(
    operation: Callable[[TokenRadarDirtyTargetRepository], object],
) -> None:
    conn = _MissingTransactionConnection()

    with pytest.raises(RuntimeError, match="requires_explicit_transaction"):
        operation(TokenRadarDirtyTargetRepository(conn))

    assert conn.sql == []
    assert conn.commits == 0


def test_mark_done_rejects_keys_without_claim_payload_hash() -> None:
    conn = _ScriptedConnection([])

    try:
        TokenRadarDirtyTargetRepository(conn).mark_done(
            [{"target_type_key": "Asset", "identity_id": "asset-1", "attempt_count": 1}],
            now_ms=1_700_000_010_000,
        )
    except ValueError as exc:
        assert "payload_hash" in str(exc)
    else:
        raise AssertionError("expected mark_done to require claimed payload_hash")

    assert conn.sql == []


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda repo, claim: repo.mark_done([claim], now_ms=1_700_000_010_000), id="done"),
        pytest.param(
            lambda repo, claim: repo.mark_error(
                [claim],
                error="projection failed",
                retry_ms=30_000,
                max_attempts=3,
                worker_name="token_radar_projection",
                now_ms=1_700_000_010_000,
            ),
            id="error",
        ),
    ],
)
def test_target_dirty_completion_requires_claim_attempt_field_without_default(
    operation: Callable[[TokenRadarDirtyTargetRepository, dict[str, Any]], object],
) -> None:
    conn = _ScriptedConnection([])
    claim = _claim()
    claim.pop("attempt_count")

    with pytest.raises(ValueError, match="token radar dirty target completion requires attempt_count") as exc_info:
        operation(TokenRadarDirtyTargetRepository(conn), claim)

    assert isinstance(exc_info.value.__cause__, KeyError)
    assert conn.sql == []


@pytest.mark.parametrize(
    ("field", "aliases"),
    [
        pytest.param("target_type_key", {"target_type": "Asset"}, id="target_type_key"),
        pytest.param("identity_id", {"target_id": "asset-1", "intent_id": "intent-1"}, id="identity_id"),
    ],
)
@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda repo, claim: repo.mark_done([claim], now_ms=1_700_000_010_000), id="done"),
        pytest.param(
            lambda repo, claim: repo.mark_error(
                [claim],
                error="projection failed",
                retry_ms=30_000,
                max_attempts=3,
                worker_name="token_radar_projection",
                now_ms=1_700_000_010_000,
            ),
            id="error",
        ),
    ],
)
def test_target_dirty_completion_requires_formal_identity_fields_without_alias_fallback(
    operation: Callable[[TokenRadarDirtyTargetRepository, dict[str, Any]], object],
    field: str,
    aliases: dict[str, str],
) -> None:
    conn = _ScriptedConnection([])
    claim = _claim()
    claim.pop(field)
    claim.update(aliases)

    with pytest.raises(ValueError, match=field) as exc_info:
        operation(TokenRadarDirtyTargetRepository(conn), claim)

    assert isinstance(exc_info.value.__cause__, KeyError)
    assert conn.sql == []


def test_enqueue_market_product_targets_accepts_only_canonical_product_keys() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 2

    count = TokenRadarDirtyTargetRepository(conn).enqueue_market_product_targets(
        [
            ("Asset", "asset-1"),
            {"target_type_key": "CexToken", "identity_id": "cex_token:BTC"},
        ],
        reason="market_tick_current_changed",
        now_ms=1_700_000_000_000,
    )

    sql = conn.sql[-1]
    assert count == 2
    assert "JOIN registry_assets" not in sql
    assert "JOIN price_feeds" not in sql
    assert "INSERT INTO token_radar_dirty_targets" in sql
    assert "ON CONFLICT(target_type_key, identity_id) DO UPDATE SET" in sql
    assert conn.params[-1]["target_type_keys"] == ["Asset", "CexToken"]
    assert conn.params[-1]["identity_ids"] == ["asset-1", "cex_token:BTC"]


def test_enqueue_market_product_targets_uses_stable_hash_and_persists_future_due() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 1

    TokenRadarDirtyTargetRepository(conn).enqueue_market_product_targets(
        [("Asset", "asset-1")],
        reason="market_tick_current_changed",
        now_ms=1_700_000_000_000,
    )

    sql = conn.sql[-1]
    assert "%(now_ms)s::text" not in sql
    assert "MAX(features.latest_market_observed_at_ms)" in sql
    assert "token_radar_target_projection_coverage" not in sql
    assert "latest_market_observed_at_ms" in sql
    assert "features.projection_version = %(projection_version)s" in sql
    assert "%(market_dirty_min_interval_ms)s" in sql
    assert "THEN latest_feature.latest_market_observed_at_ms + %(market_dirty_min_interval_ms)s" in sql
    assert "scheduled.due_at_ms" in sql
    assert "payload_hash IS DISTINCT FROM EXCLUDED.payload_hash" in sql
    assert "token_radar_dirty_targets.due_at_ms > EXCLUDED.due_at_ms" in sql
    assert "leased_until_ms = NULL" in sql
    assert "lease_owner = NULL" in sql
    assert "token_radar_dirty_targets.last_error IS NOT NULL" in sql
    assert "market_dirty = token_radar_dirty_targets.market_dirty OR EXCLUDED.market_dirty" in sql
    assert "repair_dirty = token_radar_dirty_targets.repair_dirty OR EXCLUDED.repair_dirty" in sql
    assert conn.params[-1]["projection_version"] == TOKEN_RADAR_PROJECTION_VERSION
    assert conn.params[-1]["market_dirty_min_interval_ms"] == 60_000
    assert conn.params[-1]["market_dirty"] is True
    assert conn.params[-1]["repair_dirty"] is False


def test_enqueue_recent_resolved_targets_is_bounded_freshness_gated_catch_up() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 10

    count = TokenRadarDirtyTargetRepository(conn).enqueue_recent_resolved_targets(
        since_ms=1_700_000_000_000,
        now_ms=1_700_000_060_000,
        limit=10,
        reason="projection_catch_up",
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
    assert conn.params[-1]["projection_version"] == TOKEN_RADAR_PROJECTION_VERSION


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
    assert conn.params[1]["projection_version"] == TOKEN_RADAR_PROJECTION_VERSION


@pytest.mark.parametrize("limit", [-1, True, "25"])
@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda repo, limit: repo.enqueue_recent_resolved_targets(
                since_ms=1_700_000_000_000,
                now_ms=1_700_000_060_000,
                limit=limit,
                reason="projection_catch_up",
            ),
            id="enqueue-recent-resolved",
        ),
        pytest.param(
            lambda repo, limit: repo.count_recent_resolved_target_candidates(
                since_ms=1_700_000_000_000,
                now_ms=1_700_000_060_000,
                limit=limit,
            ),
            id="count-recent-resolved",
        ),
        pytest.param(
            lambda repo, limit: repo.count_recent_resolved_target_enqueue_candidates(
                since_ms=1_700_000_000_000,
                now_ms=1_700_000_060_000,
                limit=limit,
            ),
            id="count-recent-resolved-enqueueable",
        ),
        pytest.param(
            lambda repo, limit: repo.count_market_current_target_candidates(
                since_ms=123,
                now_ms=1_700_000_060_000,
                limit=limit,
            ),
            id="count-market-current",
        ),
        pytest.param(
            lambda repo, limit: repo.count_market_current_target_enqueue_candidates(
                since_ms=123,
                now_ms=1_700_000_060_000,
                limit=limit,
            ),
            id="count-market-current-enqueueable",
        ),
        pytest.param(
            lambda repo, limit: repo.enqueue_market_current_targets(
                since_ms=123,
                now_ms=1_700_000_060_000,
                limit=limit,
                reason="ops_market_current_repair",
            ),
            id="enqueue-market-current",
        ),
    ],
)
def test_repair_limit_paths_reject_malformed_limit_before_sql(
    operation: Callable[[TokenRadarDirtyTargetRepository, object], object],
    limit: object,
) -> None:
    conn = _ScriptedConnection([])

    with pytest.raises(ValueError, match="token_radar_dirty_target_limit_required"):
        operation(TokenRadarDirtyTargetRepository(conn), limit)

    assert conn.sql == []


def test_market_current_target_enqueue_maps_persisted_current_rows_since_watermark() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 4

    enqueued = TokenRadarDirtyTargetRepository(conn).enqueue_market_current_targets(
        since_ms=123,
        now_ms=1_700_000_060_000,
        limit=25,
        reason="ops_market_current_repair",
    )

    sql = conn.sql[-1]
    assert enqueued == 4
    assert "FROM market_tick_current" in sql
    assert "GREATEST(current_row.tick_observed_at_ms, current_row.updated_at_ms) >= %(since_ms)s" in sql
    assert "JOIN registry_assets" in sql
    assert "JOIN price_feeds" in sql
    assert "registry_assets.status IN ('candidate', 'canonical')" in sql
    assert "price_feeds.provider = 'binance'" in sql
    assert "price_feeds.feed_type = 'cex_swap'" in sql
    assert "price_feeds.quote_symbol = 'USDT'" in sql
    assert "price_feeds.status = 'canonical'" in sql
    assert "eligible.due_at_ms" in sql
    assert "INSERT INTO token_radar_dirty_targets" in sql
    assert "market_dirty" in sql
    assert "repair_dirty" in sql
    assert conn.params[-1]["since_ms"] == 123
    assert conn.params[-1]["limit"] == 25
    assert conn.params[-1]["dirty_reason"] == "ops_market_current_repair"
    assert conn.params[-1]["market_dirty"] is True
    assert conn.params[-1]["repair_dirty"] is True


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
    assert conn.params[1]["projection_version"] == TOKEN_RADAR_PROJECTION_VERSION


def test_repository_session_exposes_token_radar_dirty_targets() -> None:
    session = repositories_for_connection(
        _ScriptedConnection([]),
        notification_delivery_running_timeout_ms=300_000,
        notification_delivery_stale_running_terminalization_batch_size=100,
    )

    assert isinstance(session.token_radar_dirty_targets, TokenRadarDirtyTargetRepository)


def _claim() -> dict[str, Any]:
    return {
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "payload_hash": "hash-1",
        "lease_owner": "token_radar_projection",
        "attempt_count": 1,
    }


class _ScriptedConnection:
    def __init__(
        self,
        results: list[list[dict[str, Any]] | None],
        *,
        rowcount: Any = 0,
        omit_rowcount: bool = False,
    ) -> None:
        self.results = list(results)
        self.sql: list[str] = []
        self.params: list[dict[str, Any]] = []
        if not omit_rowcount:
            self.rowcount = rowcount
        self.commits = 0
        self.info = SimpleNamespace(transaction_status=pq.TransactionStatus.INTRANS)

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


class _MissingTransactionConnection:
    transaction = None

    def __init__(self) -> None:
        self.sql: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.commits = 0
        self.info = SimpleNamespace(transaction_status=pq.TransactionStatus.IDLE)

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _MissingTransactionConnection:
        self.sql.append(str(sql))
        self.params.append(params or {})
        raise AssertionError("SQL must not run without connection transaction")

    def commit(self) -> None:
        self.commits += 1
        raise AssertionError("manual commit fallback must not run")


class _TerminalizingConnection:
    def __init__(self) -> None:
        self.rowcount = 1
        self.sql: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.terminal_params: dict[str, Any] = {}
        self.info = SimpleNamespace(transaction_status=pq.TransactionStatus.INTRANS)

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _TerminalizingCursor:
        self.sql.append(str(sql))
        self.params.append(params or {})
        normalized = " ".join(str(sql).split()).lower()
        if "delete from token_radar_dirty_targets queue" in normalized:
            return _TerminalizingCursor(rowcount=1, rows=[{**_claim(), "first_dirty_at_ms": 1_700_000_000_000}])
        if "select terminal_generation" in normalized:
            return _TerminalizingCursor(rowcount=0, rows=[])
        if "select coalesce(max(terminal_generation)" in normalized:
            return _TerminalizingCursor(rowcount=1, rows=[{"terminal_generation": 1}])
        if "insert into worker_queue_terminal_events" in normalized:
            self.terminal_params = dict(params or {})
            return _TerminalizingCursor(rowcount=1, rows=[self.terminal_params])
        raise AssertionError(f"unexpected SQL: {sql}")


class _TerminalizingCursor:
    def __init__(self, *, rowcount: int, rows: list[dict[str, Any]]) -> None:
        self.rowcount = rowcount
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None
