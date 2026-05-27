from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, cast

from gmgn_twitter_intel.domains.macro_intel._constants import MACRO_VIEW_PROJECTION_VERSION
from gmgn_twitter_intel.domains.macro_intel.services.macro_sync_scheduler import ensure_due_macro_sync_windows
from gmgn_twitter_intel.domains.macro_intel.services.macro_sync_types import MacroSyncRunSummary
from gmgn_twitter_intel.domains.macro_intel.services.macrodata_bundle_importer import (
    parse_macrodata_bundle,
    write_macrodata_bundle_import,
)
from gmgn_twitter_intel.integrations.macrodata.runner import (
    MacrodataBundleRunner,
    MacrodataRunnerError,
    fred_api_key_state,
)

if TYPE_CHECKING:
    from gmgn_twitter_intel.app.runtime.repository_session import RepositorySession


_CONFIG_ERROR_CODES = {
    "macrodata_executable_missing",
}
_URI_CREDENTIAL_RE = re.compile(r"([a-z][a-z0-9+.-]*://[^:/@\s]+):([^@\s]+)@", re.IGNORECASE)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b(api[_-]?key|token|secret|password|pwd)\s*[:=]\s*([^,\s;]+)",
    re.IGNORECASE,
)


class _StaleMacroSyncClaimError(RuntimeError):
    pass


