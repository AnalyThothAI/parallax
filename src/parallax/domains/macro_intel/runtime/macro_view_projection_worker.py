from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any, cast

from parallax.domains.macro_intel._constants import (
    MACRO_EVIDENCE_PROJECTION_VERSION,
)
from parallax.domains.macro_intel.services.macro_concept_manifest import (
    MACRO_EVIDENCE_CONCEPTS,
)
from parallax.domains.macro_intel.services.macro_cross_asset_rules import (
    resolve_market_cutoff,
)
from parallax.domains.macro_intel.services.macro_evidence_snapshot import (
    build_macro_evidence_snapshot,
)
from parallax.platform.config.settings import MacroViewProjectionWorkerSettings
from parallax.platform.runtime.worker_base import WorkerBase
from parallax.platform.runtime.worker_result import WorkerResult

_MACRO_PROJECTION_CONCEPTS = MACRO_EVIDENCE_CONCEPTS


class MacroViewProjectionWorker(WorkerBase):
    def __init__(
        self,
        *,
        settings: MacroViewProjectionWorkerSettings,
        db: Any,
        telemetry: Any,
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
        )
        self.clock_ms = clock_ms or _now_ms
        self._last_snapshot_recheck_bucket: tuple[date, date] | None = None

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        with self._repository_session() as repos, repos.transaction():
            claimed = repos.macro_intel.claim_macro_projection_dirty_targets(
                projection_name="macro_evidence",
                projection_version=MACRO_EVIDENCE_PROJECTION_VERSION,
                limit=self._batch_size(),
                lease_ms=self._lease_ms(),
                lease_owner=self.name,
                now_ms=now,
            )
            if not claimed:
                recheck_bucket = _snapshot_recheck_bucket(now)
                if self._last_snapshot_recheck_bucket == recheck_bucket:
                    result = _idle_result()
                else:
                    try:
                        with repos.transaction():
                            result = self._run_clock_recheck(
                                repos,
                                now=now,
                                lookback_days=self._lookback_days(),
                                limit_per_series=self._limit_per_series(),
                            )
                    except Exception as exc:
                        result = WorkerResult(
                            processed=0,
                            failed=1,
                            notes={
                                "claimed": 0,
                                "queue_depth": 0,
                                "source_rows_scanned": 0,
                                "targets_loaded": 0,
                                "rows_written": 0,
                                "error": str(exc),
                                "recheck_reason": "freshness_clock",
                            },
                        )
                    else:
                        self._last_snapshot_recheck_bucket = recheck_bucket
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
                    if result.failed:
                        repos.macro_intel.mark_macro_projection_dirty_targets_error(
                            claimed,
                            error=str(result.notes.get("error") or "macro_observation_series_refresh_failed"),
                            retry_ms=self._retry_ms(),
                            max_attempts=self._max_attempts(),
                            worker_name=self.name,
                            now_ms=now,
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
                if not result.failed and int(result.notes.get("targets_loaded") or 0) > 0:
                    self._last_snapshot_recheck_bucket = _snapshot_recheck_bucket(now)
        return result

    def _run_clock_recheck(
        self,
        repos: Any,
        *,
        now: int,
        lookback_days: int,
        limit_per_series: int,
    ) -> WorkerResult:
        repos.require_transaction(operation="macro_view_projection_clock_recheck")
        observations = repos.macro_intel.observations_for_concepts(
            concept_keys=_MACRO_PROJECTION_CONCEPTS,
            lookback_days=lookback_days,
            limit_per_series=limit_per_series,
        )
        snapshot = build_macro_evidence_snapshot(observations, computed_at_ms=now)
        snapshot_changed = repos.macro_intel.insert_snapshot(snapshot)
        snapshot_rows_written = 1 if snapshot_changed else 0
        return WorkerResult(
            processed=1,
            notes={
                "claimed": 0,
                "queue_depth": 0,
                "source_rows_scanned": len(observations),
                "targets_loaded": len(_MACRO_PROJECTION_CONCEPTS),
                "rows_written": snapshot_rows_written,
                "projected_rows_written": 0,
                "snapshot_rows_written": snapshot_rows_written,
                "projection_version": str(snapshot["projection_version"]),
                "fact_watermark": str(snapshot["fact_watermark"] or ""),
                "market_cutoff": str(snapshot["market_cutoff"] or ""),
                "recheck_reason": "freshness_clock",
            },
        )

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
        current_refresh = _claims_current_target(claimed)
        refresh_result = repos.macro_intel.refresh_observation_series_rows_for_concepts(
            projection_version=MACRO_EVIDENCE_PROJECTION_VERSION,
            now_ms=now,
            lookback_days=lookback_days,
            limit_per_series=limit_per_series,
            claimed_targets=_supported_refresh_claims(claimed),
            concept_keys=concept_keys,
            prune_unrequested=current_refresh,
        )
        projected_rows_written = int(refresh_result.get("rows_written") or 0)
        series_status = str(refresh_result.get("status") or "")
        source_signature = str(refresh_result.get("source_signature") or "")
        if series_status not in {"published", "unchanged"}:
            error = str(refresh_result.get("latest_attempt_error") or "").strip()
            if not error:
                error = f"macro_observation_series_refresh_invalid_status:{series_status or 'missing'}"
            return WorkerResult(
                processed=0,
                failed=1,
                notes={
                    "claimed": len(claimed),
                    "queue_depth": 0,
                    "source_rows_scanned": int(refresh_result.get("source_rows") or 0),
                    "targets_loaded": 0,
                    "rows_written": projected_rows_written,
                    "projected_rows_written": projected_rows_written,
                    "snapshot_rows_written": 0,
                    "series_status": series_status,
                    "source_signature": source_signature,
                    "error": error,
                },
            )
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
                    "projection_version": MACRO_EVIDENCE_PROJECTION_VERSION,
                },
            )

        observations = repos.macro_intel.observations_for_concepts(
            concept_keys=_MACRO_PROJECTION_CONCEPTS,
            lookback_days=lookback_days,
            limit_per_series=limit_per_series,
        )
        snapshot = build_macro_evidence_snapshot(observations, computed_at_ms=now)
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
                "fact_watermark": str(snapshot["fact_watermark"] or ""),
                "market_cutoff": str(snapshot["market_cutoff"] or ""),
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


