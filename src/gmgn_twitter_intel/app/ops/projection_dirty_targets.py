from __future__ import annotations

from collections.abc import Iterable
from contextlib import nullcontext
from typing import Any

DOMAIN_CHOICES = ("all", "equity", "news")
PROJECTION_CHOICES = ("all", "story", "brief_input", "page", "timeline", "alert", "calendar", "source_quality")

_EQUITY_EVENT_PROJECTIONS = ("story", "brief_input", "page", "timeline", "alert")
_NEWS_ITEM_PROJECTIONS = ("story", "brief_input", "page")
_DEFAULT_SOURCE_QUALITY_WINDOWS = ("24h", "7d")


def enqueue_projection_dirty_targets(
    repos: Any,
    *,
    domain: str,
    execute: bool,
    now_ms: int,
    projection: str = "all",
    since_ms: int | None = None,
    source_quality_windows: Iterable[str] | None = None,
) -> dict[str, Any]:
    normalized_domain = str(domain or "all").strip().lower()
    if normalized_domain not in DOMAIN_CHOICES:
        raise ValueError(f"unsupported projection dirty target domain: {normalized_domain}")
    normalized_projection = str(projection or "all").strip().lower()
    if normalized_projection not in PROJECTION_CHOICES:
        raise ValueError(f"unsupported projection dirty target projection: {normalized_projection}")
    if execute and normalized_projection in {"all", "brief_input"} and since_ms is None:
        raise ValueError("executing brief_input repair requires --since-hours to bound expensive agent work")
    windows = _source_quality_windows(source_quality_windows)
    include_equity = normalized_domain in {"all", "equity"}
    include_news = normalized_domain in {"all", "news"}
    result: dict[str, Any] = {
        "domain": normalized_domain,
        "projection": normalized_projection,
        "execute": bool(execute),
        "now_ms": int(now_ms),
        "since_ms": int(since_ms) if since_ms is not None else None,
        "equity": {},
        "news": {},
    }

    context = _transaction(repos.conn) if execute else nullcontext()
    with context:
        if include_equity:
            result["equity"] = _enqueue_equity_targets(
                repos,
                execute=execute,
                now_ms=now_ms,
                projection=normalized_projection,
                since_ms=since_ms,
            )
        if include_news:
            result["news"] = _enqueue_news_targets(
                repos,
                execute=execute,
                now_ms=now_ms,
                projection=normalized_projection,
                since_ms=since_ms,
                windows=windows,
            )
    return result


def _enqueue_equity_targets(
    repos: Any,
    *,
    execute: bool,
    now_ms: int,
    projection: str,
    since_ms: int | None,
) -> dict[str, int]:
    company_event_projections = _selected_projections(projection, _EQUITY_EVENT_PROJECTIONS)
    include_expected_events = projection in {"all", "calendar"}
    company_event_rows = _fetch_id_watermarks(
        repos.conn,
        """
        SELECT company_event_id, event_time_ms AS source_watermark_ms
          FROM equity_company_events
         {where_clause}
         ORDER BY company_event_id ASC
        """,
        "company_event_id",
        since_column="event_time_ms",
        since_ms=since_ms,
    )
    expected_event_ids = (
        _fetch_ids(
            repos.conn,
            """
            SELECT expected_event_id
              FROM equity_expected_events
             ORDER BY expected_event_id ASC
            """,
            "expected_event_id",
        )
        if include_expected_events
        else []
    )
    company_event_targets = [
        {
            "projection_name": selected_projection,
            "target_kind": "company_event",
            "target_id": company_event_id,
            "source_watermark_ms": source_watermark_ms,
        }
        for company_event_id, source_watermark_ms in company_event_rows
        for selected_projection in company_event_projections
    ]
    expected_event_targets = [
        {"projection_name": "calendar", "target_kind": "expected_event", "target_id": expected_event_id}
        for expected_event_id in expected_event_ids
    ]
    enqueued_company_events = (
        repos.equity_projection_dirty_targets.enqueue_targets(
            company_event_targets,
            reason="ops_projection_dirty_repair",
            now_ms=now_ms,
            commit=False,
        )
        if execute and company_event_targets
        else 0
    )
    enqueued_expected_events = (
        repos.equity_projection_dirty_targets.enqueue_targets(
            expected_event_targets,
            reason="ops_projection_dirty_repair",
            now_ms=now_ms,
            commit=False,
        )
        if execute and expected_event_targets
        else 0
    )
    return {
        "company_event_ids": len(company_event_rows),
        "company_event_targets": len(company_event_targets),
        "company_event_targets_enqueued": int(enqueued_company_events),
        "expected_event_ids": len(expected_event_ids),
        "expected_event_targets": len(expected_event_targets),
        "expected_event_targets_enqueued": int(enqueued_expected_events),
    }


