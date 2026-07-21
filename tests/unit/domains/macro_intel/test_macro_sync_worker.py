from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from parallax.domains.macro_intel.services.macro_sync_types import MacroSyncRunSummary
from parallax.platform.config.settings import MacroSyncWorkerSettings


def test_worker_idle_claims_no_window_and_does_not_call_runner() -> None:
    from parallax.domains.macro_intel.runtime.macro_sync_worker import MacroSyncWorker

    service = FakeService(result=None, enqueue_summary={"due_count": 0, "open_count": 0})
    worker = MacroSyncWorker(
        name="macro_sync",
        settings=_macro_sync_settings(),
        db=object(),
        telemetry=object(),
        settings_root=_settings_root(),
        wake_emitter=object(),
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
        settings=_macro_sync_settings(),
        db=object(),
        telemetry=object(),
        settings_root=_settings_root(),
        wake_emitter=object(),
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
        settings=_macro_sync_settings(),
        db=object(),
        telemetry=object(),
        settings_root=_settings_root(),
        wake_emitter=object(),
        service_factory=lambda: FakeService(result=failure),
    )

    failed_result = failed_worker.run_once_sync(now_ms=1_779_000_000_000)

    assert failed_result.processed == 0
    assert failed_result.failed == 1
    assert failed_result.notes["status"] == "retryable_error"


def test_worker_drains_due_windows_up_to_batch_size() -> None:
    from parallax.domains.macro_intel.runtime.macro_sync_worker import MacroSyncWorker

    results = [
        MacroSyncRunSummary(
            sync_run_id=f"sync-run-{index}",
            import_run_id=f"import-run-{index}",
            status="ok",
            observations_count=1,
            imported_observation_count=1,
            asof_date=date(2026, 5, 25 + index),
            max_observed_at=date(2026, 5, 25 + index),
            diagnostics={},
        )
        for index in range(1, 4)
    ]
    service = FakeService(results=results)
    worker = MacroSyncWorker(
        name="macro_sync",
        settings=_macro_sync_settings(batch_size=3),
        db=object(),
        telemetry=object(),
        settings_root=_settings_root(),
        wake_emitter=object(),
        service_factory=lambda: service,
    )

    result = worker.run_once_sync(now_ms=1_779_000_000_000)

    assert result.processed == 3
    assert result.failed == 0
    assert result.notes["claimed"] == 3
    assert result.notes["provider_calls"] == 3
    assert result.notes["imported_observation_count"] == 3
    assert result.notes["sync_run_ids"] == ["sync-run-1", "sync-run-2", "sync-run-3"]
    assert service.calls == [
        ("enqueue_due_windows", {"now_ms": 1_779_000_000_000}),
        ("run_claimed_window_once", {"lease_owner": "macro_sync", "now_ms": 1_779_000_000_000}),
        ("run_claimed_window_once", {"lease_owner": "macro_sync", "now_ms": 1_779_000_000_000}),
        ("run_claimed_window_once", {"lease_owner": "macro_sync", "now_ms": 1_779_000_000_000}),
    ]


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
        settings=_macro_sync_settings(),
        db=object(),
        telemetry=object(),
        settings_root=_settings_root(),
        wake_emitter=object(),
        service_factory=lambda: FakeService(result=success),
    )

    result = worker.run_once_sync(now_ms=1_779_000_000_000)

    assert result.processed == 1
    assert result.failed == 0
    assert result.notes["status"] == "ok"
    assert result.notes["imported_observation_count"] == 0


def test_worker_uses_formal_batch_size_without_hidden_cycle_cap() -> None:
    from parallax.domains.macro_intel.runtime.macro_sync_worker import MacroSyncWorker

    results = [
        MacroSyncRunSummary(
            sync_run_id=f"sync-run-{index}",
            import_run_id=f"import-run-{index}",
            status="ok",
            observations_count=1,
            imported_observation_count=1,
            asof_date=date(2026, 6, index),
            max_observed_at=date(2026, 6, index),
            diagnostics={},
        )
        for index in range(1, 8)
    ]
    service = FakeService(results=results)
    worker = MacroSyncWorker(
        name="macro_sync",
        settings=_macro_sync_settings(batch_size=7),
        db=object(),
        telemetry=object(),
        settings_root=_settings_root(),
        wake_emitter=object(),
        service_factory=lambda: service,
    )

    result = worker.run_once_sync(now_ms=1_779_000_000_000)

    assert result.processed == 7
    assert result.notes["claimed"] == 7
    assert [call[0] for call in service.calls].count("run_claimed_window_once") == 7


@pytest.mark.parametrize("batch_size", [0, True, "3"])
def test_worker_rejects_malformed_batch_size_before_claim_loop(batch_size: object) -> None:
    from parallax.domains.macro_intel.runtime.macro_sync_worker import MacroSyncWorker

    service = FakeService(result=None, enqueue_summary={"due_count": 1, "open_count": 1})
    worker = MacroSyncWorker(
        name="macro_sync",
        settings=SimpleNamespace(enabled=True, batch_size=batch_size),
        db=object(),
        telemetry=object(),
        settings_root=_settings_root(),
        wake_emitter=object(),
        service_factory=lambda: service,
    )

    with pytest.raises(ValueError, match="macro_sync_batch_size_required"):
        worker.run_once_sync(now_ms=1_779_000_000_000)

    assert service.calls == [("enqueue_due_windows", {"now_ms": 1_779_000_000_000})]


def _macro_sync_settings(**overrides: object) -> MacroSyncWorkerSettings:
    payload = {
        "enabled": True,
        "batch_size": 1,
        **overrides,
    }
    return MacroSyncWorkerSettings(**payload)


def _settings_root() -> object:
    return object()


class FakeService:
    def __init__(
        self,
        *,
        result: MacroSyncRunSummary | None = None,
        results: list[MacroSyncRunSummary | None] | None = None,
        enqueue_summary: dict[str, object] | None = None,
    ) -> None:
        self.result = result
        self.results = list(results) if results is not None else None
        self.enqueue_summary = enqueue_summary or {}
        self.calls: list[tuple[str, dict[str, object]]] = []

    def enqueue_due_windows(self, *, now_ms: int | None = None) -> dict[str, object]:
        self.calls.append(("enqueue_due_windows", {"now_ms": now_ms}))
        return self.enqueue_summary

    def run_claimed_window_once(self, *, lease_owner: str, now_ms: int | None = None) -> MacroSyncRunSummary | None:
        self.calls.append(("run_claimed_window_once", {"lease_owner": lease_owner, "now_ms": now_ms}))
        if self.results is not None:
            return self.results.pop(0) if self.results else None
        return self.result
