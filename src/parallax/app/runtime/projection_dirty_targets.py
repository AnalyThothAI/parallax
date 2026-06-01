from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from contextlib import nullcontext
from typing import Any

from parallax.domains.news_intel.services.news_item_agent_policy import (
    news_item_agent_brief_eligibility,
    news_item_agent_brief_priority,
)

DOMAIN_CHOICES = ("all", "news")
PROJECTION_CHOICES = ("all", "brief_input", "page", "source_quality")

_NEWS_ITEM_PROJECTIONS = ("brief_input", "page")
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
                windows=windows,
            )
    return result


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
    news_item_rows = _fetch_news_item_rows(
        repos.conn,
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
        _news_item_dirty_target(
            projection_name=selected_projection,
            row=row,
        )
        for row in news_item_rows
        for selected_projection in news_item_projections
        if selected_projection != "brief_input" or _row_brief_eligible(row, now_ms=now_ms)
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


def _news_item_dirty_target(*, projection_name: str, row: Mapping[str, Any]) -> dict[str, Any]:
    target = {
        "projection_name": projection_name,
        "target_kind": "news_item",
        "target_id": str(row["news_item_id"]),
        "source_watermark_ms": int(row["source_watermark_ms"] or 0),
    }
    if projection_name == "brief_input":
        target["priority"] = news_item_agent_brief_priority(
            item=row,
            token_mentions=_json_list(row.get("token_mentions_json")),
            fact_candidates=_json_list(row.get("fact_candidates_json")),
            context_items=_json_list(row.get("context_items_json")),
        )
    return target


def _row_brief_eligible(row: Mapping[str, Any], *, now_ms: int) -> bool:
    return news_item_agent_brief_eligibility(
        item=row,
        token_mentions=_json_list(row.get("token_mentions_json")),
        fact_candidates=_json_list(row.get("fact_candidates_json")),
        context_items=_json_list(row.get("context_items_json")),
        now_ms=now_ms,
    ).eligible


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
               items.lifecycle_status,
               items.content_class,
               items.content_classification_json,
               items.provider_signal_json,
               sources.provider_type,
               COALESCE(mentions.token_mentions_json, '[]'::jsonb) AS token_mentions_json,
               COALESCE(facts.fact_candidates_json, '[]'::jsonb) AS fact_candidates_json,
               COALESCE(context_items.context_items_json, '[]'::jsonb) AS context_items_json
          FROM news_items AS items
          JOIN news_sources AS sources ON sources.source_id = items.source_id
          LEFT JOIN LATERAL (
            SELECT jsonb_agg(to_jsonb(mentions.*) ORDER BY mentions.mention_id) AS token_mentions_json
              FROM news_token_mentions AS mentions
             WHERE mentions.news_item_id = items.news_item_id
          ) AS mentions ON true
          LEFT JOIN LATERAL (
            SELECT jsonb_agg(to_jsonb(facts.*) ORDER BY facts.fact_candidate_id) AS fact_candidates_json
              FROM news_fact_candidates AS facts
             WHERE facts.news_item_id = items.news_item_id
          ) AS facts ON true
          LEFT JOIN LATERAL (
            SELECT jsonb_agg(to_jsonb(context_items.*) ORDER BY context_items.context_item_id) AS context_items_json
              FROM news_context_items AS context_items
             WHERE context_items.parent_news_item_id = items.news_item_id
          ) AS context_items ON true
         {where_clause}
         ORDER BY items.news_item_id ASC
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows if row["news_item_id"] is not None]


def _json_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [dict(row) for row in parsed if isinstance(row, Mapping)]
    return []


def _source_quality_windows(windows: Iterable[str] | None) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(window).strip().lower() for window in (windows or ()) if str(window).strip()))
    return normalized or _DEFAULT_SOURCE_QUALITY_WINDOWS


def _transaction(conn: Any) -> Any:
    transaction = getattr(conn, "transaction", None)
    if transaction is None:
        return nullcontext()
    return transaction()


__all__ = ["DOMAIN_CHOICES", "PROJECTION_CHOICES", "enqueue_projection_dirty_targets"]
