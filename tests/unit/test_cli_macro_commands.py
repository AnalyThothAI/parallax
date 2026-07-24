from __future__ import annotations

import io
import json
import subprocess
import sys
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest

from parallax.app.operations.macro import MacroSyncExecution
from parallax.app.surfaces.cli.parser import build_parser
from parallax.cli import main
from parallax.domains.macro_intel._constants import (
    MACRO_EVENT_PROVIDER_SERIES_TO_CONCEPT,
    MACRO_IMPORTABLE_PROVIDER_SERIES_TO_CONCEPT,
    MACRO_PROVIDER_SERIES_TO_CONCEPT,
)
from parallax.domains.macro_intel.services.macro_sync_types import MacroSyncRunSummary

NOW_MS = 1_779_000_000_000
MACRODATA_COMMAND_PREFIX = (
    sys.executable,
    "-c",
    "from macrodata.surfaces.cli import main; main()",
)

ENVELOPE = {
    "ok": True,
    "command": "bundle.macro-core",
    "data": {
        "snapshot": {
            "bundle": "macro-core",
            "asof": "2026-05-21",
            "observations": [
                {
                    "series_key": "nyfed:SOFR",
                    "provider": "nyfed",
                    "observed_at": "2026-05-19",
                    "value": 3.51,
                    "unit": "percent",
                    "frequency": "daily",
                    "source_ts": "2026-05-19",
                    "data_quality": "ok",
                }
            ],
            "coverage": {"requested": 20, "available": 1},
            "missing_series": ["fred:WALCL"],
            "series_errors": [{"series_key": "fred:WALCL", "provider": "fred", "code": "missing_api_key"}],
            "source_chain": ["nyfed"],
            "data_quality": "partial",
            "reason_codes": ["missing_series", "missing_api_key"],
        }
    },
}


def _macrodata_workers(timeout_seconds: float = 240.0) -> SimpleNamespace:
    return SimpleNamespace(
        macro_sync=SimpleNamespace(
            bundle_names=(
                "macro-core",
                "macro-calendar-core",
                "treasury-auction-core",
                "fed-text-core",
                "crypto-derivatives-core",
            ),
            macrodata_timeout_seconds=timeout_seconds,
        )
    )


def test_macro_import_bundle_parser_accepts_file() -> None:
    args = build_parser().parse_args(["macro", "import-bundle", "--file", "bundle.json"])

    assert args.command == "macro"
    assert args.macro_command == "import-bundle"
    assert args.file == "bundle.json"
    assert args.stdin is False


def test_macro_import_bundle_parser_accepts_stdin() -> None:
    args = build_parser().parse_args(["macro", "import-bundle", "--stdin"])

    assert args.command == "macro"
    assert args.macro_command == "import-bundle"
    assert args.file is None
    assert args.stdin is True


def test_macro_import_bundle_handler_requires_parser_owned_arguments() -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    with pytest.raises(AttributeError):
        macro_module._handle_import_bundle(SimpleNamespace())


def test_macro_parser_rejects_direct_projection_paths() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["macro", "project-once"])

    with pytest.raises(SystemExit):
        parser.parse_args(
            ["macro", "sync", "--bundle", "macro-core", "--start", "2026-01-01", "--end", "2026-05-21", "--project"]
        )


def test_macro_status_parser() -> None:
    status = build_parser().parse_args(["macro", "status"])

    assert status.command == "macro"
    assert status.macro_command == "status"


def test_macro_sync_parser_accepts_history_args() -> None:
    args = build_parser().parse_args(
        ["macro", "sync", "--bundle", "macro-core", "--start", "2026-01-01", "--end", "2026-05-21"]
    )

    assert args.command == "macro"
    assert args.macro_command == "sync"
    assert args.bundle == "macro-core"
    assert args.start == "2026-01-01"
    assert args.end == "2026-05-21"
    assert not hasattr(args, "project")


def test_macrodata_runner_injects_fred_env_without_exposing_secret(monkeypatch) -> None:
    from parallax.integrations.macrodata.runner import MacrodataBundleRunner

    secret = "dummy-fred-secret"
    calls: list[dict[str, object]] = []

    class Settings:
        providers = SimpleNamespace(macrodata=SimpleNamespace(fred_api_key_env="APP_FRED_KEY"))
        macrodata_fred_api_key = None
        workers = _macrodata_workers()

    class Completed:
        returncode = 0
        stdout = json.dumps(ENVELOPE)
        stderr = f"warning without {secret}"

    def fake_run(command, *, env, cwd, capture_output, text, check, timeout=None):
        calls.append(
            {
                "command": command,
                "env_fred_api_key": env.get("FRED_API_KEY"),
                "cwd": cwd,
                "capture_output": capture_output,
                "text": text,
                "check": check,
                "timeout": timeout,
            }
        )
        return Completed()

    monkeypatch.setenv("APP_FRED_KEY", secret)
    monkeypatch.setattr("parallax.integrations.macrodata.runner._macrodata_cli_entrypoint_available", lambda: True)
    monkeypatch.setattr("parallax.integrations.macrodata.runner.subprocess.run", fake_run)

    result = MacrodataBundleRunner(settings=Settings()).history_bundle(
        bundle="macro-core",
        start="2026-01-01",
        end="2026-05-21",
    )

    assert result.envelope == ENVELOPE
    assert calls == [
        {
            "command": [
                *MACRODATA_COMMAND_PREFIX,
                "bundle",
                "history",
                "macro-core",
                "--start",
                "2026-01-01",
                "--end",
                "2026-05-21",
            ],
            "env_fred_api_key": secret,
            "cwd": None,
            "capture_output": True,
            "text": True,
            "check": False,
            "timeout": 240.0,
        }
    ]
    rendered = json.dumps(result.diagnostics)
    assert calls[0]["command"][:3] == list(MACRODATA_COMMAND_PREFIX)
    assert "uv" not in calls[0]["command"]
    assert calls[0]["command"][3:] == [
        "bundle",
        "history",
        "macro-core",
        "--start",
        "2026-01-01",
        "--end",
        "2026-05-21",
    ]
    assert result.diagnostics == {
        "fred_api_key_env": "APP_FRED_KEY",
        "fred_api_key_configured": True,
        "command": calls[0]["command"],
        "timeout_seconds": 240.0,
        "returncode": 0,
    }
    assert secret not in rendered
    assert secret not in " ".join(calls[0]["command"])


