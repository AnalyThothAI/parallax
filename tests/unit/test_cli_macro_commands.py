from __future__ import annotations

import io
import json
import subprocess
import sys
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace, TracebackType

import pytest

from parallax.app.operations.macro import MacroSyncExecution
from parallax.app.surfaces.cli.parser import build_parser
from parallax.cli import main
from parallax.domains.macro_intel._constants import (
    MACRO_EVENT_PROVIDER_SERIES_TO_CONCEPT,
    MACRO_IMPORTABLE_PROVIDER_SERIES_TO_CONCEPT,
    MACRO_PROVIDER_SERIES_TO_CONCEPT,
)
from parallax.domains.macro_intel.observation_identity import (
    macro_observation_fact_payload_hash,
    macro_observation_id,
)
from parallax.domains.macro_intel.services.macro_concept_manifest import (
    MACRO_EVIDENCE_CONCEPTS,
    MACRO_PAGE_IDS,
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


def test_macro_status_reports_repository_counts(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository()
    repo.sync_queue = {"open_count": 2, "due_count": 1, "running_count": 0}
    repo.publication_state = {
        "projection_version": "macro_evidence_v1",
        "row_count": 318,
        "latest_attempt_status": "published",
        "latest_attempt_finished_at_ms": NOW_MS,
        "latest_attempt_error": None,
    }
    repo.latest = {
        "snapshot_key": "current",
        "projection_version": "macro_evidence_v1",
        "fact_watermark": "2026-05-20",
        "market_cutoff": "2026-05-20",
        "computed_at_ms": NOW_MS,
        "payload_hash": "sha256:test",
        **{f"{page_id}_json": _macro_page(page_id) for page_id in MACRO_PAGE_IDS},
    }
    _patch_macro_dependencies(monkeypatch, macro_module, repo, settings=FakeSettings(fred_env="APP_FRED_KEY"))
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
    assert data["observations_count"] == 0
    assert data["concept_count"] == 0
    assert data["manifest"] == {
        "declared_concept_count": len(MACRO_EVIDENCE_CONCEPTS),
        "observed_concept_count": len(MACRO_EVIDENCE_CONCEPTS),
        "missing_concept_count": 0,
        "missing_concept_sample": [],
        "lookback_days": 1095,
    }
    assert data["sync_queue"] == {"open_count": 2, "due_count": 1, "running_count": 0}
    assert data["publication_state"]["projection_version"] == "macro_evidence_v1"
    assert data["facts_max_observed_at"] == "2026-05-21"
    assert data["projection_lag_days"] == 1
    assert data["projection_behind_facts"] is True
    assert data["latest_snapshot"] == {
        "projection_version": "macro_evidence_v1",
        "fact_watermark": "2026-05-20",
        "market_cutoff": "2026-05-20",
        "computed_at_ms": NOW_MS,
        "pages": {
            page_id: {
                "status": "insufficient_evidence",
                "judgment": "insufficient_evidence",
                "freshness_status": "insufficient_evidence",
                "evidence_count": 0,
                "unavailable_evidence_count": 0,
            }
            for page_id in MACRO_PAGE_IDS
        },
    }
    assert "regime" not in output
    assert "overall_score" not in output
    assert "coverage_ratio" not in output
    assert repo.latest_snapshot_calls == 1


def test_macro_status_reports_projection_behind_when_material_facts_exist_without_snapshot(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository()
    repo.latest = None
    _patch_macro_dependencies(monkeypatch, macro_module, repo)
    stdout = io.StringIO()

    code = main(["macro", "status"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["data"]["facts_max_observed_at"] == "2026-05-21"
    assert payload["data"]["projection_lag_days"] is None
    assert payload["data"]["projection_behind_facts"] is True
    assert payload["data"]["latest_snapshot"] is None


def test_macro_status_compares_snapshot_to_raw_material_facts_not_compact_series(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository(
        concept_history=[
            {
                "concept_key": concept_key,
                "points": 21,
                "latest_observed_at": "2026-05-15",
                "oldest_observed_at": "2026-04-15",
                "sources": ["fixture"],
            }
            for concept_key in MACRO_EVIDENCE_CONCEPTS
        ],
        material_fact_max_observed_at="2026-05-16",
    )
    repo.latest = {
        "snapshot_key": "current",
        "projection_version": "macro_evidence_v1",
        "fact_watermark": "2026-05-15",
        "market_cutoff": "2026-05-15",
        "computed_at_ms": NOW_MS,
        "payload_hash": "sha256:test",
        **{f"{page_id}_json": _macro_page(page_id) for page_id in MACRO_PAGE_IDS},
    }
    _patch_macro_dependencies(monkeypatch, macro_module, repo)
    stdout = io.StringIO()

    code = main(["macro", "status"], stdout=stdout)

    data = json.loads(stdout.getvalue())["data"]
    assert code == 0
    assert data["facts_max_observed_at"] == "2026-05-16"
    assert data["projection_lag_days"] == 1
    assert data["projection_behind_facts"] is True
    assert repo.material_fact_max_calls
    queried_concepts, through_date = repo.material_fact_max_calls[0]
    assert "asset:spy" in queried_concepts
    assert "event:fomc_decision_next" not in queried_concepts
    assert through_date == date(2026, 5, 17)


def test_macro_status_repository_exception_returns_structured_error_without_secret(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository(fail_concept_history_counts=True)
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


def test_macro_status_reports_manifest_availability_without_universal_readiness_score(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository(
        concept_history=[
            {
                "concept_key": "asset:spx",
                "points": 1,
                "latest_observed_at": "2026-05-21",
                "oldest_observed_at": "2026-05-21",
                "sources": ["fred"],
            }
        ]
    )
    _patch_macro_dependencies(monkeypatch, macro_module, repo)
    stdout = io.StringIO()

    code = main(["macro", "status"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["data"]["manifest"]["observed_concept_count"] == 1
    assert payload["data"]["manifest"]["missing_concept_count"] == len(MACRO_EVIDENCE_CONCEPTS) - 1
    assert "history_ready" not in payload["data"]
    assert "history_coverage" not in payload["data"]
    assert "coverage_ratio" not in payload["data"]["manifest"]
    assert repo.concept_history_count_calls == [
        {
            "concept_keys": MACRO_EVIDENCE_CONCEPTS,
            "lookback_days": 1095,
        }
    ]


def _patch_macro_dependencies(
    monkeypatch,
    macro_module,
    repo: FakeMacroIntelRepository,
    *,
    settings: object | None = None,
) -> None:
    from parallax.app.operations import macro as operation_module

    @contextmanager
    def fake_repositories(_settings: object):
        yield FakeRepositorySession(repo)

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


def _macro_page(page_id: str) -> dict[str, object]:
    return {
        "page_id": page_id,
        "conclusion": {
            "status": "insufficient_evidence",
            "judgment": "insufficient_evidence",
        },
        "freshness": {"status": "insufficient_evidence"},
        "evidence": [],
        "unavailable_evidence": [],
    }


class FakeSettings:
    def __init__(self, *, fred_env: str | None = None) -> None:
        self.providers = SimpleNamespace(macrodata=SimpleNamespace(fred_api_key_env=fred_env))
        self.macrodata_fred_api_key = None
        self.workers = _macrodata_workers()


class FakeConnection:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


class FakeMacroIntelRepository:
    def __init__(
        self,
        *,
        observations: list[dict[str, object]] | None = None,
        concept_history: list[dict[str, object]] | None = None,
        fail_record_run: bool = False,
        fail_latest_observations: bool = False,
        fail_observations_for_series: bool = False,
        fail_concept_history_counts: bool = False,
        material_fact_max_observed_at: str | None = "2026-05-21",
    ) -> None:
        self.conn = FakeConnection()
        self.source_observations = observations or []
        self.source_concept_history = concept_history
        self.observations: list[dict[str, object]] = []
        self.sync_runs: list[dict[str, object]] = []
        self.snapshots: list[dict[str, object]] = []
        self.latest_observation_limits: list[int] = []
        self.observations_for_concepts_calls: list[dict[str, object]] = []
        self.concept_history_count_calls: list[dict[str, object]] = []
        self.sync_queue: dict[str, object] = {}
        self.enqueued_dirty_targets: list[dict[str, object]] = []
        self.publication_state: dict[str, object] | None = None
        self.latest: dict[str, object] | None = None
        self.latest_snapshot_calls = 0
        self.fail_record_run = fail_record_run
        self.fail_latest_observations = fail_latest_observations
        self.fail_observations_for_series = fail_observations_for_series
        self.fail_concept_history_counts = fail_concept_history_counts
        self.material_fact_max_observed_at_value = material_fact_max_observed_at
        self.material_fact_max_calls: list[tuple[tuple[str, ...], date]] = []
        self.transaction_events: list[str] = []
        self._observation_index: dict[str, int] = {}

    def upsert_observation(self, observation: dict[str, object]) -> dict[str, object]:
        observation_id = macro_observation_id(observation)
        fact_payload_hash = macro_observation_fact_payload_hash(observation)
        existing_index = self._observation_index.get(observation_id)
        if existing_index is None:
            self._observation_index[observation_id] = len(self.observations)
            self.observations.append(dict(observation))
            status = "inserted"
        else:
            existing_hash = macro_observation_fact_payload_hash(self.observations[existing_index])
            if existing_hash == fact_payload_hash:
                status = "noop"
            else:
                self.observations[existing_index] = dict(observation)
                status = "changed"
        return {
            "observation_id": observation_id,
            "status": status,
            "concept_key": str(observation["concept_key"]),
            "observed_at": observation["observed_at"],
            "fact_payload_hash": fact_payload_hash,
        }

    def record_macro_sync_run(self, sync_run: dict[str, object]) -> None:
        if self.fail_record_run:
            raise RuntimeError("postgres://user:secret@db record failed")
        self.sync_runs.append(sync_run)

    def enqueue_macro_projection_dirty_targets_for_changes(self, **kwargs: object) -> int:
        self.enqueued_dirty_targets.append(dict(kwargs))
        return 1

    def latest_observations(self, *, limit: int) -> list[dict[str, object]]:
        if self.fail_latest_observations:
            raise RuntimeError("postgres://user:secret@db latest failed")
        self.latest_observation_limits.append(limit)
        return self.source_observations

    def observations_for_concepts(
        self,
        *,
        concept_keys: tuple[str, ...],
        lookback_days: int,
        limit_per_series: int,
    ) -> list[dict[str, object]]:
        if self.fail_observations_for_series:
            raise RuntimeError("postgres://user:secret@db history failed")
        self.observations_for_concepts_calls.append(
            {
                "concept_keys": concept_keys,
                "lookback_days": lookback_days,
                "limit_per_series": limit_per_series,
            }
        )
        return self.source_observations

    def concept_history_counts(
        self,
        *,
        concept_keys: tuple[str, ...],
        lookback_days: int,
    ) -> list[dict[str, object]]:
        if self.fail_concept_history_counts:
            raise RuntimeError("postgres://user:secret@db history failed")
        self.concept_history_count_calls.append(
            {
                "concept_keys": concept_keys,
                "lookback_days": lookback_days,
            }
        )
        if self.source_concept_history is not None:
            explicit = {str(row["concept_key"]): row for row in self.source_concept_history}
            return [
                dict(
                    explicit.get(
                        concept_key,
                        {
                            "concept_key": concept_key,
                            "points": 0,
                            "latest_observed_at": None,
                            "oldest_observed_at": None,
                            "sources": [],
                        },
                    )
                )
                for concept_key in concept_keys
            ]
        return [
            {
                "concept_key": concept_key,
                "points": 126,
                "latest_observed_at": "2026-05-21",
                "oldest_observed_at": "2026-01-01",
                "sources": ["fixture"],
            }
            for concept_key in concept_keys
        ]

    def material_fact_max_observed_at(
        self,
        *,
        concept_keys: tuple[str, ...],
        through_date: date,
    ) -> str | None:
        self.material_fact_max_calls.append((concept_keys, through_date))
        return self.material_fact_max_observed_at_value

    def insert_snapshot(self, snapshot: dict[str, object]) -> None:
        self.snapshots.append(snapshot)

    def observations_count(self) -> int:
        return len(self.observations)

    def concept_count(self) -> int:
        return len({observation["concept_key"] for observation in self.observations})

    def macro_sync_queue_summary(self, *, now_ms: int) -> dict[str, object]:
        assert now_ms == NOW_MS
        return self.sync_queue

    def macro_series_publication_state(self, projection_version: str) -> dict[str, object] | None:
        assert projection_version == "macro_evidence_v1"
        return self.publication_state

    def latest_snapshot(self) -> dict[str, object] | None:
        self.latest_snapshot_calls += 1
        return self.latest


class FakeRepositorySession:
    def __init__(self, macro_intel: FakeMacroIntelRepository) -> None:
        self.macro_intel = macro_intel
        self.conn = macro_intel.conn
        self.in_transaction = False

    def transaction(self):
        return FakeTransaction(self)

    def require_transaction(self, *, operation: str) -> None:
        assert operation == "macrodata_bundle_import"
        if not self.in_transaction:
            raise RuntimeError(f"{operation}:transaction_required")


class FakeTransaction:
    def __init__(self, repos: FakeRepositorySession) -> None:
        self.repos = repos
        self.macro_intel = repos.macro_intel
        self.observations: list[dict[str, object]] = []
        self.observation_index: dict[str, int] = {}
        self.sync_runs: list[dict[str, object]] = []
        self.enqueued_dirty_targets: list[dict[str, object]] = []

    def __enter__(self):
        self.repos.in_transaction = True
        self.observations = list(self.macro_intel.observations)
        self.observation_index = dict(self.macro_intel._observation_index)
        self.sync_runs = list(self.macro_intel.sync_runs)
        self.enqueued_dirty_targets = list(self.macro_intel.enqueued_dirty_targets)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if exc_type is not None:
            self.macro_intel.observations = self.observations
            self.macro_intel._observation_index = self.observation_index
            self.macro_intel.sync_runs = self.sync_runs
            self.macro_intel.enqueued_dirty_targets = self.enqueued_dirty_targets
            self.macro_intel.transaction_events.append("rollback")
        else:
            self.macro_intel.transaction_events.append("commit")
        self.repos.in_transaction = False
        return False
