from __future__ import annotations

from typing import Any

from parallax.domains.news_intel._constants import NEWS_ITEM_BRIEF_SCHEMA_VERSION

DEFAULT_CLEANUP_LIMIT = 5000
HARD_CUT_DIRTY_REASON = "news_item_brief_schema_hard_cut"


def cleanup_news_item_brief_schema_hard_cut(
    repos: Any,
    *,
    execute: bool,
    now_ms: int,
    limit: int = DEFAULT_CLEANUP_LIMIT,
    required_schema_version: str = NEWS_ITEM_BRIEF_SCHEMA_VERSION,
) -> dict[str, Any]:
    bounded_limit = max(1, int(limit))
    candidate_ids = repos.news.list_current_brief_ids_outside_schema(
        required_schema_version=required_schema_version,
        limit=bounded_limit,
    )
    result: dict[str, Any] = {
        "execute": bool(execute),
        "required_schema_version": required_schema_version,
        "candidate_count": len(candidate_ids),
        "cleared_count": 0,
        "page_targets_enqueued": 0,
        "brief_input_targets_enqueued": 0,
        "news_item_ids": candidate_ids,
    }
    if not execute or not candidate_ids:
        return result

    cleared_ids = repos.news.clear_current_briefs_outside_schema(
        required_schema_version=required_schema_version,
        news_item_ids=candidate_ids,
        commit=False,
    )
    page_count = _enqueue_projection_targets(repos, projection_name="page", news_item_ids=cleared_ids, now_ms=now_ms)
    brief_count = _enqueue_projection_targets(
        repos,
        projection_name="brief_input",
        news_item_ids=cleared_ids,
        now_ms=now_ms,
    )
    repos.conn.commit()
    result.update(
        {
            "cleared_count": len(cleared_ids),
            "page_targets_enqueued": page_count,
            "brief_input_targets_enqueued": brief_count,
            "news_item_ids": cleared_ids,
        }
    )
    return result


def _enqueue_projection_targets(
    repos: Any,
    *,
    projection_name: str,
    news_item_ids: list[str],
    now_ms: int,
) -> int:
    rows = [
        {
            "projection_name": projection_name,
            "target_kind": "news_item",
            "target_id": news_item_id,
            "window": "",
        }
        for news_item_id in news_item_ids
    ]
    if not rows:
        return 0
    return int(
        repos.news_projection_dirty_targets.enqueue_targets(
            rows,
            reason=HARD_CUT_DIRTY_REASON,
            now_ms=now_ms,
            commit=False,
        )
    )


__all__ = ["cleanup_news_item_brief_schema_hard_cut"]
