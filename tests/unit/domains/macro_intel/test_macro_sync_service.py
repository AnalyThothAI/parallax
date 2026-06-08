from __future__ import annotations

import json
from datetime import date, datetime
from types import TracebackType

from parallax.integrations.macrodata.runner import MacrodataBundleRunResult, MacrodataRunnerError

NOW_MS = 1_779_000_000_000

ENVELOPE = {
    "ok": True,
    "data": {
        "snapshot": {
            "bundle": "macro-core",
            "asof": "2026-05-27",
            "observations": [
                {
                    "series_key": "nyfed:SOFR",
                    "provider": "nyfed",
                    "observed_at": "2026-05-27",
                    "value": 3.51,
                    "unit": "percent",
                    "frequency": "daily",
                    "source_ts": "2026-05-27",
                    "data_quality": "ok",
                }
            ],
            "coverage": {"requested": 1, "available": 1},
            "missing_series": [],
            "series_errors": [],
            "data_quality": "ok",
            "reason_codes": [],
        }
    },
}


def test_sync_service_date_contract_accepts_only_date_and_yyyy_mm_dd_text() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import _to_date

    assert _to_date(date(2026, 5, 28)) == date(2026, 5, 28)
    assert _to_date("2026-05-28") == date(2026, 5, 28)
    assert _to_date(None) is None
    assert _to_date(datetime(2026, 5, 28)) is None
    assert _to_date("20260528") is None
    assert _to_date("2026-W22-4") is None
    assert _to_date("2026-05-28T00:00:00Z") is None


def test_sync_service_idle_claims_no_window_and_does_not_call_runner() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    repo = FakeMacroIntelRepository(claimed_window=None)
    runner = FakeRunner()
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=runner,
        wake_bus=FakeWakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    assert service.run_claimed_window_once(lease_owner="macro_sync") is None
    assert runner.calls == []
    assert repo.sync_runs == []


def test_sync_service_claims_window_before_provider_io() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    events: list[str] = []
    repo = FakeMacroIntelRepository(claimed_window=_window(), events=events)
    runner = FakeRunner(events=events)
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo, events=events),
        runner=runner,
        wake_bus=FakeWakeBus(events=events),
        clock_ms=lambda: NOW_MS,
    )

    service.run_claimed_window_once(lease_owner="macro_sync")

    assert events.index("claim") < events.index("session-close")
    assert events.index("session-close") < events.index("runner")
    assert events.index("runner") < events.index("transaction-commit")


def test_sync_service_import_success_writes_facts_completes_window_and_wakes_projection() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    events: list[str] = []
    repo = FakeMacroIntelRepository(claimed_window=_window(), events=events)
    wake_bus = FakeWakeBus(events=events)
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo, events=events),
        runner=FakeRunner(events=events),
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "ok"
    assert result.imported_observation_count == 1
    assert repo.observations[0]["series_key"] == "nyfed:SOFR"
    assert repo.import_runs[0]["bundle_name"] == "macro-core"
    assert repo.sync_runs[0]["import_run_id"] == repo.import_runs[0]["run_id"]
    assert repo.completed_windows == [
        {
            "sync_window_id": "window-1",
            "lease_owner": "macro_sync",
            "attempt_count": 1,
            "sync_run_id": result.sync_run_id,
            "completed_at_ms": NOW_MS,
        }
    ]
    assert repo.enqueued_dirty_targets == [
        {
            "changed_observations": [
                {
                        "observation_id": "observation-1",
                        "status": "inserted",
                        "concept_key": "liquidity:sofr",
                        "observed_at": date(2026, 5, 27),
                        "fact_payload_hash": "hash-1",
                    }
                ],
            "projection_name": "macro_view",
            "projection_version": "macro_regime_v4",
            "now_ms": NOW_MS,
            "due_at_ms": NOW_MS,
            "reason": "macro_observations_changed",
            "commit": False,
        }
    ]
    assert wake_bus.notifications == [
        {"count": 1, "max_observed_at": "2026-05-27", "asof_date": "2026-05-27"}
    ]
    assert events.index("transaction-commit") < events.index("wake")