def test_macrodata_runner_injects_configured_fred_key_without_exposing_secret(monkeypatch) -> None:
    from parallax.integrations.macrodata.runner import MacrodataBundleRunner

    secret = "configured-fred-secret"
    stale_env_secret = "stale-parent-fred-secret"
    calls: list[dict[str, object]] = []

    class Settings:
        providers = SimpleNamespace(macrodata=SimpleNamespace(fred_api_key_env="APP_FRED_KEY"))
        macrodata_fred_api_key = secret
        workers = _macrodata_workers()

    class Completed:
        returncode = 0
        stdout = json.dumps(ENVELOPE)
        stderr = ""

    def fake_run(command, *, env, cwd, capture_output, text, check, timeout=None):
        calls.append({"command": command, "env_fred_api_key": env.get("FRED_API_KEY"), "timeout": timeout})
        return Completed()

    monkeypatch.setenv("APP_FRED_KEY", stale_env_secret)
    monkeypatch.setattr("parallax.integrations.macrodata.runner._macrodata_cli_entrypoint_available", lambda: True)
    monkeypatch.setattr("parallax.integrations.macrodata.runner.subprocess.run", fake_run)

    result = MacrodataBundleRunner(settings=Settings()).history_bundle(
        bundle="macro-core",
        start="2026-01-01",
        end="2026-05-21",
    )

    assert result.envelope == ENVELOPE
    assert calls[0]["env_fred_api_key"] == secret
    assert result.diagnostics["fred_api_key_env"] == "APP_FRED_KEY"
    assert result.diagnostics["fred_api_key_configured"] is True
    rendered = json.dumps(result.diagnostics)
    assert secret not in rendered
    assert stale_env_secret not in rendered


def test_macrodata_runner_requires_formal_fred_and_timeout_settings_contracts() -> None:
    from parallax.integrations.macrodata import runner

    class MissingEnvSettings:
        macrodata_fred_api_key = None
        workers = _macrodata_workers()

    class MissingSecretSettings:
        providers = SimpleNamespace(macrodata=SimpleNamespace(fred_api_key_env="APP_FRED_KEY"))
        workers = _macrodata_workers()

    class MissingTimeoutSettings:
        providers = SimpleNamespace(macrodata=SimpleNamespace(fred_api_key_env=None))
        macrodata_fred_api_key = None
        workers = SimpleNamespace()

    with pytest.raises(RuntimeError, match="macrodata_provider_settings_required"):
        runner.fred_api_key_state(MissingEnvSettings(), environ={})
    with pytest.raises(RuntimeError, match="macrodata_fred_api_key_settings_required"):
        runner.fred_api_key_state(MissingSecretSettings(), environ={})
    with pytest.raises(RuntimeError, match="macrodata_timeout_settings_required"):
        runner._macrodata_timeout_seconds(MissingTimeoutSettings())


@pytest.mark.parametrize("timeout_seconds", [0.0, -1.0, True, "240"])
def test_macrodata_runner_rejects_malformed_timeout_settings(timeout_seconds: object) -> None:
    from parallax.integrations.macrodata import runner

    class Settings:
        workers = _macrodata_workers(timeout_seconds=timeout_seconds)

    with pytest.raises(ValueError, match="macrodata_timeout_seconds_required"):
        runner._macrodata_timeout_seconds(Settings())


def test_macrodata_runner_honors_disabled_fred_env_without_defaulting(monkeypatch) -> None:
    from parallax.integrations.macrodata.runner import MacrodataBundleRunner

    calls: list[dict[str, object]] = []

    class Settings:
        providers = SimpleNamespace(macrodata=SimpleNamespace(fred_api_key_env=None))
        macrodata_fred_api_key = None
        workers = _macrodata_workers()

    class Completed:
        returncode = 0
        stdout = json.dumps(ENVELOPE)
        stderr = ""

    def fake_run(command, *, env, cwd, capture_output, text, check, timeout=None):
        calls.append({"command": command, "env_has_fred": "FRED_API_KEY" in env, "cwd": cwd})
        return Completed()

    monkeypatch.delenv("FINANCE_FRED_API_KEY", raising=False)
    monkeypatch.setattr("parallax.integrations.macrodata.runner._macrodata_cli_entrypoint_available", lambda: True)
    monkeypatch.setattr("parallax.integrations.macrodata.runner.subprocess.run", fake_run)

    result = MacrodataBundleRunner(settings=Settings()).history_bundle(
        bundle="macro-core",
        start="2026-01-01",
        end="2026-05-21",
    )

    assert result.diagnostics["fred_api_key_env"] is None
    assert result.diagnostics["fred_api_key_configured"] is False
    assert calls[0]["env_has_fred"] is False


