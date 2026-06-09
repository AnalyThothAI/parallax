from __future__ import annotations

import json
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any, cast

from parallax.app.runtime.wake_bus import WakeBus
from parallax.app.surfaces.cli.dependencies import postgres_connection, repositories
from parallax.domains.macro_intel._constants import (
    MACRO_CONCEPT_METADATA,
    MACRO_HISTORY_REQUIRED_CONCEPTS,
    MACRO_HISTORY_REQUIRED_POINTS_BY_CONCEPT,
    MACRO_PROVIDER_SERIES_TO_CONCEPT,
    MACRO_REQUIRED_STAT_POINTS,
    MACRO_VIEW_HISTORY_LOOKBACK_DAYS,
    MACRO_VIEW_PROJECTION_VERSION,
)
from parallax.domains.macro_intel.observation_identity import normalize_macro_date
from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService
from parallax.domains.macro_intel.services.macro_sync_types import MacroSyncRunSummary
from parallax.domains.macro_intel.services.macrodata_bundle_importer import import_macrodata_bundle
from parallax.integrations.macrodata import MacrodataBundleRunner, fred_api_key_state, macrodata_runtime_state
from parallax.platform.config.settings import load_settings


def handle_macro(args: object) -> tuple[int, dict[str, Any]]:
    if args.macro_command == "import-bundle":
        return _handle_import_bundle(args)
    if args.macro_command == "sync":
        return _handle_sync(args)
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
        _notify_imported_observations(settings, summary)
    except Exception as exc:
        return 1, _error_payload("macro_import_bundle_failed", exc)
    return 0, {"ok": True, "data": _json_ready(summary)}


