from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import threading
from collections.abc import Mapping, Sequence
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from typing import Any

from tracefold.macro import MacrodataBundleRunResult

_MACRODATA_PYTHON_ENTRYPOINT = "from macrodata.surfaces.cli import main; main()"


class MacrodataBundleRunner:
    def __init__(self, *, settings: object, environ: Mapping[str, str] | None = None) -> None:
        self.settings = settings
        self.environ = os.environ if environ is None else environ
        self._process_lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None

    def history_bundle(self, *, bundle: str, start: str, end: str) -> MacrodataBundleRunResult:
        fred_state = fred_api_key_state(self.settings, environ=self.environ)
        command_prefix = resolve_macrodata_command()
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
        env_name = fred_state["fred_api_key_env"]
        if not key_value and isinstance(env_name, str) and env_name:
            key_value = self.environ.get(env_name, "").strip()
        if key_value:
            child_env["FRED_API_KEY"] = key_value

        diagnostics = {
            **fred_state,
            "command": command,
            "timeout_seconds": timeout_seconds,
        }
        try:
            process = subprocess.Popen(  # noqa: S603
                command,
                env=child_env,
                cwd=None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            with self._process_lock:
                self._process = process
            stdout, _stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            self.cancel()
            raise MacrodataRunnerError(
                "macrodata bundle history timed out",
                diagnostics={
                    **diagnostics,
                    "returncode": None,
                    "error_code": "macrodata_runner_timeout",
                },
            ) from exc
        finally:
            with self._process_lock:
                if self._process is locals().get("process"):
                    self._process = None
        diagnostics["returncode"] = process.returncode
        if process.returncode != 0:
            raise MacrodataRunnerError("macrodata bundle history failed", diagnostics=diagnostics)

        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise MacrodataRunnerError(
                "macrodata bundle history returned invalid JSON",
                diagnostics=diagnostics,
            ) from exc
        if not isinstance(envelope, Mapping):
            raise MacrodataRunnerError("macrodata bundle history returned non-object JSON", diagnostics=diagnostics)
        return MacrodataBundleRunResult(envelope=envelope, diagnostics=diagnostics)

    def cancel(self) -> None:
        with self._process_lock:
            process = self._process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


class MacrodataRunnerError(RuntimeError):
    def __init__(self, message: str, *, diagnostics: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.diagnostics = dict(diagnostics)


def resolve_macrodata_command() -> list[str]:
    if _macrodata_cli_entrypoint_available():
        return [sys.executable, "-c", _MACRODATA_PYTHON_ENTRYPOINT]
    raise MacrodataRunnerError(
        "macrodata package entrypoint not found",
        diagnostics={"error_code": "macrodata_entrypoint_missing"},
    )


def macrodata_runtime_state(
    *,
    required_series: Sequence[str] = (),
    required_bundles: Sequence[str] = (),
    required_bundle_series: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    command_path: str | None = None
    command_mode = "missing"
    command_error_code: str | None = None
    try:
        command = resolve_macrodata_command()
        command_path = command[0] if command else None
        command_mode = "python_entrypoint"
    except MacrodataRunnerError as exc:
        command_error_code = str(exc.diagnostics.get("error_code") or "macrodata_runner_error")

    catalog_series = _macrodata_catalog_series()
    macro_core_series = _macrodata_bundle_series("macro-core")
    required = tuple(dict.fromkeys(str(item) for item in required_series))
    required_bundle_names = tuple(dict.fromkeys(str(item).strip() for item in required_bundles if str(item).strip()))
    missing_required_bundles = [
        bundle_name for bundle_name in required_bundle_names if _macrodata_bundle_series(bundle_name) is None
    ]
    missing = [series_key for series_key in required if catalog_series is None or series_key not in catalog_series]
    if required_bundle_series:
        required_bundle_name_set = set(required_bundle_names)
        missing_bundle_by_name: dict[str, list[str]] = {}
        missing_bundle: list[str] = []
        for bundle_name, expected_series in required_bundle_series.items():
            normalized_bundle_name = str(bundle_name).strip()
            if not normalized_bundle_name or (
                required_bundle_name_set and normalized_bundle_name not in required_bundle_name_set
            ):
                continue
            bundle_series = _macrodata_bundle_series(normalized_bundle_name)
            missing_for_bundle = [
                str(series_key)
                for series_key in dict.fromkeys(str(item) for item in expected_series)
                if bundle_series is None or str(series_key) not in bundle_series
            ]
            if missing_for_bundle:
                missing_bundle_by_name[normalized_bundle_name] = missing_for_bundle
                missing_bundle.extend(f"{normalized_bundle_name}:{series_key}" for series_key in missing_for_bundle)
    else:
        missing_bundle_by_name = {}
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
        "required_bundle_count": len(required_bundle_names),
        "missing_required_bundle_count": len(missing_required_bundles),
        "required_bundles_available": not missing_required_bundles,
        "missing_required_bundles": list(missing_required_bundles),
        "macro_core_bundle_available": macro_core_series is not None,
        "missing_required_bundle_series_count": len(missing_bundle),
        "required_bundle_series_available": False if macro_core_series is None else not missing_bundle,
        "missing_required_bundle_series_sample": _edge_sample(missing_bundle, edge_count=12),
        "missing_required_bundle_series_by_bundle": missing_bundle_by_name,
    }


def _macrodata_cli_entrypoint_available() -> bool:
    try:
        return find_spec("macrodata.surfaces.cli") is not None
    except (ImportError, AttributeError, ValueError):
        return False


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
    return None


def _edge_sample(values: Sequence[str], *, edge_count: int) -> list[str]:
    if len(values) <= edge_count * 2:
        return list(values)
    return [*values[:edge_count], "...", *values[-edge_count:]]


def fred_api_key_state(settings: object, *, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    env_name = _configured_fred_env_name(settings)
    configured_key = _configured_fred_api_key(settings=settings)
    return {
        "fred_api_key_env": env_name,
        "fred_api_key_configured": bool(configured_key or (env.get(env_name, "").strip() if env_name else "")),
    }


def _configured_fred_env_name(settings: object) -> str | None:
    try:
        env_name = settings.providers.macrodata.fred_api_key_env
    except AttributeError as exc:
        raise RuntimeError("macrodata_provider_settings_required") from exc
    if env_name is None:
        return None
    if isinstance(env_name, str) and env_name.strip():
        return env_name.strip()
    return None


def _configured_fred_api_key(*, settings: object) -> str | None:
    try:
        value = settings.macrodata_fred_api_key
    except AttributeError as exc:
        raise RuntimeError("macrodata_fred_api_key_settings_required") from exc
    return _secret_string(value)


def _secret_string(value: object) -> str | None:
    if value is None:
        return None
    getter = getattr(value, "get_secret_value", None)
    if callable(getter):
        value = getter()
    normalized = str(value).strip()
    return normalized or None


def _macrodata_timeout_seconds(settings: object) -> float:
    try:
        value = settings.workers.macro_sync.macrodata_timeout_seconds
    except AttributeError as exc:
        raise RuntimeError("macrodata_timeout_settings_required") from exc
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("macrodata_timeout_seconds_required")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 1.0:
        raise ValueError("macrodata_timeout_seconds_required")
    return parsed


__all__ = [
    "MacrodataBundleRunResult",
    "MacrodataBundleRunner",
    "MacrodataRunnerError",
    "fred_api_key_state",
    "macrodata_runtime_state",
    "resolve_macrodata_command",
]
