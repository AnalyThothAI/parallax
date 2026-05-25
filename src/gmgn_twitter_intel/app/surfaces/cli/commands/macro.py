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
    MACRO_CONCEPT_METADATA,
    MACRO_CORE_CONCEPTS,
    MACRO_HISTORY_REQUIRED_CONCEPTS,
    MACRO_HISTORY_REQUIRED_POINTS_BY_CONCEPT,
    MACRO_REQUIRED_STAT_POINTS,
    MACRO_VIEW_HISTORY_LIMIT_PER_SERIES,
    MACRO_VIEW_HISTORY_LOOKBACK_DAYS,
    MACRO_VIEW_PROJECTION_VERSION,
)
from gmgn_twitter_intel.domains.macro_intel.services.macro_regime_engine import build_macro_view_snapshot
from gmgn_twitter_intel.domains.macro_intel.services.macrodata_bundle_importer import import_macrodata_bundle
from gmgn_twitter_intel.integrations.macrodata import (
    MacrodataBundleRunner,
    MacrodataBundleRunResult,
    fred_api_key_state,
)
from gmgn_twitter_intel.platform.config.settings import load_settings


def handle_macro(args: object) -> tuple[int, dict[str, Any]]:
    if args.macro_command == "import-bundle":
        return _handle_import_bundle(args)
    if args.macro_command == "sync":
        return _handle_sync(args)
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


def _handle_sync(args: object) -> tuple[int, dict[str, Any]]:
    fred_state: Mapping[str, Any] = {}
    try:
        settings = load_settings(require_ws_token=False)
        fred_state = fred_api_key_state(settings)
        run_result = MacrodataBundleRunner(settings=settings).history_bundle(
            bundle=str(args.bundle),
            start=str(args.start),
            end=str(args.end),
        )
        if not isinstance(run_result.envelope, Mapping):
            raise ValueError("macrodata envelope must be a JSON object")
        with repositories(settings) as repos:
            summary = import_macrodata_bundle(run_result.envelope, repos=repos, now_ms=_now_ms())
            projection = _project_once(repos=repos, now_ms=_now_ms()) if bool(getattr(args, "project", False)) else None
    except Exception as exc:
        payload = _error_payload("macro_sync_failed", exc)
        payload.update(_fred_payload_from_diagnostics(fred_state))
        diagnostics = getattr(exc, "diagnostics", None)
        if isinstance(diagnostics, Mapping):
            payload.update(_fred_payload_from_diagnostics(diagnostics))
        return 1, payload

    return (
        0,
        {
            "ok": True,
            "data": {
                **_fred_payload_from_diagnostics(run_result.diagnostics),
                "import": _sync_import_summary(summary),
                "projection": projection,
                "runner": _runner_diagnostics_payload(run_result.diagnostics),
            },
        },
    )


def _handle_project_once() -> tuple[int, dict[str, Any]]:
    try:
        now_ms = _now_ms()
        settings = load_settings(require_ws_token=False)
        with repositories(settings) as repos:
            data = _project_once(repos=repos, now_ms=now_ms)
    except Exception as exc:
        return 1, _error_payload("macro_project_once_failed", exc)
    return (
        0,
        {
            "ok": True,
            "data": data,
        },
    )


def _handle_status() -> tuple[int, dict[str, Any]]:
    settings = load_settings(require_ws_token=False)
    fred_state = fred_api_key_state(settings)
    try:
        with repositories(settings) as repos:
            history = repos.macro_intel.concept_history_counts(
                concept_keys=MACRO_HISTORY_REQUIRED_CONCEPTS,
                lookback_days=MACRO_VIEW_HISTORY_LOOKBACK_DAYS,
            )
            data = {
                "migration_ready": True,
                **fred_state,
                "observations_count": repos.macro_intel.observations_count(),
                "concept_count": repos.macro_intel.concept_count(),
                "required_history_concept_count": len(MACRO_HISTORY_REQUIRED_CONCEPTS),
                **_history_readiness_payload(history),
                "latest_import_run": _json_ready(repos.macro_intel.latest_import_run()),
                "latest_snapshot": _json_ready(
                    repos.macro_intel.latest_snapshot(
                        projection_version=MACRO_VIEW_PROJECTION_VERSION,
                    )
                ),
            }
    except Exception:
        data = {
            "migration_ready": False,
            **fred_state,
            "observations_count": 0,
            "concept_count": 0,
            "history_ready": False,
            "history_coverage": {
                "required_points": MACRO_REQUIRED_STAT_POINTS,
                "required_concept_count": len(MACRO_HISTORY_REQUIRED_CONCEPTS),
                "ready_concept_count": 0,
                "coverage_ratio": 0.0,
                "lookback_days": MACRO_VIEW_HISTORY_LOOKBACK_DAYS,
            },
            "concepts_below_min_history": [],
            "latest_import_run": None,
            "latest_snapshot": None,
        }
    return 0, {"ok": True, "data": data}


