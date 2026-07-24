from __future__ import annotations

import json
import sys
import time
from argparse import Namespace
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from parallax.app.operations.macro import (
    MacroStatusOperationError,
    MacroSyncOperationError,
    import_macro_bundle,
    macro_status,
    retry_failed_macro_research,
    sync_macro_window,
)
from parallax.domains.macro_intel.observation_identity import normalize_macro_date
from parallax.domains.macro_intel.services.macro_sync_types import MacroSyncRunSummary
from parallax.platform.config.settings import load_settings


def handle_macro(args: Namespace) -> tuple[int, dict[str, Any]]:
    if args.macro_command == "import-bundle":
        return _handle_import_bundle(args)
    if args.macro_command == "sync":
        return _handle_sync(args)
    if args.macro_command == "retry-research":
        return _handle_retry_research(args)
    if args.macro_command == "status":
        return _handle_status()
    return 2, {"ok": False, "error": f"unknown macro command: {args.macro_command}"}


def _handle_import_bundle(args: Namespace) -> tuple[int, dict[str, Any]]:
    file_path = args.file
    use_stdin = bool(args.stdin)
    if bool(file_path) == use_stdin:
        return 2, {"ok": False, "error": "macro_import_bundle_requires_file_or_stdin"}

    try:
        raw_json = sys.stdin.read() if use_stdin else Path(str(file_path)).read_text(encoding="utf-8")
        envelope = json.loads(raw_json)
        if not isinstance(envelope, Mapping):
            raise ValueError("macrodata envelope must be a JSON object")
        settings = load_settings(require_ws_token=False)
        summary = import_macro_bundle(settings, envelope, now_ms=_now_ms())
    except Exception as exc:
        return 1, _error_payload("macro_import_bundle_failed", exc)
    return 0, {"ok": True, "data": _json_ready(summary)}


def _handle_sync(args: Namespace) -> tuple[int, dict[str, Any]]:
    try:
        settings = load_settings(require_ws_token=False)
        window_start = _parse_cli_date(str(args.start), field="start")
        window_end = _parse_cli_date(str(args.end), field="end")
        if window_start > window_end:
            return 2, {"ok": False, "error": "macro_sync_invalid_date_range"}
        execution = sync_macro_window(
            settings,
            bundle_name=str(args.bundle),
            window_start=window_start,
            window_end=window_end,
            now_ms=_now_ms(),
        )
        summary = execution.summary
        sync_payload = _sync_summary(summary, window_start=window_start, window_end=window_end)
        sync_ok = summary.status in {"ok", "partial"}
    except _MacroSyncCliValidationError as exc:
        return 2, {"ok": False, "error": "macro_sync_invalid_date", "field": exc.field}
    except MacroSyncOperationError as exc:
        payload = _error_payload("macro_sync_failed", exc.cause)
        payload.update(_fred_payload_from_diagnostics(exc.diagnostics))
        return 1, payload
    except Exception as exc:
        return 1, _error_payload("macro_sync_failed", exc)

    data = {
        **_fred_payload_from_diagnostics(execution.diagnostics),
        "sync": sync_payload,
    }
    if not sync_ok:
        return 1, {"ok": False, "error": "macro_sync_failed", "data": data}

    return (
        0,
        {
            "ok": True,
            "data": data,
        },
    )


def _handle_status() -> tuple[int, dict[str, Any]]:
    settings = load_settings(require_ws_token=False)
    try:
        data = macro_status(settings, now_ms=_now_ms())
    except MacroStatusOperationError as exc:
        payload = _error_payload("macro_status_unavailable", exc.cause)
        payload["error_type"] = type(exc.cause).__name__
        payload["data"] = {
            **_fred_payload_from_diagnostics(exc.diagnostics),
            "macrodata_cli": exc.diagnostics.get("macrodata_cli", {}),
        }
        return 1, payload
    return 0, {"ok": True, "data": data}


def _handle_retry_research(args: Namespace) -> tuple[int, dict[str, Any]]:
    try:
        session_date = _parse_cli_date(str(args.session_date), field="session_date")
        settings = load_settings(require_ws_token=False)
        data = retry_failed_macro_research(
            settings,
            session_date=session_date,
            now_ms=_now_ms(),
        )
    except _MacroSyncCliValidationError as exc:
        return 2, {"ok": False, "error": "macro_retry_research_invalid_date", "field": exc.field}
    except Exception as exc:
        return 1, _error_payload("macro_retry_research_failed", exc)
    return 0, {"ok": True, "data": _json_ready(data)}


def _fred_payload_from_diagnostics(diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fred_api_key_env": diagnostics.get("fred_api_key_env"),
        "fred_api_key_configured": bool(diagnostics.get("fred_api_key_configured")),
    }


class _MacroSyncCliValidationError(ValueError):
    def __init__(self, *, field: str) -> None:
        super().__init__(field)
        self.field = field


def _parse_cli_date(raw: str, *, field: str) -> date:
    try:
        return normalize_macro_date(raw)
    except ValueError as exc:
        raise _MacroSyncCliValidationError(field=field) from exc


def _sync_summary(summary: MacroSyncRunSummary, *, window_start: date, window_end: date) -> dict[str, Any]:
    return {
        "sync_run_id": summary.sync_run_id,
        "status": summary.status,
        "window_start": str(window_start),
        "window_end": str(window_end),
        "imported_observation_count": summary.imported_observation_count,
        "max_observed_at": str(summary.max_observed_at) if summary.max_observed_at else None,
        "asof_date": str(summary.asof_date) if summary.asof_date else None,
    }


def _error_payload(error: str, exc: Exception) -> dict[str, Any]:
    return {"ok": False, "error": error, "detail": type(exc).__name__}


def _json_ready(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_ready(item) for item in value]
    if isinstance(value, date):
        return value.isoformat()
    return value


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["handle_macro"]
