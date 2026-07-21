from __future__ import annotations

import json
from datetime import date, datetime
from types import SimpleNamespace, TracebackType

import pytest

from parallax.domains.macro_intel.services.macro_sync_types import MacrodataBundleRunResult
from parallax.integrations.macrodata.runner import MacrodataRunnerError

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


def test_sync_success_status_requires_import_status() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import _sync_success_status

    with pytest.raises(ValueError, match="macro_sync_import_status_required"):
        _sync_success_status(None)
    with pytest.raises(ValueError, match="macro_sync_import_status_required"):
        _sync_success_status("")

    assert _sync_success_status("ok") == "ok"
    assert _sync_success_status("partial") == "partial"
    assert _sync_success_status("stale") == "partial"
    assert _sync_success_status("unavailable") == "partial"
    for invalid_status in ("empty", "unknown"):
        with pytest.raises(ValueError, match="macro_sync_import_status_invalid"):
            _sync_success_status(invalid_status)


def test_sync_service_idle_claims_no_window_and_does_not_call_runner() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    repo = FakeMacroIntelRepository(claimed_window=None)
    runner = FakeRunner()
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=runner,
        clock_ms=lambda: NOW_MS,
    )

    assert service.run_claimed_window_once(lease_owner="macro_sync") is None
    assert runner.calls == []
    assert repo.sync_runs == []


def test_sync_service_enqueue_due_windows_uses_formal_queue_summary_repository_contract() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    repo = FakeMacroSyncQueueRepository(max_observed_at=date(2026, 5, 27))
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=FakeRunner(),
        clock_ms=lambda: NOW_MS,
    )

    summary = service.enqueue_due_windows(now_ms=NOW_MS)

    assert repo.queue_summary_calls == [{"now_ms": NOW_MS}]
    assert summary["open_count"] == 9
    assert summary["due_count"] == 4
    assert summary["enqueued_steady_windows"] == 1


def test_sync_service_enqueue_due_windows_schedules_all_configured_product_bundles() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    bundle_names = (
        "macro-core",
        "macro-calendar-core",
        "treasury-auction-core",
        "fed-text-core",
        "crypto-derivatives-core",
    )
    repo = FakeMacroSyncQueueRepository(
        max_observed_at_by_bundle={
            "macro-core": date(2026, 5, 17),
            "macro-calendar-core": None,
            "treasury-auction-core": date(2026, 5, 10),
            "fed-text-core": date(2026, 5, 8),
            "crypto-derivatives-core": date(2026, 5, 20),
        }
    )
    service = MacroSyncService(
        settings=FakeSettings(bundle_names=bundle_names),
        repository_factory=FakeRepositoryFactory(repo),
        runner=FakeRunner(),
        clock_ms=lambda: NOW_MS,
    )

    summary = service.enqueue_due_windows(now_ms=NOW_MS)

    assert summary["scheduled_bundle_names"] == bundle_names
    assert summary["enqueued_steady_windows"] == 5
    assert summary["enqueued_bootstrap_windows"] == 1
    assert summary["enqueued_gap_windows"] == 2
    assert repo.sync_state_reads == [
        {"source_name": "macrodata-cli", "bundle_name": "macro-core"},
        {"source_name": "macrodata-cli", "bundle_name": "macro-calendar-core"},
        {"source_name": "macrodata-cli", "bundle_name": "treasury-auction-core"},
        {"source_name": "macrodata-cli", "bundle_name": "fed-text-core"},
        {"source_name": "macrodata-cli", "bundle_name": "crypto-derivatives-core"},
    ]
    assert {window["bundle_name"] for window in repo.enqueued_windows} == set(bundle_names)


def test_sync_service_enqueue_due_windows_requires_formal_queue_summary_repository_contract() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    repo = FakeMacroSyncQueueRepositoryWithoutSummary(max_observed_at=date(2026, 5, 27))
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=FakeRunner(),
        clock_ms=lambda: NOW_MS,
    )

    try:
        service.enqueue_due_windows(now_ms=NOW_MS)
    except AttributeError as exc:
        assert "macro_sync_queue_summary" in str(exc)
    else:
        raise AssertionError("missing macro_sync_queue_summary should fail as repository wiring error")


