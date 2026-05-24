from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.equity_event_intel.services.source_reconcile import (
    build_source_reconcile_payloads,
)


class EquityEventSourceReconcileWorker(WorkerBase):
    def __init__(
        self,
        *,
        equity_settings: Any,
        wake_bus: Any | None,
        clock_ms: Callable[[], int] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.equity_settings = equity_settings
        self.wake_bus = wake_bus
        self.clock_ms = clock_ms or _now_ms

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        with self._repository_session() as repos:
            payloads = build_source_reconcile_payloads(
                settings=self.equity_settings,
                registry_lookup=repos.registry.find_us_equity_symbol,
                now_ms=now,
            )
            source_catalog = repos.equity_events.reconcile_source_catalog(
                sources=payloads.sources,
                universe_members=payloads.universe_members,
                now_ms=now,
                commit=False,
            )
            expected_events = repos.equity_events.reconcile_expected_events(
                expected_events=payloads.expected_events,
                scoped_source_ids=payloads.expected_event_source_ids,
                now_ms=now,
                commit=False,
            )
            material_expected_events = [event for event in expected_events if _is_material_reconcile(event)]
            expected_event_ids = _unique_ids([str(event["expected_event_id"]) for event in material_expected_events])
            expected_calendar_targets = _expected_event_dirty_targets(
                expected_event_ids=expected_event_ids,
                source_watermark_ms=now,
            )
            if expected_calendar_targets:
                repos.equity_projection_dirty_targets.enqueue_targets(
                    expected_calendar_targets,
                    reason="expected_event_reconciled",
                    now_ms=now,
                    commit=False,
                )
            company_ids = _unique_ids([str(company_id) for company_id in source_catalog.get("changed_company_ids", [])])
            affected_company_event_ids = repos.equity_events.company_event_ids_for_companies(company_ids=company_ids)
            affected_expected_event_ids = repos.equity_events.expected_event_ids_for_companies(company_ids=company_ids)
            metadata_targets = _company_event_dirty_targets(
                company_event_ids=affected_company_event_ids,
                source_watermark_ms=now,
            )
            metadata_targets.extend(
                _expected_event_dirty_targets(
                    expected_event_ids=[
                        expected_event_id
                        for expected_event_id in affected_expected_event_ids
                        if expected_event_id not in set(expected_event_ids)
                    ],
                    source_watermark_ms=now,
                )
            )
            if metadata_targets:
                repos.equity_projection_dirty_targets.enqueue_targets(
                    metadata_targets,
                    reason="universe_metadata_reconciled",
                    now_ms=now,
                    commit=False,
                )
            repos.conn.commit()

        sources = [dict(row) for row in source_catalog.get("sources", [])]
        count = len(sources)
        if self.wake_bus is not None:
            self.wake_bus.notify_equity_event_sources_reconciled(count=count)
        return WorkerResult(
            processed=count,
            notes={
                "sources": count,
                "universe_members": len(payloads.universe_members),
                "expected_events": len(material_expected_events),
            },
        )

    def _repository_session(self) -> Any:
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )


def _now_ms() -> int:
    return int(time.time() * 1000)


def _company_event_dirty_targets(*, company_event_ids: list[str], source_watermark_ms: int) -> list[dict[str, Any]]:
    return [
        {
            "projection_name": projection_name,
            "target_kind": "company_event",
            "target_id": company_event_id,
            "source_watermark_ms": int(source_watermark_ms),
        }
        for company_event_id in _unique_ids(company_event_ids)
        for projection_name in ("page", "timeline", "alert")
    ]


def _expected_event_dirty_targets(*, expected_event_ids: list[str], source_watermark_ms: int) -> list[dict[str, Any]]:
    return [
        {
            "projection_name": "calendar",
            "target_kind": "expected_event",
            "target_id": expected_event_id,
            "source_watermark_ms": int(source_watermark_ms),
        }
        for expected_event_id in _unique_ids(expected_event_ids)
    ]


def _unique_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _is_material_reconcile(row: Any) -> bool:
    status = str(dict(row).get("reconcile_status") or "")
    return status != "duplicate"