def _project_once(*, repos: object, now_ms: int) -> dict[str, Any]:
    observations = repos.macro_intel.observations_for_concepts(
        concept_keys=MACRO_CORE_CONCEPTS,
        lookback_days=MACRO_VIEW_HISTORY_LOOKBACK_DAYS,
        limit_per_series=MACRO_VIEW_HISTORY_LIMIT_PER_SERIES,
    )
    snapshot = build_macro_view_snapshot(observations, computed_at_ms=now_ms)
    repos.macro_intel.insert_snapshot(snapshot)
    return {
        "projection_version": snapshot["projection_version"],
        "status": snapshot["status"],
        "regime": snapshot["regime"],
        "snapshot_id": snapshot["snapshot_id"],
    }


def _fred_payload_from_diagnostics(diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fred_api_key_env": diagnostics.get("fred_api_key_env"),
        "fred_api_key_configured": bool(diagnostics.get("fred_api_key_configured")),
    }


def _runner_diagnostics_payload(diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "command": list(diagnostics.get("command") or []),
        "returncode": diagnostics.get("returncode"),
    }


def _sync_import_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    imported_ids = list(summary.get("imported_observation_ids") or [])
    return {
        key: _json_ready(value)
        for key, value in summary.items()
        if key != "imported_observation_ids"
    } | {
        "imported_observation_count": len(imported_ids),
        "imported_observation_sample": _edge_sample(imported_ids),
    }


def _history_readiness_payload(history_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows_by_concept = {str(row.get("concept_key")): row for row in history_rows}
    below_min: list[dict[str, Any]] = []
    ready_count = 0
    for concept_key in MACRO_HISTORY_REQUIRED_CONCEPTS:
        row = rows_by_concept.get(concept_key, {})
        points = int(row.get("points") or 0)
        required_points = MACRO_HISTORY_REQUIRED_POINTS_BY_CONCEPT.get(concept_key, MACRO_REQUIRED_STAT_POINTS)
        if points >= required_points:
            ready_count += 1
            continue
        metadata = MACRO_CONCEPT_METADATA.get(concept_key, {})
        below_min.append(
            {
                "concept_key": concept_key,
                "label": metadata.get("label") or concept_key,
                "short_label": metadata.get("short_label") or concept_key,
                "points": points,
                "required_points": required_points,
                "latest_observed_at": _json_ready(row.get("latest_observed_at")),
                "oldest_observed_at": _json_ready(row.get("oldest_observed_at")),
                "sources": list(row.get("sources") or []),
            }
        )

    required_count = len(MACRO_HISTORY_REQUIRED_CONCEPTS)
    coverage_ratio = round(ready_count / required_count, 6) if required_count else 1.0
    return {
        "history_ready": not below_min,
        "history_coverage": {
            "required_points": MACRO_REQUIRED_STAT_POINTS,
            "required_concept_count": required_count,
            "ready_concept_count": ready_count,
            "coverage_ratio": coverage_ratio,
            "lookback_days": MACRO_VIEW_HISTORY_LOOKBACK_DAYS,
        },
        "concepts_below_min_history": below_min,
    }


def _edge_sample(values: Sequence[Any], *, edge_count: int = 3) -> list[Any]:
    if len(values) <= edge_count * 2:
        return list(values)
    return [*values[:edge_count], "...", *values[-edge_count:]]


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


__all__ = ["MacrodataBundleRunResult", "MacrodataBundleRunner", "handle_macro"]