def test_sync_service_claims_window_before_provider_io() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    events: list[str] = []
    repo = FakeMacroIntelRepository(claimed_window=_window(), events=events)
    runner = FakeRunner(events=events)
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo, events=events),
        runner=runner,
        clock_ms=lambda: NOW_MS,
    )

    service.run_claimed_window_once(lease_owner="macro_sync")

    assert events.index("claim") < events.index("session-close")
    assert events.index("session-close") < events.index("runner")
    commit_indexes = [index for index, event in enumerate(events) if event == "transaction-commit"]
    assert events.index("claim") < commit_indexes[0] < events.index("session-close")
    assert events.index("runner") < commit_indexes[-1]


def test_sync_service_import_success_writes_facts_and_completes_window() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    events: list[str] = []
    repo = FakeMacroIntelRepository(claimed_window=_window(), events=events)
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo, events=events),
        runner=FakeRunner(events=events),
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "ok"
    assert result.imported_observation_count == 1
    assert repo.observations[0]["series_key"] == "nyfed:SOFR"
    assert repo.sync_runs[0]["bundle_name"] == "macro-core"
    assert repo.sync_runs[0]["coverage_json"] == {"available": 1, "requested": 1}
    assert repo.sync_state_updates == [
        {
            "source_name": "macrodata-cli",
            "bundle_name": "macro-core",
            "max_observed_at": date(2026, 5, 27),
            "now_ms": NOW_MS,
        }
    ]
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
        }
    ]


def test_sync_service_rejects_runner_result_without_diagnostics_before_fact_write() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    class MissingDiagnosticsRunner:
        def history_bundle(self, *, bundle: str, start: str, end: str) -> object:
            return SimpleNamespace(envelope=ENVELOPE)

    repo = FakeMacroIntelRepository(claimed_window=_window())
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=MissingDiagnosticsRunner(),  # type: ignore[arg-type]
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "failed"
    assert result.imported_observation_count == 0
    assert repo.observations == []
    assert repo.enqueued_dirty_targets == []
    assert repo.failed_windows[0]["error_code"] == "AttributeError"


def test_sync_service_unavailable_import_does_not_enqueue_projection_dirty_target() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    repo = FakeMacroIntelRepository(claimed_window=_window())
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=FakeRunner(envelope=_unavailable_envelope()),
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "partial"
    assert result.imported_observation_count == 0
    assert repo.sync_runs[0]["status"] == "partial"
    assert repo.enqueued_dirty_targets == []
    assert repo.sync_state_updates == [
        {
            "source_name": "macrodata-cli",
            "bundle_name": "macro-core",
            "max_observed_at": date(2026, 5, 27),
            "now_ms": NOW_MS,
        }
    ]


def test_sync_service_noop_overlap_records_seen_and_does_not_enqueue_dirty_target() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    repo = FakeMacroIntelRepository(claimed_window=_window(), upsert_statuses=["noop"])
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=FakeRunner(),
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
    assert repo.sync_state_updates == [
        {
            "source_name": "macrodata-cli",
            "bundle_name": "macro-core",
            "max_observed_at": date(2026, 5, 27),
            "now_ms": NOW_MS,
        }
    ]


def test_sync_service_stale_completion_rolls_back_facts() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    events: list[str] = []
    repo = FakeMacroIntelRepository(claimed_window=_window(), events=events, complete_result=False)
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo, events=events),
        runner=FakeRunner(events=events),
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "stale_claim"
    assert repo.observations == []
    assert repo.sync_runs == []
    assert repo.sync_state_updates == []
    assert "transaction-rollback" in events


def test_sync_service_provider_failure_records_retry_without_fabricating_facts() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    repo = FakeMacroIntelRepository(claimed_window=_window())
    runner = FakeRunner(error=MacrodataRunnerError("provider failed", diagnostics={"error_code": "provider_down"}))
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=runner,
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "retryable_error"
    assert repo.observations == []
    assert repo.sync_runs[0]["status"] == "retryable_error"
    assert repo.sync_state_updates == []
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
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "failed"
    assert repo.sync_runs[0]["status"] == "failed"
    assert repo.retry_windows == []
    assert repo.failed_windows[0]["error_code"] == "provider_down"


def test_sync_service_attempt_budget_requires_claim_attempt_fields_without_defaults() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import _attempt_budget_exhausted

    missing_attempt = _window()
    missing_attempt.pop("attempt_count")
    with pytest.raises(ValueError, match="macro_sync_window_attempt_count_required"):
        _attempt_budget_exhausted(missing_attempt)

    missing_max = _window()
    missing_max.pop("max_attempts")
    with pytest.raises(ValueError, match="macro_sync_window_max_attempts_required"):
        _attempt_budget_exhausted(missing_max)


