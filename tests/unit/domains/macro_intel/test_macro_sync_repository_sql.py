from __future__ import annotations

import inspect
from datetime import date
from typing import Any

import pytest

from parallax.domains.macro_intel.repositories.macro_intel_repository import (
    MacroIntelRepository,
    _macro_daily_brief_payload_hash,
    _macro_projection_dirty_change_payload_hash,
    _macro_projection_dirty_payload_hash,
)

CONTROL_METHODS = (
    "enqueue_macro_sync_window",
    "claim_macro_sync_window",
    "claim_macro_sync_window_by_id",
    "record_macro_sync_run",
    "complete_macro_sync_window",
    "retry_macro_sync_window",
    "fail_macro_sync_window",
    "latest_macro_sync_run",
    "macro_sync_queue_summary",
    "macro_sync_state_max_observed_at",
    "update_macro_sync_state",
    "rebuild_macro_sync_state",
    "enqueue_macro_projection_dirty_targets_for_changes",
)


def test_macro_sync_repository_exposes_control_plane_methods_without_commits() -> None:
    for method_name in CONTROL_METHODS:
        method = getattr(MacroIntelRepository, method_name)
        source = inspect.getsource(method)

        assert ".commit(" not in source


def test_claim_macro_sync_window_uses_atomic_claim_first_sql() -> None:
    source = inspect.getsource(MacroIntelRepository.claim_macro_sync_window)
    normalized_source = " ".join(source.split())

    assert "FOR UPDATE SKIP LOCKED" in source
    assert "expired_terminal AS" in source
    assert "status = 'running'" in source
    assert "attempt_count >= max_attempts" in source
    assert "macro_sync_lease_expired_attempt_budget_exhausted" in source
    assert "UPDATE macro_sync_windows AS sync_window" in source
    assert "RETURNING sync_window.*" in source
    assert " AS window" not in source
    assert "attempt_count < max_attempts" in normalized_source
    assert "status IN ('pending', 'retryable')" in source
    assert "(status = 'running' AND leased_until_ms IS NOT NULL AND leased_until_ms <= %s)" in normalized_source
    assert "due_at_ms <= %s" in source
    assert (
        "ORDER BY priority ASC, window_end DESC, due_at_ms ASC, updated_at_ms ASC, sync_window_id ASC"
        in normalized_source
    )
    assert "FROM macro_observations" not in source


def test_claim_macro_sync_window_by_id_only_claims_requested_window() -> None:
    source = inspect.getsource(MacroIntelRepository.claim_macro_sync_window_by_id)
    normalized_source = " ".join(source.split())

    assert "FOR UPDATE SKIP LOCKED" in source
    assert "WHERE sync_window_id = %s" in source
    assert "status IN ('pending', 'retryable')" in source
    assert "attempt_count < max_attempts" in normalized_source
    assert "UPDATE macro_sync_windows AS sync_window" in source
    assert "RETURNING sync_window.*" in source
    assert "ORDER BY priority ASC" not in source
    assert "FROM macro_observations" not in source


def test_window_terminal_updates_have_stale_completion_guards() -> None:
    for method_name in ("complete_macro_sync_window", "retry_macro_sync_window", "fail_macro_sync_window"):
        source = inspect.getsource(getattr(MacroIntelRepository, method_name))

        assert "WHERE sync_window_id = %s" in source
        assert "AND lease_owner = %s" in source
        assert "AND attempt_count = %s" in source
        assert "FROM macro_observations" not in source


def test_queue_control_methods_do_not_scan_macro_observations() -> None:
    for method_name in (
        "enqueue_macro_sync_window",
        "claim_macro_sync_window",
        "claim_macro_sync_window_by_id",
        "complete_macro_sync_window",
        "retry_macro_sync_window",
        "fail_macro_sync_window",
    ):
        source = inspect.getsource(getattr(MacroIntelRepository, method_name))

        assert "FROM macro_observations" not in source
        assert "JOIN macro_observations" not in source


def test_macro_sync_state_lookup_uses_control_state_not_observation_scan() -> None:
    source = inspect.getsource(MacroIntelRepository.macro_sync_state_max_observed_at)

    assert "FROM macro_sync_state" in source
    assert "source_name = %s" in source
    assert "bundle_name = %s" in source
    assert "FROM macro_observations" not in source


def test_update_macro_sync_state_is_monotonic_and_zero_write_when_not_advanced() -> None:
    source = inspect.getsource(MacroIntelRepository.update_macro_sync_state)
    normalized_source = " ".join(source.split())

    assert "INSERT INTO macro_sync_state" in source
    assert "ON CONFLICT(source_name, bundle_name) DO UPDATE" in source
    assert "EXCLUDED.max_observed_at > macro_sync_state.max_observed_at" in normalized_source
    assert "WHERE macro_sync_state.max_observed_at IS NULL OR EXCLUDED.max_observed_at >" in normalized_source


