from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
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
        command = [
            "uv",
            "run",
            "macrodata",
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
        key_value = self.environ.get(fred_state["fred_api_key_env"], "").strip()
        if key_value:
            child_env["FRED_API_KEY"] = key_value

        cli_project_dir = _configured_cli_project_dir(self.settings)
        completed = subprocess.run(  # noqa: S603
            command,
            env=child_env,
            cwd=cli_project_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        diagnostics = {
            **fred_state,
            "command": command,
            "cli_project_dir": str(cli_project_dir) if cli_project_dir else None,
            "returncode": completed.returncode,
        }
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


def fred_api_key_state(settings: object, *, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    env_name = _configured_fred_env_name(settings)
    return {
        "fred_api_key_env": env_name,
        "fred_api_key_configured": bool(env.get(env_name, "").strip()),
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


def _configured_cli_project_dir(settings: object) -> str | None:
    value = getattr(settings, "macrodata_cli_project_dir", None)
    if not isinstance(value, str) or not value.strip():
        providers = getattr(settings, "providers", None)
        macrodata = getattr(providers, "macrodata", None)
        value = getattr(macrodata, "cli_project_dir", None)
    if not isinstance(value, str) or not value.strip():
        return None
    return str(Path(value.strip()).expanduser())


__all__ = [
    "DEFAULT_FRED_API_KEY_ENV",
    "MacrodataBundleRunResult",
    "MacrodataBundleRunner",
    "MacrodataRunnerError",
    "fred_api_key_state",
]