def test_macrodata_runner_uses_only_current_python_package_entrypoint(monkeypatch) -> None:
    from parallax.integrations.macrodata.runner import MacrodataBundleRunner

    calls: list[dict[str, object]] = []

    class Settings:
        providers = SimpleNamespace(macrodata=SimpleNamespace(fred_api_key_env=None))
        macrodata_fred_api_key = None
        workers = _macrodata_workers()

    class Completed:
        returncode = 0
        stdout = json.dumps(ENVELOPE)
        stderr = ""

    def fake_run(command, *, env, cwd, capture_output, text, check, timeout=None):
        calls.append({"command": command, "cwd": cwd, "timeout": timeout})
        return Completed()

    monkeypatch.setattr("parallax.integrations.macrodata.runner._macrodata_cli_entrypoint_available", lambda: True)
    monkeypatch.setattr("parallax.integrations.macrodata.runner.subprocess.run", fake_run)

    result = MacrodataBundleRunner(settings=Settings()).history_bundle(
        bundle="macro-core",
        start="2026-01-01",
        end="2026-05-21",
    )

    assert result.envelope == ENVELOPE
    assert calls[0]["command"][:3] == [
        sys.executable,
        "-c",
        "from macrodata.surfaces.cli import main; main()",
    ]
    assert calls[0]["command"][3:] == [
        "bundle",
        "history",
        "macro-core",
        "--start",
        "2026-01-01",
        "--end",
        "2026-05-21",
    ]
    assert calls[0]["cwd"] is None
    assert result.diagnostics["command"] == calls[0]["command"]


def test_macrodata_runner_command_is_independent_of_path(monkeypatch) -> None:
    from parallax.integrations.macrodata.runner import resolve_macrodata_command

    monkeypatch.setattr("parallax.integrations.macrodata.runner._macrodata_cli_entrypoint_available", lambda: True)

    command = resolve_macrodata_command()

    assert command == list(MACRODATA_COMMAND_PREFIX)


def test_macrodata_runner_reports_missing_package_entrypoint(monkeypatch) -> None:
    from parallax.integrations.macrodata.runner import MacrodataRunnerError, resolve_macrodata_command

    monkeypatch.setattr("parallax.integrations.macrodata.runner._macrodata_cli_entrypoint_available", lambda: False)

    with pytest.raises(MacrodataRunnerError) as excinfo:
        resolve_macrodata_command()

    assert excinfo.value.diagnostics == {"error_code": "macrodata_entrypoint_missing"}


def test_macrodata_runner_reports_missing_parent_package_as_unavailable(monkeypatch) -> None:
    from parallax.integrations.macrodata import runner

    def missing_spec(_name: str) -> None:
        raise ModuleNotFoundError("No module named 'macrodata'")

    monkeypatch.setattr(runner, "find_spec", missing_spec)

    assert runner._macrodata_cli_entrypoint_available() is False


def test_macrodata_runtime_state_reports_missing_required_catalog_series(monkeypatch) -> None:
    from parallax.integrations.macrodata import runner

    monkeypatch.setattr(runner, "_macrodata_cli_package_version", lambda: "0.1.5")
    monkeypatch.setattr(runner, "_macrodata_catalog_series", lambda: {"fred:SP500"})
    monkeypatch.setattr(runner, "_macrodata_bundle_series", lambda bundle_name: {"fred:SP500"})
    monkeypatch.setattr(runner, "_macrodata_cli_entrypoint_available", lambda: True)

    state = runner.macrodata_runtime_state(
        required_series=("fred:SP500", "nyfed:SRF", "yahoo:USDCNY=X"),
    )

    assert state == {
        "package_version": "0.1.5",
        "entrypoint_available": True,
        "command_mode": "python_entrypoint",
        "command_path": sys.executable,
        "command_error_code": None,
        "catalog_available": True,
        "required_series_count": 3,
        "missing_required_series_count": 2,
        "required_series_available": False,
        "missing_required_series_sample": ["nyfed:SRF", "yahoo:USDCNY=X"],
        "required_bundle_count": 0,
        "missing_required_bundle_count": 0,
        "required_bundles_available": True,
        "missing_required_bundles": [],
        "macro_core_bundle_available": True,
        "missing_required_bundle_series_count": 2,
        "required_bundle_series_available": False,
        "missing_required_bundle_series_sample": ["nyfed:SRF", "yahoo:USDCNY=X"],
        "missing_required_bundle_series_by_bundle": {},
    }


def test_macrodata_runtime_state_reports_missing_configured_sync_bundles(monkeypatch) -> None:
    from parallax.integrations.macrodata import runner

    bundle_series = {
        "macro-core": {"fred:SP500"},
        "macro-calendar-core": None,
        "treasury-auction-core": {"treasury_auction:10y_bid_to_cover"},
        "fed-text-core": {"official_fed_text:speech_latest"},
    }

    monkeypatch.setattr(runner, "_macrodata_cli_package_version", lambda: "0.1.8")
    monkeypatch.setattr(
        runner,
        "_macrodata_catalog_series",
        lambda: {"fred:SP500", "treasury_auction:10y_bid_to_cover"},
    )
    monkeypatch.setattr(runner, "_macrodata_bundle_series", lambda bundle_name: bundle_series[bundle_name])
    monkeypatch.setattr(runner, "_macrodata_cli_entrypoint_available", lambda: True)

    state = runner.macrodata_runtime_state(
        required_series=("fred:SP500",),
        required_bundles=("macro-core", "macro-calendar-core", "treasury-auction-core", "fed-text-core"),
    )

    assert state["required_bundle_count"] == 4
    assert state["missing_required_bundle_count"] == 1
    assert state["required_bundles_available"] is False
    assert state["missing_required_bundles"] == ["macro-calendar-core"]