def _enqueue_news_targets(
    repos: Any,
    *,
    execute: bool,
    now_ms: int,
    projection: str,
    since_ms: int | None,
    windows: tuple[str, ...],
) -> dict[str, int]:
    news_item_projections = _selected_projections(projection, _NEWS_ITEM_PROJECTIONS)
    include_source_quality = projection in {"all", "source_quality"}
    news_item_rows = _fetch_id_watermarks(
        repos.conn,
        """
        SELECT news_item_id, published_at_ms AS source_watermark_ms
          FROM news_items
         {where_clause}
         ORDER BY news_item_id ASC
        """,
        "news_item_id",
        since_column="published_at_ms",
        since_ms=since_ms,
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
    news_item_targets = [
        {
            "projection_name": selected_projection,
            "target_kind": "news_item",
            "target_id": news_item_id,
            "source_watermark_ms": source_watermark_ms,
        }
        for news_item_id, source_watermark_ms in news_item_rows
        for selected_projection in news_item_projections
    ]
    source_quality_targets = [
        {
            "projection_name": "source_quality",
            "target_kind": "source",
            "target_id": source_id,
            "window": window,
        }
        for source_id in source_ids
        for window in windows
    ]
    enqueued_news_items = (
        repos.news_projection_dirty_targets.enqueue_targets(
            news_item_targets,
            reason="ops_projection_dirty_repair",
            now_ms=now_ms,
            commit=False,
        )
        if execute and news_item_targets
        else 0
    )
    enqueued_source_quality = (
        repos.news_projection_dirty_targets.enqueue_targets(
            source_quality_targets,
            reason="ops_projection_dirty_repair",
            now_ms=now_ms,
            commit=False,
        )
        if execute and source_quality_targets
        else 0
    )
    return {
        "news_item_ids": len(news_item_rows),
        "news_item_targets": len(news_item_targets),
        "news_item_targets_enqueued": int(enqueued_news_items),
        "source_ids": len(source_ids),
        "source_quality_targets": len(source_quality_targets),
        "source_quality_targets_enqueued": int(enqueued_source_quality),
    }


def _selected_projections(requested: str, available: tuple[str, ...]) -> tuple[str, ...]:
    if requested == "all":
        return available
    if requested in available:
        return (requested,)
    return ()


def _fetch_ids(conn: Any, sql: str, column: str) -> list[str]:
    rows = conn.execute(sql).fetchall()
    return [str(row[column]) for row in rows if row[column] is not None]


def _fetch_id_watermarks(
    conn: Any,
    sql_template: str,
    column: str,
    *,
    since_column: str,
    since_ms: int | None,
) -> list[tuple[str, int]]:
    params: dict[str, Any] = {}
    where_clause = ""
    if since_ms is not None:
        where_clause = f"WHERE {since_column} >= %(since_ms)s"
        params["since_ms"] = int(since_ms)
    rows = conn.execute(sql_template.format(where_clause=where_clause), params).fetchall()
    return [
        (str(row[column]), int(row["source_watermark_ms"] or 0))
        for row in rows
        if row[column] is not None
    ]


def _source_quality_windows(windows: Iterable[str] | None) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(window).strip().lower() for window in (windows or ()) if str(window).strip()))
    return normalized or _DEFAULT_SOURCE_QUALITY_WINDOWS


def _transaction(conn: Any) -> Any:
    transaction = getattr(conn, "transaction", None)
    if transaction is None:
        return nullcontext()
    return transaction()


__all__ = ["DOMAIN_CHOICES", "PROJECTION_CHOICES", "enqueue_projection_dirty_targets"]