def test_rebuild_macro_sync_state_is_named_source_bundle_repair_only() -> None:
    source = inspect.getsource(MacroIntelRepository.rebuild_macro_sync_state)
    normalized_source = " ".join(source.split())

    assert "FROM macro_sync_runs" in source
    assert "WHERE source_name = %s" in source
    assert "AND bundle_name = %s" in source
    assert "status IN ('ok', 'partial')" in source
    assert "COALESCE(max_seen_observed_at, max_observed_at, requested_end)" in normalized_source
    assert "FROM macro_observations" in source
    assert 'str(source_name) == "macrodata-cli"' in source
    assert 'str(bundle_name) == "macro-core"' in source
    assert "ORDER BY observed_at DESC" in source
    assert "LIMIT 1" in source
    assert "macrodata-cli" in source
    assert "macro-core" in source
    assert "INSERT INTO macro_sync_state" in source
    assert "ON CONFLICT(source_name, bundle_name) DO UPDATE" in source
    assert "source_name" in normalized_source
    assert "bundle_name" in normalized_source


def test_enqueue_macro_sync_window_coalesces_by_identity_and_returns_id() -> None:
    conn = FakeConnection(rows=[{"sync_window_id": "macro-sync-window:abc"}])
    repo = MacroIntelRepository(conn)

    sync_window_id = repo.enqueue_macro_sync_window(
        source_name="macrodata-cli",
        bundle_name="macro-core",
        window_start="2026-05-01",
        window_end="2026-05-27",
        trigger_reason="bootstrap",
        priority=25,
        due_at_ms=1_779_000_000_000,
        max_attempts=8,
        now_ms=1_779_000_000_000,
    )

    assert sync_window_id == "macro-sync-window:abc"
    query, params = conn.executions[0]
    assert "INSERT INTO macro_sync_windows" in query
    assert "ON CONFLICT(source_name, bundle_name, window_start, window_end, trigger_reason) DO UPDATE" in query
    assert "excluded.trigger_reason IN ('steady_overlap', 'operator_sync')" in query
    assert "THEN 'pending'" in query
    assert "attempt_count = CASE" in query
    assert "completed_at_ms = CASE" in query
    assert "RETURNING sync_window_id" in query
    assert params[1:6] == ("macrodata-cli", "macro-core", "2026-05-01", "2026-05-27", "bootstrap")


def test_macro_projection_dirty_target_methods_use_claim_done_error_contract() -> None:
    claim_source = inspect.getsource(MacroIntelRepository.claim_macro_projection_dirty_targets)
    done_source = inspect.getsource(MacroIntelRepository.mark_macro_projection_dirty_targets_done)
    error_source = inspect.getsource(MacroIntelRepository.mark_macro_projection_dirty_targets_error)

    assert "FROM macro_projection_dirty_targets" in claim_source
    assert "FOR UPDATE SKIP LOCKED" in claim_source
    assert "leased_until_ms" in claim_source
    assert "lease_owner" in claim_source
    assert "attempt_count = macro_projection_dirty_targets.attempt_count + 1" in claim_source
    assert "DELETE FROM macro_projection_dirty_targets" in done_source
    assert "payload_hash" in done_source
    assert "attempt_count" in done_source
    assert "UPDATE macro_projection_dirty_targets" in error_source
    assert "last_error" in error_source
    assert "worker_queue_terminal_events" in error_source or "terminalize_source_row" in error_source
    assert "max_attempts" in error_source


def test_macro_projection_dirty_target_default_writes_require_connection_transaction_before_sql() -> None:
    conn = DirtyTargetConnectionWithoutTransaction()
    repo = MacroIntelRepository(conn)

    with pytest.raises(RuntimeError, match="macro_projection_dirty_target_transaction_required"):
        repo.claim_macro_projection_dirty_targets(
            projection_name="macro_view",
            projection_version="macro_regime_v4",
            limit=10,
            lease_ms=30_000,
            lease_owner="worker-1",
            now_ms=1_779_000_000_000,
        )

    assert conn.executions == []