def test_sync_service_empty_import_does_not_enqueue_projection_dirty_target() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    repo = FakeMacroIntelRepository(claimed_window=_window())
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=FakeRunner(envelope=_empty_envelope()),
        wake_bus=FakeWakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.imported_observation_count == 0
    assert repo.enqueued_dirty_targets == []


def test_sync_service_noop_overlap_records_seen_and_does_not_wake_or_dirty() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    repo = FakeMacroIntelRepository(claimed_window=_window(), upsert_statuses=["noop"])
    wake_bus = FakeWakeBus()
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=FakeRunner(),
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.seen_observation_count == 1
    assert result.inserted_observation_count == 0
    assert result.changed_observation_count == 0
    assert result.noop_observation_count == 1
    assert result.imported_observation_count == 0
    assert repo.sync_runs[0]["seen_observation_count"] == 1
    assert repo.enqueued_dirty_targets == []
    assert wake_bus.notifications == []


def test_sync_service_wake_failure_preserves_committed_success() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    events: list[str] = []
    repo = FakeMacroIntelRepository(claimed_window=_window(), events=events)
    wake_bus = FakeWakeBus(events=events, fail_notify=True)
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo, events=events),
        runner=FakeRunner(events=events),
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "ok"
    assert repo.observations[0]["series_key"] == "nyfed:SOFR"
    assert repo.sync_runs[0]["status"] == "ok"
    assert repo.completed_windows[0]["sync_window_id"] == "window-1"
    assert repo.retry_windows == []
    assert repo.failed_windows == []
    assert events.index("transaction-commit") < events.index("wake")


def test_sync_service_stale_completion_rolls_back_facts_and_does_not_wake() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    events: list[str] = []
    repo = FakeMacroIntelRepository(claimed_window=_window(), events=events, complete_result=False)
    wake_bus = FakeWakeBus(events=events)
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo, events=events),
        runner=FakeRunner(events=events),
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "stale_claim"
    assert repo.observations == []
    assert repo.import_runs == []
    assert repo.sync_runs == []
    assert wake_bus.notifications == []
    assert "transaction-rollback" in events


def test_sync_service_provider_failure_records_retry_without_fabricating_facts() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    repo = FakeMacroIntelRepository(claimed_window=_window())
    runner = FakeRunner(error=MacrodataRunnerError("provider failed", diagnostics={"error_code": "provider_down"}))
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=runner,
        wake_bus=FakeWakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "retryable_error"
    assert repo.observations == []
    assert repo.import_runs == []
    assert repo.sync_runs[0]["status"] == "retryable_error"
    assert repo.retry_windows[0]["error_code"] == "provider_down"


def test_sync_service_provider_failure_at_attempt_budget_records_failed_without_retry() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    window = _window() | {"attempt_count": 8, "max_attempts": 8}
    repo = FakeMacroIntelRepository(claimed_window=window)
    runner = FakeRunner(error=MacrodataRunnerError("provider failed", diagnostics={"error_code": "provider_down"}))
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=runner,
        wake_bus=FakeWakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "failed"
    assert repo.sync_runs[0]["status"] == "failed"
    assert repo.retry_windows == []
    assert repo.failed_windows[0]["error_code"] == "provider_down"


def test_sync_service_stale_retry_rolls_back_failure_audit() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    repo = FakeMacroIntelRepository(claimed_window=_window(), retry_result=False)
    runner = FakeRunner(error=MacrodataRunnerError("provider failed", diagnostics={"error_code": "provider_down"}))
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=runner,
        wake_bus=FakeWakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "stale_claim"
    assert repo.sync_runs == []
    assert repo.retry_windows == []
    assert repo.failed_windows == []


def test_sync_service_stale_fail_rolls_back_failure_audit() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    repo = FakeMacroIntelRepository(claimed_window=_window(), fail_result=False)
    runner = FakeRunner(
        error=MacrodataRunnerError(
            "macrodata executable not found",
            diagnostics={"error_code": "macrodata_executable_missing"},
        )
    )
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=runner,
        wake_bus=FakeWakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "stale_claim"
    assert repo.sync_runs == []
    assert repo.retry_windows == []
    assert repo.failed_windows == []


