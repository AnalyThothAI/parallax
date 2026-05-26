from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable, Mapping
from contextlib import nullcontext
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.news_intel.services.source_quality_projection import build_source_quality_rows
from gmgn_twitter_intel.domains.news_intel.types.source_quality_policy import window_ms_for_label


class NewsSourceQualityProjectionWorker(WorkerBase):
    def __init__(
        self,
        *,
        wake_bus: Any | None = None,
        clock_ms: Callable[[], int] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.wake_bus = wake_bus
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
        with self._repository_session() as repos, _transaction(repos.conn):
            claimed = repos.news_projection_dirty_targets.claim_due(
                limit=self._batch_size(),
                lease_ms=self._lease_ms(),
                now_ms=now,
                lease_owner=self.name,
                projection_name="source_quality",
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
                with _transaction(repos.conn):
                    source_windows = _source_windows(claimed)
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
                    page_targets = _page_dirty_targets(changed_item_ids)
                    if page_targets:
                        dirty_page_count = int(
                            repos.news_projection_dirty_targets.enqueue_targets(
                                page_targets,
                                reason="source_quality_status_changed",
                                now_ms=now,
                                commit=False,
                            )
                        )
                    repos.news_projection_dirty_targets.mark_done(claimed, now_ms=now, commit=False)
                    future_targets = _future_source_quality_targets(aggregate_inputs, now_ms=now)
                    if future_targets:
                        rescheduled = int(
                            repos.news_projection_dirty_targets.enqueue_targets(
                                future_targets,
                                reason="source_quality_window_due",
                                now_ms=now,
                                due_at_ms=min(int(target["due_at_ms"]) for target in future_targets),
                                commit=False,
                            )
                        )
                    processed = len(rows)
            except Exception as exc:
                marked_error = repos.news_projection_dirty_targets.mark_error(
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
            self.wake_bus,
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
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )

    def _windows(self) -> tuple[str, ...]:
        windows = tuple(str(window).strip().lower() for window in getattr(self.settings, "windows", ("24h", "7d")))
        return tuple(window for window in windows if window) or ("24h", "7d")

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 100)))

    def _lease_ms(self) -> int:
        return max(1, int(getattr(self.settings, "lease_ms", 120_000)))

    def _retry_ms(self) -> int:
        return max(1, int(getattr(self.settings, "retry_ms", 30_000)))


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


def _transaction(conn: Any) -> Any:
    transaction = getattr(conn, "transaction", None)
    if transaction is None:
        return nullcontext()
    return transaction()


def _source_windows(rows: Iterable[Mapping[str, Any]]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if str(row.get("projection_name") or "") != "source_quality":
            continue
        if str(row.get("target_kind") or "") != "source":
            continue
        source_id = str(row.get("target_id") or "")
        window = str(row.get("window") or "").strip().lower()
        key = (source_id, window)
        if not source_id or not window or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _ordered_windows(source_windows: Iterable[tuple[str, str]]) -> list[str]:
    return list(dict.fromkeys(window for _source_id, window in source_windows))


def _page_dirty_targets(news_item_ids: Iterable[str]) -> list[dict[str, Any]]:
    return [
        {"projection_name": "page", "target_kind": "news_item", "target_id": news_item_id}
        for news_item_id in dict.fromkeys(str(item) for item in news_item_ids if str(item))
    ]


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
            due_candidates = [int(now_ms) + window_ms]
        targets.append(
            {
                "projection_name": "source_quality",
                "target_kind": "source",
                "target_id": source_id,
                "window": window,
                "due_at_ms": max(int(now_ms) + 1, min(due_candidates)),
                "source_watermark_ms": int(row.get("computed_at_ms") or now_ms),
            }
        )
    return targets


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _now_ms() -> int:
    return int(time.time() * 1000)


def _notify_news_page_dirty(wake_bus: Any | None, *, count: int, reason: str) -> None:
    if count <= 0 or wake_bus is None:
        return
    notify = getattr(wake_bus, "notify_news_page_dirty", None)
    if notify is None:
        return
    notify(count=int(count), reason=str(reason))


__all__ = ["NewsSourceQualityProjectionWorker"]
