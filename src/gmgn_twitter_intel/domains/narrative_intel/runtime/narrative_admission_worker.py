from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION
from gmgn_twitter_intel.domains.narrative_intel.services.narrative_admission import NarrativeAdmissionService
from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION


class NarrativeAdmissionWorker(WorkerBase):
    SINGLE_WRITER_KEY = 2026051901

    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        wake_bus: Any | None = None,
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry)
        self.wake_bus = wake_bus
        self.admission = NarrativeAdmissionService(
            hot_rank_limit=int(getattr(settings, "hot_rank_limit", 50) or 50),
            min_rank_score=int(getattr(settings, "min_rank_score", 30) or 30),
        )

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync, now_ms=now_ms)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        stats = self._rebuild_admissions_sync(now_ms=resolved_now_ms)
        processed = int(stats.get("admissions_upserted") or 0) + int(stats.get("admissions_suppressed") or 0)
        if processed <= 0:
            return WorkerResult(skipped=1, notes={"reason": "no_frontier_changes", **stats})
        return WorkerResult(processed=processed, notes=stats)

    def _rebuild_admissions_sync(self, *, now_ms: int) -> dict[str, int]:
        windows = tuple(getattr(self.settings, "windows", ("24h",)) or ("24h",))
        scopes = tuple(getattr(self.settings, "scopes", ("matched",)) or ("matched",))
        admission_limit = max(1, int(getattr(self.settings, "admission_limit", 200) or 200))
        source_limit = max(1, int(getattr(self.settings, "source_limit", 2000) or 2000))
        stats = {
            "frontier_rows": 0,
            "source_events": 0,
            "admissions_upserted": 0,
            "admissions_suppressed": 0,
            "coverage_missing": 0,
        }
        with self._repository_session() as repos:
            for window in windows:
                for scope in scopes:
                    radar_rows = [
                        _radar_row_for_admission(row)
                        for row in repos.narratives.admitted_radar_rows(
                            window=str(window),
                            scope=str(scope),
                            limit=admission_limit,
                            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
                        )
                    ]
                    if not radar_rows:
                        stats["coverage_missing"] += 1
                        suppressed = repos.narratives.suppress_admissions_outside_frontier(
                            window=str(window),
                            scope=str(scope),
                            schema_version=NARRATIVE_SCHEMA_VERSION,
                            active_target_keys=[],
                            now_ms=now_ms,
                        )
                        stats["admissions_suppressed"] += int(suppressed.get("suppressed") or 0)
                        continue
                    existing = repos.narratives.admissions_for_window_scope(
                        window=str(window),
                        scope=str(scope),
                        schema_version=NARRATIVE_SCHEMA_VERSION,
                        limit=admission_limit,
                    )
                    decisions = self.admission.reconcile_from_radar_rows(
                        radar_rows,
                        existing_admissions=existing,
                        window=str(window),
                        scope=str(scope),
                        schema_version=NARRATIVE_SCHEMA_VERSION,
                        now_ms=now_ms,
                    )
                    upsert_rows: list[dict[str, Any]] = []
                    active_keys: list[tuple[str, str]] = []
                    for decision in decisions:
                        payload = asdict(decision)
                        if decision.status == "admitted":
                            projection_computed_at_ms = decision.projection_computed_at_ms or now_ms
                            source_end_ms = projection_computed_at_ms
                            source_start_ms = max(0, int(source_end_ms) - _window_ms(str(window)))
                            source_set = repos.narratives.source_set_for_admission(
                                target_type=decision.target_type,
                                target_id=decision.target_id,
                                since_ms=source_start_ms,
                                until_ms=int(source_end_ms),
                                watched_only=str(scope) == "matched",
                                limit=source_limit,
                            )
                            payload.update(source_set)
                            payload["projection_computed_at_ms"] = projection_computed_at_ms
                            payload["source_window_start_ms"] = source_start_ms
                            payload["source_window_end_ms"] = source_end_ms
                            payload["admission_generation"] = f"{window}:{scope}:{source_end_ms}"
                            active_keys.append((decision.target_type, decision.target_id))
                            stats["source_events"] += int(source_set.get("source_event_count") or 0)
                        upsert_rows.append(payload)
                    upserted = repos.narratives.upsert_admissions(upsert_rows, now_ms=now_ms, limit=admission_limit)
                    suppressed = repos.narratives.suppress_admissions_outside_frontier(
                        window=str(window),
                        scope=str(scope),
                        schema_version=NARRATIVE_SCHEMA_VERSION,
                        active_target_keys=active_keys,
                        now_ms=now_ms,
                    )
                    stats["frontier_rows"] += len(radar_rows)
                    stats["admissions_upserted"] += int(upserted.get("upserted") or 0)
                    stats["admissions_suppressed"] += int(suppressed.get("suppressed") or 0)
        return stats

    @contextmanager
    def _repository_session(self) -> Iterator[Any]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            yield repos


def _now_ms() -> int:
    return int(time.time() * 1000)


def _window_ms(window: str) -> int:
    return {"5m": 300_000, "1h": 3_600_000, "4h": 14_400_000, "24h": 86_400_000}.get(window, 86_400_000)


def _radar_row_for_admission(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    source_event_ids = normalized.get("source_event_ids") or normalized.get("source_event_ids_json") or []
    normalized["source_event_ids"] = [str(event_id) for event_id in source_event_ids if str(event_id)]
    return normalized