def test_sync_service_stale_retry_rolls_back_failure_audit() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    repo = FakeMacroIntelRepository(claimed_window=_window(), retry_result=False)
    runner = FakeRunner(error=MacrodataRunnerError("provider failed", diagnostics={"error_code": "provider_down"}))
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=runner,
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
            "macrodata package entrypoint not found",
            diagnostics={"error_code": "macrodata_entrypoint_missing"},
        )
    )
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=runner,
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "stale_claim"
    assert repo.sync_runs == []
    assert repo.retry_windows == []
    assert repo.failed_windows == []


def test_sync_service_missing_macrodata_entrypoint_is_config_error_without_retry() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    repo = FakeMacroIntelRepository(claimed_window=_window())
    runner = FakeRunner(
        error=MacrodataRunnerError(
            "macrodata package entrypoint not found",
            diagnostics={"error_code": "macrodata_entrypoint_missing"},
        )
    )
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=runner,
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "config_error"
    assert repo.retry_windows == []
    assert repo.failed_windows[0]["error_code"] == "macrodata_entrypoint_missing"


def test_sync_service_reads_formal_settings_for_session_claim_and_retry() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    repo = FakeMacroIntelRepository(claimed_window=_window() | {"max_attempts": 5})
    db = FakeDB(repo)
    runner = FakeRunner(error=MacrodataRunnerError("provider failed", diagnostics={"error_code": "provider_down"}))
    service = MacroSyncService(
        settings=FakeSettings(
            lease_ms=45_000,
            retry_delay_ms=12_000,
            statement_timeout_seconds=17.0,
            max_attempts=5,
        ),
        db=db,
        runner=runner,
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert result.status == "retryable_error"
    assert db.worker_sessions == [{"name": "macro_sync", "statement_timeout_seconds": 17.0}] * 2
    assert repo.claim_calls == [
        {
            "lease_owner": "macro_sync",
            "lease_ms": 45_000,
            "now_ms": NOW_MS,
        }
    ]
    assert repo.retry_windows[0]["retry_delay_ms"] == 12_000


def test_sync_service_explicit_window_enqueues_and_claims_target_in_one_transaction() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    events: list[str] = []
    repo = FakeMacroIntelRepository(claimed_window=_window() | {"sync_window_id": "target-window"}, events=events)
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo, events=events),
        runner=FakeRunner(events=events),
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
            "command": ["python", "-c", "from macrodata.surfaces.cli import main; main()"],
        }
    )
    service = MacroSyncService(
        settings=FakeSettings(fred_env="APP_FRED_KEY"),
        repository_factory=FakeRepositoryFactory(repo),
        runner=runner,
        clock_ms=lambda: NOW_MS,
    )

    result = service.run_claimed_window_once(lease_owner="macro_sync")

    assert result is not None
    assert secret not in json.dumps(result.diagnostics)
    assert secret not in json.dumps(repo.sync_runs, default=str)
    assert repo.sync_runs[0]["fred_api_key_env"] == "APP_FRED_KEY"
    assert repo.sync_runs[0]["fred_api_key_configured"] is True


def test_sync_service_requires_formal_fred_env_settings_contract() -> None:
    from parallax.domains.macro_intel.services import macro_sync_service as service_module

    with pytest.raises(RuntimeError, match="macrodata_provider_settings_required"):
        service_module._fred_api_key_state(object())


def test_sync_service_honors_disabled_fred_env_without_defaulting(monkeypatch) -> None:
    from parallax.domains.macro_intel.services import macro_sync_service as service_module

    class Settings:
        providers = SimpleNamespace(macrodata=SimpleNamespace(fred_api_key_env=None))

    monkeypatch.delenv("FINANCE_FRED_API_KEY", raising=False)

    assert service_module._fred_api_key_state(Settings()) == {
        "fred_api_key_env": None,
        "fred_api_key_configured": False,
    }


def test_sync_service_redacts_secret_like_error_messages_before_persisting() -> None:
    from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService

    secret = "super-secret"
    repo = FakeMacroIntelRepository(claimed_window=_window())
    runner = FakeRunner(generic_error=RuntimeError(f"postgres://macro:{secret}@db:5432/app failed"))
    service = MacroSyncService(
        settings=FakeSettings(),
        repository_factory=FakeRepositoryFactory(repo),
        runner=runner,
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


def _unavailable_envelope() -> dict[str, object]:
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
                "data_quality": "unavailable",
                "reason_codes": ["no_observations"],
            }
        },
    }


