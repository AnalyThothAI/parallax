from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from parallax.app.runtime.repository_session import repositories
from parallax.domains.macro_intel._constants import (
    MACRO_CONCEPT_METADATA,
    MACRO_EVENT_PROVIDER_SERIES_TO_CONCEPT,
    MACRO_HISTORY_REQUIRED_CONCEPTS,
    MACRO_HISTORY_REQUIRED_POINTS_BY_CONCEPT,
    MACRO_IMPORTABLE_PROVIDER_SERIES_TO_CONCEPT,
    MACRO_PROVIDER_SERIES_TO_CONCEPT,
    MACRO_REQUIRED_STAT_POINTS,
    MACRO_VIEW_HISTORY_LOOKBACK_DAYS,
    MACRO_VIEW_PROJECTION_VERSION,
)
from parallax.domains.macro_intel.observation_identity import normalize_macro_date
from parallax.domains.macro_intel.services.macro_module_shared import required_list, required_mapping
from parallax.domains.macro_intel.services.macro_sync_service import MacroSyncService
from parallax.domains.macro_intel.services.macro_sync_types import MacroSyncRunSummary
from parallax.domains.macro_intel.services.macrodata_bundle_importer import import_macrodata_bundle
from parallax.integrations.macrodata import MacrodataBundleRunner, fred_api_key_state, macrodata_runtime_state
from parallax.platform.config.settings import Settings


@dataclass(frozen=True, slots=True)
class MacroSyncExecution:
    summary: MacroSyncRunSummary
    diagnostics: dict[str, Any]


class MacroSyncOperationError(RuntimeError):
    def __init__(self, cause: Exception, *, diagnostics: Mapping[str, Any]) -> None:
        super().__init__("macro_sync_operation_failed")
        self.cause = cause
        self.diagnostics = dict(diagnostics)


class MacroStatusOperationError(RuntimeError):
    def __init__(self, cause: Exception, *, diagnostics: Mapping[str, Any]) -> None:
        super().__init__("macro_status_operation_failed")
        self.cause = cause
        self.diagnostics = dict(diagnostics)


def import_macro_bundle(
    settings: Settings,
    envelope: Mapping[str, Any],
    *,
    now_ms: int | None = None,
) -> Mapping[str, Any]:
    """Persist one validated bundle for interval-driven projection catch-up."""
    with repositories(settings) as repos:
        summary = import_macrodata_bundle(
            envelope,
            repos=repos,
            now_ms=_now_ms() if now_ms is None else int(now_ms),
        )
    return summary


def sync_macro_window(
    settings: Settings,
    *,
    bundle_name: str,
    window_start: date,
    window_end: date,
    now_ms: int | None = None,
) -> MacroSyncExecution:
    """Compose the macro provider runner and execute one explicit sync window."""
    diagnostics: dict[str, Any] = {}
    try:
        diagnostics.update(fred_api_key_state(settings))
        service = MacroSyncService(
            settings=settings,
            repository_factory=lambda: repositories(settings),
            runner=MacrodataBundleRunner(settings=settings),
        )
        summary = service.run_explicit_window_once(
            bundle_name=bundle_name,
            window_start=window_start,
            window_end=window_end,
            now_ms=_now_ms() if now_ms is None else int(now_ms),
        )
    except Exception as exc:
        error_diagnostics = getattr(exc, "diagnostics", None)
        if isinstance(error_diagnostics, Mapping):
            diagnostics.update(error_diagnostics)
        raise MacroSyncOperationError(exc, diagnostics=diagnostics) from exc
    diagnostics.update(summary.diagnostics)
    return MacroSyncExecution(summary=summary, diagnostics=diagnostics)


def macro_status(settings: Settings, *, now_ms: int | None = None) -> dict[str, Any]:
    """Return the operator macro status snapshot without exposing provider composition to CLI."""
    diagnostics: dict[str, Any] = {}
    try:
        diagnostics.update(fred_api_key_state(settings))
        diagnostics["macrodata_cli"] = macrodata_runtime_state(
            required_series=tuple(MACRO_IMPORTABLE_PROVIDER_SERIES_TO_CONCEPT),
            required_bundles=tuple(settings.workers.macro_sync.bundle_names),
            required_bundle_series=_required_macrodata_bundle_series(settings.workers.macro_sync.bundle_names),
        )
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
            return {
                "migration_ready": True,
                **_fred_payload(diagnostics),
                "macrodata_cli": diagnostics["macrodata_cli"],
                "observations_count": repos.macro_intel.observations_count(),
                "concept_count": repos.macro_intel.concept_count(),
                "required_history_concept_count": len(MACRO_HISTORY_REQUIRED_CONCEPTS),
                **_history_readiness_payload(history),
                "sync_queue": _json_ready(
                    repos.macro_intel.macro_sync_queue_summary(now_ms=_now_ms() if now_ms is None else int(now_ms))
                ),
                "publication_state": _publication_state_status(publication_state),
                "facts_max_observed_at": _json_ready(facts_max_observed_at),
                "projection_lag_days": _projection_lag_days(facts_max_observed_at, snapshot_asof),
                "projection_behind_facts": projection_behind_facts,
                "latest_snapshot": _snapshot_status_summary(latest_snapshot),
            }
    except Exception as exc:
        raise MacroStatusOperationError(exc, diagnostics=diagnostics) from exc


