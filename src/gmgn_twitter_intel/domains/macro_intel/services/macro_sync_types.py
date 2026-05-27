from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True, slots=True)
class MacroSyncWindow:
    sync_window_id: str
    source_name: str
    bundle_name: str
    window_start: date
    window_end: date
    trigger_reason: str
    status: str
    attempt_count: int
    max_attempts: int
    payload_hash: str


@dataclass(frozen=True, slots=True)
class MacroSyncRunSummary:
    sync_run_id: str
    import_run_id: str | None
    status: str
    observations_count: int
    imported_observation_count: int
    asof_date: date | None
    max_observed_at: date | None
    diagnostics: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class MacrodataBundleImport:
    import_run: Mapping[str, Any]
    observations: Sequence[Mapping[str, Any]]
    bundle_name: str
    asof: date | str | None
    status: str
    coverage: Mapping[str, Any]
    missing_series: Sequence[Any]
    series_errors: Sequence[Any]
    reason_codes: Sequence[Any]
    max_observed_at: date | str | None


__all__ = ["MacroSyncRunSummary", "MacroSyncWindow", "MacrodataBundleImport"]