@pytest.mark.parametrize("operation", ("current", "changes"))
def test_macro_projection_dirty_target_default_enqueues_require_connection_transaction_before_sql(
    operation: str,
) -> None:
    conn = DirtyTargetConnectionWithoutTransaction()
    repo = MacroIntelRepository(conn)

    with pytest.raises(RuntimeError, match="macro_projection_dirty_target_transaction_required"):
        if operation == "current":
            repo.enqueue_macro_projection_dirty_target(
                projection_name="macro_view",
                projection_version="macro_regime_v4",
                now_ms=1_779_000_000_000,
                reason="macro_observations_imported",
            )
        else:
            repo.enqueue_macro_projection_dirty_targets_for_changes(
                changed_observations=[{"concept_key": "liquidity:sofr", "observed_at": "2026-05-28"}],
                projection_name="macro_view",
                projection_version="macro_regime_v4",
                now_ms=1_779_000_000_000,
                reason="macro_observations_changed",
            )

    assert conn.executions == []


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        pytest.param({"limit": -1}, "macro_projection_dirty_target_claim_limit_required", id="limit-negative"),
        pytest.param({"limit": True}, "macro_projection_dirty_target_claim_limit_required", id="limit-bool"),
        pytest.param({"limit": "10"}, "macro_projection_dirty_target_claim_limit_required", id="limit-string"),
        pytest.param({"lease_ms": 0}, "macro_projection_dirty_target_claim_lease_ms_required", id="lease-zero"),
        pytest.param({"lease_ms": True}, "macro_projection_dirty_target_claim_lease_ms_required", id="lease-bool"),
        pytest.param(
            {"lease_ms": "30000"},
            "macro_projection_dirty_target_claim_lease_ms_required",
            id="lease-string",
        ),
    ],
)
def test_macro_projection_dirty_target_claim_rejects_malformed_parameters_before_transaction(
    overrides: dict[str, object],
    error_code: str,
) -> None:
    conn = DirtyTargetConnection()
    repo = MacroIntelRepository(conn)
    params = {
        "projection_name": "macro_view",
        "projection_version": "macro_regime_v4",
        "limit": 10,
        "lease_ms": 30_000,
        "lease_owner": "worker-1",
        "now_ms": 1_779_000_000_000,
    }
    params.update(overrides)

    with pytest.raises(ValueError, match=error_code):
        repo.claim_macro_projection_dirty_targets(**params)

    assert conn.events == []
    assert conn.executions == []
    assert conn.commit_count == 0


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        pytest.param({"retry_ms": 0}, "macro_projection_dirty_target_retry_ms_required", id="retry-zero"),
        pytest.param({"retry_ms": True}, "macro_projection_dirty_target_retry_ms_required", id="retry-bool"),
        pytest.param({"retry_ms": "5000"}, "macro_projection_dirty_target_retry_ms_required", id="retry-string"),
        pytest.param(
            {"max_attempts": 0},
            "macro_projection_dirty_target_max_attempts_required",
            id="attempts-zero",
        ),
        pytest.param(
            {"max_attempts": True},
            "macro_projection_dirty_target_max_attempts_required",
            id="attempts-bool",
        ),
        pytest.param(
            {"max_attempts": "3"},
            "macro_projection_dirty_target_max_attempts_required",
            id="attempts-string",
        ),
    ],
)
def test_macro_projection_dirty_target_error_rejects_malformed_parameters_before_transaction(
    overrides: dict[str, object],
    error_code: str,
) -> None:
    conn = DirtyTargetConnection()
    repo = MacroIntelRepository(conn)
    params = {
        "error": "projection failed",
        "retry_ms": 5_000,
        "max_attempts": 3,
        "worker_name": "macro_view_projection",
        "now_ms": 1_779_000_000_002,
    }
    params.update(overrides)

    with pytest.raises(ValueError, match=error_code):
        repo.mark_macro_projection_dirty_targets_error([_dirty_target_claim()], **params)

    assert conn.events == []
    assert conn.executions == []
    assert conn.commit_count == 0


def test_macro_projection_dirty_target_default_writes_use_connection_transaction_without_manual_commit() -> None:
    claim = _dirty_target_claim()
    conn = DirtyTargetConnection(rows=[claim], rowcount=1)
    repo = MacroIntelRepository(conn)

    claimed = repo.claim_macro_projection_dirty_targets(
        projection_name="macro_view",
        projection_version="macro_regime_v4",
        limit=10,
        lease_ms=30_000,
        lease_owner="worker-1",
        now_ms=1_779_000_000_000,
    )
    done_count = repo.mark_macro_projection_dirty_targets_done(claimed, now_ms=1_779_000_000_001)
    error_count = repo.mark_macro_projection_dirty_targets_error(
        claimed,
        error="projection failed",
        retry_ms=5_000,
        max_attempts=3,
        worker_name="macro_view_projection",
        now_ms=1_779_000_000_002,
    )

    assert claimed == [claim]
    assert done_count == 1
    assert error_count == 1
    assert conn.events == [
        "begin",
        "execute",
        "commit",
        "begin",
        "execute",
        "commit",
        "begin",
        "execute",
        "commit",
    ]
    assert conn.commit_count == 0


def test_macro_projection_dirty_target_caller_owned_writes_do_not_open_inner_transaction() -> None:
    claim = _dirty_target_claim()
    conn = DirtyTargetConnection(rows=[claim], rowcount=1)
    repo = MacroIntelRepository(conn)

    claimed = repo.claim_macro_projection_dirty_targets(
        projection_name="macro_view",
        projection_version="macro_regime_v4",
        limit=10,
        lease_ms=30_000,
        lease_owner="worker-1",
        now_ms=1_779_000_000_000,
        commit=False,
    )
    repo.mark_macro_projection_dirty_targets_done(claimed, now_ms=1_779_000_000_001, commit=False)
    repo.mark_macro_projection_dirty_targets_error(
        claimed,
        error="projection failed",
        retry_ms=5_000,
        max_attempts=3,
        worker_name="macro_view_projection",
        now_ms=1_779_000_000_002,
        commit=False,
    )

    assert claimed == [claim]
    assert conn.events == ["execute", "execute", "execute"]
    assert conn.commit_count == 0