def test_macrodata_runtime_state_reports_missing_event_bundle_series(monkeypatch) -> None:
    from parallax.integrations.macrodata import runner

    bundle_series = {
        "macro-core": {"fred:SP500"},
        "macro-calendar-core": {
            "official_calendar:fomc_decision_next",
            "official_calendar:bea_gdp_next",
            "official_calendar:bea_pce_next",
        },
    }
    required_calendar_series = (
        "official_calendar:fomc_decision_next",
        "official_calendar:bea_gdp_next",
        "official_calendar:bea_pce_next",
        "official_calendar:bls_cpi_next",
        "official_calendar:bls_employment_next",
        "official_calendar:bls_ppi_next",
    )

    monkeypatch.setattr(runner, "_macrodata_cli_package_version", lambda: "0.1.11")
    monkeypatch.setattr(runner, "_macrodata_catalog_series", lambda: {"fred:SP500", *required_calendar_series})
    monkeypatch.setattr(runner, "_macrodata_bundle_series", lambda bundle_name: bundle_series[bundle_name])
    monkeypatch.setattr(runner, "_macrodata_cli_entrypoint_available", lambda: True)

    state = runner.macrodata_runtime_state(
        required_series=("fred:SP500", *required_calendar_series),
        required_bundles=("macro-core", "macro-calendar-core"),
        required_bundle_series={
            "macro-core": ("fred:SP500",),
            "macro-calendar-core": required_calendar_series,
        },
    )

    assert state["missing_required_bundle_count"] == 0
    assert state["required_bundles_available"] is True
    assert state["required_bundle_series_available"] is False
    assert state["missing_required_bundle_series_count"] == 3
    assert state["missing_required_bundle_series_sample"] == [
        "macro-calendar-core:official_calendar:bls_cpi_next",
        "macro-calendar-core:official_calendar:bls_employment_next",
        "macro-calendar-core:official_calendar:bls_ppi_next",
    ]
    assert state["missing_required_bundle_series_by_bundle"] == {
        "macro-calendar-core": [
            "official_calendar:bls_cpi_next",
            "official_calendar:bls_employment_next",
            "official_calendar:bls_ppi_next",
        ]
    }


def test_macrodata_runtime_state_reports_only_python_entrypoint(monkeypatch) -> None:
    from parallax.integrations.macrodata import runner

    monkeypatch.setattr(runner, "_macrodata_cli_package_version", lambda: "0.1.6")
    monkeypatch.setattr(runner, "_macrodata_catalog_series", lambda: {"nyfed:SRF"})
    monkeypatch.setattr(runner, "_macrodata_bundle_series", lambda bundle_name: {"nyfed:SRF"})
    monkeypatch.setattr(runner, "_macrodata_cli_entrypoint_available", lambda: True)
    state = runner.macrodata_runtime_state(required_series=("nyfed:SRF",))

    assert state["command_mode"] == "python_entrypoint"
    assert state["command_path"] == sys.executable
    assert state["required_series_available"] is True
    assert state["required_bundle_series_available"] is True


def test_macrodata_bundle_catalog_requires_bundles_without_legacy_macro_core(monkeypatch) -> None:
    from parallax.integrations.macrodata import runner

    monkeypatch.setattr(
        runner,
        "import_module",
        lambda _name: SimpleNamespace(MACRO_CORE=("fred:SP500",)),
    )
    assert runner._macrodata_bundle_series("macro-core") is None

    monkeypatch.setattr(
        runner,
        "import_module",
        lambda _name: SimpleNamespace(BUNDLES={"macro-core": ("fred:SP500",)}),
    )
    assert runner._macrodata_bundle_series("macro-core") == {"fred:SP500"}


def test_macrodata_runner_passes_configured_timeout_to_child_process(monkeypatch) -> None:
    from parallax.integrations.macrodata.runner import MacrodataBundleRunner

    calls: list[dict[str, object]] = []

    class Settings:
        providers = SimpleNamespace(macrodata=SimpleNamespace(fred_api_key_env=None))
        macrodata_fred_api_key = None
        workers = _macrodata_workers(12.5)

    class Completed:
        returncode = 0
        stdout = json.dumps(ENVELOPE)
        stderr = ""

    def fake_run(command, *, env, cwd, capture_output, text, check, timeout=None):
        calls.append({"command": command, "timeout": timeout})
        return Completed()

    monkeypatch.setattr("parallax.integrations.macrodata.runner._macrodata_cli_entrypoint_available", lambda: True)
    monkeypatch.setattr("parallax.integrations.macrodata.runner.subprocess.run", fake_run)

    result = MacrodataBundleRunner(settings=Settings()).history_bundle(
        bundle="macro-core",
        start="2026-01-01",
        end="2026-05-21",
    )

    assert result.diagnostics["timeout_seconds"] == 12.5
    assert calls[0]["timeout"] == 12.5


def test_macrodata_runner_timeout_raises_redacted_runner_error(monkeypatch) -> None:
    from parallax.integrations.macrodata.runner import MacrodataBundleRunner, MacrodataRunnerError

    class Settings:
        providers = SimpleNamespace(macrodata=SimpleNamespace(fred_api_key_env=None))
        macrodata_fred_api_key = None
        workers = _macrodata_workers(9.0)

    def fake_run(command, *, env, cwd, capture_output, text, check, timeout=None):
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr("parallax.integrations.macrodata.runner._macrodata_cli_entrypoint_available", lambda: True)
    monkeypatch.setattr("parallax.integrations.macrodata.runner.subprocess.run", fake_run)

    with pytest.raises(MacrodataRunnerError) as excinfo:
        MacrodataBundleRunner(settings=Settings()).history_bundle(
            bundle="macro-core",
            start="2026-01-01",
            end="2026-05-21",
        )

    assert excinfo.value.diagnostics["error_code"] == "macrodata_runner_timeout"
    assert excinfo.value.diagnostics["timeout_seconds"] == 9.0
    assert excinfo.value.diagnostics["returncode"] is None