def test_sync_service_missing_macrodata_executable_is_config_error_without_retry() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    repo = FakeMacroIntelRepository(claimed_window=_window())
    runner = FakeRunner(
        error=MacrodataRunnerError(
            "macrodata executable not found",
            diagnostics={"error_code": "macrodata_executable_missing"},
        )
    )
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=runner,
        wake_bus=FakeWakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "config_error"
    assert repo.retry_windows == []
    assert repo.failed_windows[0]["error_code"] == "macrodata_executable_missing"


def test_sync_service_explicit_window_enqueues_and_claims_target_in_one_transaction() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    events: list[str] = []
    repo = FakeMacroIntelRepository(claimed_window=_window() | {"sync_window_id": "target-window"}, events=events)
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo, events=events),
        runner=FakeRunner(events=events),
        wake_bus=FakeWakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_explicit_window_once(
        bundle_name="macro-core",
        window_start=date(2026, 5, 27),
        window_end=date(2026, 5, 27),
        now_ms=NOW_MS,
    )

    assert result.status == "ok"
    assert repo.enqueued_windows[0]["trigger_reason"] == "operator_sync"
    assert repo.claimed_by_id == [
        {
            "sync_window_id": "target-window",
            "lease_owner": "macro_cli_sync",
            "lease_ms": 300_000,
            "now_ms": NOW_MS,
        }
    ]
    assert repo.claim_calls == []
    assert events.index("transaction-open") < events.index("enqueue")
    assert events.index("enqueue") < events.index("claim")
    assert events.index("claim") < events.index("transaction-commit")
    assert events.index("transaction-commit") < events.index("runner")


def test_sync_service_explicit_window_trigger_identity_allows_repeated_repairs() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    repo = FakeMacroIntelRepository(claimed_window=_window() | {"sync_window_id": "target-window"})
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=FakeRunner(),
        wake_bus=FakeWakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    service.run_explicit_window_once(
        bundle_name="macro-core",
        window_start=date(2026, 5, 27),
        window_end=date(2026, 5, 27),
        now_ms=NOW_MS,
    )
    service.run_explicit_window_once(
        bundle_name="macro-core",
        window_start=date(2026, 5, 27),
        window_end=date(2026, 5, 27),
        now_ms=NOW_MS + 1,
    )

    trigger_reasons = [str(window["trigger_reason"]) for window in repo.enqueued_windows]
    assert trigger_reasons == ["operator_sync", "operator_sync"]


