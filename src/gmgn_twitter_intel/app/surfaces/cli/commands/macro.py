from __future__ import annotations

import json
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

from gmgn_twitter_intel.app.surfaces.cli.dependencies import repositories
from gmgn_twitter_intel.domains.macro_intel._constants import (
    MACRO_CORE_SERIES,
    MACRO_VIEW_HISTORY_LIMIT_PER_SERIES,
    MACRO_VIEW_HISTORY_LOOKBACK_DAYS,
)
from gmgn_twitter_intel.domains.macro_intel.services.macro_regime_engine import build_macro_view_snapshot
from gmgn_twitter_intel.domains.macro_intel.services.macrodata_bundle_importer import import_macrodata_bundle
from gmgn_twitter_intel.platform.config.settings import load_settings


def handle_macro(args: object) -> tuple[int, dict[str, Any]]:
    if args.macro_command == "import-bundle":
        return _handle_import_bundle(args)
    if args.macro_command == "project-once":
        return _handle_project_once()
    if args.macro_command == "status":
        return _handle_status()
    return 2, {"ok": False, "error": f"unknown macro command: {args.macro_command}"}


def _handle_import_bundle(args: object) -> tuple[int, dict[str, Any]]:
    file_path = getattr(args, "file", None)
    use_stdin = bool(getattr(args, "stdin", False))
    if bool(file_path) == use_stdin:
        return 2, {"ok": False, "error": "macro_import_bundle_requires_file_or_stdin"}

    try:
        raw_json = sys.stdin.read() if use_stdin else Path(str(file_path)).read_text(encoding="utf-8")
        envelope = json.loads(raw_json)
        if not isinstance(envelope, Mapping):
            raise ValueError("macrodata envelope must be a JSON object")
        settings = load_settings(require_ws_token=False)
        with repositories(settings) as repos:
            summary = import_macrodata_bundle(envelope, repos=repos, now_ms=_now_ms())
    except Exception as exc:
        return 1, _error_payload("macro_import_bundle_failed", exc)
    return 0, {"ok": True, "data": summary}


def _handle_project_once() -> tuple[int, dict[str, Any]]:
    try:
        now_ms = _now_ms()
        settings = load_settings(require_ws_token=False)
        with repositories(settings) as repos:
            observations = repos.macro_intel.observations_for_series(
                series_keys=MACRO_CORE_SERIES,
                lookback_days=MACRO_VIEW_HISTORY_LOOKBACK_DAYS,
                limit_per_series=MACRO_VIEW_HISTORY_LIMIT_PER_SERIES,
            )
            snapshot = build_macro_view_snapshot(observations, computed_at_ms=now_ms)
            repos.macro_intel.insert_snapshot(snapshot)
    except Exception as exc:
        return 1, _error_payload("macro_project_once_failed", exc)
    return (
        0,
        {
            "ok": True,
            "data": {
                "projection_version": snapshot["projection_version"],
                "status": snapshot["status"],
                "regime": snapshot["regime"],
                "snapshot_id": snapshot["snapshot_id"],
            },
        },
    )


def _handle_status() -> tuple[int, dict[str, Any]]:
    settings = load_settings(require_ws_token=False)
    try:
        with repositories(settings) as repos:
            data = {
                "migration_ready": True,
                "observations_count": repos.macro_intel.observations_count(),
                "series_count": repos.macro_intel.series_count(),
                "latest_import_run": _json_ready(repos.macro_intel.latest_import_run()),
                "latest_snapshot": _json_ready(repos.macro_intel.latest_snapshot()),
            }
    except Exception:
        data = {
            "migration_ready": False,
            "observations_count": 0,
            "series_count": 0,
            "latest_import_run": None,
            "latest_snapshot": None,
        }
    return 0, {"ok": True, "data": data}


def _error_payload(error: str, exc: Exception) -> dict[str, Any]:
    return {"ok": False, "error": error, "detail": type(exc).__name__}


def _json_ready(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_ready(item) for item in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["handle_macro"]
