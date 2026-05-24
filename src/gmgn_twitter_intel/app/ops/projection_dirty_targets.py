from __future__ import annotations

from collections.abc import Iterable
from contextlib import nullcontext
from typing import Any

DOMAIN_CHOICES = ("all", "equity", "news")

_EQUITY_EVENT_PROJECTIONS = ("story", "page", "timeline", "alert")
_NEWS_ITEM_PROJECTIONS = ("story", "page")
_DEFAULT_SOURCE_QUALITY_WINDOWS = ("24h", "7d")


def enqueue_projection_dirty_targets(
    repos: Any,
    *,
    domain: str,
    execute: bool,
    now_ms: int,
    source_quality_windows: Iterable[str] | None = None,
) -> dict[str, Any]:
    normalized_domain = str(domain or "all").strip().lower()
    if normalized_domain not in DOMAIN_CHOICES:
        raise ValueError(f"unsupported projection dirty target domain: {normalized_domain}")
    windows = _source_quality_windows(source_quality_windows)
    include_equity = normalized_domain in {"all", "equity"}
    include_news = normalized_domain in {"all", "news"}
    result: dict[str, Any] = {
        "domain": normalized_domain,
        "execute": bool(execute),
        "now_ms": int(now_ms),
        "equity": {},
        "news": {},
    }

    context = _transaction(repos.conn) if execute else nullcontext()
    with context:
        if include_equity:
            result["equity"] = _enqueue_equity_targets(repos, execute=execute, now_ms=now_ms)
        if include_news:
            result["news"] = _enqueue_news_targets(repos, execute=execute, now_ms=now_ms, windows=windows)
    return result


def _enqueue_equity_targets(repos: Any, *, execute: bool, now_ms: int) -> dict[str, int]:
    company_event_ids = _fetch_ids(
        repos.conn,
        """
        SELECT company_event_id
          FROM equity_company_events
         ORDER BY company_event_id ASC
        """,
        "company_event_id",
    )
    expected_event_ids = _fetch_ids(
        repos.conn,
        """
        SELECT expected_event_id
          FROM equity_expected_events
         ORDER BY expected_event_id ASC
        """,
        "expected_event_id",
    )
    company_event_targets = [
        {"projection_name": projection, "target_kind": "company_event", "target_id": company_event_id}
        for company_event_id in company_event_ids
        for projection in _EQUITY_EVENT_PROJECTIONS
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
        "company_event_ids": len(company_event_ids),
        "company_event_targets": len(company_event_targets),
        "company_event_targets_enqueued": int(enqueued_company_events),
        "expected_event_ids": len(expected_event_ids),
        "expected_event_targets": len(expected_event_targets),
        "expected_event_targets_enqueued": int(enqueued_expected_events),
    }


def _enqueue_news_targets(repos: Any, *, execute: bool, now_ms: int, windows: tuple[str, ...]) -> dict[str, int]:
    news_item_ids = _fetch_ids(
        repos.conn,
        """
        SELECT news_item_id
          FROM news_items
         ORDER BY news_item_id ASC
        """,
        "news_item_id",
    )
    source_ids = _fetch_ids(
        repos.conn,
        """
        SELECT source_id
          FROM news_sources
         ORDER BY source_id ASC
        """,
        "source_id",
    )
    news_item_targets = [
        {"projection_name": projection, "target_kind": "news_item", "target_id": news_item_id}
        for news_item_id in news_item_ids
        for projection in _NEWS_ITEM_PROJECTIONS
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
        "news_item_ids": len(news_item_ids),
        "news_item_targets": len(news_item_targets),
        "news_item_targets_enqueued": int(enqueued_news_items),
        "source_ids": len(source_ids),
        "source_quality_targets": len(source_quality_targets),
        "source_quality_targets_enqueued": int(enqueued_source_quality),
    }


def _fetch_ids(conn: Any, sql: str, column: str) -> list[str]:
    rows = conn.execute(sql).fetchall()
    return [str(row[column]) for row in rows if row[column] is not None]


def _source_quality_windows(windows: Iterable[str] | None) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(window).strip().lower() for window in (windows or ()) if str(window).strip()))
    return normalized or _DEFAULT_SOURCE_QUALITY_WINDOWS


def _transaction(conn: Any) -> Any:
    transaction = getattr(conn, "transaction", None)
    if transaction is None:
        return nullcontext()
    return transaction()


__all__ = ["DOMAIN_CHOICES", "enqueue_projection_dirty_targets"]