def test_sync_service_redacts_secret_from_run_payload_and_diagnostics() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    secret = "dummy-fred-secret"
    repo = FakeMacroIntelRepository(claimed_window=_window())
    runner = FakeRunner(
        diagnostics={
            "fred_api_key_env": "APP_FRED_KEY",
            "fred_api_key_configured": True,
            "stderr": f"upstream echoed {secret}",
            "command": ["/app/.venv/bin/macrodata"],
        }
    )
    service = MacroSyncService(
        settings=FakeSettings(fred_env="APP_FRED_KEY"),
        repository_factory=FakeRepositoryFactory(repo),
        runner=runner,
        wake_bus=FakeWakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert secret not in json.dumps(result.diagnostics)
    assert secret not in json.dumps(repo.sync_runs, default=str)
    assert repo.sync_runs[0]["fred_api_key_env"] == "APP_FRED_KEY"
    assert repo.sync_runs[0]["fred_api_key_configured"] is True


def test_sync_service_redacts_secret_like_error_messages_before_persisting() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    secret = "super-secret"
    repo = FakeMacroIntelRepository(claimed_window=_window())
    runner = FakeRunner(generic_error=RuntimeError(f"postgres://macro:{secret}@db:5432/app failed"))
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=runner,
        wake_bus=FakeWakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "failed"
    rendered = json.dumps({"sync_runs": repo.sync_runs, "failed_windows": repo.failed_windows}, default=str)
    assert secret not in rendered
    assert "postgres://macro:***@db:5432/app failed" in rendered


def _window() -> dict[str, object]:
    return {
        "sync_window_id": "window-1",
        "source_name": "macrodata-cli",
        "bundle_name": "macro-core",
        "window_start": date(2026, 5, 27),
        "window_end": date(2026, 5, 27),
        "trigger_reason": "steady_overlap",
        "status": "running",
        "attempt_count": 1,
        "max_attempts": 8,
        "payload_hash": "payload-hash",
    }


def _empty_envelope() -> dict[str, object]:
    return {
        "ok": True,
        "data": {
            "snapshot": {
                "bundle": "macro-core",
                "asof": "2026-05-27",
                "observations": [],
                "coverage": {"requested": 1, "available": 0},
                "missing_series": ["nyfed:SOFR"],
                "series_errors": [],
                "data_quality": "empty",
                "reason_codes": ["no_observations"],
            }
        },
    }


class FakeSettings:
    macrodata_enabled = True

    def __init__(self, *, fred_env: str | None = None) -> None:
        self.macrodata_fred_api_key_env = fred_env
        self.workers = type(
            "Workers",
            (),
            {
                "macro_sync": type(
                    "MacroSyncSettings",
                    (),
                    {
                        "bundle_name": "macro-core",
                        "source_name": "macrodata-cli",
                        "bootstrap_lookback_days": 1095,
                        "max_window_days": 31,
                        "steady_overlap_days": 7,
                        "interval_seconds": 900.0,
                        "max_bootstrap_windows_per_cycle": 1,
                        "max_attempts": 8,
                        "lease_ms": 300_000,
                        "retry_delay_ms": 900_000,
                        "statement_timeout_seconds": 30.0,
                    },
                )()
            },
        )()


class FakeRunner:
    def __init__(
        self,
        *,
        events: list[str] | None = None,
        diagnostics: dict[str, object] | None = None,
        error: MacrodataRunnerError | None = None,
        generic_error: Exception | None = None,
        envelope: dict[str, object] | None = None,
    ) -> None:
        self.events = events
        self.diagnostics = diagnostics or {
            "fred_api_key_env": "FINANCE_FRED_API_KEY",
            "fred_api_key_configured": False,
            "command": ["/app/.venv/bin/macrodata"],
        }
        self.error = error
        self.generic_error = generic_error
        self.envelope = envelope or ENVELOPE
        self.calls: list[dict[str, str]] = []

    def history_bundle(self, *, bundle: str, start: str, end: str) -> MacrodataBundleRunResult:
        if self.events is not None:
            self.events.append("runner")
        self.calls.append({"bundle": bundle, "start": start, "end": end})
        if self.generic_error is not None:
            raise self.generic_error
        if self.error is not None:
            raise self.error
        return MacrodataBundleRunResult(envelope=self.envelope, diagnostics=self.diagnostics)


class FakeRepositoryFactory:
    def __init__(self, repo: FakeMacroIntelRepository, *, events: list[str] | None = None) -> None:
        self.repo = repo
        self.events = events

    def __call__(self):
        return FakeRepositoryContext(self.repo, events=self.events)


class FakeRepositoryContext:
    def __init__(self, repo: FakeMacroIntelRepository, *, events: list[str] | None = None) -> None:
        self.repo = repo
        self.events = events

    def __enter__(self):
        if self.events is not None:
            self.events.append("session-open")
        return FakeRepositorySession(self.repo, events=self.events)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if self.events is not None:
            self.events.append("session-close")
        return False


class FakeRepositorySession:
    def __init__(self, repo: FakeMacroIntelRepository, *, events: list[str] | None = None) -> None:
        self.macro_intel = repo
        self.events = events
        self.in_transaction = False

    def unit_of_work(self):
        return FakeTransaction(self, events=self.events)

    def require_transaction(self, *, operation: str) -> None:
        assert operation == "macrodata_bundle_import"
        assert self.in_transaction is True


class FakeTransaction:
    def __init__(self, repos: FakeRepositorySession, *, events: list[str] | None = None) -> None:
        self.repos = repos
        self.events = events

    def __enter__(self):
        self.repos.in_transaction = True
        self.observations = list(self.repos.macro_intel.observations)
        self.import_runs = list(self.repos.macro_intel.import_runs)
        self.sync_runs = list(self.repos.macro_intel.sync_runs)
        self.completed_windows = list(self.repos.macro_intel.completed_windows)
        self.retry_windows = list(self.repos.macro_intel.retry_windows)
        self.failed_windows = list(self.repos.macro_intel.failed_windows)
        self.enqueued_dirty_targets = list(self.repos.macro_intel.enqueued_dirty_targets)
        if self.events is not None:
            self.events.append("transaction-open")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        self.repos.in_transaction = False
        if self.events is not None:
            self.events.append("transaction-rollback" if exc_type else "transaction-commit")
        if exc_type is not None:
            self.repos.macro_intel.observations = self.observations
            self.repos.macro_intel.import_runs = self.import_runs
            self.repos.macro_intel.sync_runs = self.sync_runs
            self.repos.macro_intel.completed_windows = self.completed_windows
            self.repos.macro_intel.retry_windows = self.retry_windows
            self.repos.macro_intel.failed_windows = self.failed_windows
            self.repos.macro_intel.enqueued_dirty_targets = self.enqueued_dirty_targets
        return False


class FakeMacroIntelRepository:
    def __init__(
        self,
        *,
        claimed_window: dict[str, object] | None,
        events: list[str] | None = None,
        complete_result: bool = True,
        retry_result: bool = True,
        fail_result: bool = True,
        upsert_statuses: list[str] | None = None,
    ) -> None:
        self.claimed_window = claimed_window
        self.events = events
        self.complete_result = complete_result
        self.retry_result = retry_result
        self.fail_result = fail_result
        self.upsert_statuses = list(upsert_statuses or [])
        self.observations: list[dict[str, object]] = []
        self.import_runs: list[dict[str, object]] = []
        self.sync_runs: list[dict[str, object]] = []
        self.completed_windows: list[dict[str, object]] = []
        self.retry_windows: list[dict[str, object]] = []
        self.failed_windows: list[dict[str, object]] = []
        self.enqueued_windows: list[dict[str, object]] = []
        self.claim_calls: list[dict[str, object]] = []
        self.claimed_by_id: list[dict[str, object]] = []
        self.enqueued_dirty_targets: list[dict[str, object]] = []

    def enqueue_macro_sync_window(self, **kwargs: object) -> str:
        if self.events is not None:
            self.events.append("enqueue")
        self.enqueued_windows.append(dict(kwargs))
        return "target-window"

    def claim_macro_sync_window(self, **kwargs: object) -> dict[str, object] | None:
        if self.events is not None:
            self.events.append("claim")
        self.claim_calls.append(dict(kwargs))
        return self.claimed_window

    def claim_macro_sync_window_by_id(self, **kwargs: object) -> dict[str, object] | None:
        if self.events is not None:
            self.events.append("claim")
        self.claimed_by_id.append(dict(kwargs))
        return self.claimed_window

    def upsert_observation(self, observation: dict[str, object]) -> dict[str, object]:
        self.observations.append(observation)
        observation_id = f"observation-{len(self.observations)}"
        status = self.upsert_statuses.pop(0) if self.upsert_statuses else "inserted"
        return {
            "observation_id": observation_id,
            "status": status,
            "concept_key": observation["concept_key"],
            "observed_at": observation["observed_at"],
            "fact_payload_hash": f"hash-{len(self.observations)}",
        }

    def record_import_run(self, import_run: dict[str, object]) -> None:
        self.import_runs.append(import_run)

    def enqueue_macro_projection_dirty_targets_for_changes(self, **kwargs: object) -> int:
        self.enqueued_dirty_targets.append(dict(kwargs))
        return 1

    def record_macro_sync_run(self, run: dict[str, object]) -> None:
        self.sync_runs.append(run)

    def complete_macro_sync_window(self, **kwargs: object) -> bool:
        if self.complete_result:
            self.completed_windows.append(dict(kwargs))
        return self.complete_result

    def retry_macro_sync_window(self, **kwargs: object) -> bool:
        if self.retry_result:
            self.retry_windows.append(dict(kwargs))
        return self.retry_result

    def fail_macro_sync_window(self, **kwargs: object) -> bool:
        if self.fail_result:
            self.failed_windows.append(dict(kwargs))
        return self.fail_result


class FakeWakeBus:
    def __init__(self, *, events: list[str] | None = None, fail_notify: bool = False) -> None:
        self.events = events
        self.fail_notify = fail_notify
        self.notifications: list[dict[str, object]] = []

    def notify_macro_observations_imported(self, **kwargs: object) -> None:
        if self.events is not None:
            self.events.append("wake")
        if self.fail_notify:
            raise RuntimeError("wake bus unavailable")
        self.notifications.append(dict(kwargs))