class FakeMacroSyncSettings:
    def __init__(self, **overrides: object) -> None:
        self.bundle_name = "macro-core"
        self.bundle_names = ("macro-core",)
        self.source_name = "macrodata-cli"
        self.bootstrap_lookback_days = 1095
        self.max_window_days = 31
        self.steady_overlap_days = 7
        self.interval_seconds = 900.0
        self.max_bootstrap_windows_per_cycle = 1
        self.max_attempts = 8
        self.lease_ms = 300_000
        self.retry_delay_ms = 900_000
        self.statement_timeout_seconds = 30.0
        for key, value in overrides.items():
            setattr(self, key, value)


class FakeSettings:
    def __init__(self, *, fred_env: str | None = None, **sync_overrides: object) -> None:
        self.providers = SimpleNamespace(macrodata=SimpleNamespace(enabled=True, fred_api_key_env=fred_env))
        self.workers = type(
            "Workers",
            (),
            {"macro_sync": FakeMacroSyncSettings(**sync_overrides)},
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
            "command": ["python", "-c", "from macrodata.surfaces.cli import main; main()"],
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


class FakeDB:
    def __init__(self, repo: FakeMacroIntelRepository) -> None:
        self.repo = repo
        self.worker_sessions: list[dict[str, object]] = []

    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        self.worker_sessions.append(
            {
                "name": name,
                "statement_timeout_seconds": statement_timeout_seconds,
            }
        )
        return FakeRepositoryContext(self.repo)


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

    def transaction(self):
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
        self.snapshots = {
            name: list(getattr(self.repos.macro_intel, name))
            for name in (
                "observations",
                "sync_runs",
                "sync_state_updates",
                "completed_windows",
                "retry_windows",
                "failed_windows",
                "enqueued_dirty_targets",
                "enqueued_windows",
            )
            if hasattr(self.repos.macro_intel, name)
        }
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
            for name, snapshot in self.snapshots.items():
                setattr(self.repos.macro_intel, name, snapshot)
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
        self.sync_runs: list[dict[str, object]] = []
        self.sync_state_updates: list[dict[str, object]] = []
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

    def enqueue_macro_projection_dirty_targets_for_changes(self, **kwargs: object) -> int:
        self.enqueued_dirty_targets.append(dict(kwargs))
        return 1

    def record_macro_sync_run(self, run: dict[str, object]) -> None:
        self.sync_runs.append(run)

    def update_macro_sync_state(self, **kwargs: object) -> int:
        self.sync_state_updates.append(dict(kwargs))
        return 1

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


class FakeMacroSyncQueueRepository:
    def __init__(
        self,
        *,
        max_observed_at: date | None = None,
        max_observed_at_by_bundle: dict[str, date | None] | None = None,
    ) -> None:
        self.max_observed_at = max_observed_at
        self.max_observed_at_by_bundle = dict(max_observed_at_by_bundle or {})
        self.enqueued_windows: list[dict[str, object]] = []
        self.queue_summary_calls: list[dict[str, object]] = []
        self.sync_state_reads: list[dict[str, object]] = []

    def macro_sync_state_max_observed_at(self, *, source_name: str, bundle_name: str) -> date | None:
        assert source_name == "macrodata-cli"
        self.sync_state_reads.append({"source_name": source_name, "bundle_name": bundle_name})
        if bundle_name in self.max_observed_at_by_bundle:
            return self.max_observed_at_by_bundle[bundle_name]
        return self.max_observed_at

    def enqueue_macro_sync_window(self, **kwargs: object) -> str:
        self.enqueued_windows.append(dict(kwargs))
        return f"window-{len(self.enqueued_windows)}"

    def macro_sync_queue_summary(self, *, now_ms: int) -> dict[str, object]:
        self.queue_summary_calls.append({"now_ms": now_ms})
        return {
            "open_count": 9,
            "due_count": 4,
            "running_count": 1,
            "expired_running_count": 0,
            "expired_running_exhausted_count": 0,
            "exhausted_count": 0,
            "failed_count": 0,
        }


class FakeMacroSyncQueueRepositoryWithoutSummary:
    def __init__(self, *, max_observed_at: date | None) -> None:
        self.max_observed_at = max_observed_at
        self.enqueued_windows: list[dict[str, object]] = []

    def macro_sync_state_max_observed_at(self, *, source_name: str, bundle_name: str) -> date | None:
        assert source_name == "macrodata-cli"
        assert bundle_name == "macro-core"
        return self.max_observed_at

    def enqueue_macro_sync_window(self, **kwargs: object) -> str:
        self.enqueued_windows.append(dict(kwargs))
        return f"window-{len(self.enqueued_windows)}"
