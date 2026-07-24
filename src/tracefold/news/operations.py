from __future__ import annotations

from collections.abc import Mapping
from contextlib import nullcontext
from typing import Any

from tracefold.news.projection.constants import NEWS_STORY_IDENTITY_VERSION
from tracefold.news.projection.work import (
    enqueue_page_reprojection,
)

PROJECTION_CHOICES = ("all", "page")

_NEWS_ITEM_PROJECTIONS = ("page",)


def enqueue_projection_dirty_targets(
    repos: Any,
    *,
    execute: bool,
    now_ms: int,
    projection: str = "all",
    since_ms: int | None = None,
) -> dict[str, Any]:
    normalized_projection = str(projection or "all").strip().lower()
    if normalized_projection not in PROJECTION_CHOICES:
        raise ValueError(f"unsupported projection dirty target projection: {normalized_projection}")
    result: dict[str, Any] = {
        "projection": normalized_projection,
        "execute": bool(execute),
        "now_ms": int(now_ms),
        "since_ms": int(since_ms) if since_ms is not None else None,
    }

    context = repos.transaction() if execute else nullcontext()
    with context:
        result.update(
            _enqueue_news_targets(
                repos,
                execute=execute,
                now_ms=now_ms,
                projection=normalized_projection,
                since_ms=since_ms,
            )
        )
    return result


def _enqueue_news_targets(
    repos: Any,
    *,
    execute: bool,
    now_ms: int,
    projection: str,
    since_ms: int | None,
) -> dict[str, int]:
    news_item_projections = _selected_projections(projection, _NEWS_ITEM_PROJECTIONS)
    news_item_rows = (
        _fetch_news_item_rows(
            repos.conn,
            since_ms=since_ms,
        )
        if news_item_projections
        else []
    )
    page_rows = [row for row in news_item_rows if "page" in news_item_projections]
    watermarks = {str(row["news_item_id"]): _news_item_source_watermark_ms(row) for row in news_item_rows}
    enqueued_pages = (
        enqueue_page_reprojection(
            repos,
            news_item_ids=[str(row["news_item_id"]) for row in page_rows],
            source_watermark_ms_by_news_item_id=watermarks,
            reason="ops_projection_dirty_repair",
            now_ms=now_ms,
        )
        if execute and page_rows
        else 0
    )
    return {
        "news_item_ids": len(news_item_rows),
        "news_item_targets": len(page_rows),
        "news_item_targets_enqueued": int(enqueued_pages),
    }


def _selected_projections(requested: str, available: tuple[str, ...]) -> tuple[str, ...]:
    if requested == "all":
        return available
    if requested in available:
        return (requested,)
    return ()


def _news_item_source_watermark_ms(row: Mapping[str, Any]) -> int:
    try:
        value = row["source_watermark_ms"]
    except KeyError as exc:
        raise ValueError("ops_news_projection_dirty_source_watermark_required") from exc
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("ops_news_projection_dirty_source_watermark_required")
    if value <= 0:
        raise ValueError("ops_news_projection_dirty_source_watermark_required")
    return int(value)


def _fetch_news_item_rows(conn: Any, *, since_ms: int | None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"story_identity_version": NEWS_STORY_IDENTITY_VERSION}
    where_clauses = [
        "items.lifecycle_status = 'processed'",
        "items.story_key <> ''",
        "items.story_identity_version = %(story_identity_version)s",
    ]
    if since_ms is not None:
        where_clauses.append(
            """
            GREATEST(
              COALESCE(NULLIF(items.published_at_ms, 0), 0),
              COALESCE(NULLIF(items.fetched_at_ms, 0), 0)
            ) >= %(since_ms)s
            """
        )
        params["since_ms"] = int(since_ms)
    where_clause = " AND ".join(where_clauses)
    rows = conn.execute(
        f"""
        SELECT items.news_item_id,
               items.story_key,
               GREATEST(
                 COALESCE(NULLIF(items.published_at_ms, 0), 0),
                 COALESCE(NULLIF(items.fetched_at_ms, 0), 0)
               )::bigint AS source_watermark_ms,
               items.story_identity_version
          FROM news_items AS items
         WHERE {where_clause}
         ORDER BY items.news_item_id ASC
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows if row["news_item_id"] is not None]


__all__ = ["PROJECTION_CHOICES", "enqueue_projection_dirty_targets"]
