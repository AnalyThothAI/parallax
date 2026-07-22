from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from parallax.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from parallax.domains.news_intel.runtime.news_projection_work import (
    PAGE_PROJECTION,
    claim_page_projection_work,
    mark_work_done,
    mark_work_error,
)
from parallax.domains.news_intel.services.news_page_projection import build_news_page_row
from parallax.platform.config.settings import NewsPageProjectionWorkerSettings
from parallax.platform.runtime.worker_base import WorkerBase
from parallax.platform.runtime.worker_result import WorkerResult


class NewsPageProjectionWorker(WorkerBase):
    settings: NewsPageProjectionWorkerSettings

    def __init__(
        self,
        *,
        settings: NewsPageProjectionWorkerSettings,
        db: Any,
        telemetry: Any,
        clock_ms: Callable[[], int] | None = None,
        name: str = "news_page_projection",
    ) -> None:
        if db is None:
            raise RuntimeError("news_page_projection_db_required")
        super().__init__(
            name=name,
            settings=settings,
            db=db,
            telemetry=telemetry,
        )
        self.clock_ms = clock_ms or _now_ms

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        claimed: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        deleted = 0
        unchanged = 0
        marked_error = 0
        story_groups_projected = 0
        story_member_items = 0
        claimed_ids: list[str] = []
        batch_size = self._batch_size()
        lease_ms = self._lease_ms()
        retry_ms = self._retry_ms()
        self._max_attempts()

        with self._repository_session() as repos, repos.transaction():
            claimed = claim_page_projection_work(
                repos,
                limit=batch_size,
                lease_ms=lease_ms,
                now_ms=now,
                lease_owner=self.name,
            )
            if not claimed:
                return WorkerResult(
                    processed=0,
                    notes=_notes(
                        claimed=0,
                        projected=0,
                        deleted=0,
                        unchanged=0,
                        marked_error=0,
                        story_groups_projected=0,
                        story_member_items=0,
                    ),
                )

            try:
                claimed_ids = _required_page_claim_news_item_ids(claimed)
                with repos.transaction():
                    payloads = repos.news_pages.load_story_projection_payloads_for_items(news_item_ids=claimed_ids)
                    story_keys: list[str] = []
                    member_item_ids: list[str] = []
                    for payload in payloads:
                        item, token_mentions, fact_candidates, current_brief, story, member_items = _projection_parts(
                            payload
                        )
                        rows.append(
                            build_news_page_row(
                                item=item,
                                token_mentions=token_mentions,
                                fact_candidates=fact_candidates,
                                story=story,
                                agent_brief=current_brief,
                                computed_at_ms=now,
                            )
                        )
                        story_keys.append(str(story["story_key"]))
                        story_groups_projected += 1
                        member_item_ids.extend(_member_news_item_ids(member_items=member_items, item=item))
                    story_member_items = len(set(member_item_ids))
            except Exception as exc:
                marked_error = mark_work_error(
                    repos,
                    claimed,
                    error=str(exc),
                    retry_ms=retry_ms,
                    now_ms=now,
                    max_attempts=self._max_attempts(),
                    worker_name=self.name,
                )
                return WorkerResult(
                    failed=len(claimed),
                    notes=_notes(
                        claimed=len(claimed),
                        projected=0,
                        deleted=0,
                        unchanged=0,
                        marked_error=marked_error,
                        story_groups_projected=0,
                        story_member_items=0,
                    ),
                )

            try:
                with repos.transaction():
                    projected_member_ids = set(member_item_ids)
                    orphaned_claim_ids = [
                        news_item_id for news_item_id in claimed_ids if news_item_id not in projected_member_ids
                    ]
                    replacement = repos.news_pages.replace_page_rows_for_story_targets(
                        news_item_ids=[
                            news_item_id for news_item_id in claimed_ids if news_item_id in projected_member_ids
                        ],
                        story_keys=story_keys,
                        rows=rows,
                    )
                    if orphaned_claim_ids:
                        orphan_replacement = repos.news_pages.replace_page_rows_for_items(
                            news_item_ids=orphaned_claim_ids,
                            rows=[],
                        )
                        replacement["deleted"] = int(replacement.get("deleted", 0)) + int(
                            orphan_replacement.get("deleted", 0)
                        )
                    deleted = int(replacement.get("deleted", 0))
                    unchanged = int(replacement.get("unchanged", 0))
            except Exception as exc:
                marked_error = mark_work_error(
                    repos,
                    claimed,
                    error=str(exc),
                    retry_ms=retry_ms,
                    now_ms=now,
                    max_attempts=self._max_attempts(),
                    worker_name=self.name,
                )
                return WorkerResult(
                    failed=len(claimed),
                    notes=_notes(
                        claimed=len(claimed),
                        projected=len(rows),
                        deleted=0,
                        unchanged=0,
                        marked_error=marked_error,
                        story_groups_projected=story_groups_projected,
                        story_member_items=story_member_items,
                    ),
                )

            mark_work_done(repos, claimed, now_ms=now)

        return WorkerResult(
            processed=len(claimed_ids),
            notes=_notes(
                claimed=len(claimed),
                projected=len(rows),
                deleted=deleted,
                unchanged=unchanged,
                marked_error=marked_error,
                story_groups_projected=story_groups_projected,
                story_member_items=story_member_items,
            ),
        )

    def _repository_session(self) -> Any:
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=self.settings.statement_timeout_seconds,
        )

    def _batch_size(self) -> int:
        return self.settings.batch_size

    def _lease_ms(self) -> int:
        return self.settings.lease_ms

    def _retry_ms(self) -> int:
        return self.settings.retry_ms

    def _max_attempts(self) -> int:
        return self.settings.max_attempts