class MacroSyncService:
    def __init__(
        self,
        *,
        settings: object,
        db: Any | None = None,
        repository_factory: Callable[[], AbstractContextManager[RepositorySession]] | None = None,
        runner: MacrodataBundleRunner | None = None,
        wake_bus: Any | None = None,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self.settings = settings
        self.db = db
        self.repository_factory = repository_factory
        self.runner = runner or MacrodataBundleRunner(settings=settings)
        self.wake_bus = wake_bus
        self.clock_ms = clock_ms or _now_ms

    def enqueue_due_windows(self, *, now_ms: int | None = None) -> dict[str, Any]:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        sync_settings = _sync_settings(self.settings)
        with self._repository_session() as repos:
            summary = ensure_due_macro_sync_windows(
                repos=repos,
                source_name=str(getattr(sync_settings, "source_name", "macrodata-cli")),
                bundle_name=str(getattr(sync_settings, "bundle_name", "macro-core")),
                now=_date_from_ms(now),
                now_ms=now,
                bootstrap_lookback_days=int(getattr(sync_settings, "bootstrap_lookback_days", 1095)),
                max_window_days=int(getattr(sync_settings, "max_window_days", 31)),
                steady_overlap_days=int(getattr(sync_settings, "steady_overlap_days", 7)),
                steady_interval_seconds=float(getattr(sync_settings, "interval_seconds", 900.0)),
                max_bootstrap_windows_per_cycle=int(getattr(sync_settings, "max_bootstrap_windows_per_cycle", 1)),
                max_attempts=int(getattr(sync_settings, "max_attempts", 8)),
            )
            queue_summary = _call_queue_summary(repos, now_ms=now)
        return {**summary, **queue_summary}

    def run_claimed_window_once(self, *, lease_owner: str, now_ms: int | None = None) -> MacroSyncRunSummary | None:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        sync_settings = _sync_settings(self.settings)
        with self._repository_session() as repos:
            window = repos.macro_intel.claim_macro_sync_window(
                lease_owner=lease_owner,
                lease_ms=int(getattr(sync_settings, "lease_ms", 300_000)),
                now_ms=now,
            )
        if window is None:
            return None
        return self._run_window(window, lease_owner=lease_owner, now_ms=now)

    def run_explicit_window_once(
        self,
        *,
        bundle_name: str,
        window_start: date,
        window_end: date,
        trigger_reason: str = "operator_sync",
        lease_owner: str = "macro_cli_sync",
        now_ms: int | None = None,
    ) -> MacroSyncRunSummary:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        sync_settings = _sync_settings(self.settings)
        with self._repository_session() as repos, repos.unit_of_work():
            sync_window_id = repos.macro_intel.enqueue_macro_sync_window(
                source_name=str(getattr(sync_settings, "source_name", "macrodata-cli")),
                bundle_name=bundle_name,
                window_start=window_start,
                window_end=window_end,
                trigger_reason=_explicit_trigger_reason(trigger_reason, now_ms=now),
                priority=0,
                due_at_ms=now,
                max_attempts=int(getattr(sync_settings, "max_attempts", 8)),
                now_ms=now,
            )
            window = repos.macro_intel.claim_macro_sync_window_by_id(
                sync_window_id=sync_window_id,
                lease_owner=lease_owner,
                lease_ms=int(getattr(sync_settings, "lease_ms", 300_000)),
                now_ms=now,
            )
            if window is None:
                raise RuntimeError("macro explicit sync window was not claimable")
        return self._run_window(window, lease_owner=lease_owner, now_ms=now)

    def _run_window(
        self,
        window: Mapping[str, Any],
        *,
        lease_owner: str,
        now_ms: int,
    ) -> MacroSyncRunSummary:
        started_at_ms = now_ms
        sync_run_id = f"macro-sync:{uuid.uuid4().hex}"
        try:
            run_result = self.runner.history_bundle(
                bundle=str(window["bundle_name"]),
                start=_date_string(window["window_start"]),
                end=_date_string(window["window_end"]),
            )
            parsed = parse_macrodata_bundle(run_result.envelope, now_ms=now_ms)
            diagnostics = _safe_diagnostics(run_result.diagnostics)
            with self._repository_session() as repos, repos.unit_of_work():
                import_summary = write_macrodata_bundle_import(parsed, repos=repos)
                completed_at_ms = int(self.clock_ms())
                run_payload = _sync_run_payload(
                    sync_run_id=sync_run_id,
                    window=window,
                    status=str(import_summary.get("status") or "ok"),
                    import_run_id=cast("str | None", import_summary.get("import_run_id")),
                    observations_count=int(import_summary.get("observations_count") or 0),
                    imported_observation_count=int(import_summary.get("imported_observation_count") or 0),
                    asof_date=_to_date(import_summary.get("asof")),
                    max_observed_at=_to_date(import_summary.get("max_observed_at")),
                    diagnostics=diagnostics,
                    started_at_ms=started_at_ms,
                    completed_at_ms=completed_at_ms,
                    settings=self.settings,
                    error_code=None,
                    error_message=None,
                )
                repos.macro_intel.record_macro_sync_run(run_payload)
                if int(import_summary.get("imported_observation_count") or 0) > 0:
                    repos.macro_intel.enqueue_macro_projection_dirty_target(
                        projection_name="macro_view",
                        projection_version=MACRO_VIEW_PROJECTION_VERSION,
                        now_ms=completed_at_ms,
                        due_at_ms=completed_at_ms,
                        reason="macro_observations_imported",
                        commit=False,
                    )
                completed = repos.macro_intel.complete_macro_sync_window(
                    sync_window_id=str(window["sync_window_id"]),
                    lease_owner=lease_owner,
                    attempt_count=int(window["attempt_count"]),
                    sync_run_id=sync_run_id,
                    completed_at_ms=completed_at_ms,
                )
                if not completed:
                    raise _StaleMacroSyncClaimError("macro sync claim is no longer current")
            summary = _summary_from_payload(run_payload)
            if summary.imported_observation_count > 0 and self.wake_bus is not None:
                _notify_macro_observations_imported(self.wake_bus, summary)
            return summary
        except _StaleMacroSyncClaimError:
            return _stale_claim_summary(sync_run_id=sync_run_id)
        except MacrodataRunnerError as exc:
            error_code = str(exc.diagnostics.get("error_code") or "macrodata_runner_error")
            if error_code in _CONFIG_ERROR_CODES:
                status = "config_error"
                retry = False
            elif _attempt_budget_exhausted(window):
                status = "failed"
                retry = False
            else:
                status = "retryable_error"
                retry = True
            return self._record_failure(
                window,
                lease_owner=lease_owner,
                sync_run_id=sync_run_id,
                status=status,
                error_code=error_code,
                error_message=str(exc),
                diagnostics=_safe_diagnostics(exc.diagnostics),
                started_at_ms=started_at_ms,
                now_ms=now_ms,
                retry=retry,
            )
        except Exception as exc:
            return self._record_failure(
                window,
                lease_owner=lease_owner,
                sync_run_id=sync_run_id,
                status="failed",
                error_code=exc.__class__.__name__,
                error_message=str(exc),
                diagnostics={},
                started_at_ms=started_at_ms,
                now_ms=now_ms,
                retry=False,
            )

    def _record_failure(
        self,
        window: Mapping[str, Any],
        *,
        lease_owner: str,
        sync_run_id: str,
        status: str,
        error_code: str,
        error_message: str,
        diagnostics: Mapping[str, Any],
        started_at_ms: int,
        now_ms: int,
        retry: bool,
    ) -> MacroSyncRunSummary:
        sync_settings = _sync_settings(self.settings)
        completed_at_ms = int(self.clock_ms())
        payload = _sync_run_payload(
            sync_run_id=sync_run_id,
            window=window,
            status=status,
            import_run_id=None,
            observations_count=0,
            imported_observation_count=0,
            asof_date=None,
            max_observed_at=None,
            diagnostics=diagnostics,
            started_at_ms=started_at_ms,
            completed_at_ms=completed_at_ms,
            settings=self.settings,
            error_code=error_code,
            error_message=_safe_error_message(error_message),
        )
        try:
            with self._repository_session() as repos, repos.unit_of_work():
                repos.macro_intel.record_macro_sync_run(payload)
                if retry:
                    terminalized = repos.macro_intel.retry_macro_sync_window(
                        sync_window_id=str(window["sync_window_id"]),
                        lease_owner=lease_owner,
                        attempt_count=int(window["attempt_count"]),
                        sync_run_id=sync_run_id,
                        error_code=error_code,
                        error_message=_safe_error_message(error_message),
                        retry_delay_ms=int(getattr(sync_settings, "retry_delay_ms", 900_000)),
                        now_ms=now_ms,
                    )
                else:
                    terminalized = repos.macro_intel.fail_macro_sync_window(
                        sync_window_id=str(window["sync_window_id"]),
                        lease_owner=lease_owner,
                        attempt_count=int(window["attempt_count"]),
                        sync_run_id=sync_run_id,
                        error_code=error_code,
                        error_message=_safe_error_message(error_message),
                        now_ms=now_ms,
                    )
                if not terminalized:
                    raise _StaleMacroSyncClaimError("macro sync claim is no longer current")
        except _StaleMacroSyncClaimError:
            return _stale_claim_summary(sync_run_id=sync_run_id)
        return _summary_from_payload(payload)

    def _repository_session(self) -> AbstractContextManager[RepositorySession]:
        if self.repository_factory is not None:
            return self.repository_factory()
        if self.db is None:
            raise RuntimeError("MacroSyncService requires db or repository_factory")
        sync_settings = _sync_settings(self.settings)
        return cast(
            "AbstractContextManager[RepositorySession]",
            self.db.worker_session(
                "macro_sync",
                statement_timeout_seconds=getattr(sync_settings, "statement_timeout_seconds", None),
            ),
        )


def _sync_settings(settings: object) -> object:
    workers = getattr(settings, "workers", None)
    macro_sync = getattr(workers, "macro_sync", None)
    return macro_sync or settings


def _sync_run_payload(
    *,
    sync_run_id: str,
    window: Mapping[str, Any],
    status: str,
    import_run_id: str | None,
    observations_count: int,
    imported_observation_count: int,
    asof_date: date | None,
    max_observed_at: date | None,
    diagnostics: Mapping[str, Any],
    started_at_ms: int,
    completed_at_ms: int,
    settings: object,
    error_code: str | None,
    error_message: str | None,
) -> dict[str, Any]:
    fred_state = fred_api_key_state(settings)
    return {
        "sync_run_id": sync_run_id,
        "sync_window_id": str(window["sync_window_id"]),
        "source_name": str(window["source_name"]),
        "bundle_name": str(window["bundle_name"]),
        "requested_start": _to_date(window["window_start"]),
        "requested_end": _to_date(window["window_end"]),
        "status": status,
        "import_run_id": import_run_id,
        "asof_date": asof_date,
        "max_observed_at": max_observed_at,
        "observations_count": observations_count,
        "imported_observation_count": imported_observation_count,
        "coverage_json": {},
        "missing_series_json": [],
        "series_errors_json": [],
        "reason_codes_json": [],
        "diagnostics_json": dict(diagnostics),
        "fred_api_key_env": diagnostics.get("fred_api_key_env") or fred_state["fred_api_key_env"],
        "fred_api_key_configured": bool(
            diagnostics.get("fred_api_key_configured", fred_state["fred_api_key_configured"])
        ),
        "error_code": error_code,
        "error_message": error_message,
        "started_at_ms": started_at_ms,
        "completed_at_ms": completed_at_ms,
        "duration_ms": max(0, int(completed_at_ms) - int(started_at_ms)),
    }


def _summary_from_payload(payload: Mapping[str, Any]) -> MacroSyncRunSummary:
    return MacroSyncRunSummary(
        sync_run_id=str(payload["sync_run_id"]),
        import_run_id=cast("str | None", payload.get("import_run_id")),
        status=str(payload["status"]),
        observations_count=int(payload.get("observations_count") or 0),
        imported_observation_count=int(payload.get("imported_observation_count") or 0),
        asof_date=_to_date(payload.get("asof_date")),
        max_observed_at=_to_date(payload.get("max_observed_at")),
        diagnostics=dict(cast("Mapping[str, Any]", payload.get("diagnostics_json") or {})),
    )


def _stale_claim_summary(*, sync_run_id: str) -> MacroSyncRunSummary:
    return MacroSyncRunSummary(
        sync_run_id=sync_run_id,
        import_run_id=None,
        status="stale_claim",
        observations_count=0,
        imported_observation_count=0,
        asof_date=None,
        max_observed_at=None,
        diagnostics={},
    )


def _attempt_budget_exhausted(window: Mapping[str, Any]) -> bool:
    return int(window.get("attempt_count") or 0) >= int(window.get("max_attempts") or 1)


def _explicit_trigger_reason(trigger_reason: str, *, now_ms: int) -> str:
    return f"{trigger_reason}:{int(now_ms)}"


def _notify_macro_observations_imported(wake_bus: Any, summary: MacroSyncRunSummary) -> None:
    try:
        wake_bus.notify_macro_observations_imported(
            count=summary.imported_observation_count,
            max_observed_at=str(summary.max_observed_at) if summary.max_observed_at else None,
            asof_date=str(summary.asof_date) if summary.asof_date else None,
        )
    except Exception:
        return


def _safe_diagnostics(diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    allowed: dict[str, Any] = {}
    for key in (
        "command",
        "returncode",
        "error_code",
        "fred_api_key_env",
        "fred_api_key_configured",
    ):
        if key in diagnostics:
            allowed[key] = diagnostics[key]
    if "command" in allowed:
        allowed["command"] = [str(part) for part in cast("list[Any]", allowed["command"])]
    if "fred_api_key_configured" in allowed:
        allowed["fred_api_key_configured"] = bool(allowed["fred_api_key_configured"])
    return allowed


def _safe_error_message(message: str) -> str:
    redacted = _URI_CREDENTIAL_RE.sub(r"\1:***@", str(message))
    redacted = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=***", redacted)
    return redacted[:240]


def _call_queue_summary(repos: RepositorySession, *, now_ms: int) -> dict[str, Any]:
    queue_summary = getattr(repos.macro_intel, "macro_sync_queue_summary", None)
    if not callable(queue_summary):
        return {}
    return dict(queue_summary(now_ms=now_ms))


def _date_string(value: object) -> str:
    parsed = _to_date(value)
    return str(parsed) if parsed is not None else str(value)


def _to_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value)
    return None


def _date_from_ms(now_ms: int) -> date:
    return datetime.fromtimestamp(now_ms / 1000, tz=UTC).date()


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["MacroSyncService"]
