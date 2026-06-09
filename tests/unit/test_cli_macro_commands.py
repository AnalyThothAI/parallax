from __future__ import annotations

import io
import json
import subprocess
import sys
from contextlib import contextmanager
from datetime import date
from types import TracebackType

import pytest

from parallax.app.surfaces.cli.parser import build_parser
from parallax.cli import main
from parallax.domains.macro_intel._constants import MACRO_HISTORY_REQUIRED_CONCEPTS, MACRO_PROVIDER_SERIES_TO_CONCEPT
from parallax.domains.macro_intel.observation_identity import (
    macro_observation_fact_payload_hash,
    macro_observation_id,
)
from parallax.domains.macro_intel.services.macro_sync_types import MacroSyncRunSummary

NOW_MS = 1_779_000_000_000

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
    resolved = "/app/.venv/bin/macrodata"
    calls: list[dict[str, object]] = []

    class Settings:
        macrodata_fred_api_key_env = "APP_FRED_KEY"

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
    monkeypatch.setattr(
        "parallax.integrations.macrodata.runner.resolve_macrodata_executable",
        lambda *, environ=None: resolved,
    )
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
                resolved,
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
    assert calls[0]["command"][0] == resolved
    assert "uv" not in calls[0]["command"]
    assert calls[0]["command"][1:] == [
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


def test_macrodata_runner_uses_default_fred_env_when_unset(monkeypatch) -> None:
    from parallax.integrations.macrodata.runner import MacrodataBundleRunner

    calls: list[dict[str, object]] = []

    class Settings:
        macrodata_fred_api_key_env = None

    class Completed:
        returncode = 0
        stdout = json.dumps(ENVELOPE)
        stderr = ""

    def fake_run(command, *, env, cwd, capture_output, text, check, timeout=None):
        calls.append({"command": command, "env_has_fred": "FRED_API_KEY" in env, "cwd": cwd})
        return Completed()

    monkeypatch.delenv("FINANCE_FRED_API_KEY", raising=False)
    monkeypatch.setattr(
        "parallax.integrations.macrodata.runner.resolve_macrodata_executable",
        lambda *, environ=None: "/app/.venv/bin/macrodata",
    )
    monkeypatch.setattr("parallax.integrations.macrodata.runner.subprocess.run", fake_run)

    result = MacrodataBundleRunner(settings=Settings()).history_bundle(
        bundle="macro-core",
        start="2026-01-01",
        end="2026-05-21",
    )

    assert result.diagnostics["fred_api_key_env"] == "FINANCE_FRED_API_KEY"
    assert result.diagnostics["fred_api_key_configured"] is False
    assert calls[0]["env_has_fred"] is False


def test_macrodata_runner_falls_back_to_python_entrypoint_when_console_script_missing(monkeypatch) -> None:
    from parallax.integrations.macrodata.runner import MacrodataBundleRunner, MacrodataRunnerError

    calls: list[dict[str, object]] = []

    class Settings:
        macrodata_fred_api_key_env = None

    class Completed:
        returncode = 0
        stdout = json.dumps(ENVELOPE)
        stderr = ""

    def fake_resolve_executable(*, environ=None):
        raise MacrodataRunnerError(
            "macrodata executable not found",
            diagnostics={"error_code": "macrodata_executable_missing"},
        )

    def fake_run(command, *, env, cwd, capture_output, text, check, timeout=None):
        calls.append({"command": command, "cwd": cwd, "timeout": timeout})
        return Completed()

    monkeypatch.setattr("parallax.integrations.macrodata.runner.resolve_macrodata_executable", fake_resolve_executable)
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


def test_macrodata_runner_skips_stale_console_script_shebang(monkeypatch, tmp_path) -> None:
    from parallax.integrations.macrodata.runner import resolve_macrodata_command

    executable = tmp_path / "macrodata"
    executable.write_text(
        "#!/missing/parallax/python\nfrom macrodata.surfaces.cli import main\nmain()\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)

    monkeypatch.setattr("parallax.integrations.macrodata.runner._macrodata_cli_entrypoint_available", lambda: True)

    command = resolve_macrodata_command(environ={"PATH": str(tmp_path)})

    assert command == [sys.executable, "-c", "from macrodata.surfaces.cli import main; main()"]


def test_macrodata_runtime_state_reports_missing_required_catalog_series(monkeypatch) -> None:
    from parallax.integrations.macrodata import runner

    monkeypatch.setattr(runner, "_macrodata_cli_package_version", lambda: "0.1.5")
    monkeypatch.setattr(runner, "_macrodata_catalog_series", lambda: {"fred:SP500"})
    monkeypatch.setattr(runner, "_macrodata_bundle_series", lambda bundle_name: {"fred:SP500"})
    monkeypatch.setattr(runner, "_macrodata_cli_entrypoint_available", lambda: True)
    monkeypatch.setattr(runner, "resolve_macrodata_command", lambda *, environ=None: ["/app/.venv/bin/macrodata"])

    state = runner.macrodata_runtime_state(
        required_series=("fred:SP500", "nyfed:SRF", "yahoo:USDCNY=X"),
        environ={"PATH": "/app/.venv/bin"},
    )

    assert state == {
        "package_version": "0.1.5",
        "entrypoint_available": True,
        "command_mode": "console_script",
        "command_path": "/app/.venv/bin/macrodata",
        "command_error_code": None,
        "catalog_available": True,
        "required_series_count": 3,
        "missing_required_series_count": 2,
        "required_series_available": False,
        "missing_required_series_sample": ["nyfed:SRF", "yahoo:USDCNY=X"],
        "macro_core_bundle_available": True,
        "missing_required_bundle_series_count": 2,
        "required_bundle_series_available": False,
        "missing_required_bundle_series_sample": ["nyfed:SRF", "yahoo:USDCNY=X"],
    }


def test_macrodata_runtime_state_reports_python_entrypoint_fallback(monkeypatch) -> None:
    from parallax.integrations.macrodata import runner

    monkeypatch.setattr(runner, "_macrodata_cli_package_version", lambda: "0.1.6")
    monkeypatch.setattr(runner, "_macrodata_catalog_series", lambda: {"nyfed:SRF"})
    monkeypatch.setattr(runner, "_macrodata_bundle_series", lambda bundle_name: {"nyfed:SRF"})
    monkeypatch.setattr(runner, "_macrodata_cli_entrypoint_available", lambda: True)
    monkeypatch.setattr(
        runner,
        "resolve_macrodata_command",
        lambda *, environ=None: [sys.executable, "-c", "from macrodata.surfaces.cli import main; main()"],
    )

    state = runner.macrodata_runtime_state(required_series=("nyfed:SRF",))

    assert state["command_mode"] == "python_entrypoint"
    assert state["command_path"] == sys.executable
    assert state["required_series_available"] is True
    assert state["required_bundle_series_available"] is True


def test_macrodata_runner_passes_configured_timeout_to_child_process(monkeypatch) -> None:
    from parallax.integrations.macrodata.runner import MacrodataBundleRunner

    calls: list[dict[str, object]] = []

    class Settings:
        macrodata_fred_api_key_env = None
        macrodata_timeout_seconds = 12.5

    class Completed:
        returncode = 0
        stdout = json.dumps(ENVELOPE)
        stderr = ""

    def fake_run(command, *, env, cwd, capture_output, text, check, timeout=None):
        calls.append({"command": command, "timeout": timeout})
        return Completed()

    monkeypatch.setattr(
        "parallax.integrations.macrodata.runner.resolve_macrodata_executable",
        lambda *, environ=None: "/app/.venv/bin/macrodata",
    )
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
        macrodata_fred_api_key_env = None
        macrodata_timeout_seconds = 9.0

    def fake_run(command, *, env, cwd, capture_output, text, check, timeout=None):
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(
        "parallax.integrations.macrodata.runner.resolve_macrodata_executable",
        lambda *, environ=None: "/app/.venv/bin/macrodata",
    )
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
        macrodata_fred_api_key_env = None
        macrodata_cli_project_dir = str(tmp_path)

    class Completed:
        returncode = 0
        stdout = json.dumps(ENVELOPE)
        stderr = ""

    def fake_run(command, *, env, cwd, capture_output, text, check, timeout=None):
        calls.append({"command": command, "cwd": cwd, "capture_output": capture_output, "text": text, "check": check})
        return Completed()

    monkeypatch.setattr(
        "parallax.integrations.macrodata.runner.resolve_macrodata_executable",
        lambda *, environ=None: "/app/.venv/bin/macrodata",
    )
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
        macrodata_fred_api_key_env = "APP_FRED_KEY"

    class Completed:
        returncode = 0
        stdout = json.dumps(ENVELOPE)
        stderr = ""

    def fake_run(command, *, env, cwd, capture_output, text, check, timeout=None):
        calls.append({"env_has_fred": "FRED_API_KEY" in env, "env_fred_api_key": env.get("FRED_API_KEY")})
        return Completed()

    monkeypatch.setenv("FRED_API_KEY", stale_secret)
    monkeypatch.delenv("APP_FRED_KEY", raising=False)
    monkeypatch.setattr(
        "parallax.integrations.macrodata.runner.resolve_macrodata_executable",
        lambda *, environ=None: "/app/.venv/bin/macrodata",
    )
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
    repo = FakeMacroIntelRepository()
    _patch_macro_dependencies(monkeypatch, macro_module, repo)
    wake_notifications: list[dict[str, object]] = []

    class RecordingWakeBus:
        def __init__(self, conn_factory) -> None:
            self.conn_factory = conn_factory

        def notify_macro_observations_imported(self, *, count, max_observed_at, asof_date) -> None:
            wake_notifications.append(
                {
                    "count": count,
                    "max_observed_at": max_observed_at,
                    "asof_date": asof_date,
                }
            )

    monkeypatch.setattr(macro_module, "WakeBus", RecordingWakeBus, raising=False)
    stdout = io.StringIO()

    code = main(["macro", "import-bundle", "--file", str(bundle_path)], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["bundle_name"] == "macro-core"
    assert payload["data"]["observations_count"] == 1
    assert payload["data"]["run_id"] == repo.import_runs[0]["run_id"]
    assert repo.observations[0]["concept_key"] == "liquidity:sofr"
    assert repo.observations[0]["series_key"] == "nyfed:SOFR"
    assert repo.observations[0]["source_priority"] == 100
    assert repo.conn.commits == 0
    assert repo.transaction_events == ["commit"]
    assert repo.enqueued_dirty_targets == [
        {
            "changed_observations": [
                {
                    "observation_id": payload["data"]["imported_observation_ids"][0],
                    "status": "inserted",
                    "concept_key": "liquidity:sofr",
                    "observed_at": date(2026, 5, 19),
                    "fact_payload_hash": payload["data"]["changed_observations"][0]["fact_payload_hash"],
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
    assert wake_notifications == [
        {
            "count": 1,
            "max_observed_at": "2026-05-19",
            "asof_date": "2026-05-21",
        }
    ]


def test_macro_import_bundle_wake_failure_preserves_import_success(tmp_path, monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(ENVELOPE), encoding="utf-8")
    repo = FakeMacroIntelRepository()
    _patch_macro_dependencies(monkeypatch, macro_module, repo)

    class FailingWakeBus:
        def __init__(self, conn_factory) -> None:
            self.conn_factory = conn_factory

        def notify_macro_observations_imported(self, **kwargs: object) -> None:
            raise RuntimeError("wake failed")

    monkeypatch.setattr(macro_module, "WakeBus", FailingWakeBus, raising=False)
    stdout = io.StringIO()

    code = main(["macro", "import-bundle", "--file", str(bundle_path)], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["imported_observation_count"] == 1
    assert repo.transaction_events == ["commit"]


def test_macro_sync_delegates_to_sync_service_without_projection_payload(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository()
    _patch_macro_dependencies(monkeypatch, macro_module, repo)

    service = FakeMacroSyncService(
        result=MacroSyncRunSummary(
            sync_run_id="sync-run-1",
            import_run_id="import-run-1",
            status="ok",
            observations_count=1,
            imported_observation_count=1,
            asof_date=date(2026, 5, 21),
            max_observed_at=date(2026, 5, 21),
            diagnostics={"fred_api_key_env": "APP_FRED_KEY", "fred_api_key_configured": True},
        )
    )
    monkeypatch.setattr(macro_module, "MacroSyncService", lambda **kwargs: service)
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
    assert service.calls == [
        {
            "bundle_name": "macro-core",
            "window_start": date(2026, 1, 1),
            "window_end": date(2026, 5, 21),
            "trigger_reason": "operator_sync",
            "lease_owner": "macro_cli_sync",
        }
    ]
    assert repo.observations == []
    assert repo.snapshots == []


def test_macro_sync_failure_returns_nonzero_and_does_not_project(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository()
    _patch_macro_dependencies(monkeypatch, macro_module, repo)
    service = FakeMacroSyncService(
        result=MacroSyncRunSummary(
            sync_run_id="sync-run-fail",
            import_run_id=None,
            status="config_error",
            observations_count=0,
            imported_observation_count=0,
            asof_date=None,
            max_observed_at=None,
            diagnostics={"fred_api_key_env": "FINANCE_FRED_API_KEY", "fred_api_key_configured": False},
        )
    )
    monkeypatch.setattr(macro_module, "MacroSyncService", lambda **kwargs: service)
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
    assert repo.snapshots == []


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

    repo = FakeMacroIntelRepository()
    _patch_macro_dependencies(monkeypatch, macro_module, repo)
    stdout = io.StringIO()

    code = main(["macro", "sync", "--bundle", "macro-core", "--start", start, "--end", end], stdout=stdout)

    assert code == 2
    payload = json.loads(stdout.getvalue())
    assert payload["ok"] is False
    for key, value in expected.items():
        assert payload[key] == value


def test_macro_import_bundle_from_stdin_dispatches_to_importer(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository()
    _patch_macro_dependencies(monkeypatch, macro_module, repo)
    monkeypatch.setattr(macro_module.sys, "stdin", io.StringIO(json.dumps(ENVELOPE)))
    stdout = io.StringIO()

    code = main(["macro", "import-bundle", "--stdin"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["coverage"] == {"requested": 20, "available": 1}
    assert repo.observations[0]["raw_payload"]["series_key"] == "nyfed:SOFR"
    assert repo.transaction_events == ["commit"]


def test_macro_import_bundle_requires_exactly_one_input(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository()
    _patch_macro_dependencies(monkeypatch, macro_module, repo)
    stdout = io.StringIO()

    code = main(["macro", "import-bundle"], stdout=stdout)

    assert code == 2
    assert json.loads(stdout.getvalue()) == {"ok": False, "error": "macro_import_bundle_requires_file_or_stdin"}
    assert repo.observations == []


def test_macro_import_bundle_reports_repository_failure_without_secret(tmp_path, monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    bundle_path = tmp_path / "macro-core.json"
    bundle_path.write_text(json.dumps(ENVELOPE), encoding="utf-8")
    repo = FakeMacroIntelRepository(fail_record_run=True)
    _patch_macro_dependencies(monkeypatch, macro_module, repo)
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
    assert repo.observations == []


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
        "projection_version": "macro_regime_v4",
        "row_count": 318,
        "latest_attempt_status": "published",
        "latest_attempt_finished_at_ms": NOW_MS,
        "latest_attempt_error": None,
    }
    repo.latest = {
        "snapshot_id": "snapshot-1",
        "status": "partial",
        "computed_at_ms": NOW_MS,
        "asof_date": "2026-05-21",
        "source_coverage_json": {"latest_observed_at": "2026-05-22"},
    }
    _patch_macro_dependencies(monkeypatch, macro_module, repo, settings=FakeSettings(fred_env="APP_FRED_KEY"))
    monkeypatch.setenv("APP_FRED_KEY", "dummy-fred-secret")
    stdout = io.StringIO()

    code = main(["macro", "status"], stdout=stdout)

    output = stdout.getvalue()
    assert code == 0
    assert "dummy-fred-secret" not in output
    assert json.loads(output) == {
        "ok": True,
        "data": {
            "migration_ready": True,
            "fred_api_key_env": "APP_FRED_KEY",
            "fred_api_key_configured": True,
            "macrodata_cli": {
                "package_version": "0.1.test",
                "entrypoint_available": True,
                "command_mode": "console_script",
                "command_path": "/app/.venv/bin/macrodata",
                "command_error_code": None,
                "catalog_available": True,
                "required_series_count": len(MACRO_PROVIDER_SERIES_TO_CONCEPT),
                "missing_required_series_count": 0,
                "required_series_available": True,
                "missing_required_series_sample": [],
                "macro_core_bundle_available": True,
                "missing_required_bundle_series_count": 0,
                "required_bundle_series_available": True,
                "missing_required_bundle_series_sample": [],
            },
            "observations_count": 0,
            "concept_count": 0,
            "required_history_concept_count": len(MACRO_HISTORY_REQUIRED_CONCEPTS),
            "history_ready": True,
            "history_coverage": {
                "required_points": 126,
                "required_concept_count": len(MACRO_HISTORY_REQUIRED_CONCEPTS),
                "ready_concept_count": len(MACRO_HISTORY_REQUIRED_CONCEPTS),
                "coverage_ratio": 1.0,
                "lookback_days": 1095,
            },
            "concepts_below_min_history": [],
            "sync_queue": {"open_count": 2, "due_count": 1, "running_count": 0},
            "publication_state": {
                "projection_version": "macro_regime_v4",
                "row_count": 318,
                "latest_attempt_status": "published",
                "latest_attempt_finished_at_ms": NOW_MS,
                "latest_attempt_error": None,
            },
            "facts_max_observed_at": "2026-05-22",
            "projection_lag_days": 1,
            "projection_behind_facts": True,
            "latest_snapshot": {
                "snapshot_id": "snapshot-1",
                "projection_version": None,
                "asof_date": "2026-05-21",
                "status": "partial",
                "regime": None,
                "overall_score": None,
                "computed_at_ms": NOW_MS,
                "feature_count": 0,
                "indicator_count": 0,
                "data_gap_count": 0,
                "data_gap_codes": [],
                "coverage": {
                    "latest_coverage_ratio": None,
                    "history_coverage_ratio": None,
                    "observed_concept_count": None,
                    "required_concept_count": None,
                    "history_ready_concept_count": None,
                    "required_history_concept_count": None,
                    "concepts_below_min_history": [],
                },
                "panels": {},
            },
        },
    }
    assert repo.latest_snapshot_projection_versions == ["macro_regime_v4"]


def test_macro_status_reports_projection_behind_when_facts_exist_without_snapshot(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import macro as macro_module

    repo = FakeMacroIntelRepository()
    repo.latest = None
    _patch_macro_dependencies(monkeypatch, macro_module, repo)
    stdout = io.StringIO()

    code = main(["macro", "status"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["data"]["facts_max_observed_at"] is None
    assert payload["data"]["projection_lag_days"] is None
    assert payload["data"]["projection_behind_facts"] is False
    assert payload["data"]["latest_snapshot"] is None


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
                "command_mode": "console_script",
                "command_path": "/app/.venv/bin/macrodata",
                "command_error_code": None,
                "catalog_available": True,
                "required_series_count": len(MACRO_PROVIDER_SERIES_TO_CONCEPT),
                "missing_required_series_count": 0,
                "required_series_available": True,
                "missing_required_series_sample": [],
                "macro_core_bundle_available": True,
                "missing_required_bundle_series_count": 0,
                "required_bundle_series_available": True,
                "missing_required_bundle_series_sample": [],
            },
        },
    }


def test_macro_status_reports_one_point_history_as_not_ready(monkeypatch) -> None:
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
    assert payload["data"]["history_ready"] is False
    assert payload["data"]["history_coverage"] == {
        "required_points": 126,
        "required_concept_count": len(MACRO_HISTORY_REQUIRED_CONCEPTS),
        "ready_concept_count": len(MACRO_HISTORY_REQUIRED_CONCEPTS) - 1,
        "coverage_ratio": round((len(MACRO_HISTORY_REQUIRED_CONCEPTS) - 1) / len(MACRO_HISTORY_REQUIRED_CONCEPTS), 6),
        "lookback_days": 1095,
    }
    assert payload["data"]["concepts_below_min_history"] == [
        {
            "concept_key": "asset:spx",
            "label": "标普500",
            "short_label": "SPX",
            "points": 1,
            "required_points": 126,
            "latest_observed_at": "2026-05-21",
            "oldest_observed_at": "2026-05-21",
            "sources": ["fred"],
        }
    ]
    assert repo.concept_history_count_calls == [
        {
            "concept_keys": MACRO_HISTORY_REQUIRED_CONCEPTS,
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
    @contextmanager
    def fake_repositories(_settings: object):
        yield FakeRepositorySession(repo)

    monkeypatch.setattr(macro_module, "load_settings", lambda require_ws_token=False: settings or FakeSettings())
    monkeypatch.setattr(macro_module, "repositories", fake_repositories)
    monkeypatch.setattr(
        macro_module,
        "macrodata_runtime_state",
        lambda *, required_series: {
            "package_version": "0.1.test",
            "entrypoint_available": True,
            "command_mode": "console_script",
            "command_path": "/app/.venv/bin/macrodata",
            "command_error_code": None,
            "catalog_available": True,
            "required_series_count": len(required_series),
            "missing_required_series_count": 0,
            "required_series_available": True,
            "missing_required_series_sample": [],
            "macro_core_bundle_available": True,
            "missing_required_bundle_series_count": 0,
            "required_bundle_series_available": True,
            "missing_required_bundle_series_sample": [],
        },
    )
    monkeypatch.setattr(macro_module, "_now_ms", lambda: NOW_MS)


class FakeMacroSyncService:
    def __init__(self, *, result: MacroSyncRunSummary) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def run_explicit_window_once(
        self,
        *,
        bundle_name: str,
        window_start: date,
        window_end: date,
        trigger_reason: str = "operator_sync",
        lease_owner: str = "macro_cli_sync",
        now_ms: int | None = None,
    ) -> MacroSyncRunSummary:
        self.calls.append(
            {
                "bundle_name": bundle_name,
                "window_start": window_start,
                "window_end": window_end,
                "trigger_reason": trigger_reason,
                "lease_owner": lease_owner,
            }
        )
        assert now_ms == NOW_MS
        return self.result


class FakeSettings:
    def __init__(self, *, fred_env: str | None = None) -> None:
        self.macrodata_fred_api_key_env = fred_env


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
    ) -> None:
        self.conn = FakeConnection()
        self.source_observations = observations or []
        self.source_concept_history = concept_history
        self.observations: list[dict[str, object]] = []
        self.import_runs: list[dict[str, object]] = []
        self.snapshots: list[dict[str, object]] = []
        self.latest_observation_limits: list[int] = []
        self.observations_for_concepts_calls: list[dict[str, object]] = []
        self.concept_history_count_calls: list[dict[str, object]] = []
        self.sync_queue: dict[str, object] = {}
        self.enqueued_dirty_targets: list[dict[str, object]] = []
        self.publication_state: dict[str, object] | None = None
        self.latest: dict[str, object] | None = None
        self.latest_snapshot_projection_versions: list[str | None] = []
        self.fail_record_run = fail_record_run
        self.fail_latest_observations = fail_latest_observations
        self.fail_observations_for_series = fail_observations_for_series
        self.fail_concept_history_counts = fail_concept_history_counts
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

    def record_import_run(self, import_run: dict[str, object]) -> None:
        if self.fail_record_run:
            raise RuntimeError("postgres://user:secret@db record failed")
        self.import_runs.append(import_run)

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
                            "points": 126,
                            "latest_observed_at": "2026-05-21",
                            "oldest_observed_at": "2026-01-01",
                            "sources": ["fixture"],
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
        assert projection_version == "macro_regime_v4"
        return self.publication_state

    def latest_snapshot(self, *, projection_version: str | None = None) -> dict[str, object] | None:
        self.latest_snapshot_projection_versions.append(projection_version)
        return self.latest


class FakeRepositorySession:
    def __init__(self, macro_intel: FakeMacroIntelRepository) -> None:
        self.macro_intel = macro_intel
        self.conn = macro_intel.conn
        self.in_transaction = False

    def unit_of_work(self):
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
        self.import_runs: list[dict[str, object]] = []
        self.enqueued_dirty_targets: list[dict[str, object]] = []

    def __enter__(self):
        self.repos.in_transaction = True
        self.observations = list(self.macro_intel.observations)
        self.observation_index = dict(self.macro_intel._observation_index)
        self.import_runs = list(self.macro_intel.import_runs)
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
            self.macro_intel.import_runs = self.import_runs
            self.macro_intel.enqueued_dirty_targets = self.enqueued_dirty_targets
            self.macro_intel.transaction_events.append("rollback")
        else:
            self.macro_intel.transaction_events.append("commit")
        self.repos.in_transaction = False
        return False