def _projection_parts(
    payload: Mapping[str, Any],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any] | None,
    dict[str, Any],
    list[dict[str, Any]],
]:
    item = _required_mapping(payload, "item")
    return (
        item,
        _required_mapping_list(payload, "token_mentions"),
        _required_mapping_list(payload, "fact_candidates"),
        _optional_mapping(payload, "current_brief"),
        _required_mapping(payload, "story"),
        _required_mapping_list(payload, "member_items"),
    )


def _member_news_item_ids(
    *,
    member_items: list[dict[str, Any]],
    item: Mapping[str, Any],
) -> list[str]:
    member_ids = [_required_member_news_item_id(row, item=item) for row in member_items]
    if not member_ids:
        news_item_id = str(item.get("news_item_id") or "")
        suffix = f":{news_item_id}" if news_item_id else ""
        raise ValueError(f"news_page_projection_member_items_required{suffix}")
    return member_ids


def _required_member_news_item_id(row: Mapping[str, Any], *, item: Mapping[str, Any]) -> str:
    value = row.get("news_item_id")
    if not isinstance(value, str) or not value.strip():
        news_item_id = str(item.get("news_item_id") or "")
        suffix = f":{news_item_id}" if news_item_id else ""
        raise ValueError(f"news_page_projection_member_item_news_item_id_required{suffix}")
    return value.strip()


def _required_mapping(payload: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(f"news_page_projection_payload_{field_name}_required")
    return dict(value)


def _optional_mapping(payload: Mapping[str, Any], field_name: str) -> dict[str, Any] | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"news_page_projection_payload_{field_name}_invalid")
    return dict(value)


def _required_mapping_list(payload: Mapping[str, Any], field_name: str) -> list[dict[str, Any]]:
    value = payload.get(field_name)
    if isinstance(value, str) or not isinstance(value, list | tuple):
        raise ValueError(f"news_page_projection_payload_{field_name}_required")
    rows = [dict(row) for row in value if isinstance(row, Mapping)]
    if len(rows) != len(value):
        raise ValueError(f"news_page_projection_payload_{field_name}_invalid")
    return rows


def _required_page_claim_news_item_ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    seen: set[str] = set()
    news_item_ids: list[str] = []
    for row in rows:
        _require_claim_text(row, field="projection_name", expected=PAGE_PROJECTION)
        _require_claim_text(row, field="target_kind", expected="news_item")
        _require_claim_empty_window(row)
        news_item_id = _require_claim_text(row, field="target_id")
        if news_item_id in seen:
            continue
        seen.add(news_item_id)
        news_item_ids.append(news_item_id)
    return news_item_ids


def _require_claim_text(row: Mapping[str, Any], *, field: str, expected: str | None = None) -> str:
    try:
        value = row[field]
    except KeyError as exc:
        raise ValueError(f"news_page_projection_claim_{field}_required") from exc
    if not isinstance(value, str):
        raise ValueError(f"news_page_projection_claim_{field}_required")
    text = value.strip()
    if not text:
        raise ValueError(f"news_page_projection_claim_{field}_required")
    if expected is not None and text != expected:
        raise ValueError(f"news_page_projection_claim_{field}_required")
    return text


def _require_claim_empty_window(row: Mapping[str, Any]) -> None:
    try:
        value = row["window"]
    except KeyError as exc:
        raise ValueError("news_page_projection_claim_window_empty_required") from exc
    if value != "":
        raise ValueError("news_page_projection_claim_window_empty_required")


def _notes(
    *,
    claimed: int,
    projected: int,
    deleted: int,
    unchanged: int,
    marked_error: int,
    story_groups_projected: int,
    story_member_items: int,
) -> dict[str, int | str]:
    return {
        "projection_version": NEWS_PAGE_PROJECTION_VERSION,
        "claimed": int(claimed),
        "story_groups_projected": int(story_groups_projected),
        "story_member_items": int(story_member_items),
        "projected": int(projected),
        "deleted": int(deleted),
        "unchanged": int(unchanged),
        "marked_error": int(marked_error),
    }


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["NewsPageProjectionWorker"]