def _snapshot_recheck_bucket(now_ms: int) -> tuple[date, date]:
    computed_date = datetime.fromtimestamp(int(now_ms) / 1000, tz=UTC).date()
    return computed_date, resolve_market_cutoff(computed_at_ms=now_ms)


def _idle_result() -> WorkerResult:
    return WorkerResult(
        processed=0,
        notes={
            "claimed": 0,
            "queue_depth": 0,
            "source_rows_scanned": 0,
            "targets_loaded": 0,
            "rows_written": 0,
        },
    )


def _claimed_concept_keys(claimed: list[dict[str, Any]]) -> tuple[str, ...]:
    if _claims_current_target(claimed):
        return _MACRO_PROJECTION_CONCEPTS
    supported = set(_MACRO_PROJECTION_CONCEPTS)
    concept_keys: list[str] = []
    for target in claimed:
        concept_key = str(target.get("concept_key") or "").strip()
        if concept_key in supported:
            concept_keys.append(concept_key)
            continue
        if str(target.get("target_kind") or "") == "concept":
            target_id = str(target.get("target_id") or "").strip()
            if target_id in supported:
                concept_keys.append(target_id)
    return tuple(dict.fromkeys(concept_keys))


def _supported_refresh_claims(claimed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    supported = set(_MACRO_PROJECTION_CONCEPTS)
    return [
        target
        for target in claimed
        if str(target.get("target_kind") or "") != "concept"
        or str(target.get("concept_key") or target.get("target_id") or "").strip() in supported
    ]


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
