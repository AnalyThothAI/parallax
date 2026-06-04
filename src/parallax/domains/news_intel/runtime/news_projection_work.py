from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

PAGE_PROJECTION = "page"
ITEM_BRIEF_INPUT = "brief_input"
SOURCE_QUALITY = "source_quality"
SOURCE_QUALITY_REFRESH_WINDOW = "_refresh"


def enqueue_page_reprojection(
    repos: Any,
    *,
    news_item_ids: Iterable[str],
    reason: str,
    now_ms: int,
    source_watermark_ms_by_news_item_id: Mapping[str, int] | None = None,
    commit: bool = True,
) -> int:
    watermarks = dict(source_watermark_ms_by_news_item_id or {})
    valid_news_item_ids = _servable_news_item_ids(repos, news_item_ids)
    targets = [
        _news_item_target(PAGE_PROJECTION, news_item_id, watermarks=watermarks) for news_item_id in valid_news_item_ids
    ]
    return _enqueue(repos, targets, reason=reason, now_ms=now_ms, commit=commit)


def enqueue_item_brief_work(
    repos: Any,
    *,
    news_item_ids: Iterable[str],
    reason: str,
    now_ms: int,
    priority_by_news_item_id: Mapping[str, int] | None = None,
    source_watermark_ms_by_news_item_id: Mapping[str, int] | None = None,
    commit: bool = True,
) -> int:
    priorities = dict(priority_by_news_item_id or {})
    watermarks = dict(source_watermark_ms_by_news_item_id or {})
    targets: list[dict[str, Any]] = []
    for news_item_id in _servable_news_item_ids(repos, news_item_ids):
        target = _news_item_target(ITEM_BRIEF_INPUT, news_item_id, watermarks=watermarks)
        if news_item_id in priorities:
            target["priority"] = int(priorities[news_item_id])
        targets.append(target)
    return _enqueue(repos, targets, reason=reason, now_ms=now_ms, commit=commit)


def enqueue_source_quality_refresh(
    repos: Any,
    *,
    source_ids: Iterable[str],
    reason: str,
    now_ms: int,
    due_at_ms: int | None = None,
    commit: bool = True,
) -> int:
    targets = [
        {
            "projection_name": SOURCE_QUALITY,
            "target_kind": "source",
            "target_id": source_id,
            "window": SOURCE_QUALITY_REFRESH_WINDOW,
        }
        for source_id in _unique(source_ids)
    ]
    if not targets:
        return 0
    kwargs: dict[str, Any] = {}
    if due_at_ms is not None:
        kwargs["due_at_ms"] = int(due_at_ms)
    return int(
        repos.news_projection_dirty_targets.enqueue_targets(
            targets,
            reason=reason,
            now_ms=now_ms,
            commit=commit,
            **kwargs,
        )
    )


def enqueue_source_quality_window_work(
    repos: Any,
    *,
    source_windows: Iterable[tuple[str, str]],
    reason: str,
    now_ms: int,
    due_at_ms: int | None = None,
    source_watermark_ms_by_source_window: Mapping[tuple[str, str], int] | None = None,
    commit: bool = True,
) -> int:
    watermarks = dict(source_watermark_ms_by_source_window or {})
    targets = [
        {
            "projection_name": SOURCE_QUALITY,
            "target_kind": "source",
            "target_id": source_id,
            "window": window,
            "source_watermark_ms": int(watermarks.get((source_id, window), 0)),
            **({"due_at_ms": int(due_at_ms)} if due_at_ms is not None else {}),
        }
        for source_id, window in _unique_pairs(source_windows)
    ]
    if not targets:
        return 0
    kwargs: dict[str, Any] = {}
    if due_at_ms is not None:
        kwargs["due_at_ms"] = int(due_at_ms)
    return int(
        repos.news_projection_dirty_targets.enqueue_targets(
            targets,
            reason=reason,
            now_ms=now_ms,
            commit=commit,
            **kwargs,
        )
    )


