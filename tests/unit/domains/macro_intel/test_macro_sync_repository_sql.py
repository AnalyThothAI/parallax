from __future__ import annotations

import inspect

from gmgn_twitter_intel.domains.macro_intel.repositories.macro_intel_repository import (
    MacroIntelRepository,
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
    "macro_observations_max_observed_at",
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
    assert "ORDER BY priority ASC, due_at_ms ASC, updated_at_ms ASC, sync_window_id ASC" in normalized_source
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
