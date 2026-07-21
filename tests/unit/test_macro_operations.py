from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest

from parallax.domains.macro_intel.services.macro_sync_types import MacroSyncRunSummary


def test_import_macro_bundle_owns_persistence_and_wake_hint(monkeypatch) -> None:
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

    class Wake:
        def __init__(self, _factory) -> None:
            pass

        def notify_macro_observations_imported(self, **kwargs) -> None:
            events.append(("wake", kwargs))

    monkeypatch.setattr(operation, "repositories", fake_repositories)
    monkeypatch.setattr(operation, "import_macrodata_bundle", fake_import)
    monkeypatch.setattr(operation, "WakeBus", Wake)

    assert operation.import_macro_bundle(settings, {"ok": True}, now_ms=123) is summary
    assert events == [
        ("repos_enter", settings),
        ("import", ({"ok": True}, "repos", 123)),
        ("repos_exit", settings),
        (
            "wake",
            {"count": 2, "max_observed_at": "2026-07-20", "asof_date": "2026-07-21"},
        ),
    ]


def test_import_macro_bundle_does_not_rollback_for_wake_failure(monkeypatch) -> None:
    from parallax.app.operations import macro as operation

    @contextmanager
    def fake_repositories(_settings):
        yield object()

    class Wake:
        def __init__(self, _factory) -> None:
            pass

        def notify_macro_observations_imported(self, **_kwargs) -> None:
            raise RuntimeError("wake failed")

    monkeypatch.setattr(operation, "repositories", fake_repositories)
    monkeypatch.setattr(
        operation,
        "import_macrodata_bundle",
        lambda *_args, **_kwargs: {"imported_observation_count": 1},
    )
    monkeypatch.setattr(operation, "WakeBus", Wake)

    assert operation.import_macro_bundle(SimpleNamespace(), {"ok": True}, now_ms=123) == {
        "imported_observation_count": 1
    }


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
