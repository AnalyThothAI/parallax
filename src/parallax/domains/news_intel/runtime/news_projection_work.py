from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

PAGE_PROJECTION = "page"
STORY_BRIEF_INPUT = "story_brief"


def enqueue_page_reprojection(
    repos: Any,
    *,
    news_item_ids: Iterable[str],
    reason: str,
    now_ms: int,
    source_watermark_ms_by_news_item_id: Mapping[str, int] | None = None,
) -> int:
    watermarks = dict(source_watermark_ms_by_news_item_id or {})
    valid_news_item_ids = _servable_news_item_ids(repos, news_item_ids)
    targets = [
        _news_item_target(PAGE_PROJECTION, news_item_id, watermarks=watermarks) for news_item_id in valid_news_item_ids
    ]
    return _enqueue(repos, targets, reason=reason, now_ms=now_ms)


def enqueue_story_brief_work(
    repos: Any,
    *,
    story_keys: Iterable[str],
    reason: str,
    now_ms: int,
    priority_by_story_key: Mapping[str, int] | None = None,
    source_watermark_ms_by_story_key: Mapping[str, int] | None = None,
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
    return _enqueue(repos, targets, reason=reason, now_ms=now_ms)


def claim_page_projection_work(repos: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return _claim(repos, projection_name=PAGE_PROJECTION, **kwargs)


def claim_story_brief_work(repos: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return _claim(repos, projection_name=STORY_BRIEF_INPUT, **kwargs)


def queue_story_brief_depth(repos: Any, *, now_ms: int) -> int:
    return int(repos.news_projection_dirty_targets.queue_depth(now_ms=now_ms, projection_name=STORY_BRIEF_INPUT))


def mark_work_done(repos: Any, targets: Iterable[Mapping[str, Any]], *, now_ms: int) -> int:
    return int(repos.news_projection_dirty_targets.mark_done(targets, now_ms=now_ms))


def mark_work_error(
    repos: Any,
    targets: Iterable[Mapping[str, Any]],
    *,
    error: Exception | str,
    retry_ms: int,
    now_ms: int,
    max_attempts: int,
    worker_name: str,
    count_attempt: bool = True,
) -> int:
    target_rows = [dict(target) for target in targets]
    if not target_rows:
        return 0
    parsed_worker_name = _required_worker_name(worker_name)
    if not count_attempt:
        return int(
            repos.news_projection_dirty_targets.mark_error(
                target_rows,
                error=str(error),
                retry_ms=retry_ms,
                now_ms=now_ms,
                count_attempt=False,
            )
        )
    retry_targets = [target for target in target_rows if _completion_attempt_count(target) < max_attempts]
    exhausted_targets = [target for target in target_rows if _completion_attempt_count(target) >= max_attempts]
    changed = 0
    if retry_targets:
        changed += int(
            repos.news_projection_dirty_targets.mark_error(
                retry_targets,
                error=str(error),
                retry_ms=retry_ms,
                now_ms=now_ms,
                count_attempt=True,
            )
        )
    if exhausted_targets:
        changed += int(
            repos.news_projection_dirty_targets.terminalize_targets(
                exhausted_targets,
                worker_name=parsed_worker_name,
                final_reason=_retry_budget_exhausted_reason(error),
                final_reason_bucket="retry_budget_exhausted",
                now_ms=now_ms,
            )
        )
    return changed


def story_brief_story_keys(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return _target_ids(
        rows,
        projection_name=STORY_BRIEF_INPUT,
        target_kind="story",
        require_empty_window=True,
        error_prefix="news_story_brief_claim",
    )


def _claim(repos: Any, *, projection_name: str, **kwargs: Any) -> list[dict[str, Any]]:
    return list(repos.news_projection_dirty_targets.claim_due(projection_name=projection_name, **kwargs))


def _enqueue(repos: Any, targets: list[dict[str, Any]], *, reason: str, now_ms: int) -> int:
    if not targets:
        return 0
    return int(
        repos.news_projection_dirty_targets.enqueue_targets(
            targets,
            reason=reason,
            now_ms=now_ms,
        )
    )


def _servable_news_item_ids(repos: Any, news_item_ids: Iterable[str]) -> list[str]:
    item_ids = _unique(news_item_ids)
    if not item_ids:
        return []
    try:
        return list(repos.news_items.servable_news_item_ids(item_ids))
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


def _required_worker_name(value: str) -> str:
    worker_name = str(value or "").strip()
    if not worker_name:
        raise ValueError("news_projection_dirty_target_worker_name_required")
    return worker_name


def _completion_attempt_count(target: Mapping[str, Any]) -> int:
    try:
        value = target["attempt_count"]
    except KeyError as exc:
        raise ValueError("news_projection_dirty_target_attempt_count_required") from exc
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("news_projection_dirty_target_attempt_count_required")
    if value < 0:
        raise ValueError("news_projection_dirty_target_attempt_count_required")
    return int(value)


def _retry_budget_exhausted_reason(error: Exception | str) -> str:
    message = str(error or "").strip()
    return f"news_projection_dirty_retry_budget_exhausted: {message}"[:2048]


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
