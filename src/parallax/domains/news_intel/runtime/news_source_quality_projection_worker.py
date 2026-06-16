from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.news_intel.runtime.news_projection_work import (
    claim_source_quality_work,
    enqueue_page_reprojection,
    enqueue_source_quality_window_work,
    mark_work_done,
    mark_work_error,
    source_quality_claim_windows,
)
from parallax.domains.news_intel.services.source_quality_projection import build_source_quality_rows
from parallax.domains.news_intel.types.source_quality_policy import window_ms_for_label


class NewsSourceQualityProjectionWorker(WorkerBase):
    def __init__(
        self,
        *,
        settings: Any,
        db: Any,
        telemetry: Any,
        wake_waiter: Any | None = None,
        wake_emitter: Any | None = None,
        clock_ms: Callable[[], int] | None = None,
        name: str = "news_source_quality_projection",
    ) -> None:
        if settings is None:
            raise RuntimeError("news_source_quality_projection_settings_required")
        if db is None:
            raise RuntimeError("news_source_quality_projection_db_required")
        super().__init__(
            name=name,
            settings=settings,
            db=db,
            telemetry=telemetry,
            wake_waiter=wake_waiter,
        )
        self.wake_emitter = wake_emitter
        self.clock_ms = clock_ms or _now_ms

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        processed = 0
        claimed: list[dict[str, Any]] = []
        marked_error = 0
        dirty_page_count = 0
        rescheduled = 0
        windows = self._windows()
        with self._repository_session() as repos, repos.transaction():
            claimed = claim_source_quality_work(
                repos,
                limit=self._batch_size(),
                lease_ms=self._lease_ms(),
                now_ms=now,
                lease_owner=self.name,
                commit=False,
            )
            if not claimed:
                return WorkerResult(
                    processed=0,
                    notes=_notes(
                        claimed=0,
                        projected=0,
                        page_dirty=0,
                        rescheduled=0,
                        marked_error=0,
                        windows=windows,
                    ),
                )
            try:
                with repos.transaction():
                    source_windows = source_quality_claim_windows(claimed, configured_windows=windows)
                    aggregate_inputs = repos.news.list_source_quality_inputs_for_targets(
                        source_windows=source_windows,
                        now_ms=now,
                    )
                    inputs_by_window: dict[str, list[dict[str, Any]]] = {}
                    for row in aggregate_inputs:
                        inputs_by_window.setdefault(str(row["window"]), []).append(dict(row))
                    rows: list[dict[str, Any]] = []
                    for window in _ordered_windows(source_windows):
                        rows.extend(
                            build_source_quality_rows(
                                aggregate_inputs=inputs_by_window.get(window, []),
                                window=window,
                                window_ms=window_ms_for_label(window),
                                computed_at_ms=now,
                            )
                        )
                    changed_source_ids = repos.news.replace_source_quality_rows(
                        rows=rows,
                        status_window=windows[0],
                        commit=False,
                    )
                    changed_item_ids = (
                        repos.news.list_news_item_ids_for_sources(source_ids=changed_source_ids)
                        if changed_source_ids
                        else []
                    )
                    dirty_page_count = enqueue_page_reprojection(
                        repos,
                        news_item_ids=changed_item_ids,
                        reason="source_quality_status_changed",
                        now_ms=now,
                        source_watermark_ms_by_news_item_id={
                            str(news_item_id): now for news_item_id in changed_item_ids
                        },
                        commit=False,
                    )
                    mark_work_done(repos, claimed, now_ms=now, commit=False)
                    future_targets = _future_source_quality_targets(aggregate_inputs, now_ms=now)
                    if future_targets:
                        rescheduled = enqueue_source_quality_window_work(
                            repos,
                            source_windows=[
                                (str(target["source_id"]), str(target["window"])) for target in future_targets
                            ],
                            reason="source_quality_window_due",
                            now_ms=now,
                            due_at_ms=min(int(target["due_at_ms"]) for target in future_targets),
                            source_watermark_ms_by_source_window={
                                (str(target["source_id"]), str(target["window"])): int(target["source_watermark_ms"])
                                for target in future_targets
                            },
                            commit=False,
                        )
                    processed = len(rows)
            except Exception as exc:
                marked_error = mark_work_error(
                    repos,
                    claimed,
                    error=str(exc),
                    retry_ms=self._retry_ms(),
                    now_ms=now,
                    commit=False,
                )
                return WorkerResult(
                    failed=len(claimed),
                    notes=_notes(
                        claimed=len(claimed),
                        projected=0,
                        page_dirty=dirty_page_count,
                        rescheduled=rescheduled,
                        marked_error=marked_error,
                        windows=windows,
                    ),
                )
        _notify_news_page_dirty(
            self.wake_emitter,
            count=dirty_page_count,
            reason="source_quality_status_changed",
        )
        return WorkerResult(
            processed=processed,
            notes=_notes(
                claimed=len(claimed),
                projected=processed,
                page_dirty=dirty_page_count,
                rescheduled=rescheduled,
                marked_error=marked_error,
                windows=windows,
            ),
        )

    def _repository_session(self) -> Any:
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=self.settings.statement_timeout_seconds,
        )

    def _windows(self) -> tuple[str, ...]:
        return tuple(str(window).strip().lower() for window in self.settings.windows)

    def _batch_size(self) -> int:
        return max(1, int(self.settings.batch_size))

    def _lease_ms(self) -> int:
        return max(1, int(self.settings.lease_ms))

    def _retry_ms(self) -> int:
        return max(1, int(self.settings.retry_ms))


def _notes(
    *,
    claimed: int,
    projected: int,
    page_dirty: int,
    rescheduled: int,
    marked_error: int,
    windows: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "claimed": int(claimed),
        "projected": int(projected),
        "page_dirty": int(page_dirty),
        "rescheduled": int(rescheduled),
        "marked_error": int(marked_error),
        "windows": windows,
    }


def _ordered_windows(source_windows: Iterable[tuple[str, str]]) -> list[str]:
    return list(dict.fromkeys(window for _source_id, window in source_windows))


def _future_source_quality_targets(rows: Iterable[Mapping[str, Any]], *, now_ms: int) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for row in rows:
        window = str(row.get("window") or "").strip().lower()
        source_id = str(row.get("source_id") or "")
        if not source_id or not window:
            continue
        window_ms = window_ms_for_label(window)
        has_items = int(row.get("item_count") or 0) > 0
        due_candidates = [int(now_ms) + max(60_000, min(window_ms // 24, 3_600_000))]
        latest_item_ms = _optional_int(row.get("latest_item_published_at_ms"))
        if latest_item_ms is not None:
            due_candidates.append(latest_item_ms + window_ms + 1)
        if not has_items:
            continue
        source_watermark_ms = _source_watermark_ms(row)
        targets.append(
            {
                "source_id": source_id,
                "window": window,
                "due_at_ms": max(int(now_ms) + 1, min(due_candidates)),
                "source_watermark_ms": source_watermark_ms,
            }
        )
    return targets


def _source_watermark_ms(row: Mapping[str, Any]) -> int:
    value = _optional_int(row.get("latest_item_published_at_ms"))
    if value is None or value <= 0:
        raise ValueError("news_source_quality_window_source_watermark_required")
    return int(value)


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _now_ms() -> int:
    return int(time.time() * 1000)


def _notify_news_page_dirty(wake_emitter: Any | None, *, count: int, reason: str) -> None:
    if count <= 0 or wake_emitter is None:
        return
    wake_emitter.notify_news_page_dirty(count=int(count), reason=str(reason))


__all__ = ["NewsSourceQualityProjectionWorker"]