def test_macrodata_runner_ignores_legacy_cli_project_dir(monkeypatch, tmp_path) -> None:
    from parallax.integrations.macrodata.runner import MacrodataBundleRunner

    calls: list[dict[str, object]] = []

    class Settings:
        providers = SimpleNamespace(macrodata=SimpleNamespace(fred_api_key_env=None))
        macrodata_fred_api_key = None
        workers = _macrodata_workers()
        macrodata_cli_project_dir = str(tmp_path)

    class Completed:
        returncode = 0
        stdout = json.dumps(ENVELOPE)
        stderr = ""

    def fake_run(command, *, env, cwd, capture_output, text, check, timeout=None):
        calls.append({"command": command, "cwd": cwd, "capture_output": capture_output, "text": text, "check": check})
        return Completed()

    monkeypatch.setattr("parallax.integrations.macrodata.runner._macrodata_cli_entrypoint_available", lambda: True)
    monkeypatch.setattr("parallax.integrations.macrodata.runner.subprocess.run", fake_run)

    result = MacrodataBundleRunner(settings=Settings()).history_bundle(
        bundle="macro-core",
        start="2026-01-01",
        end="2026-05-21",
    )

    assert "cli_project_dir" not in result.diagnostics
    assert calls[0]["cwd"] is None


def test_macrodata_runner_removes_stale_parent_fred_key_when_configured_env_missing(monkeypatch) -> None:
    from parallax.integrations.macrodata.runner import MacrodataBundleRunner

    stale_secret = "dummy-stale-fred-secret"
    calls: list[dict[str, object]] = []

    class Settings:
        providers = SimpleNamespace(macrodata=SimpleNamespace(fred_api_key_env="APP_FRED_KEY"))
        macrodata_fred_api_key = None
        workers = _macrodata_workers()

    class Completed:
        returncode = 0
        stdout = json.dumps(ENVELOPE)
        stderr = ""

    def fake_run(command, *, env, cwd, capture_output, text, check, timeout=None):
        calls.append({"env_has_fred": "FRED_API_KEY" in env, "env_fred_api_key": env.get("FRED_API_KEY")})
        return Completed()

    monkeypatch.setenv("FRED_API_KEY", stale_secret)
    monkeypatch.delenv("APP_FRED_KEY", raising=False)
    monkeypatch.setattr("parallax.integrations.macrodata.runner._macrodata_cli_entrypoint_available", lambda: True)
    monkeypatch.setattr("parallax.integrations.macrodata.runner.subprocess.run", fake_run)

    result = MacrodataBundleRunner(settings=Settings()).history_bundle(
        bundle="macro-core",
        start="2026-01-01",
        end="2026-05-21",
    )

    assert result.diagnostics["fred_api_key_env"] == "APP_FRED_KEY"
    assert result.diagnostics["fred_api_key_configured"] is False
    assert calls == [{"env_has_fred": False, "env_fred_api_key": None}]
    assert stale_secret not in json.dumps(result.diagnostics)