def test_macro_projection_dirty_target_error_terminalizes_exhausted_claim() -> None:
    conn = DirtyTargetTerminalizingConnection()
    repo = MacroIntelRepository(conn)
    claim = _dirty_target_claim()

    changed = repo.mark_macro_projection_dirty_targets_error(
        [claim],
        error="projection failed",
        retry_ms=5_000,
        max_attempts=1,
        worker_name="macro_view_projection",
        now_ms=1_779_000_000_002,
        commit=False,
    )

    assert changed == 1
    assert "DELETE FROM macro_projection_dirty_targets queue" in conn.sql_log[0]
    assert any("INSERT INTO worker_queue_terminal_events" in sql for sql in conn.sql_log)
    assert conn.terminal_params["worker_name"] == "macro_view_projection"
    assert conn.terminal_params["source_table"] == "macro_projection_dirty_targets"
    assert conn.terminal_params["target_key"] == "macro_view:macro_regime_v4:current:current"
    assert conn.terminal_params["final_status"] == "terminal"
    assert conn.terminal_params["final_reason"] == ("macro_view_projection_retry_budget_exhausted: projection failed")
    assert conn.terminal_params["final_reason_bucket"] == "retry_budget_exhausted"
    assert conn.terminal_params["attempt_count"] == 1
    assert conn.terminal_params["payload_hash"] == "sha256:dirty"


def test_enqueue_macro_projection_dirty_target_coalesces_current_target() -> None:
    conn = FakeConnection(rows=[{"inserted": 1}], rowcount=1)
    repo = MacroIntelRepository(conn)

    inserted = repo.enqueue_macro_projection_dirty_target(
        projection_name="macro_view",
        projection_version="macro_regime_v4",
        now_ms=1_779_000_000_000,
        due_at_ms=1_779_000_000_000,
        reason="macro_observations_imported",
        commit=False,
    )

    assert inserted == 1
    query, params = conn.executions[0]
    assert "INSERT INTO macro_projection_dirty_targets" in query
    assert "ON CONFLICT (projection_name, projection_version, target_kind, target_id) DO UPDATE" in query
    assert params["projection_name"] == "macro_view"
    assert params["projection_version"] == "macro_regime_v4"
    assert params["target_kind"] == "current"
    assert params["target_id"] == "current"
    assert str(params["payload_hash"]).startswith("sha256:")


def test_macro_projection_dirty_payload_hash_rejects_legacy_payload_shapes() -> None:
    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        _macro_projection_dirty_payload_hash(
            projection_name="macro_view",
            projection_version="macro_regime_v4",
            target_kind="current",
            target_id="current",
            reason={123: "legacy"},  # type: ignore[arg-type]
            source_watermark_ms=1_779_000_000_000,
        )


def test_upsert_observation_updates_only_when_fact_payload_hash_changes() -> None:
    source = inspect.getsource(MacroIntelRepository.upsert_observation)
    normalized_source = " ".join(source.split())

    assert "fact_payload_hash" in source
    assert "IS DISTINCT FROM excluded.fact_payload_hash" in source
    assert "RETURNING" in source
    assert "status" in source
    assert "noop" in source
    assert "ingested_at_ms = excluded.ingested_at_ms" in source
    assert "WHERE macro_observations.fact_payload_hash IS DISTINCT FROM excluded.fact_payload_hash" in normalized_source


def test_upsert_observation_requires_explicit_data_quality_without_default_ok() -> None:
    source = inspect.getsource(MacroIntelRepository.upsert_observation)

    assert 'observation.get("data_quality") or "ok"' not in source
    assert '_required_observation_text(observation, "data_quality")' in source


def test_upsert_macro_daily_brief_is_stable_key_payload_hash_read_model() -> None:
    source = inspect.getsource(MacroIntelRepository.upsert_macro_daily_brief)
    hash_source = inspect.getsource(_macro_daily_brief_payload_hash)
    normalized_source = " ".join(source.split())

    assert "INSERT INTO macro_daily_briefs" in source
    assert "ON CONFLICT(brief_key) DO UPDATE" in source
    assert "payload_hash" in source
    assert "RETURNING true AS changed" in source
    assert "WHERE macro_daily_briefs.payload_hash IS DISTINCT FROM excluded.payload_hash" in normalized_source
    assert '"computed_at_ms"' in hash_source
    assert "if key not in" in hash_source
    assert "stable_current_payload_hash" in hash_source
    assert "postgres_safe_json" not in hash_source


