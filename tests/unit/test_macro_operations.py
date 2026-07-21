from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest

from parallax.domains.macro_intel.services.macro_sync_types import MacroSyncRunSummary


def test_import_macro_bundle_owns_persistence(monkeypatch) -> None:
    from parallax.app.operations import macro as operation

    events: list[tuple[str, object]] = []
    settings = SimpleNamespace()
    summary = {
        "imported_observation_count": 2,
        "max_observed_at": date(2026, 7, 20),
        "asof": date(2026, 7, 21),
    }

    @contextmanager
    def fake_repositories(current_settings):
        events.append(("repos_enter", current_settings))
        yield "repos"
        events.append(("repos_exit", current_settings))

    def fake_import(envelope, *, repos, now_ms):
        events.append(("import", (envelope, repos, now_ms)))
        return summary

    monkeypatch.setattr(operation, "repositories", fake_repositories)
    monkeypatch.setattr(operation, "import_macrodata_bundle", fake_import)

    assert operation.import_macro_bundle(settings, {"ok": True}, now_ms=123) is summary
    assert events == [
        ("repos_enter", settings),
        ("import", ({"ok": True}, "repos", 123)),
        ("repos_exit", settings),
    ]


def test_snapshot_status_uses_only_exact_current_sections() -> None:
    from parallax.app.operations import macro as operation

    snapshot = _macro_snapshot()
    snapshot["source_coverage_json"] = {
        "latest_coverage_ratio": 0,
        "history_coverage_ratio": 0,
        "observed_concept_count": 0,
        "required_concept_count": 0,
        "history_ready_concept_count": 0,
        "required_history_concept_count": 0,
        "concepts_below_min_history": [],
    }
    snapshot["scorecard_json"] = {
        "latest_coverage_ratio": 0.9,
        "history_coverage_ratio": 0.8,
        "observed_concept_count": 99,
        "required_concept_count": 100,
    }

    summary = operation._snapshot_status_summary(snapshot)

    assert summary is not None
    assert summary["coverage"] == {
        "latest_coverage_ratio": 0,
        "history_coverage_ratio": 0,
        "observed_concept_count": 0,
        "required_concept_count": 0,
        "history_ready_concept_count": 0,
        "required_history_concept_count": 0,
        "concepts_below_min_history": [],
    }


@pytest.mark.parametrize("panels", [None, [], {"rates": "not-an-object"}])
def test_snapshot_status_rejects_malformed_panels_without_chain_fallback(panels: object) -> None:
    from parallax.app.operations import macro as operation

    snapshot = _macro_snapshot()
    if panels is None:
        snapshot.pop("panels_json")
    else:
        snapshot["panels_json"] = panels
    snapshot["chain_json"] = {"rates": {"score": 99, "regime": "risk_on"}}

    with pytest.raises(ValueError, match="panels_json"):
        operation._snapshot_status_summary(snapshot)


def test_sync_macro_window_composes_provider_and_service(monkeypatch) -> None:
    from parallax.app.operations import macro as operation

    settings = SimpleNamespace()
    calls: list[tuple[str, object]] = []
    summary = MacroSyncRunSummary(
        sync_run_id="run-1",
        status="ok",
        observations_count=3,
        imported_observation_count=2,
        asof_date=date(2026, 7, 21),
        max_observed_at=date(2026, 7, 20),
        diagnostics={"provider": "macrodata"},
    )

    class Service:
        def __init__(self, **kwargs) -> None:
            calls.append(("service", kwargs))

        def run_explicit_window_once(self, **kwargs):
            calls.append(("run", kwargs))
            return summary

    monkeypatch.setattr(operation, "fred_api_key_state", lambda _settings: {"fred_api_key_configured": True})
    monkeypatch.setattr(operation, "MacrodataBundleRunner", lambda **kwargs: ("runner", kwargs))
    monkeypatch.setattr(operation, "MacroSyncService", Service)

    result = operation.sync_macro_window(
        settings,
        bundle_name="macro-core",
        window_start=date(2026, 1, 1),
        window_end=date(2026, 7, 21),
        now_ms=123,
    )

    assert result.summary is summary
    assert result.diagnostics == {"fred_api_key_configured": True, "provider": "macrodata"}
    assert calls[1] == (
        "run",
        {
            "bundle_name": "macro-core",
            "window_start": date(2026, 1, 1),
            "window_end": date(2026, 7, 21),
            "now_ms": 123,
        },
    )


def _macro_snapshot() -> dict[str, object]:
    return {
        "projection_version": "macro_regime_v4",
        "asof_date": "2026-07-21",
        "status": "partial",
        "regime": "mixed",
        "overall_score": 50,
        "computed_at_ms": 1_779_000_000_000,
        "panels_json": {"rates": {"score": 50, "regime": "mixed", "evidence": [], "data_gaps": []}},
        "indicators_json": {},
        "triggers_json": [],
        "data_gaps_json": [],
        "source_coverage_json": {},
        "features_json": {},
        "chain_json": {},
        "scenario_json": {},
        "scorecard_json": {},
        "module_views_json": {},
    }


def test_sync_macro_window_preserves_redacted_diagnostics_on_failure(monkeypatch) -> None:
    from parallax.app.operations import macro as operation

    class ProviderError(RuntimeError):
        def __init__(self, message: str) -> None:
            super().__init__(message)
            self.diagnostics = {"fred_api_key_configured": False, "provider_status": "missing_key"}

    class Service:
        def __init__(self, **_kwargs) -> None:
            pass

        def run_explicit_window_once(self, **_kwargs):
            raise ProviderError("provider failed")

    monkeypatch.setattr(operation, "fred_api_key_state", lambda _settings: {"fred_api_key_configured": True})
    monkeypatch.setattr(operation, "MacrodataBundleRunner", lambda **_kwargs: object())
    monkeypatch.setattr(operation, "MacroSyncService", Service)

    with pytest.raises(operation.MacroSyncOperationError) as error:
        operation.sync_macro_window(
            SimpleNamespace(),
            bundle_name="macro-core",
            window_start=date(2026, 1, 1),
            window_end=date(2026, 7, 21),
            now_ms=123,
        )

    assert isinstance(error.value.cause, ProviderError)
    assert error.value.diagnostics == {
        "fred_api_key_configured": False,
        "provider_status": "missing_key",
    }
