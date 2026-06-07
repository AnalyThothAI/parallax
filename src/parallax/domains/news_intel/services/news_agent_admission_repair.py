from __future__ import annotations

from collections import Counter
from typing import Any

from parallax.domains.news_intel.runtime.news_projection_work import (
    enqueue_item_brief_work,
    enqueue_page_reprojection,
)
from parallax.domains.news_intel.services.news_item_agent_admission import (
    NewsItemAgentAdmissionContext,
    decide_news_item_agent_admission,
)
from parallax.domains.news_intel.services.news_item_agent_policy import news_item_agent_brief_priority


def repair_news_agent_market_admission(
    *,
    repos: Any,
    since_ms: int,
    until_ms: int,
    limit: int = 500,
    dry_run: bool = True,
    now_ms: int | None = None,
) -> dict[str, Any]:
    resolved_now_ms = int(now_ms if now_ms is not None else until_ms)
    candidates = repos.news.list_agent_admission_repair_candidates(
        since_ms=int(since_ms),
        until_ms=int(until_ms),
        limit=int(limit),
    )
    counts_by_status: Counter[str] = Counter()
    counts_by_previous_reason: Counter[str] = Counter()
    would_enqueue = 0
    enqueued = 0
    updated = 0

    for candidate in candidates:
        item = dict(candidate.get("item") or {})
        previous_reason = str(item.get("agent_admission_reason") or item.get("analysis_admission_reason") or "")
        counts_by_previous_reason[previous_reason] += 1
        admission = decide_news_item_agent_admission(
            item=item,
            entities=_list_of_dicts(candidate.get("entities")),
            token_mentions=_list_of_dicts(candidate.get("token_mentions")),
            fact_candidates=_list_of_dicts(candidate.get("fact_candidates")),
            context=NewsItemAgentAdmissionContext.from_repository_context(candidate),
            now_ms=resolved_now_ms,
        )
        counts_by_status[admission.status] += 1
        if admission.eligible:
            would_enqueue += 1
        if dry_run:
            continue
        updated += repos.news.update_item_agent_admission(
            news_item_id=str(item.get("news_item_id") or ""),
            admission=admission,
            now_ms=resolved_now_ms,
            commit=False,
        )
        enqueue_page_reprojection(
            repos,
            news_item_ids=[str(item.get("news_item_id") or "")],
            reason="news_agent_market_admission_repair",
            now_ms=resolved_now_ms,
            commit=False,
        )
        if admission.eligible:
            representative_news_item_id = admission.representative_news_item_id or str(item.get("news_item_id") or "")
            enqueued += enqueue_item_brief_work(
                repos,
                news_item_ids=[representative_news_item_id],
                priority_by_news_item_id={
                    representative_news_item_id: news_item_agent_brief_priority(
                        item=item
                    )
                },
                reason="news_agent_market_admission_repair",
                now_ms=resolved_now_ms,
                commit=False,
            )

    return {
        "mode": "dry_run" if dry_run else "execute",
        "window": {"since_ms": int(since_ms), "until_ms": int(until_ms)},
        "limit": int(limit),
        "evaluated": len(candidates),
        "would_enqueue": would_enqueue,
        "enqueued": enqueued,
        "updated": updated,
        "counts_by_status": dict(sorted(counts_by_status.items())),
        "counts_by_previous_reason": dict(sorted(counts_by_previous_reason.items())),
    }


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [dict(row) for row in value if isinstance(row, dict)]


__all__ = ["repair_news_agent_market_admission"]