def _required_macrodata_bundle_series(bundle_names: Sequence[str]) -> dict[str, tuple[str, ...]]:
    configured = tuple(dict.fromkeys(str(item).strip() for item in bundle_names if str(item).strip()))
    required: dict[str, tuple[str, ...]] = {}
    for bundle_name in configured:
        if bundle_name == "macro-core":
            required[bundle_name] = _numeric_series_excluding_crypto_derivatives()
        elif bundle_name == "macro-calendar-core":
            required[bundle_name] = _event_series_with_prefix("official_calendar:")
        elif bundle_name == "treasury-auction-core":
            required[bundle_name] = _event_series_with_prefix("treasury_auction:")
        elif bundle_name == "fed-text-core":
            required[bundle_name] = _event_series_with_prefix("official_fed_text:")
        elif bundle_name == "crypto-derivatives-core":
            required[bundle_name] = _crypto_derivatives_series()
    return required


def _numeric_series_excluding_crypto_derivatives() -> tuple[str, ...]:
    return tuple(
        series_key
        for series_key, concept_key in MACRO_PROVIDER_SERIES_TO_CONCEPT.items()
        if not concept_key.startswith("crypto_derivatives:")
    )


def _crypto_derivatives_series() -> tuple[str, ...]:
    return tuple(
        series_key
        for series_key, concept_key in MACRO_PROVIDER_SERIES_TO_CONCEPT.items()
        if concept_key.startswith("crypto_derivatives:")
    )


def _event_series_with_prefix(prefix: str) -> tuple[str, ...]:
    return tuple(series_key for series_key in MACRO_EVENT_PROVIDER_SERIES_TO_CONCEPT if series_key.startswith(prefix))


def _projection_lag_days(facts_max_observed_at: date | None, snapshot_asof: date | None) -> int | None:
    if facts_max_observed_at is None or snapshot_asof is None:
        return None
    return max(0, (facts_max_observed_at - snapshot_asof).days)


def _snapshot_status_summary(snapshot: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    panels = _required_object_map(snapshot, "panels_json")
    features = required_mapping(snapshot, "features_json")
    indicators = required_mapping(snapshot, "indicators_json")
    required_list(snapshot, "triggers_json")
    data_gaps = required_list(snapshot, "data_gaps_json")
    source_coverage = required_mapping(snapshot, "source_coverage_json")
    for field_name in ("chain_json", "scenario_json", "scorecard_json", "module_views_json"):
        required_mapping(snapshot, field_name)
    return {
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
            "latest_coverage_ratio": source_coverage.get("latest_coverage_ratio"),
            "history_coverage_ratio": source_coverage.get("history_coverage_ratio"),
            "observed_concept_count": source_coverage.get("observed_concept_count"),
            "required_concept_count": source_coverage.get("required_concept_count"),
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


def _fred_payload(diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fred_api_key_env": diagnostics.get("fred_api_key_env"),
        "fred_api_key_configured": bool(diagnostics.get("fred_api_key_configured")),
    }


def _edge_sample(values: Sequence[Any], *, edge_count: int = 3) -> list[Any]:
    if len(values) <= edge_count * 2:
        return list(values)
    return [*values[:edge_count], "...", *values[-edge_count:]]


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _required_object_map(value: Mapping[str, Any], field_name: str) -> dict[str, Mapping[str, Any]]:
    items = required_mapping(value, field_name)
    invalid_key = next((str(key) for key, item in items.items() if not isinstance(item, Mapping)), None)
    if invalid_key is not None:
        raise ValueError(f"macro_view_snapshot_section_invalid:{field_name}.{invalid_key}")
    return {str(key): item for key, item in items.items() if isinstance(item, Mapping)}


def _sequence(value: object) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return value
    return ()


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


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = [
    "MacroStatusOperationError",
    "MacroSyncExecution",
    "MacroSyncOperationError",
    "import_macro_bundle",
    "macro_status",
    "sync_macro_window",
]
