from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

PAGE_PROJECTION = "page"


def enqueue_page_reprojection(
    repos: Any,
    *,
    news_item_ids: Iterable[str],
    reason: str,
    now_ms: int,
    source_watermark_ms_by_news_item_id: Mapping[str, int] | None = None,
) -> int:
    watermarks = dict(source_watermark_ms_by_news_item_id or {})
    item_ids = _unique(news_item_ids)
    if not item_ids:
        return 0
    valid_news_item_ids = list(repos.news_items.servable_news_item_ids(item_ids))
    targets = [
        _news_item_target(PAGE_PROJECTION, news_item_id, watermarks=watermarks) for news_item_id in valid_news_item_ids
    ]
    return _enqueue(repos, targets, reason=reason, now_ms=now_ms)


def claim_page_projection_work(repos: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return _claim(repos, projection_name=PAGE_PROJECTION, **kwargs)


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
