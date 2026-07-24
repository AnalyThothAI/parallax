from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from parallax.app.runtime.repository_session import repositories
from parallax.domains.macro_intel._constants import (
    MACRO_EVENT_PROVIDER_SERIES_TO_CONCEPT,
    MACRO_IMPORTABLE_PROVIDER_SERIES_TO_CONCEPT,
    MACRO_PROVIDER_SERIES_TO_CONCEPT,
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
            through_date = datetime.fromtimestamp(effective_now_ms / 1000, tz=UTC).date()
            material_facts = repos.macro_intel.material_fact_state(
                through_date=through_date,
            )
            research_state = repos.macro_research.research_state(None)
            return {
                "migration_ready": True,
                **_fred_payload(diagnostics),
                "macrodata_cli": diagnostics["macrodata_cli"],
                "material_facts": _json_ready(material_facts),
                "sync_queue": _json_ready(repos.macro_intel.macro_sync_queue_summary(now_ms=effective_now_ms)),
                "latest_research": _research_status_summary(research_state),
            }
    except Exception as exc:
        raise MacroStatusOperationError(exc, diagnostics=diagnostics) from exc


def retry_failed_macro_research(
    settings: Settings,
    *,
    session_date: date,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Grant one immediately due attempt only when the persisted run is failed."""
    effective_now_ms = _now_ms() if now_ms is None else int(now_ms)
    with repositories(settings) as repos, repos.transaction():
        result = repos.macro_research.retry_failed_run(
            session_date=session_date,
            now_ms=effective_now_ms,
        )
    return {
        "action": "retry_research",
        "requested_at_ms": effective_now_ms,
        "outcome": "applied" if result["applied"] else "no_op",
        **result,
    }


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


def _research_status_summary(state: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if state is None:
        return None
    return {
        "session_date": _json_ready(state.get("session_date")),
        "market_cutoff_ms": state.get("market_cutoff_ms"),
        "sealed_at_ms": state.get("sealed_at_ms"),
        "run_status": state.get("run_status"),
        "attempt_count": state.get("attempt_count"),
        "max_attempts": state.get("max_attempts"),
        "due_at_ms": state.get("due_at_ms"),
        "published_at_ms": state.get("published_at_ms"),
        "model_name": state.get("model_name"),
        "prompt_version": state.get("prompt_version"),
        "workflow_version": state.get("workflow_version"),
        "last_error_code": state.get("last_error_code"),
        "last_error_message": state.get("last_error_message"),
    }


def _fred_payload(diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fred_api_key_env": diagnostics.get("fred_api_key_env"),
        "fred_api_key_configured": bool(diagnostics.get("fred_api_key_configured")),
    }


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


__all__ = [
    "MacroStatusOperationError",
    "MacroSyncExecution",
    "MacroSyncOperationError",
    "import_macro_bundle",
    "macro_status",
    "retry_failed_macro_research",
    "sync_macro_window",
]