@pytest.mark.parametrize(
    ("rowcount", "rows", "expected_error"),
    (
        (None, [{"changed": True}], "macro_intel_repository_rowcount_required"),
        (True, [{"changed": True}], "macro_intel_repository_rowcount_invalid"),
        (False, [{"changed": True}], "macro_intel_repository_rowcount_invalid"),
        ("1", [{"changed": True}], "macro_intel_repository_rowcount_invalid"),
        (-1, [{"changed": True}], "macro_intel_repository_rowcount_invalid"),
        (2, [{"changed": True}], "macro_intel_repository_rowcount_invalid"),
        (0, [{"changed": True}], "macro_intel_repository_rowcount_invalid"),
        (1, [], "macro_intel_repository_rowcount_invalid"),
    ),
)
def test_upsert_macro_daily_brief_requires_returning_rowcount_match(
    rowcount: object,
    rows: list[dict[str, object]],
    expected_error: str,
) -> None:
    conn = DailyBriefReturningConnection(rows=rows, rowcount=rowcount)
    repo = MacroIntelRepository(conn)

    with pytest.raises(TypeError, match=expected_error):
        repo.upsert_macro_daily_brief(_daily_brief(), now_ms=1_779_000_000_000)


def test_macro_daily_brief_payload_hash_rejects_legacy_payload_keys() -> None:
    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        _macro_daily_brief_payload_hash(
            {
                "brief_key": "assets_today",
                "projection_version": "macro_regime_v4",
                "status": "ready",
                "headline": "Liquidity improving",
                "payload_json": {"status": "ready"},
                123: "legacy",
            }
        )


def test_record_run_methods_write_hard_cut_observation_counts_and_watermarks() -> None:
    import_source = inspect.getsource(MacroIntelRepository.record_import_run)
    sync_source = inspect.getsource(MacroIntelRepository.record_macro_sync_run)

    for column_name in (
        "seen_observation_count",
        "inserted_observation_count",
        "changed_observation_count",
        "noop_observation_count",
    ):
        assert column_name in import_source
        assert column_name in sync_source
    for column_name in ("max_seen_observed_at", "min_changed_observed_at", "max_changed_observed_at"):
        assert column_name in sync_source


def test_enqueue_macro_projection_dirty_targets_for_changes_groups_by_concept_watermark() -> None:
    conn = FakeConnection(rows=[{"inserted": 1}], rowcount=1)
    repo = MacroIntelRepository(conn)

    inserted = repo.enqueue_macro_projection_dirty_targets_for_changes(
        changed_observations=[
            {"concept_key": "liquidity:sofr", "observed_at": "2026-05-27"},
            {"concept_key": "liquidity:sofr", "observed_at": "2026-05-28"},
        ],
        projection_name="macro_view",
        projection_version="macro_regime_v4",
        now_ms=1_779_000_000_000,
        due_at_ms=1_779_000_000_000,
        reason="macro_observations_changed",
        commit=False,
    )

    assert inserted == 1
    query, params = conn.executions[0]
    assert "INSERT INTO macro_projection_dirty_targets" in query
    assert "concept_key" in query
    assert "min_observed_at" in query
    assert "max_observed_at" in query
    assert "source_watermark_date" in query
    assert "target_kind" in query
    assert params["target_kinds"] == ["concept"]
    assert params["target_ids"] == ["liquidity:sofr"]
    assert params["concept_keys"] == ["liquidity:sofr"]
    assert params["min_observed_ats"] == [date(2026, 5, 27)]
    assert params["max_observed_ats"] == [date(2026, 5, 28)]
    assert params["source_watermark_dates"] == [date(2026, 5, 28)]
    assert str(params["payload_hashes"][0]).startswith("sha256:")


def test_macro_projection_dirty_change_payload_hash_rejects_legacy_payload_shapes() -> None:
    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        _macro_projection_dirty_change_payload_hash(
            projection_name="macro_view",
            projection_version="macro_regime_v4",
            concept_key="liquidity:sofr",
            min_observed_at=date(2026, 5, 27),
            max_observed_at=date(2026, 5, 28),
            source_watermark_date=date(2026, 5, 28),
            reason={123: "legacy"},  # type: ignore[arg-type]
        )


def test_retry_macro_sync_window_terminalizes_when_attempt_budget_is_exhausted() -> None:
    source = inspect.getsource(MacroIntelRepository.retry_macro_sync_window)
    normalized_source = " ".join(source.split())

    assert "CASE WHEN attempt_count >= max_attempts THEN 'failed' ELSE 'retryable' END" in normalized_source
    assert "completed_at_ms = CASE WHEN attempt_count >= max_attempts THEN %s ELSE completed_at_ms END" in (
        normalized_source
    )


def test_queue_summary_excludes_exhausted_retryable_windows_from_open_count() -> None:
    source = inspect.getsource(MacroIntelRepository.macro_sync_queue_summary)
    normalized_source = " ".join(source.split())

    assert "status IN ('pending', 'retryable') AND attempt_count < max_attempts" in normalized_source
    assert "expired_running_count" in source
    assert "expired_running_exhausted_count" in source
    assert "exhausted_count" in source


@pytest.mark.parametrize(
    "operation",
    (
        "complete_window",
        "retry_window",
        "fail_window",
        "update_sync_state",
        "rebuild_sync_state_delete",
        "rebuild_sync_state_upsert",
        "enqueue_dirty_current",
        "enqueue_dirty_changes",
        "dirty_done",
        "dirty_error",
    ),
)
def test_macro_repository_write_counts_require_cursor_rowcount(operation: str) -> None:
    conn = MacroRowcountConnection(rowcount=_ROWCOUNT_MISSING, operation=operation)

    with pytest.raises(TypeError, match="macro_intel_repository_rowcount_required"):
        _run_macro_rowcount_operation(MacroIntelRepository(conn), operation)


