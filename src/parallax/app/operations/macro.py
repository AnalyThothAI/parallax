from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from parallax.app.runtime.repository_session import repositories
from parallax.domains.macro_intel._constants import (
    MACRO_EVENT_PROVIDER_SERIES_TO_CONCEPT,
    MACRO_EVIDENCE_HISTORY_LOOKBACK_DAYS,
    MACRO_EVIDENCE_PROJECTION_VERSION,
    MACRO_IMPORTABLE_PROVIDER_SERIES_TO_CONCEPT,
    MACRO_PROVIDER_SERIES_TO_CONCEPT,
)
from parallax.domains.macro_intel.observation_identity import normalize_macro_date
from parallax.domains.macro_intel.services.macro_concept_manifest import (
    MACRO_CONCEPT_MANIFEST,
    MACRO_EVIDENCE_CONCEPTS,
    MACRO_PAGE_IDS,
)
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


_MATERIAL_CLAIM_CONCEPTS = tuple(
    concept_key
    for concept_key in MACRO_EVIDENCE_CONCEPTS
    if MACRO_CONCEPT_MANIFEST[concept_key].claim_effect != "catalyst_only"
)


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
        effective_now_ms = _now_ms() if now_ms is None else int(now_ms)
        with repositories(settings) as repos:
            history = repos.macro_intel.concept_history_counts(
                concept_keys=MACRO_EVIDENCE_CONCEPTS,
                lookback_days=MACRO_EVIDENCE_HISTORY_LOOKBACK_DAYS,
            )
            latest_snapshot = repos.macro_intel.latest_snapshot()
            publication_state = repos.macro_intel.macro_series_publication_state(MACRO_EVIDENCE_PROJECTION_VERSION)
            facts_max_observed_at = _to_date(
                repos.macro_intel.material_fact_max_observed_at(
                    concept_keys=_MATERIAL_CLAIM_CONCEPTS,
                    through_date=datetime.fromtimestamp(effective_now_ms / 1000, tz=UTC).date(),
                )
            )
            snapshot_fact_watermark = _to_date(latest_snapshot.get("fact_watermark") if latest_snapshot else None)
            projection_behind_facts = facts_max_observed_at is not None and (
                snapshot_fact_watermark is None or snapshot_fact_watermark < facts_max_observed_at
            )
            return {
                "migration_ready": True,
                **_fred_payload(diagnostics),
                "macrodata_cli": diagnostics["macrodata_cli"],
                "observations_count": repos.macro_intel.observations_count(),
                "concept_count": repos.macro_intel.concept_count(),
                "manifest": _manifest_inventory_payload(history),
                "sync_queue": _json_ready(repos.macro_intel.macro_sync_queue_summary(now_ms=effective_now_ms)),
                "publication_state": _publication_state_status(publication_state),
                "facts_max_observed_at": _json_ready(facts_max_observed_at),
                "projection_lag_days": _projection_lag_days(facts_max_observed_at, snapshot_fact_watermark),
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
    pages: dict[str, Any] = {}
    for page_id in MACRO_PAGE_IDS:
        page = _required_mapping(snapshot, f"{page_id}_json")
        conclusion = _required_mapping(page, "conclusion")
        freshness = _required_mapping(page, "freshness")
        pages[page_id] = {
            "status": conclusion.get("status"),
            "judgment": conclusion.get("judgment"),
            "freshness_status": freshness.get("status"),
            "evidence_count": len(_sequence(page.get("evidence"))),
            "unavailable_evidence_count": len(_sequence(page.get("unavailable_evidence"))),
        }
    return {
        "projection_version": snapshot.get("projection_version"),
        "fact_watermark": _json_ready(snapshot.get("fact_watermark")),
        "market_cutoff": _json_ready(snapshot.get("market_cutoff")),
        "computed_at_ms": snapshot.get("computed_at_ms"),
        "pages": pages,
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


def _manifest_inventory_payload(history_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows_by_concept = {str(row.get("concept_key")): row for row in history_rows}
    observed: list[str] = []
    missing: list[str] = []
    for concept_key in MACRO_EVIDENCE_CONCEPTS:
        row = rows_by_concept.get(concept_key, {})
        (observed if int(row.get("points") or 0) > 0 else missing).append(concept_key)
    return {
        "declared_concept_count": len(MACRO_EVIDENCE_CONCEPTS),
        "observed_concept_count": len(observed),
        "missing_concept_count": len(missing),
        "missing_concept_sample": _edge_sample(missing),
        "lookback_days": MACRO_EVIDENCE_HISTORY_LOOKBACK_DAYS,
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


def _required_mapping(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    item = value.get(field_name)
    if not isinstance(item, Mapping):
        raise ValueError(f"macro_evidence_snapshot_section_invalid:{field_name}")
    return item


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
