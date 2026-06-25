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
from parallax.domains.news_intel.runtime.news_runtime_settings import positive_worker_setting_int
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
        batch_size = self._batch_size()
        lease_ms = self._lease_ms()
        retry_ms = self._retry_ms()
        self._max_attempts()
        with self._repository_session() as repos, repos.transaction():
            claimed = claim_source_quality_work(
                repos,
                limit=batch_size,
                lease_ms=lease_ms,
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
                    source_watermarks = _source_watermark_ms_by_source(
                        aggregate_inputs,
                        status_window=windows[0],
                    )
                    changed_item_watermarks = _page_dirty_watermarks_for_changed_sources(
                        repos.news,
                        changed_source_ids=changed_source_ids,
                        source_watermark_ms_by_source=source_watermarks,
                    )
                    dirty_page_count = enqueue_page_reprojection(
                        repos,
                        news_item_ids=changed_item_watermarks,
                        reason="source_quality_status_changed",
                        now_ms=now,
                        source_watermark_ms_by_news_item_id=changed_item_watermarks,
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
                    retry_ms=retry_ms,
                    now_ms=now,
                    max_attempts=self._max_attempts(),
                    worker_name=self.name,
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
        return positive_worker_setting_int(self.settings, "batch_size", worker_name=self.name)

    def _lease_ms(self) -> int:
        return positive_worker_setting_int(self.settings, "lease_ms", worker_name=self.name)

    def _retry_ms(self) -> int:
        return positive_worker_setting_int(self.settings, "retry_ms", worker_name=self.name)

    def _max_attempts(self) -> int:
        return positive_worker_setting_int(self.settings, "max_attempts", worker_name=self.name)


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
        window = _required_future_target_text(row, "window").lower()
        source_id = _required_future_target_text(row, "source_id")
        window_ms = window_ms_for_label(window)
        has_items = _required_future_target_item_count(row) > 0
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


def _source_watermark_ms_by_source(
    rows: Iterable[Mapping[str, Any]],
    *,
    status_window: str,
) -> dict[str, int]:
    normalized_status_window = str(status_window).strip().lower()
    watermarks: dict[str, int] = {}
    for row in rows:
        window = _required_future_target_text(row, "window").lower()
        if window != normalized_status_window:
            continue
        source_id = _required_future_target_text(row, "source_id")
        watermark = _source_watermark_ms(row)
        watermarks[source_id] = max(watermarks.get(source_id, 0), watermark)
    return watermarks


def _page_dirty_watermarks_for_changed_sources(
    news_repo: Any,
    *,
    changed_source_ids: Iterable[str],
    source_watermark_ms_by_source: Mapping[str, int],
) -> dict[str, int]:
    watermarks: dict[str, int] = {}
    for source_id in dict.fromkeys(str(source_id) for source_id in changed_source_ids if str(source_id)):
        source_watermark_ms = source_watermark_ms_by_source.get(source_id)
        if source_watermark_ms is None or source_watermark_ms <= 0:
            raise ValueError("news_source_quality_page_dirty_source_watermark_required")
        item_ids = news_repo.list_news_item_ids_for_sources(source_ids=[source_id])
        for item_id in item_ids:
            news_item_id = str(item_id)
            if news_item_id:
                watermarks[news_item_id] = max(watermarks.get(news_item_id, 0), int(source_watermark_ms))
    return watermarks


def _required_future_target_text(row: Mapping[str, Any], field_name: str) -> str:
    try:
        value = row[field_name]
    except KeyError as exc:
        raise ValueError(f"news_source_quality_future_target_{field_name}_required") from exc
    if not isinstance(value, str):
        raise ValueError(f"news_source_quality_future_target_{field_name}_required")
    text = value.strip()
    if not text:
        raise ValueError(f"news_source_quality_future_target_{field_name}_required")
    return text


def _required_future_target_item_count(row: Mapping[str, Any]) -> int:
    try:
        value = row["item_count"]
    except KeyError as exc:
        raise ValueError("news_source_quality_future_target_item_count_required") from exc
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("news_source_quality_future_target_item_count_required")
    if value < 0:
        raise ValueError("news_source_quality_future_target_item_count_required")
    return int(value)


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
