from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager, nullcontext
from typing import Any, cast

from parallax.domains.news_intel.runtime.news_projection_work import (
    enqueue_item_brief_work,
    enqueue_page_reprojection,
    enqueue_source_quality_refresh,
)
from parallax.domains.news_intel.services.news_item_agent_policy import (
    news_item_agent_brief_priority,
)

DOMAIN_CHOICES = ("all", "news")
PROJECTION_CHOICES = ("all", "brief_input", "page", "source_quality")

_NEWS_ITEM_PROJECTIONS = ("brief_input", "page")


def enqueue_projection_dirty_targets(
    repos: Any,
    *,
    domain: str,
    execute: bool,
    now_ms: int,
    projection: str = "all",
    since_ms: int | None = None,
) -> dict[str, Any]:
    normalized_domain = str(domain or "all").strip().lower()
    if normalized_domain not in DOMAIN_CHOICES:
        raise ValueError(f"unsupported projection dirty target domain: {normalized_domain}")
    normalized_projection = str(projection or "all").strip().lower()
    if normalized_projection not in PROJECTION_CHOICES:
        raise ValueError(f"unsupported projection dirty target projection: {normalized_projection}")
    if execute and normalized_projection in {"all", "brief_input"} and since_ms is None:
        raise ValueError("executing brief_input repair requires --since-hours to bound expensive agent work")
    include_news = normalized_domain in {"all", "news"}
    result: dict[str, Any] = {
        "domain": normalized_domain,
        "projection": normalized_projection,
        "execute": bool(execute),
        "now_ms": int(now_ms),
        "since_ms": int(since_ms) if since_ms is not None else None,
        "news": {},
    }

    context = _transaction(repos.conn) if execute else nullcontext()
    with context:
        if include_news:
            result["news"] = _enqueue_news_targets(
                repos,
                execute=execute,
                now_ms=now_ms,
                projection=normalized_projection,
                since_ms=since_ms,
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
    include_source_quality = projection in {"all", "source_quality"}
    news_item_rows = (
        _fetch_news_item_rows(
            repos.conn,
            since_ms=since_ms,
        )
        if news_item_projections
        else []
    )
    source_ids = (
        _fetch_ids(
            repos.conn,
            """
            SELECT source_id
              FROM news_sources
             ORDER BY source_id ASC
            """,
            "source_id",
        )
        if include_source_quality
        else []
    )
    page_rows = [row for row in news_item_rows if "page" in news_item_projections]
    brief_rows = [row for row in news_item_rows if "brief_input" in news_item_projections and _row_brief_eligible(row)]
    watermarks = {str(row["news_item_id"]): int(row["source_watermark_ms"] or 0) for row in news_item_rows}
    enqueued_pages = (
        enqueue_page_reprojection(
            repos,
            news_item_ids=[str(row["news_item_id"]) for row in page_rows],
            source_watermark_ms_by_news_item_id=watermarks,
            reason="ops_projection_dirty_repair",
            now_ms=now_ms,
            commit=False,
        )
        if execute and page_rows
        else 0
    )
    enqueued_briefs = (
        enqueue_item_brief_work(
            repos,
            news_item_ids=[str(row["news_item_id"]) for row in brief_rows],
            priority_by_news_item_id={str(row["news_item_id"]): _news_item_brief_priority(row) for row in brief_rows},
            source_watermark_ms_by_news_item_id=watermarks,
            reason="ops_projection_dirty_repair",
            now_ms=now_ms,
            commit=False,
        )
        if execute and brief_rows
        else 0
    )
    enqueued_source_quality = (
        enqueue_source_quality_refresh(
            repos,
            source_ids=source_ids,
            reason="ops_projection_dirty_repair",
            now_ms=now_ms,
            commit=False,
        )
        if execute and source_ids
        else 0
    )
    return {
        "news_item_ids": len(news_item_rows),
        "news_item_targets": len(page_rows) + len(brief_rows),
        "news_item_targets_enqueued": int(enqueued_pages) + int(enqueued_briefs),
        "source_ids": len(source_ids),
        "source_quality_targets": len(source_ids),
        "source_quality_targets_enqueued": int(enqueued_source_quality),
    }


def _selected_projections(requested: str, available: tuple[str, ...]) -> tuple[str, ...]:
    if requested == "all":
        return available
    if requested in available:
        return (requested,)
    return ()


def _row_brief_eligible(row: Mapping[str, Any]) -> bool:
    return str(row.get("agent_admission_status") or "").strip().lower() == "eligible"


def _news_item_brief_priority(row: Mapping[str, Any]) -> int:
    return news_item_agent_brief_priority(item=row)


def _fetch_ids(conn: Any, sql: str, column: str) -> list[str]:
    rows = conn.execute(sql).fetchall()
    return [str(row[column]) for row in rows if row[column] is not None]


def _fetch_news_item_rows(conn: Any, *, since_ms: int | None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    where_clause = ""
    if since_ms is not None:
        where_clause = "WHERE items.published_at_ms >= %(since_ms)s"
        params["since_ms"] = int(since_ms)
    rows = conn.execute(
        f"""
        SELECT items.news_item_id,
               items.published_at_ms,
               items.published_at_ms AS source_watermark_ms,
               items.agent_admission_status
          FROM news_items AS items
         {where_clause}
         ORDER BY items.news_item_id ASC
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows if row["news_item_id"] is not None]


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("projection_dirty_targets_transaction_required") from exc
    if not callable(transaction):
        raise RuntimeError("projection_dirty_targets_transaction_required")
    return cast(AbstractContextManager[Any], transaction())


__all__ = ["DOMAIN_CHOICES", "PROJECTION_CHOICES", "enqueue_projection_dirty_targets"]
