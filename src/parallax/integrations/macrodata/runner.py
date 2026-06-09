from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from pathlib import Path
from typing import Any

DEFAULT_FRED_API_KEY_ENV = "FINANCE_FRED_API_KEY"


@dataclass(frozen=True)
class MacrodataBundleRunResult:
    envelope: Mapping[str, Any]
    diagnostics: dict[str, Any]


class MacrodataBundleRunner:
    def __init__(self, *, settings: object, environ: Mapping[str, str] | None = None) -> None:
        self.settings = settings
        self.environ = os.environ if environ is None else environ

    def history_bundle(self, *, bundle: str, start: str, end: str) -> MacrodataBundleRunResult:
        fred_state = fred_api_key_state(self.settings, environ=self.environ)
        command_prefix = resolve_macrodata_command(environ=self.environ)
        timeout_seconds = _macrodata_timeout_seconds(self.settings)
        command = [
            *command_prefix,
            "bundle",
            "history",
            bundle,
            "--start",
            start,
            "--end",
            end,
        ]
        child_env = dict(self.environ)
        child_env.pop("FRED_API_KEY", None)
        key_value = _configured_fred_api_key(settings=self.settings)
        if not key_value:
            key_value = self.environ.get(fred_state["fred_api_key_env"], "").strip()
        if key_value:
            child_env["FRED_API_KEY"] = key_value

        diagnostics = {
            **fred_state,
            "command": command,
            "timeout_seconds": timeout_seconds,
        }
        try:
            completed = subprocess.run(  # noqa: S603
                command,
                env=child_env,
                cwd=None,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise MacrodataRunnerError(
                "macrodata bundle history timed out",
                diagnostics={
                    **diagnostics,
                    "returncode": None,
                    "error_code": "macrodata_runner_timeout",
                },
            ) from exc
        diagnostics["returncode"] = completed.returncode
        if completed.returncode != 0:
            raise MacrodataRunnerError("macrodata bundle history failed", diagnostics=diagnostics)

        try:
            envelope = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise MacrodataRunnerError(
                "macrodata bundle history returned invalid JSON",
                diagnostics=diagnostics,
            ) from exc
        if not isinstance(envelope, Mapping):
            raise MacrodataRunnerError("macrodata bundle history returned non-object JSON", diagnostics=diagnostics)
        return MacrodataBundleRunResult(envelope=envelope, diagnostics=diagnostics)


class MacrodataRunnerError(RuntimeError):
    def __init__(self, message: str, *, diagnostics: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.diagnostics = dict(diagnostics)


def resolve_macrodata_executable(*, environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    executable = shutil.which("macrodata", path=env.get("PATH"))
    if executable and _executable_path_is_usable(executable):
        return executable
    sibling = Path(sys.executable).parent / "macrodata"
    if sibling.exists() and _executable_path_is_usable(str(sibling)):
        return str(sibling)
    raise MacrodataRunnerError(
        "macrodata executable not found",
        diagnostics={"error_code": "macrodata_executable_missing"},
    )


def resolve_macrodata_command(*, environ: Mapping[str, str] | None = None) -> list[str]:
    try:
        return [resolve_macrodata_executable(environ=environ)]
    except MacrodataRunnerError as exc:
        diagnostics = getattr(exc, "diagnostics", {})
        if diagnostics.get("error_code") != "macrodata_executable_missing":
            raise
        if _macrodata_cli_entrypoint_available():
            return [sys.executable, "-c", "from macrodata.surfaces.cli import main; main()"]
        raise


def macrodata_runtime_state(
    *,
    required_series: Sequence[str] = (),
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    command_path: str | None = None
    command_mode = "missing"
    command_error_code: str | None = None
    try:
        command = resolve_macrodata_command(environ=environ)
        command_path = command[0] if command else None
        command_mode = "python_entrypoint" if _is_python_entrypoint_command(command) else "console_script"
    except MacrodataRunnerError as exc:
        diagnostics = getattr(exc, "diagnostics", {})
        command_error_code = str(diagnostics.get("error_code") or "macrodata_runner_error")

    catalog_series = _macrodata_catalog_series()
    macro_core_series = _macrodata_bundle_series("macro-core")
    required = tuple(dict.fromkeys(str(item) for item in required_series))
    missing = [series_key for series_key in required if catalog_series is None or series_key not in catalog_series]
    missing_bundle = [
        series_key for series_key in required if macro_core_series is None or series_key not in macro_core_series
    ]
    return {
        "package_version": _macrodata_cli_package_version(),
        "entrypoint_available": _macrodata_cli_entrypoint_available(),
        "command_mode": command_mode,
        "command_path": command_path,
        "command_error_code": command_error_code,
        "catalog_available": catalog_series is not None,
        "required_series_count": len(required),
        "missing_required_series_count": len(missing),
        "required_series_available": False if catalog_series is None else not missing,
        "missing_required_series_sample": _edge_sample(missing, edge_count=12),
        "macro_core_bundle_available": macro_core_series is not None,
        "missing_required_bundle_series_count": len(missing_bundle),
        "required_bundle_series_available": False if macro_core_series is None else not missing_bundle,
        "missing_required_bundle_series_sample": _edge_sample(missing_bundle, edge_count=12),
    }


def _macrodata_cli_entrypoint_available() -> bool:
    return find_spec("macrodata.surfaces.cli") is not None


def _macrodata_cli_package_version() -> str | None:
    try:
        return version("macrodata-cli")
    except PackageNotFoundError:
        return None


def _macrodata_catalog_series() -> set[str] | None:
    try:
        module = import_module("macrodata.catalog.entries")
    except Exception:
        return None
    entries = getattr(module, "CATALOG_ENTRIES", None)
    if not isinstance(entries, Sequence):
        return None
    series: set[str] = set()
    for entry in entries:
        series_key = getattr(entry, "series_key", None)
        if isinstance(series_key, str) and series_key:
            series.add(series_key)
    return series


def _macrodata_bundle_series(bundle_name: str) -> set[str] | None:
    try:
        module = import_module("macrodata.app.services")
    except Exception:
        return None
    bundles = getattr(module, "BUNDLES", None)
    if isinstance(bundles, Mapping):
        bundle_series = bundles.get(bundle_name)
        if isinstance(bundle_series, Sequence) and not isinstance(bundle_series, str | bytes | bytearray):
            return {str(series_key) for series_key in bundle_series}
    if bundle_name == "macro-core":
        macro_core = getattr(module, "MACRO_CORE", None)
        if isinstance(macro_core, Sequence) and not isinstance(macro_core, str | bytes | bytearray):
            return {str(series_key) for series_key in macro_core}
    return None


def _is_python_entrypoint_command(command: Sequence[str]) -> bool:
    return len(command) >= 3 and command[1] == "-c" and "macrodata.surfaces.cli" in command[2]


def _edge_sample(values: Sequence[str], *, edge_count: int) -> list[str]:
    if len(values) <= edge_count * 2:
        return list(values)
    return [*values[:edge_count], "...", *values[-edge_count:]]


def _executable_path_is_usable(path: str) -> bool:
    if not os.access(path, os.X_OK):
        return False
    try:
        with Path(path).open("rb") as handle:
            first_line = handle.readline(256).rstrip()
    except (IndexError, OSError):
        return True
    if not first_line.startswith(b"#!"):
        return True
    interpreter = first_line[2:].strip().split(maxsplit=1)[0].decode(errors="ignore")
    return not interpreter.startswith("/") or Path(interpreter).exists()


def fred_api_key_state(settings: object, *, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    env_name = _configured_fred_env_name(settings)
    configured_key = _configured_fred_api_key(settings=settings)
    return {
        "fred_api_key_env": env_name,
        "fred_api_key_configured": bool(configured_key or env.get(env_name, "").strip()),
    }


def _configured_fred_env_name(settings: object) -> str:
    env_name = getattr(settings, "macrodata_fred_api_key_env", None)
    if isinstance(env_name, str) and env_name.strip():
        return env_name.strip()
    providers = getattr(settings, "providers", None)
    macrodata = getattr(providers, "macrodata", None)
    nested_env_name = getattr(macrodata, "fred_api_key_env", None)
    if isinstance(nested_env_name, str) and nested_env_name.strip():
        return nested_env_name.strip()
    return DEFAULT_FRED_API_KEY_ENV


def _configured_fred_api_key(*, settings: object) -> str | None:
    value = getattr(settings, "macrodata_fred_api_key", None)
    normalized = _secret_string(value)
    if normalized:
        return normalized
    providers = getattr(settings, "providers", None)
    macrodata = getattr(providers, "macrodata", None)
    nested_value = getattr(macrodata, "fred_api_key", None)
    return _secret_string(nested_value)


def _secret_string(value: object) -> str | None:
    if value is None:
        return None
    getter = getattr(value, "get_secret_value", None)
    if callable(getter):
        value = getter()
    normalized = str(value).strip()
    return normalized or None


def _macrodata_timeout_seconds(settings: object) -> float:
    value = getattr(settings, "macrodata_timeout_seconds", None)
    if value is None:
        workers = getattr(settings, "workers", None)
        macro_sync = getattr(workers, "macro_sync", None)
        value = getattr(macro_sync, "macrodata_timeout_seconds", None)
    return max(1.0, float(value if value is not None else 240.0))


__all__ = [
    "DEFAULT_FRED_API_KEY_ENV",
    "MacrodataBundleRunResult",
    "MacrodataBundleRunner",
    "MacrodataRunnerError",
    "fred_api_key_state",
    "macrodata_runtime_state",
    "resolve_macrodata_command",
    "resolve_macrodata_executable",
]