def _handle_sync(args: object) -> tuple[int, dict[str, Any]]:
    fred_state: Mapping[str, Any] = {}
    try:
        settings = load_settings(require_ws_token=False)
        fred_state = fred_api_key_state(settings)
        window_start = _parse_cli_date(str(args.start), field="start")
        window_end = _parse_cli_date(str(args.end), field="end")
        if window_start > window_end:
            return 2, {"ok": False, "error": "macro_sync_invalid_date_range"}
        now_ms = _now_ms()
        service = MacroSyncService(
            settings=settings,
            repository_factory=lambda: repositories(settings),
            runner=MacrodataBundleRunner(settings=settings),
        )
        summary = service.run_explicit_window_once(
            bundle_name=str(args.bundle),
            window_start=window_start,
            window_end=window_end,
            now_ms=now_ms,
        )
        sync_payload = _sync_summary(summary, window_start=window_start, window_end=window_end)
        sync_ok = summary.status in {"ok", "partial"}
    except _MacroSyncCliValidationError as exc:
        return 2, {"ok": False, "error": "macro_sync_invalid_date", "field": exc.field}
    except Exception as exc:
        payload = _error_payload("macro_sync_failed", exc)
        payload.update(_fred_payload_from_diagnostics(fred_state))
        diagnostics = getattr(exc, "diagnostics", None)
        if isinstance(diagnostics, Mapping):
            payload.update(_fred_payload_from_diagnostics(diagnostics))
        return 1, payload

    data = {
        **_fred_payload_from_diagnostics({**dict(fred_state), **summary.diagnostics}),
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
    fred_state = fred_api_key_state(settings)
    macrodata_state = macrodata_runtime_state(required_series=tuple(MACRO_PROVIDER_SERIES_TO_CONCEPT))
    try:
        with repositories(settings) as repos:
            history = repos.macro_intel.concept_history_counts(
                concept_keys=MACRO_HISTORY_REQUIRED_CONCEPTS,
                lookback_days=MACRO_VIEW_HISTORY_LOOKBACK_DAYS,
            )
            latest_snapshot = repos.macro_intel.latest_snapshot(
                projection_version=MACRO_VIEW_PROJECTION_VERSION,
            )
            publication_state = repos.macro_intel.macro_series_publication_state(MACRO_VIEW_PROJECTION_VERSION)
            facts_max_observed_at = _snapshot_latest_observed_at(latest_snapshot)
            snapshot_asof = _to_date(latest_snapshot.get("asof_date") if latest_snapshot else None)
            projection_behind_facts = facts_max_observed_at is not None and (
                snapshot_asof is None or snapshot_asof < facts_max_observed_at
            )
            data = {
                "migration_ready": True,
                **fred_state,
                "macrodata_cli": macrodata_state,
                "observations_count": repos.macro_intel.observations_count(),
                "concept_count": repos.macro_intel.concept_count(),
                "required_history_concept_count": len(MACRO_HISTORY_REQUIRED_CONCEPTS),
                **_history_readiness_payload(history),
                "sync_queue": _json_ready(repos.macro_intel.macro_sync_queue_summary(now_ms=_now_ms())),
                "publication_state": _publication_state_status(publication_state),
                "facts_max_observed_at": _json_ready(facts_max_observed_at),
                "projection_lag_days": _projection_lag_days(facts_max_observed_at, snapshot_asof),
                "projection_behind_facts": projection_behind_facts,
                "latest_snapshot": _snapshot_status_summary(latest_snapshot),
            }
    except Exception as exc:
        payload = _error_payload("macro_status_unavailable", exc)
        payload["error_type"] = type(exc).__name__
        payload["data"] = {**_fred_payload_from_diagnostics(fred_state), "macrodata_cli": macrodata_state}
        return 1, payload
    return 0, {"ok": True, "data": data}


def _fred_payload_from_diagnostics(diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fred_api_key_env": diagnostics.get("fred_api_key_env"),
        "fred_api_key_configured": bool(diagnostics.get("fred_api_key_configured")),
    }


def _notify_imported_observations(settings: object, summary: Mapping[str, Any]) -> None:
    imported_count = int(summary.get("imported_observation_count") or 0)
    if imported_count <= 0:
        return
    try:
        WakeBus(lambda: postgres_connection(settings)).notify_macro_observations_imported(
            count=imported_count,
            max_observed_at=_json_ready(summary.get("max_observed_at")),
            asof_date=_json_ready(summary.get("asof")),
        )
    except Exception:
        return


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


def _projection_lag_days(facts_max_observed_at: date | None, snapshot_asof: date | None) -> int | None:
    if facts_max_observed_at is None or snapshot_asof is None:
        return None
    return max(0, (facts_max_observed_at - snapshot_asof).days)


def _snapshot_status_summary(snapshot: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    heavy_keys = {
        "chain_json",
        "data_gaps_json",
        "features_json",
        "indicators_json",
        "panels_json",
        "scenario_json",
        "scorecard_json",
        "source_coverage_json",
    }
    if not any(key in snapshot for key in heavy_keys):
        return cast(dict[str, Any], _json_ready(snapshot))

    panels = _object_map(snapshot.get("panels_json")) or _object_map(snapshot.get("chain_json"))
    features = _object_map(snapshot.get("features_json"))
    indicators = _object_map(snapshot.get("indicators_json"))
    data_gaps = _sequence(snapshot.get("data_gaps_json"))
    scorecard = _mapping(snapshot.get("scorecard_json"))
    source_coverage = _mapping(snapshot.get("source_coverage_json"))
    return {
        "snapshot_id": snapshot.get("snapshot_id"),
        "projection_version": snapshot.get("projection_version"),
        "asof_date": _json_ready(snapshot.get("asof_date")),
        "status": snapshot.get("status"),
        "regime": snapshot.get("regime"),
        "overall_score": snapshot.get("overall_score"),
        "computed_at_ms": snapshot.get("computed_at_ms"),
        "feature_count": len(features),
        "indicator_count": len(indicators),
        "data_gap_count": len(data_gaps),
        "data_gap_codes": _edge_sample([str(gap.get("code")) for gap in data_gaps if isinstance(gap, Mapping)]),
        "coverage": {
            "latest_coverage_ratio": source_coverage.get("latest_coverage_ratio")
            or scorecard.get("latest_coverage_ratio"),
            "history_coverage_ratio": source_coverage.get("history_coverage_ratio")
            or scorecard.get("history_coverage_ratio"),
            "observed_concept_count": source_coverage.get("observed_concept_count")
            or scorecard.get("observed_concept_count"),
            "required_concept_count": source_coverage.get("required_concept_count")
            or scorecard.get("required_concept_count"),
            "history_ready_concept_count": source_coverage.get("history_ready_concept_count"),
            "required_history_concept_count": source_coverage.get("required_history_concept_count"),
            "concepts_below_min_history": list(source_coverage.get("concepts_below_min_history") or []),
        },
        "panels": {
            str(panel_id): {
                "score": panel.get("score"),
                "regime": panel.get("regime"),
                "evidence_count": len(_sequence(panel.get("evidence"))),
                "data_gap_count": len(_sequence(panel.get("data_gaps"))),
            }
            for panel_id, panel in panels.items()
        },
    }


def _publication_state_status(state: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if state is None:
        return None
    return {
        "projection_version": state.get("projection_version"),
        "row_count": state.get("row_count"),
        "latest_attempt_status": state.get("latest_attempt_status"),
        "latest_attempt_finished_at_ms": state.get("latest_attempt_finished_at_ms"),
        "latest_attempt_error": state.get("latest_attempt_error"),
    }


def _snapshot_latest_observed_at(snapshot: Mapping[str, Any] | None) -> date | None:
    coverage = _mapping(snapshot.get("source_coverage_json") if snapshot else None)
    return _to_date(coverage.get("latest_observed_at") or (snapshot or {}).get("asof_date"))


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


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _object_map(value: object) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items() if isinstance(item, Mapping)}


def _sequence(value: object) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return value
    return ()


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


def _to_date(value: object) -> date | None:
    if value is None:
        return None
    try:
        return normalize_macro_date(value)
    except ValueError:
        return None
    return None


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["handle_macro"]
