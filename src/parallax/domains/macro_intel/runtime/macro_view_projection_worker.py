from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.macro_intel._constants import (
    MACRO_CORE_CONCEPTS,
    MACRO_VIEW_PROJECTION_VERSION,
)
from parallax.domains.macro_intel.services.macro_regime_engine import (
    build_macro_view_snapshot,
)

if TYPE_CHECKING:
    from parallax.app.runtime.repository_session import RepositorySession


class MacroViewProjectionWorker(WorkerBase):
    def __init__(
        self,
        *,
        settings: Any,
        db: Any,
        telemetry: Any,
        wake_waiter: Any | None = None,
        wake_emitter: Any | None = None,
        clock_ms: Callable[[], int] | None = None,
        name: str = "macro_view_projection",
    ) -> None:
        if settings is None:
            raise RuntimeError("macro_view_projection_settings_required")
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
        self.wake_emitter = wake_emitter

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        wake_payload: dict[str, str] | None = None
        with self._repository_session() as repos, repos.transaction():
            claimed = repos.macro_intel.claim_macro_projection_dirty_targets(
                projection_name="macro_view",
                projection_version=MACRO_VIEW_PROJECTION_VERSION,
                limit=self._batch_size(),
                lease_ms=self._lease_ms(),
                lease_owner=self.name,
                now_ms=now,
                commit=False,
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
                try:
                    with repos.transaction():
                        result, wake_payload = self._run_claimed_once(repos, claimed=claimed, now=now)
                except Exception as exc:
                    repos.macro_intel.mark_macro_projection_dirty_targets_error(
                        claimed,
                        error=str(exc),
                        retry_ms=self._retry_ms(),
                        now_ms=now,
                        commit=False,
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
        if wake_payload is not None and self.wake_emitter is not None:
            self.wake_emitter.notify_macro_view_snapshot_updated(**wake_payload)
        return result

    def _run_claimed_once(
        self, repos: RepositorySession, *, claimed: list[dict[str, Any]], now: int
    ) -> tuple[WorkerResult, dict[str, str] | None]:
        repos.require_transaction(operation="macro_view_projection")
        concept_keys = _claimed_concept_keys(claimed)
        refresh_result = repos.macro_intel.refresh_observation_series_rows_for_concepts(
            projection_version=MACRO_VIEW_PROJECTION_VERSION,
            now_ms=now,
            lookback_days=self._lookback_days(),
            limit_per_series=self._limit_per_series(),
            claimed_targets=claimed,
            concept_keys=concept_keys,
        )
        projected_rows_written = int(refresh_result.get("rows_written") or 0)
        series_status = str(refresh_result.get("status") or "")
        source_signature = str(refresh_result.get("source_signature") or "")
        if series_status == "unchanged" and not _claims_current_target(claimed):
            repos.macro_intel.mark_macro_projection_dirty_targets_done(claimed, now_ms=now, commit=False)
            return (
                WorkerResult(
                    processed=1,
                    notes={
                        "claimed": len(claimed),
                        "queue_depth": 0,
                        "source_rows_scanned": 0,
                        "targets_loaded": 0,
                        "rows_written": 0,
                        "projected_rows_written": 0,
                        "snapshot_rows_written": 0,
                        "series_status": series_status,
                        "source_signature": source_signature,
                        "projection_version": MACRO_VIEW_PROJECTION_VERSION,
                    },
                ),
                None,
            )

        observations = repos.macro_intel.observations_for_concepts(
            concept_keys=MACRO_CORE_CONCEPTS,
            lookback_days=self._lookback_days(),
            limit_per_series=self._limit_per_series(),
        )
        snapshot = build_macro_view_snapshot(observations, computed_at_ms=now)
        snapshot_changed = repos.macro_intel.insert_snapshot(snapshot)
        snapshot_rows_written = 1 if snapshot_changed else 0
        repos.macro_intel.mark_macro_projection_dirty_targets_done(claimed, now_ms=now, commit=False)
        wake_payload = (
            {
                "projection_version": str(snapshot["projection_version"]),
                "status": str(snapshot["status"]),
                "regime": str(snapshot["regime"]),
            }
            if snapshot_changed
            else None
        )
        return (
            WorkerResult(
                processed=1,
                notes={
                    "claimed": len(claimed),
                    "queue_depth": 0,
                    "source_rows_scanned": len(observations),
                    "targets_loaded": len(MACRO_CORE_CONCEPTS),
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
            ),
            wake_payload,
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
        return max(1, int(self.settings.batch_size))

    def _lookback_days(self) -> int:
        return max(1, int(self.settings.lookback_days))

    def _limit_per_series(self) -> int:
        return max(1, int(self.settings.limit_per_series))

    def _lease_ms(self) -> int:
        return max(1, int(self.settings.lease_ms))

    def _retry_ms(self) -> int:
        return max(1, int(self.settings.retry_ms))


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
            concept_keys.extend(MACRO_CORE_CONCEPTS)
    return tuple(dict.fromkeys(concept_keys))


def _claims_current_target(claimed: list[dict[str, Any]]) -> bool:
    return any(str(target.get("target_kind") or "") == "current" for target in claimed)


__all__ = ["MacroViewProjectionWorker"]
