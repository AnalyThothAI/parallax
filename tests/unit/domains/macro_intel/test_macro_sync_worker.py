from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from parallax.domains.macro_intel.services.macro_sync_types import MacroSyncRunSummary


def test_worker_idle_claims_no_window_and_does_not_call_runner() -> None:
    from parallax.domains.macro_intel.runtime.macro_sync_worker import MacroSyncWorker

    service = FakeService(result=None, enqueue_summary={"due_count": 0, "open_count": 0})
    worker = MacroSyncWorker(
        name="macro_sync",
        settings=SimpleNamespace(enabled=True),
        db=object(),
        telemetry=object(),
        settings_root=object(),
        wake_bus=object(),
        service_factory=lambda: service,
    )

    result = worker.run_once_sync(now_ms=1_779_000_000_000)

    assert result.processed == 0
    assert result.skipped == 1
    assert result.failed == 0
    assert result.notes["claimed"] == 0
    assert result.notes["provider_calls"] == 0
    assert result.notes["imported_observation_count"] == 0
    assert service.calls == [
        ("enqueue_due_windows", {"now_ms": 1_779_000_000_000}),
        ("run_claimed_window_once", {"lease_owner": "macro_sync", "now_ms": 1_779_000_000_000}),
    ]


def test_worker_success_and_failure_results_reflect_sync_summary() -> None:
    from parallax.domains.macro_intel.runtime.macro_sync_worker import MacroSyncWorker

    success = MacroSyncRunSummary(
        sync_run_id="sync-run-ok",
        import_run_id="import-run-1",
        status="ok",
        observations_count=1,
        imported_observation_count=1,
        asof_date=date(2026, 5, 27),
        max_observed_at=date(2026, 5, 27),
        diagnostics={},
    )
    worker = MacroSyncWorker(
        name="macro_sync",
        settings=SimpleNamespace(enabled=True),
        db=object(),
        telemetry=object(),
        settings_root=object(),
        wake_bus=object(),
        service_factory=lambda: FakeService(result=success),
    )

    result = worker.run_once_sync(now_ms=1_779_000_000_000)

    assert result.processed == 1
    assert result.failed == 0
    assert result.notes["claimed"] == 1
    assert result.notes["provider_calls"] == 1
    assert result.notes["sync_run_id"] == "sync-run-ok"
    assert result.notes["max_observed_at"] == "2026-05-27"

    failure = MacroSyncRunSummary(
        sync_run_id="sync-run-fail",
        import_run_id=None,
        status="retryable_error",
        observations_count=0,
        imported_observation_count=0,
        asof_date=None,
        max_observed_at=None,
        diagnostics={},
    )
    failed_worker = MacroSyncWorker(
        name="macro_sync",
        settings=SimpleNamespace(enabled=True),
        db=object(),
        telemetry=object(),
        settings_root=object(),
        wake_bus=object(),
        service_factory=lambda: FakeService(result=failure),
    )

    failed_result = failed_worker.run_once_sync(now_ms=1_779_000_000_000)

    assert failed_result.processed == 0
    assert failed_result.failed == 1
    assert failed_result.notes["status"] == "retryable_error"


def test_worker_counts_successful_empty_window_as_processed() -> None:
    from parallax.domains.macro_intel.runtime.macro_sync_worker import MacroSyncWorker

    success = MacroSyncRunSummary(
        sync_run_id="sync-run-empty",
        import_run_id="import-run-empty",
        status="ok",
        observations_count=0,
        imported_observation_count=0,
        asof_date=date(2026, 5, 27),
        max_observed_at=None,
        diagnostics={},
    )
    worker = MacroSyncWorker(
        name="macro_sync",
        settings=SimpleNamespace(enabled=True),
        db=object(),
        telemetry=object(),
        settings_root=object(),
        wake_bus=object(),
        service_factory=lambda: FakeService(result=success),
    )

    result = worker.run_once_sync(now_ms=1_779_000_000_000)

    assert result.processed == 1
    assert result.failed == 0
    assert result.notes["status"] == "ok"
    assert result.notes["imported_observation_count"] == 0


class FakeService:
    def __init__(
        self,
        *,
        result: MacroSyncRunSummary | None,
        enqueue_summary: dict[str, object] | None = None,
    ) -> None:
        self.result = result
        self.enqueue_summary = enqueue_summary or {}
        self.calls: list[tuple[str, dict[str, object]]] = []

    def enqueue_due_windows(self, *, now_ms: int | None = None) -> dict[str, object]:
        self.calls.append(("enqueue_due_windows", {"now_ms": now_ms}))
        return self.enqueue_summary

    def run_claimed_window_once(self, *, lease_owner: str, now_ms: int | None = None) -> MacroSyncRunSummary | None:
        self.calls.append(("run_claimed_window_once", {"lease_owner": lease_owner, "now_ms": now_ms}))
        return self.result