@pytest.mark.parametrize(
    "operation",
    (
        "complete_window",
        "retry_window",
        "fail_window",
        "update_sync_state",
        "rebuild_sync_state_delete",
        "rebuild_sync_state_upsert",
        "enqueue_dirty_current",
        "enqueue_dirty_changes",
        "dirty_done",
        "dirty_error",
    ),
)
@pytest.mark.parametrize("rowcount", (True, False, "1", None, -1))
def test_macro_repository_write_counts_reject_invalid_cursor_rowcount(operation: str, rowcount: Any) -> None:
    conn = MacroRowcountConnection(rowcount=rowcount, operation=operation)

    with pytest.raises(TypeError, match="macro_intel_repository_rowcount_invalid"):
        _run_macro_rowcount_operation(MacroIntelRepository(conn), operation)


@pytest.mark.parametrize(
    "operation",
    (
        "complete_window",
        "retry_window",
        "fail_window",
        "update_sync_state",
        "rebuild_sync_state_delete",
        "rebuild_sync_state_upsert",
    ),
)
def test_macro_single_row_write_counts_reject_multi_row_cursor_rowcount(operation: str) -> None:
    conn = MacroRowcountConnection(rowcount=2, operation=operation)

    with pytest.raises(TypeError, match="macro_intel_repository_rowcount_invalid"):
        _run_macro_rowcount_operation(MacroIntelRepository(conn), operation)


@pytest.mark.parametrize(
    ("operation", "expected_error"),
    (
        ("enqueue_window", "macro_intel_repository_rowcount_required"),
        ("claim_window", "macro_intel_repository_rowcount_required"),
        ("claim_window_by_id", "macro_intel_repository_rowcount_required"),
    ),
)
def test_macro_sync_window_returning_writes_require_cursor_rowcount(operation: str, expected_error: str) -> None:
    conn = MacroSyncWindowReturningConnection(rowcount=_ROWCOUNT_MISSING, rows=[_macro_sync_window_row()])

    with pytest.raises(TypeError, match=expected_error):
        _run_macro_sync_window_returning_operation(MacroIntelRepository(conn), operation)


@pytest.mark.parametrize(
    ("operation", "expected_error"),
    (
        ("enqueue_window", "macro_intel_repository_rowcount_invalid"),
        ("claim_window", "macro_intel_repository_rowcount_invalid"),
        ("claim_window_by_id", "macro_intel_repository_rowcount_invalid"),
    ),
)
@pytest.mark.parametrize("rowcount", (True, False, "1", None, -1, 2))
def test_macro_sync_window_returning_writes_reject_invalid_cursor_rowcount(
    operation: str,
    expected_error: str,
    rowcount: object,
) -> None:
    conn = MacroSyncWindowReturningConnection(rowcount=rowcount, rows=[_macro_sync_window_row()])

    with pytest.raises(TypeError, match=expected_error):
        _run_macro_sync_window_returning_operation(MacroIntelRepository(conn), operation)


@pytest.mark.parametrize("operation", ("claim_window", "claim_window_by_id"))
def test_macro_sync_window_claim_returning_rows_reject_rowcount_row_mismatch(operation: str) -> None:
    conn = MacroSyncWindowReturningConnection(rowcount=0, rows=[_macro_sync_window_row()])

    with pytest.raises(TypeError, match="macro_intel_repository_rowcount_invalid"):
        _run_macro_sync_window_returning_operation(MacroIntelRepository(conn), operation)


@pytest.mark.parametrize("operation", ("claim_window", "claim_window_by_id"))
def test_macro_sync_window_claim_returning_rows_accept_zero_row_noop(operation: str) -> None:
    conn = MacroSyncWindowReturningConnection(rowcount=0, rows=[])

    assert _run_macro_sync_window_returning_operation(MacroIntelRepository(conn), operation) is None


def test_macro_sync_window_enqueue_returning_row_requires_one_row() -> None:
    conn = MacroSyncWindowReturningConnection(rowcount=0, rows=[])

    with pytest.raises(TypeError, match="macro_intel_repository_rowcount_invalid"):
        _run_macro_sync_window_returning_operation(MacroIntelRepository(conn), "enqueue_window")


class FakeConnection:
    def __init__(self, *, rows: list[dict[str, object]] | None = None, rowcount: int = 1) -> None:
        self.rows = rows or []
        self.rowcount = rowcount
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...] = ()) -> FakeCursor:
        self.executions.append((query, params))
        return FakeCursor(self.rows, rowcount=self.rowcount)


