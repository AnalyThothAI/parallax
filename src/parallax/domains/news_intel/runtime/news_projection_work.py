from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

PAGE_PROJECTION = "page"
ITEM_BRIEF_INPUT = "brief_input"
STORY_BRIEF_INPUT = "story_brief"
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
            target["priority"] = _priority_for_key(priorities, news_item_id)
        targets.append(target)
    return _enqueue(repos, targets, reason=reason, now_ms=now_ms, commit=commit)


def enqueue_story_brief_work(
    repos: Any,
    *,
    story_keys: Iterable[str],
    reason: str,
    now_ms: int,
    priority_by_story_key: Mapping[str, int] | None = None,
    source_watermark_ms_by_story_key: Mapping[str, int] | None = None,
    commit: bool = True,
) -> int:
    priorities = dict(priority_by_story_key or {})
    watermarks = dict(source_watermark_ms_by_story_key or {})
    targets: list[dict[str, Any]] = []
    for story_key in _unique(story_keys):
        target = {
            "projection_name": STORY_BRIEF_INPUT,
            "target_kind": "story",
            "target_id": story_key,
            "source_watermark_ms": _watermark_for_key(watermarks, story_key),
        }
        if story_key in priorities:
            target["priority"] = _priority_for_key(priorities, story_key)
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
    due_at = _optional_due_at_ms(due_at_ms)
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
    if due_at is not None:
        kwargs["due_at_ms"] = due_at
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
    due_at = _optional_due_at_ms(due_at_ms)
    watermarks = dict(source_watermark_ms_by_source_window or {})
    targets = [
        {
            "projection_name": SOURCE_QUALITY,
            "target_kind": "source",
            "target_id": source_id,
            "window": window,
            "source_watermark_ms": _watermark_for_key(watermarks, (source_id, window)),
            **({"due_at_ms": due_at} if due_at is not None else {}),
        }
        for source_id, window in _unique_pairs(source_windows)
    ]
    if not targets:
        return 0
    kwargs: dict[str, Any] = {}
    if due_at is not None:
        kwargs["due_at_ms"] = due_at
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


def claim_story_brief_work(repos: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return _claim(repos, projection_name=STORY_BRIEF_INPUT, **kwargs)


def claim_source_quality_work(repos: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return _claim(repos, projection_name=SOURCE_QUALITY, **kwargs)


def queue_item_brief_depth(repos: Any, *, now_ms: int) -> int:
    return int(repos.news_projection_dirty_targets.queue_depth(now_ms=now_ms, projection_name=ITEM_BRIEF_INPUT))


def queue_story_brief_depth(repos: Any, *, now_ms: int) -> int:
    return int(repos.news_projection_dirty_targets.queue_depth(now_ms=now_ms, projection_name=STORY_BRIEF_INPUT))


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


def page_news_item_ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return _target_ids(
        rows,
        projection_name=PAGE_PROJECTION,
        target_kind="news_item",
        require_empty_window=True,
        error_prefix="news_page_projection_claim",
    )


def item_brief_news_item_ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return _target_ids(
        rows,
        projection_name=ITEM_BRIEF_INPUT,
        target_kind="news_item",
        require_empty_window=True,
        error_prefix="news_item_brief_claim",
    )


def story_brief_story_keys(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return _target_ids(
        rows,
        projection_name=STORY_BRIEF_INPUT,
        target_kind="story",
        require_empty_window=True,
        error_prefix="news_story_brief_claim",
    )


def source_quality_claim_windows(
    rows: Iterable[Mapping[str, Any]],
    *,
    configured_windows: Sequence[str],
) -> list[tuple[str, str]]:
    configured = tuple(_unique(str(window).strip().lower() for window in configured_windows if str(window).strip()))
    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        _require_claim_text(
            row,
            field="projection_name",
            expected=SOURCE_QUALITY,
            error_prefix="news_source_quality_projection_claim",
        )
        _require_claim_text(
            row,
            field="target_kind",
            expected="source",
            error_prefix="news_source_quality_projection_claim",
        )
        source_id = _require_claim_text(
            row,
            field="target_id",
            error_prefix="news_source_quality_projection_claim",
        )
        window = _require_source_quality_claim_window(row)
        windows = configured if window == SOURCE_QUALITY_REFRESH_WINDOW else (window,)
        for resolved_window in windows:
            key = (source_id, resolved_window)
            if key not in seen:
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
    try:
        return list(repos.news.servable_news_item_ids(item_ids))
    except AttributeError as exc:
        raise ValueError("news repository must expose servable_news_item_ids for projection dirty targets") from exc


def _news_item_target(
    projection_name: str,
    news_item_id: str,
    *,
    watermarks: Mapping[str, int],
) -> dict[str, Any]:
    return {
        "projection_name": projection_name,
        "target_kind": "news_item",
        "target_id": news_item_id,
        "source_watermark_ms": _watermark_for_key(watermarks, news_item_id),
    }


def _watermark_for_key(watermarks: Mapping[Any, int], key: Any) -> int:
    try:
        value = watermarks[key]
    except KeyError as exc:
        raise ValueError("news_projection_dirty_target_source_watermark_required") from exc
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("news_projection_dirty_target_source_watermark_required")
    if value <= 0:
        raise ValueError("news_projection_dirty_target_source_watermark_required")
    return int(value)


def _priority_for_key(priorities: Mapping[str, int], key: str) -> int:
    value = priorities[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("news_projection_dirty_target_priority_required")
    return value


def _optional_due_at_ms(value: int | None) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("news_projection_dirty_target_due_at_ms_required")
    return value


def _target_ids(
    rows: Iterable[Mapping[str, Any]],
    *,
    projection_name: str,
    target_kind: str,
    require_empty_window: bool,
    error_prefix: str,
) -> list[str]:
    target_ids: list[str] = []
    for row in rows:
        _require_claim_text(row, field="projection_name", expected=projection_name, error_prefix=error_prefix)
        _require_claim_text(row, field="target_kind", expected=target_kind, error_prefix=error_prefix)
        if require_empty_window:
            _require_claim_empty_window(row, error_prefix=error_prefix)
        target_ids.append(_require_claim_text(row, field="target_id", error_prefix=error_prefix))
    return _unique(target_ids)


def _require_claim_text(
    row: Mapping[str, Any],
    *,
    field: str,
    error_prefix: str,
    expected: str | None = None,
) -> str:
    try:
        value = row[field]
    except KeyError as exc:
        raise ValueError(f"{error_prefix}_{field}_required") from exc
    if not isinstance(value, str):
        raise ValueError(f"{error_prefix}_{field}_required")
    text = value.strip()
    if not text:
        raise ValueError(f"{error_prefix}_{field}_required")
    if expected is not None and text != expected:
        raise ValueError(f"{error_prefix}_{field}_required")
    return text


def _require_claim_empty_window(row: Mapping[str, Any], *, error_prefix: str) -> None:
    try:
        value = row["window"]
    except KeyError as exc:
        raise ValueError(f"{error_prefix}_window_empty_required") from exc
    if value != "":
        raise ValueError(f"{error_prefix}_window_empty_required")


def _require_source_quality_claim_window(row: Mapping[str, Any]) -> str:
    window = _require_claim_text(
        row,
        field="window",
        error_prefix="news_source_quality_projection_claim",
    ).lower()
    if not window:
        raise ValueError("news_source_quality_projection_claim_window_required")
    return window


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
