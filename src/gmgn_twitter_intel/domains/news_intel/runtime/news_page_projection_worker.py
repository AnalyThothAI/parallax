from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable, Mapping
from contextlib import nullcontext
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from gmgn_twitter_intel.domains.news_intel.services.news_page_projection import build_news_page_row


class NewsPageProjectionWorker(WorkerBase):
    def __init__(
        self,
        *,
        wake_bus: Any | None = None,
        clock_ms: Callable[[], int] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.wake_bus = wake_bus
        self.clock_ms = clock_ms or _now_ms

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        claimed: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        deleted = 0
        marked_error = 0

        with self._repository_session() as repos, _transaction(repos.conn):
            claimed = repos.news_projection_dirty_targets.claim_due(
                limit=self._batch_size(),
                lease_ms=self._lease_ms(),
                now_ms=now,
                lease_owner=self.name,
                projection_name="page",
                commit=False,
            )
            if not claimed:
                return WorkerResult(processed=0, notes=_notes(claimed=0, projected=0, deleted=0, marked_error=0))

            claimed_ids = _target_ids(claimed)
            try:
                with _transaction(repos.conn):
                    payloads = repos.news.load_items_for_page_projection(news_item_ids=claimed_ids)
                    rows_by_item_id: dict[str, dict[str, Any]] = {}
                    for payload in payloads:
                        item, token_mentions, fact_candidates, current_brief = _projection_parts(payload)
                        news_item_id = str(item["news_item_id"])
                        rows_by_item_id[news_item_id] = build_news_page_row(
                            item=item,
                            token_mentions=token_mentions,
                            fact_candidates=fact_candidates,
                            agent_brief=current_brief,
                            computed_at_ms=now,
                        )
                    rows = [
                        rows_by_item_id[news_item_id] for news_item_id in claimed_ids if news_item_id in rows_by_item_id
                    ]
            except Exception as exc:
                marked_error = repos.news_projection_dirty_targets.mark_error(
                    claimed,
                    error=str(exc),
                    retry_ms=self._retry_ms(),
                    now_ms=now,
                    commit=False,
                )
                return WorkerResult(
                    failed=len(claimed),
                    notes=_notes(claimed=len(claimed), projected=0, deleted=0, marked_error=marked_error),
                )

            try:
                with _transaction(repos.conn):
                    repos.news.replace_page_rows_for_items(news_item_ids=claimed_ids, rows=rows, commit=False)
                    deleted = len(set(claimed_ids) - {str(row["news_item_id"]) for row in rows})
            except Exception as exc:
                marked_error = repos.news_projection_dirty_targets.mark_error(
                    claimed,
                    error=str(exc),
                    retry_ms=self._retry_ms(),
                    now_ms=now,
                    commit=False,
                )
                return WorkerResult(
                    failed=len(claimed),
                    notes=_notes(claimed=len(claimed), projected=len(rows), deleted=0, marked_error=marked_error),
                )

            repos.news_projection_dirty_targets.mark_done(claimed, now_ms=now, commit=False)

        return WorkerResult(
            processed=len(_processed_keys(claimed)),
            notes=_notes(claimed=len(claimed), projected=len(rows), deleted=deleted, marked_error=marked_error),
        )

    def _repository_session(self) -> Any:
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 100)))

    def _lease_ms(self) -> int:
        return max(1, int(getattr(self.settings, "lease_ms", 120_000)))

    def _retry_ms(self) -> int:
        return max(1, int(getattr(self.settings, "retry_ms", 30_000)))


def _projection_parts(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    item = dict(payload.get("item") or payload)
    current_brief = payload.get("current_brief")
    return (
        item,
        [dict(row) for row in payload.get("token_mentions") or []],
        [dict(row) for row in payload.get("fact_candidates") or []],
        dict(current_brief) if current_brief is not None else None,
    )


def _target_ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return _unique_values(
        [
            str(row.get("target_id") or "")
            for row in rows
            if str(row.get("projection_name") or "") == "page"
            and str(row.get("target_kind") or "") == "news_item"
            and str(row.get("window") or "") == ""
        ]
    )


def _processed_keys(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    return set(_target_ids(rows))


def _unique_values(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _notes(*, claimed: int, projected: int, deleted: int, marked_error: int) -> dict[str, int | str]:
    return {
        "projection_version": NEWS_PAGE_PROJECTION_VERSION,
        "claimed": int(claimed),
        "projected": int(projected),
        "deleted": int(deleted),
        "marked_error": int(marked_error),
    }


def _transaction(conn: Any) -> Any:
    transaction = getattr(conn, "transaction", None)
    if transaction is None:
        return nullcontext()
    return transaction()


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["NewsPageProjectionWorker"]
