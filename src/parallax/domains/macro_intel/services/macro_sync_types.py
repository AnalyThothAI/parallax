from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True, slots=True)
class MacroSyncRunSummary:
    sync_run_id: str
    status: str
    observations_count: int
    imported_observation_count: int
    seen_observation_count: int = 0
    inserted_observation_count: int = 0
    changed_observation_count: int = 0
    noop_observation_count: int = 0
    asof_date: date | None = None
    max_observed_at: date | None = None
    max_seen_observed_at: date | None = None
    min_changed_observed_at: date | None = None
    max_changed_observed_at: date | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MacrodataBundleImport:
    sync_run_id: str
    started_at_ms: int
    completed_at_ms: int
    observations: Sequence[Mapping[str, Any]]
    bundle_name: str
    asof: date | str | None
    status: str
    coverage: Mapping[str, Any]
    missing_series: Sequence[Any]
    series_errors: Sequence[Any]
    reason_codes: Sequence[Any]
    min_observed_at: date | str | None
    max_observed_at: date | str | None


__all__ = ["MacroSyncRunSummary", "MacrodataBundleImport"]