def claim_page_projection_work(repos: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return _claim(repos, projection_name=PAGE_PROJECTION, **kwargs)


def claim_item_brief_work(repos: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return _claim(repos, projection_name=ITEM_BRIEF_INPUT, **kwargs)


def claim_source_quality_work(repos: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return _claim(repos, projection_name=SOURCE_QUALITY, **kwargs)


def queue_item_brief_depth(repos: Any, *, now_ms: int) -> int:
    return int(repos.news_projection_dirty_targets.queue_depth(now_ms=now_ms, projection_name=ITEM_BRIEF_INPUT))


def mark_work_done(repos: Any, targets: Iterable[Mapping[str, Any]], *, now_ms: int, commit: bool = True) -> int:
    return int(repos.news_projection_dirty_targets.mark_done(targets, now_ms=now_ms, commit=commit))


def mark_work_error(
    repos: Any,
    targets: Iterable[Mapping[str, Any]],
    *,
    error: Exception | str,
    retry_ms: int,
    now_ms: int,
    count_attempt: bool = True,
    commit: bool = True,
) -> int:
    return int(
        repos.news_projection_dirty_targets.mark_error(
            targets,
            error=str(error),
            retry_ms=retry_ms,
            now_ms=now_ms,
            count_attempt=count_attempt,
            commit=commit,
        )
    )


def terminalize_work(repos: Any, targets: Iterable[Mapping[str, Any]], **kwargs: Any) -> int:
    return int(repos.news_projection_dirty_targets.terminalize_targets(targets, **kwargs))


def page_news_item_ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return _target_ids(rows, projection_name=PAGE_PROJECTION, target_kind="news_item", require_empty_window=True)


def item_brief_news_item_ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return _target_ids(rows, projection_name=ITEM_BRIEF_INPUT, target_kind="news_item", require_empty_window=True)


def source_quality_claim_windows(
    rows: Iterable[Mapping[str, Any]],
    *,
    configured_windows: Sequence[str],
) -> list[tuple[str, str]]:
    configured = tuple(_unique(str(window).strip().lower() for window in configured_windows if str(window).strip()))
    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if str(row.get("projection_name") or "") != SOURCE_QUALITY:
            continue
        if str(row.get("target_kind") or "") != "source":
            continue
        source_id = str(row.get("target_id") or "")
        window = str(row.get("window") or "").strip().lower()
        windows = configured if window == SOURCE_QUALITY_REFRESH_WINDOW else (window,)
        for resolved_window in windows:
            key = (source_id, resolved_window)
            if source_id and resolved_window and key not in seen:
                seen.add(key)
                result.append(key)
    return result


def _claim(repos: Any, *, projection_name: str, **kwargs: Any) -> list[dict[str, Any]]:
    return list(repos.news_projection_dirty_targets.claim_due(projection_name=projection_name, **kwargs))


def _enqueue(repos: Any, targets: list[dict[str, Any]], *, reason: str, now_ms: int, commit: bool) -> int:
    if not targets:
        return 0
    return int(
        repos.news_projection_dirty_targets.enqueue_targets(
            targets,
            reason=reason,
            now_ms=now_ms,
            commit=commit,
        )
    )


def _servable_news_item_ids(repos: Any, news_item_ids: Iterable[str]) -> list[str]:
    item_ids = _unique(news_item_ids)
    if not item_ids:
        return []
    news_repo = getattr(repos, "news", None)
    servable = getattr(news_repo, "servable_news_item_ids", None)
    if not callable(servable):
        return item_ids
    return list(servable(item_ids))


def _news_item_target(
    projection_name: str,
    news_item_id: str,
    *,
    watermarks: Mapping[str, int],
) -> dict[str, Any]:
    target: dict[str, Any] = {"projection_name": projection_name, "target_kind": "news_item", "target_id": news_item_id}
    if news_item_id in watermarks:
        target["source_watermark_ms"] = int(watermarks[news_item_id])
    return target


def _target_ids(
    rows: Iterable[Mapping[str, Any]],
    *,
    projection_name: str,
    target_kind: str,
    require_empty_window: bool,
) -> list[str]:
    return _unique(
        str(row.get("target_id") or "")
        for row in rows
        if str(row.get("projection_name") or "") == projection_name
        and str(row.get("target_kind") or "") == target_kind
        and (not require_empty_window or str(row.get("window") or "") == "")
    )


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "")
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _unique_pairs(values: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []
    for source_id, window in values:
        key = (str(source_id or ""), str(window or "").strip().lower())
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result
