from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any, cast

from parallax.domains.macro_intel._constants import (
    MACRO_CORE_CONCEPTS,
    MACRO_VIEW_PROJECTION_VERSION,
)
from parallax.domains.macro_intel.services.macro_assets_brief import build_macro_assets_brief
from parallax.domains.macro_intel.services.macro_module_catalog import MACRO_MODULE_CONCEPTS
from parallax.domains.macro_intel.services.macro_module_views import build_macro_module_views
from parallax.domains.macro_intel.services.macro_regime_engine import (
    build_macro_view_snapshot,
)
from parallax.platform.config.settings import MacroViewProjectionWorkerSettings
from parallax.platform.runtime.worker_base import WorkerBase
from parallax.platform.runtime.worker_result import WorkerResult

_MACRO_PROJECTION_CONCEPTS = tuple(dict.fromkeys((*MACRO_CORE_CONCEPTS, *MACRO_MODULE_CONCEPTS)))


class MacroViewProjectionWorker(WorkerBase):
    def __init__(
        self,
        *,
        settings: MacroViewProjectionWorkerSettings,
        db: Any,
        telemetry: Any,
        wake_waiter: Any | None = None,
        clock_ms: Callable[[], int] | None = None,
        name: str = "macro_view_projection",
    ) -> None:
        if db is None:
            raise RuntimeError("macro_view_projection_db_required")
        super().__init__(
            name=name,
            settings=settings,
            db=db,
            telemetry=telemetry,
            wake_waiter=wake_waiter,
        )
        self.clock_ms = clock_ms or _now_ms

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        with self._repository_session() as repos, repos.transaction():
            claimed = repos.macro_intel.claim_macro_projection_dirty_targets(
                projection_name="macro_view",
                projection_version=MACRO_VIEW_PROJECTION_VERSION,
                limit=self._batch_size(),
                lease_ms=self._lease_ms(),
                lease_owner=self.name,
                now_ms=now,
            )
            if not claimed:
                result = WorkerResult(
                    processed=0,
                    notes={
                        "claimed": 0,
                        "queue_depth": 0,
                        "source_rows_scanned": 0,
                        "targets_loaded": 0,
                        "rows_written": 0,
                    },
                )
            else:
                lookback_days = self._lookback_days()
                limit_per_series = self._limit_per_series()
                try:
                    with repos.transaction():
                        result = self._run_claimed_once(
                            repos,
                            claimed=claimed,
                            now=now,
                            lookback_days=lookback_days,
                            limit_per_series=limit_per_series,
                        )
                except Exception as exc:
                    repos.macro_intel.mark_macro_projection_dirty_targets_error(
                        claimed,
                        error=str(exc),
                        retry_ms=self._retry_ms(),
                        max_attempts=self._max_attempts(),
                        worker_name=self.name,
                        now_ms=now,
                    )
                    result = WorkerResult(
                        processed=0,
                        failed=1,
                        notes={
                            "claimed": len(claimed),
                            "queue_depth": 0,
                            "source_rows_scanned": 0,
                            "targets_loaded": 0,
                            "rows_written": 0,
                            "error": str(exc),
                        },
                    )
        return result

    def _run_claimed_once(
        self,
        repos: Any,
        *,
        claimed: list[dict[str, Any]],
        now: int,
        lookback_days: int,
        limit_per_series: int,
    ) -> WorkerResult:
        repos.require_transaction(operation="macro_view_projection")
        concept_keys = _claimed_concept_keys(claimed)
        refresh_result = repos.macro_intel.refresh_observation_series_rows_for_concepts(
            projection_version=MACRO_VIEW_PROJECTION_VERSION,
            now_ms=now,
            lookback_days=lookback_days,
            limit_per_series=limit_per_series,
            claimed_targets=claimed,
            concept_keys=concept_keys,
        )
        projected_rows_written = int(refresh_result.get("rows_written") or 0)
        series_status = str(refresh_result.get("status") or "")
        source_signature = str(refresh_result.get("source_signature") or "")
        if not _should_rebuild_snapshot(claimed=claimed, concept_keys=concept_keys, series_status=series_status):
            repos.macro_intel.mark_macro_projection_dirty_targets_done(claimed, now_ms=now)
            return WorkerResult(
                processed=1,
                notes={
                    "claimed": len(claimed),
                    "queue_depth": 0,
                    "source_rows_scanned": 0,
                    "targets_loaded": 0,
                    "rows_written": projected_rows_written,
                    "projected_rows_written": projected_rows_written,
                    "snapshot_rows_written": 0,
                    "series_status": series_status,
                    "source_signature": source_signature,
                    "projection_version": MACRO_VIEW_PROJECTION_VERSION,
                },
            )

        observations = repos.macro_intel.observations_for_concepts(
            concept_keys=_MACRO_PROJECTION_CONCEPTS,
            lookback_days=lookback_days,
            limit_per_series=limit_per_series,
        )
        core_observations = [
            observation
            for observation in observations
            if str(observation.get("concept_key") or "") in set(MACRO_CORE_CONCEPTS)
        ]
        snapshot = build_macro_view_snapshot(core_observations, computed_at_ms=now)
        snapshot["assets_brief_json"] = build_macro_assets_brief(snapshot=snapshot)
        snapshot["module_views_json"] = build_macro_module_views(snapshot=snapshot, observations=observations)
        snapshot_changed = repos.macro_intel.insert_snapshot(snapshot)
        snapshot_rows_written = 1 if snapshot_changed else 0
        repos.macro_intel.mark_macro_projection_dirty_targets_done(claimed, now_ms=now)
        return WorkerResult(
            processed=1,
            notes={
                "claimed": len(claimed),
                "queue_depth": 0,
                "source_rows_scanned": len(observations),
                "targets_loaded": len(_MACRO_PROJECTION_CONCEPTS),
                "rows_written": projected_rows_written + snapshot_rows_written,
                "projected_rows_written": projected_rows_written,
                "snapshot_rows_written": snapshot_rows_written,
                "series_status": series_status,
                "source_signature": source_signature,
                "projection_version": str(snapshot["projection_version"]),
                "status": str(snapshot["status"]),
                "regime": str(snapshot["regime"]),
                "history_coverage_ratio": str(
                    (snapshot.get("source_coverage_json") or {}).get("history_coverage_ratio", 0.0)
                ),
                "data_gap_count": str(len(snapshot.get("data_gaps_json") or [])),
            },
        )

    def _repository_session(self) -> Any:
        return cast(
            "Any",
            self.db.worker_session(
                self.name,
                statement_timeout_seconds=self.settings.statement_timeout_seconds,
            ),
        )

    def _batch_size(self) -> int:
        return int(self.settings.batch_size)

    def _lookback_days(self) -> int:
        return int(self.settings.lookback_days)

    def _limit_per_series(self) -> int:
        return int(self.settings.limit_per_series)

    def _lease_ms(self) -> int:
        return int(self.settings.lease_ms)

    def _retry_ms(self) -> int:
        return int(self.settings.retry_ms)

    def _max_attempts(self) -> int:
        return int(self.settings.max_attempts)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _claimed_concept_keys(claimed: list[dict[str, Any]]) -> tuple[str, ...]:
    concept_keys: list[str] = []
    for target in claimed:
        concept_key = str(target.get("concept_key") or "").strip()
        if concept_key:
            concept_keys.append(concept_key)
            continue
        if str(target.get("target_kind") or "") == "concept":
            target_id = str(target.get("target_id") or "").strip()
            if target_id:
                concept_keys.append(target_id)
            continue
        if str(target.get("target_kind") or "") == "current":
            concept_keys.extend(_MACRO_PROJECTION_CONCEPTS)
    return tuple(dict.fromkeys(concept_keys))


def _claims_current_target(claimed: list[dict[str, Any]]) -> bool:
    return any(str(target.get("target_kind") or "") == "current" for target in claimed)


def _should_rebuild_snapshot(
    *,
    claimed: list[dict[str, Any]],
    concept_keys: tuple[str, ...],
    series_status: str,
) -> bool:
    if _claims_current_target(claimed):
        return True
    if series_status == "unchanged":
        return False
    projection_concepts = set(_MACRO_PROJECTION_CONCEPTS)
    return any(concept_key in projection_concepts for concept_key in concept_keys)


__all__ = ["MacroViewProjectionWorker"]