class FakeCursor:
    def __init__(self, rows: list[dict[str, object]], *, rowcount: int) -> None:
        self.rows = rows
        self.rowcount = rowcount

    def fetchone(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None


class DailyBriefReturningConnection:
    def __init__(self, *, rows: list[dict[str, object]], rowcount: object) -> None:
        self.rows = rows
        self.rowcount = rowcount
        self.executions: list[tuple[str, object]] = []

    def execute(self, query: str, params: object = ()) -> DailyBriefReturningCursor:
        self.executions.append((query, params))
        return DailyBriefReturningCursor(self.rows, rowcount=self.rowcount)


class DailyBriefReturningCursor:
    def __init__(self, rows: list[dict[str, object]], *, rowcount: object) -> None:
        self.rows = rows
        if rowcount is not None:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None


class DirtyTargetConnection:
    def __init__(self, *, rows: list[dict[str, object]] | None = None, rowcount: int = 1) -> None:
        self.rows = rows or []
        self.rowcount = rowcount
        self.executions: list[tuple[str, object]] = []
        self.events: list[str] = []
        self.commit_count = 0

    def execute(self, query: str, params: object = ()) -> DirtyTargetCursor:
        self.events.append("execute")
        self.executions.append((query, params))
        return DirtyTargetCursor(self.rows, rowcount=self.rowcount)

    def commit(self) -> None:
        self.commit_count += 1

    def transaction(self) -> DirtyTargetTransaction:
        return DirtyTargetTransaction(self)


class DirtyTargetConnectionWithoutTransaction(DirtyTargetConnection):
    def __getattribute__(self, name: str) -> object:
        if name == "transaction":
            raise AttributeError(name)
        return super().__getattribute__(name)


class DirtyTargetTransaction:
    def __init__(self, conn: DirtyTargetConnection) -> None:
        self.conn = conn

    def __enter__(self) -> DirtyTargetTransaction:
        self.conn.events.append("begin")
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        self.conn.events.append("rollback" if exc_type is not None else "commit")
        return False


class DirtyTargetCursor:
    def __init__(self, rows: list[dict[str, object]], *, rowcount: int) -> None:
        self.rows = rows
        self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows


class DirtyTargetTerminalizingConnection:
    def __init__(self) -> None:
        self.sql_log: list[str] = []
        self.terminal_params: dict[str, object] = {}

    def execute(self, query: str, params: object = ()) -> DirtyTargetTerminalizingCursor:
        text = str(query)
        self.sql_log.append(text)
        if "DELETE FROM macro_projection_dirty_targets queue" in text:
            return DirtyTargetTerminalizingCursor(rowcount=1, rows=[_dirty_target_claim()])
        if "SELECT terminal_generation" in text:
            return DirtyTargetTerminalizingCursor(rowcount=0, row=None)
        if "SELECT COALESCE(MAX(terminal_generation), 0) + 1 AS terminal_generation" in text:
            return DirtyTargetTerminalizingCursor(rowcount=1, row={"terminal_generation": 1})
        if "INSERT INTO worker_queue_terminal_events" in text:
            if isinstance(params, dict):
                self.terminal_params = dict(params)
            return DirtyTargetTerminalizingCursor(rowcount=1, row=self.terminal_params)
        raise AssertionError(f"unexpected SQL: {text}")


class DirtyTargetTerminalizingCursor:
    def __init__(
        self,
        *,
        rowcount: int,
        rows: list[dict[str, object]] | None = None,
        row: dict[str, object] | None = None,
    ) -> None:
        self.rowcount = rowcount
        self.rows = rows or []
        self.row = row

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows

    def fetchone(self) -> dict[str, object] | None:
        return self.row


def _dirty_target_claim() -> dict[str, object]:
    return {
        "projection_name": "macro_view",
        "projection_version": "macro_regime_v4",
        "target_kind": "current",
        "target_id": "current",
        "payload_hash": "sha256:dirty",
        "lease_owner": "worker-1",
        "attempt_count": 1,
    }


def _daily_brief() -> dict[str, object]:
    return {
        "brief_key": "assets_today",
        "projection_version": "macro_regime_v4",
        "brief_date": "2026-05-27",
        "asof_date": "2026-05-27",
        "status": "ready",
        "headline": "Liquidity improving",
        "sections": [],
    }


_ROWCOUNT_MISSING = object()


class MacroRowcountConnection:
    def __init__(self, *, rowcount: object, operation: str) -> None:
        self.rowcount = rowcount
        self.operation = operation
        self.execute_index = 0
        self.executions: list[tuple[str, object]] = []

    def execute(self, query: str, params: object = ()) -> MacroRowcountCursor:
        self.execute_index += 1
        self.executions.append((query, params))
        row = self._row_for_query(query)
        if self.rowcount is _ROWCOUNT_MISSING:
            return MacroRowcountCursor([row] if row is not None else [])
        return MacroRowcountCursor([row] if row is not None else [], rowcount=self.rowcount)

    def _row_for_query(self, query: str) -> dict[str, object] | None:
        if self.operation == "rebuild_sync_state_upsert" and "SELECT MAX" in query:
            return {"max_observed_at": date(2026, 5, 20)}
        return None


class MacroRowcountCursor:
    def __init__(self, rows: list[dict[str, object]], *, rowcount: object = _ROWCOUNT_MISSING) -> None:
        self.rows = rows
        if rowcount is not _ROWCOUNT_MISSING:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None


class MacroSyncWindowReturningConnection:
    def __init__(self, *, rowcount: object, rows: list[dict[str, object]]) -> None:
        self.rowcount = rowcount
        self.rows = rows
        self.executions: list[tuple[str, object]] = []

    def execute(self, query: str, params: object = ()) -> MacroSyncWindowReturningCursor:
        self.executions.append((query, params))
        return MacroSyncWindowReturningCursor(self.rows, rowcount=self.rowcount)


class MacroSyncWindowReturningCursor:
    def __init__(self, rows: list[dict[str, object]], *, rowcount: object) -> None:
        self.rows = rows
        if rowcount is not _ROWCOUNT_MISSING:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None


def _run_macro_rowcount_operation(repository: MacroIntelRepository, operation: str) -> object:
    if operation == "complete_window":
        return repository.complete_macro_sync_window(
            sync_window_id="window-1",
            lease_owner="macro_sync",
            attempt_count=1,
            sync_run_id="run-1",
            completed_at_ms=1_779_000_000_000,
        )
    if operation == "retry_window":
        return repository.retry_macro_sync_window(
            sync_window_id="window-1",
            lease_owner="macro_sync",
            attempt_count=1,
            sync_run_id="run-1",
            error_code="provider_error",
            error_message="provider failed",
            retry_delay_ms=30_000,
            now_ms=1_779_000_000_000,
        )
    if operation == "fail_window":
        return repository.fail_macro_sync_window(
            sync_window_id="window-1",
            lease_owner="macro_sync",
            attempt_count=1,
            sync_run_id="run-1",
            error_code="provider_error",
            error_message="provider failed",
            now_ms=1_779_000_000_000,
        )
    if operation == "update_sync_state":
        return repository.update_macro_sync_state(
            source_name="macrodata-cli",
            bundle_name="macro-core",
            max_observed_at=date(2026, 5, 20),
            now_ms=1_779_000_000_000,
        )
    if operation == "rebuild_sync_state_delete":
        return repository.rebuild_macro_sync_state(
            source_name="fred",
            bundle_name="empty",
            now_ms=1_779_000_000_000,
        )
    if operation == "rebuild_sync_state_upsert":
        return repository.rebuild_macro_sync_state(
            source_name="fred",
            bundle_name="macro-core",
            now_ms=1_779_000_000_000,
        )
    if operation == "enqueue_dirty_current":
        return repository.enqueue_macro_projection_dirty_target(
            projection_name="macro_view",
            projection_version="macro_regime_v4",
            now_ms=1_779_000_000_000,
            reason="macro_observations_imported",
            commit=False,
        )
    if operation == "enqueue_dirty_changes":
        return repository.enqueue_macro_projection_dirty_targets_for_changes(
            changed_observations=[{"concept_key": "rates:dgs10", "observed_at": "2026-05-20"}],
            projection_name="macro_view",
            projection_version="macro_regime_v4",
            now_ms=1_779_000_000_000,
            reason="macro_observations_changed",
            commit=False,
        )
    if operation == "dirty_done":
        return repository.mark_macro_projection_dirty_targets_done(
            [_dirty_target_claim()],
            now_ms=1_779_000_000_000,
            commit=False,
        )
    if operation == "dirty_error":
        return repository.mark_macro_projection_dirty_targets_error(
            [_dirty_target_claim()],
            error="projection failed",
            retry_ms=30_000,
            max_attempts=3,
            worker_name="macro_view_projection",
            now_ms=1_779_000_000_000,
            commit=False,
        )
    raise AssertionError(operation)


def _run_macro_sync_window_returning_operation(repository: MacroIntelRepository, operation: str) -> object:
    if operation == "enqueue_window":
        return repository.enqueue_macro_sync_window(
            source_name="macrodata-cli",
            bundle_name="macro-core",
            window_start="2026-05-01",
            window_end="2026-05-27",
            trigger_reason="bootstrap",
            priority=25,
            due_at_ms=1_779_000_000_000,
            max_attempts=8,
            now_ms=1_779_000_000_000,
        )
    if operation == "claim_window":
        return repository.claim_macro_sync_window(
            lease_owner="macro_sync",
            lease_ms=30_000,
            now_ms=1_779_000_000_000,
        )
    if operation == "claim_window_by_id":
        return repository.claim_macro_sync_window_by_id(
            sync_window_id="macro-sync-window:abc",
            lease_owner="macro_sync",
            lease_ms=30_000,
            now_ms=1_779_000_000_000,
        )
    raise AssertionError(operation)


def _macro_sync_window_row() -> dict[str, object]:
    return {
        "sync_window_id": "macro-sync-window:abc",
        "source_name": "macrodata-cli",
        "bundle_name": "macro-core",
        "status": "running",
        "attempt_count": 1,
        "max_attempts": 8,
    }