def test_macro_import_bundle_from_file_dispatches_to_importer(tmp_path, monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    bundle_path = tmp_path / "macro-core.json"
    bundle_path.write_text(json.dumps(ENVELOPE), encoding="utf-8")
    settings = FakeSettings()
    captured: dict[str, object] = {}
    monkeypatch.setattr(macro_module, "load_settings", lambda require_ws_token=False: settings)

    def fake_import(current_settings, envelope, *, now_ms):
        captured.update(settings=current_settings, envelope=envelope, now_ms=now_ms)
        return {"bundle_name": "macro-core", "imported_observation_count": 1}

    monkeypatch.setattr(macro_module, "import_macro_bundle", fake_import)
    monkeypatch.setattr(macro_module, "_now_ms", lambda: NOW_MS)
    stdout = io.StringIO()

    code = main(["macro", "import-bundle", "--file", str(bundle_path)], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload == {"ok": True, "data": {"bundle_name": "macro-core", "imported_observation_count": 1}}
    assert captured == {"settings": settings, "envelope": ENVELOPE, "now_ms": NOW_MS}


def test_macro_sync_delegates_to_sync_service_without_projection_payload(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    settings = FakeSettings()
    monkeypatch.setattr(macro_module, "load_settings", lambda require_ws_token=False: settings)
    calls: list[dict[str, object]] = []
    summary = MacroSyncRunSummary(
        sync_run_id="sync-run-1",
        status="ok",
        observations_count=1,
        imported_observation_count=1,
        asof_date=date(2026, 5, 21),
        max_observed_at=date(2026, 5, 21),
        diagnostics={"fred_api_key_env": "APP_FRED_KEY", "fred_api_key_configured": True},
    )

    def fake_sync(current_settings, **kwargs):
        calls.append({"settings": current_settings, **kwargs})
        return MacroSyncExecution(summary=summary, diagnostics=dict(summary.diagnostics))

    monkeypatch.setattr(macro_module, "sync_macro_window", fake_sync)
    monkeypatch.setattr(macro_module, "_now_ms", lambda: NOW_MS)
    stdout = io.StringIO()

    code = main(
        ["macro", "sync", "--bundle", "macro-core", "--start", "2026-01-01", "--end", "2026-05-21"],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert "projection" not in payload["data"]
    assert payload["data"]["fred_api_key_env"] == "APP_FRED_KEY"
    assert payload["data"]["fred_api_key_configured"] is True
    assert payload["data"]["sync"] == {
        "sync_run_id": "sync-run-1",
        "status": "ok",
        "window_start": "2026-01-01",
        "window_end": "2026-05-21",
        "imported_observation_count": 1,
        "max_observed_at": "2026-05-21",
        "asof_date": "2026-05-21",
    }
    assert calls == [
        {
            "settings": settings,
            "bundle_name": "macro-core",
            "window_start": date(2026, 1, 1),
            "window_end": date(2026, 5, 21),
            "now_ms": NOW_MS,
        }
    ]


def test_macro_sync_failure_returns_nonzero_and_does_not_project(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    settings = FakeSettings()
    monkeypatch.setattr(macro_module, "load_settings", lambda require_ws_token=False: settings)
    summary = MacroSyncRunSummary(
        sync_run_id="sync-run-fail",
        status="config_error",
        observations_count=0,
        imported_observation_count=0,
        asof_date=None,
        max_observed_at=None,
        diagnostics={"fred_api_key_env": "FINANCE_FRED_API_KEY", "fred_api_key_configured": False},
    )
    monkeypatch.setattr(
        macro_module,
        "sync_macro_window",
        lambda *_args, **_kwargs: MacroSyncExecution(summary=summary, diagnostics=dict(summary.diagnostics)),
    )
    stdout = io.StringIO()

    code = main(
        ["macro", "sync", "--bundle", "macro-core", "--start", "2026-01-01", "--end", "2026-05-21"],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 1
    assert payload["ok"] is False
    assert payload["error"] == "macro_sync_failed"
    assert payload["data"]["sync"]["status"] == "config_error"
    assert "projection" not in payload["data"]


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("not-a-date", "2026-05-21", {"error": "macro_sync_invalid_date", "field": "start"}),
        ("2026-05-21", "also-bad", {"error": "macro_sync_invalid_date", "field": "end"}),
        ("20260521", "2026-05-22", {"error": "macro_sync_invalid_date", "field": "start"}),
        ("2026-05-21", "2026-W22-5", {"error": "macro_sync_invalid_date", "field": "end"}),
        ("2026-05-22", "2026-05-21", {"error": "macro_sync_invalid_date_range"}),
    ],
)
def test_macro_sync_validates_dates_before_service_call(
    monkeypatch,
    start: str,
    end: str,
    expected: dict[str, str],
) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    monkeypatch.setattr(macro_module, "load_settings", lambda require_ws_token=False: FakeSettings())
    monkeypatch.setattr(
        macro_module,
        "sync_macro_window",
        lambda *_args, **_kwargs: pytest.fail("invalid CLI dates must not reach the operation"),
    )
    stdout = io.StringIO()

    code = main(["macro", "sync", "--bundle", "macro-core", "--start", start, "--end", end], stdout=stdout)

    assert code == 2
    payload = json.loads(stdout.getvalue())
    assert payload["ok"] is False
    for key, value in expected.items():
        assert payload[key] == value


def test_macro_import_bundle_from_stdin_dispatches_to_importer(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    settings = FakeSettings()
    monkeypatch.setattr(macro_module, "load_settings", lambda require_ws_token=False: settings)
    monkeypatch.setattr(
        macro_module,
        "import_macro_bundle",
        lambda current_settings, envelope, *, now_ms: {
            "coverage": envelope["data"]["snapshot"]["coverage"],
            "settings_match": current_settings is settings,
            "now_ms": now_ms,
        },
    )
    monkeypatch.setattr(macro_module, "_now_ms", lambda: NOW_MS)
    monkeypatch.setattr(macro_module.sys, "stdin", io.StringIO(json.dumps(ENVELOPE)))
    stdout = io.StringIO()

    code = main(["macro", "import-bundle", "--stdin"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"] == {
        "coverage": {"requested": 20, "available": 1},
        "settings_match": True,
        "now_ms": NOW_MS,
    }


def test_macro_import_bundle_requires_exactly_one_input() -> None:
    stdout = io.StringIO()

    code = main(["macro", "import-bundle"], stdout=stdout)

    assert code == 2
    assert json.loads(stdout.getvalue()) == {"ok": False, "error": "macro_import_bundle_requires_file_or_stdin"}


def test_macro_import_bundle_reports_repository_failure_without_secret(tmp_path, monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    bundle_path = tmp_path / "macro-core.json"
    bundle_path.write_text(json.dumps(ENVELOPE), encoding="utf-8")
    monkeypatch.setattr(macro_module, "load_settings", lambda require_ws_token=False: FakeSettings())
    monkeypatch.setattr(
        macro_module,
        "import_macro_bundle",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("repository failed with secret")),
    )
    stdout = io.StringIO()

    code = main(["macro", "import-bundle", "--file", str(bundle_path)], stdout=stdout)

    output = stdout.getvalue()
    assert code == 1
    assert "secret" not in output
    assert json.loads(output) == {
        "ok": False,
        "error": "macro_import_bundle_failed",
        "detail": "RuntimeError",
    }


def test_macro_project_once_command_is_removed(monkeypatch) -> None:
    stdout = io.StringIO()

    code = main(["macro", "project-once"], stdout=stdout)

    assert code == 2
    assert stdout.getvalue() == ""


def test_macro_status_reports_material_facts_sync_queue_and_latest_research(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository(
        material_facts={
            "max_observed_at": date(2026, 5, 21),
            "observations_count": 87_002,
            "concept_count": 188,
        },
        sync_queue={"open_count": 2, "due_count": 1, "running_count": 0},
    )
    research = FakeMacroResearchRepository(
        state={
            "session_date": date(2026, 5, 21),
            "market_cutoff_ms": 1_779_000_000_000,
            "sealed_at_ms": 1_779_000_030_000,
            "run_status": "published",
            "attempt_count": 1,
            "max_attempts": 3,
            "due_at_ms": 1_779_000_030_000,
            "published_at_ms": 1_779_000_120_000,
            "model_name": "openai/gpt-5.6-terra",
            "prompt_version": "macro-research-v1",
            "workflow_version": "deepagents-v1",
            "last_error_code": None,
            "last_error_message": None,
            "artifact_json": {"schema_version": "macro_research_artifact_v2"},
            "report_markdown": "# 宏观研究",
        }
    )
    _patch_macro_dependencies(
        monkeypatch,
        macro_module,
        repo,
        research=research,
        settings=FakeSettings(fred_env="APP_FRED_KEY"),
    )
    monkeypatch.setenv("APP_FRED_KEY", "dummy-fred-secret")
    stdout = io.StringIO()

    code = main(["macro", "status"], stdout=stdout)

    output = stdout.getvalue()
    assert code == 0
    assert "dummy-fred-secret" not in output
    payload = json.loads(output)
    data = payload["data"]
    assert payload["ok"] is True
    assert data["migration_ready"] is True
    assert data["fred_api_key_env"] == "APP_FRED_KEY"
    assert data["fred_api_key_configured"] is True
    assert data["material_facts"] == {
        "max_observed_at": "2026-05-21",
        "observations_count": 87_002,
        "concept_count": 188,
    }
    assert data["sync_queue"] == {"open_count": 2, "due_count": 1, "running_count": 0}
    assert data["latest_research"] == {
        "session_date": "2026-05-21",
        "market_cutoff_ms": 1_779_000_000_000,
        "sealed_at_ms": 1_779_000_030_000,
        "run_status": "published",
        "attempt_count": 1,
        "max_attempts": 3,
        "due_at_ms": 1_779_000_030_000,
        "published_at_ms": 1_779_000_120_000,
        "model_name": "openai/gpt-5.6-terra",
        "prompt_version": "macro-research-v1",
        "workflow_version": "deepagents-v1",
        "last_error_code": None,
        "last_error_message": None,
    }
    assert "artifact_json" not in output
    assert "report_markdown" not in output
    assert repo.material_fact_state_calls == [date(2026, 5, 17)]
    assert research.calls == [None]


def test_macro_status_reports_missing_latest_research_without_synthesizing_a_judgment(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository(
        material_facts={
            "max_observed_at": date(2026, 5, 21),
            "observations_count": 42,
            "concept_count": 7,
        }
    )
    research = FakeMacroResearchRepository(state=None)
    _patch_macro_dependencies(monkeypatch, macro_module, repo, research=research)
    stdout = io.StringIO()

    code = main(["macro", "status"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["data"]["material_facts"] == {
        "max_observed_at": "2026-05-21",
        "observations_count": 42,
        "concept_count": 7,
    }
    assert payload["data"]["latest_research"] is None
    assert "judgment" not in payload["data"]
    assert research.calls == [None]


def test_macro_status_reports_failed_research_run_state(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    research = FakeMacroResearchRepository(
        state={
            "session_date": date(2026, 5, 16),
            "market_cutoff_ms": 1_778_800_000_000,
            "sealed_at_ms": 1_778_800_030_000,
            "run_status": "failed",
            "attempt_count": 3,
            "max_attempts": 3,
            "due_at_ms": 1_778_800_030_000,
            "published_at_ms": None,
            "model_name": None,
            "prompt_version": None,
            "workflow_version": None,
            "last_error_code": "provider_timeout",
            "last_error_message": "macro research provider timed out",
        }
    )
    _patch_macro_dependencies(
        monkeypatch,
        macro_module,
        FakeMacroIntelRepository(),
        research=research,
    )
    stdout = io.StringIO()

    code = main(["macro", "status"], stdout=stdout)

    data = json.loads(stdout.getvalue())["data"]
    assert code == 0
    assert data["latest_research"]["session_date"] == "2026-05-16"
    assert data["latest_research"]["run_status"] == "failed"
    assert data["latest_research"]["attempt_count"] == 3
    assert data["latest_research"]["last_error_code"] == "provider_timeout"
    assert data["latest_research"]["published_at_ms"] is None


def test_macro_status_repository_exception_returns_structured_error_without_secret(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository(fail_material_fact_state=True)
    _patch_macro_dependencies(monkeypatch, macro_module, repo, settings=FakeSettings(fred_env="APP_FRED_KEY"))
    monkeypatch.setenv("APP_FRED_KEY", "dummy-fred-secret")
    stdout = io.StringIO()

    code = main(["macro", "status"], stdout=stdout)

    output = stdout.getvalue()
    payload = json.loads(output)
    assert code == 1
    assert "dummy-fred-secret" not in output
    assert payload == {
        "ok": False,
        "error": "macro_status_unavailable",
        "detail": "RuntimeError",
        "error_type": "RuntimeError",
        "data": {
            "fred_api_key_env": "APP_FRED_KEY",
            "fred_api_key_configured": True,
            "macrodata_cli": {
                "package_version": "0.1.test",
                "entrypoint_available": True,
                "command_mode": "python_entrypoint",
                "command_path": sys.executable,
                "command_error_code": None,
                "catalog_available": True,
                "required_series_count": len(MACRO_IMPORTABLE_PROVIDER_SERIES_TO_CONCEPT),
                "missing_required_series_count": 0,
                "required_series_available": True,
                "missing_required_series_sample": [],
                "required_bundle_count": 5,
                "missing_required_bundle_count": 0,
                "required_bundles_available": True,
                "missing_required_bundles": [],
                "macro_core_bundle_available": True,
                "missing_required_bundle_series_count": 0,
                "required_bundle_series_available": True,
                "missing_required_bundle_series_sample": [],
                "missing_required_bundle_series_by_bundle": {},
            },
        },
    }


def test_macro_status_requires_importable_event_bundle_series(monkeypatch) -> None:
    from parallax.app.operations import macro as operation_module
    from parallax.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository()
    captured: dict[str, object] = {}
    _patch_macro_dependencies(monkeypatch, macro_module, repo, settings=FakeSettings(fred_env="APP_FRED_KEY"))

    def fake_macrodata_runtime_state(*, required_series, required_bundles, required_bundle_series):
        captured["required_series"] = tuple(required_series)
        captured["required_bundles"] = tuple(required_bundles)
        captured["required_bundle_series"] = {
            bundle_name: tuple(series_keys) for bundle_name, series_keys in required_bundle_series.items()
        }
        return {
            "package_version": "0.1.test",
            "entrypoint_available": True,
            "command_mode": "python_entrypoint",
            "command_path": sys.executable,
            "command_error_code": None,
            "catalog_available": True,
            "required_series_count": len(required_series),
            "missing_required_series_count": 0,
            "required_series_available": True,
            "missing_required_series_sample": [],
            "required_bundle_count": len(required_bundles),
            "missing_required_bundle_count": 0,
            "required_bundles_available": True,
            "missing_required_bundles": [],
            "macro_core_bundle_available": True,
            "missing_required_bundle_series_count": 0,
            "required_bundle_series_available": True,
            "missing_required_bundle_series_sample": [],
            "missing_required_bundle_series_by_bundle": {},
        }

    monkeypatch.setattr(operation_module, "macrodata_runtime_state", fake_macrodata_runtime_state)
    stdout = io.StringIO()

    code = main(["macro", "status"], stdout=stdout)

    assert code == 0
    assert captured["required_series"] == tuple(MACRO_IMPORTABLE_PROVIDER_SERIES_TO_CONCEPT)
    assert captured["required_bundles"] == (
        "macro-core",
        "macro-calendar-core",
        "treasury-auction-core",
        "fed-text-core",
        "crypto-derivatives-core",
    )
    assert all(
        not series_key.startswith(("okx:", "deribit:"))
        for series_key in captured["required_bundle_series"]["macro-core"]
    )
    assert captured["required_bundle_series"] == {
        "macro-core": tuple(
            series_key
            for series_key, concept_key in MACRO_PROVIDER_SERIES_TO_CONCEPT.items()
            if not concept_key.startswith("crypto_derivatives:")
        ),
        "macro-calendar-core": tuple(
            series_key
            for series_key in MACRO_EVENT_PROVIDER_SERIES_TO_CONCEPT
            if series_key.startswith("official_calendar:")
        ),
        "treasury-auction-core": tuple(
            series_key
            for series_key in MACRO_EVENT_PROVIDER_SERIES_TO_CONCEPT
            if series_key.startswith("treasury_auction:")
        ),
        "fed-text-core": tuple(
            series_key
            for series_key in MACRO_EVENT_PROVIDER_SERIES_TO_CONCEPT
            if series_key.startswith("official_fed_text:")
        ),
        "crypto-derivatives-core": tuple(
            series_key
            for series_key, concept_key in MACRO_PROVIDER_SERIES_TO_CONCEPT.items()
            if concept_key.startswith("crypto_derivatives:")
        ),
    }


def _patch_macro_dependencies(
    monkeypatch,
    macro_module,
    repo: FakeMacroIntelRepository,
    *,
    research: FakeMacroResearchRepository | None = None,
    settings: object | None = None,
) -> None:
    from parallax.app.operations import macro as operation_module

    @contextmanager
    def fake_repositories(_settings: object):
        yield FakeRepositorySession(
            repo,
            research or FakeMacroResearchRepository(state=None),
        )

    monkeypatch.setattr(macro_module, "load_settings", lambda require_ws_token=False: settings or FakeSettings())
    monkeypatch.setattr(operation_module, "repositories", fake_repositories)
    monkeypatch.setattr(
        operation_module,
        "macrodata_runtime_state",
        lambda *, required_series, required_bundles, required_bundle_series: {
            "package_version": "0.1.test",
            "entrypoint_available": True,
            "command_mode": "python_entrypoint",
            "command_path": sys.executable,
            "command_error_code": None,
            "catalog_available": True,
            "required_series_count": len(required_series),
            "missing_required_series_count": 0,
            "required_series_available": True,
            "missing_required_series_sample": [],
            "required_bundle_count": len(required_bundles),
            "missing_required_bundle_count": 0,
            "required_bundles_available": True,
            "missing_required_bundles": [],
            "macro_core_bundle_available": True,
            "missing_required_bundle_series_count": 0,
            "required_bundle_series_available": True,
            "missing_required_bundle_series_sample": [],
            "missing_required_bundle_series_by_bundle": {},
        },
    )
    monkeypatch.setattr(operation_module, "_now_ms", lambda: NOW_MS)
    monkeypatch.setattr(macro_module, "_now_ms", lambda: NOW_MS)


class FakeSettings:
    def __init__(self, *, fred_env: str | None = None) -> None:
        self.providers = SimpleNamespace(macrodata=SimpleNamespace(fred_api_key_env=fred_env))
        self.macrodata_fred_api_key = None
        self.workers = _macrodata_workers()


class FakeMacroIntelRepository:
    def __init__(
        self,
        *,
        material_facts: dict[str, object] | None = None,
        sync_queue: dict[str, object] | None = None,
        fail_material_fact_state: bool = False,
    ) -> None:
        self.material_facts = material_facts or {
            "max_observed_at": None,
            "observations_count": 0,
            "concept_count": 0,
        }
        self.sync_queue = sync_queue or {}
        self.fail_material_fact_state = fail_material_fact_state
        self.material_fact_state_calls: list[date] = []

    def material_fact_state(self, *, through_date: date) -> dict[str, object]:
        if self.fail_material_fact_state:
            raise RuntimeError("postgres://user:secret@db material facts failed")
        self.material_fact_state_calls.append(through_date)
        return dict(self.material_facts)

    def macro_sync_queue_summary(self, *, now_ms: int) -> dict[str, object]:
        assert now_ms == NOW_MS
        return self.sync_queue


class FakeMacroResearchRepository:
    def __init__(self, *, state: dict[str, object] | None) -> None:
        self.state = state
        self.calls: list[date | None] = []

    def research_state(self, session_date: date | None) -> dict[str, object] | None:
        self.calls.append(session_date)
        return dict(self.state) if self.state is not None else None


class FakeRepositorySession:
    def __init__(
        self,
        macro_intel: FakeMacroIntelRepository,
        macro_research: FakeMacroResearchRepository,
    ) -> None:
        self.macro_intel = macro_intel
        self.macro_research = macro_research
