from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_brief_worker import (
    EquityEventBriefWorker,
)
from gmgn_twitter_intel.domains.equity_event_intel.types import EQUITY_EVENT_BRIEF_LANE
from gmgn_twitter_intel.platform.agent_execution import (
    AgentCapacityReservation,
    AgentExecutionError,
    AgentExecutionErrorClass,
)

NOW_MS = 1_779_000_000_000


def test_worker_capacity_denied_does_not_claim_dirty_target_or_write_ledger() -> None:
    asyncio.run(_test_worker_capacity_denied_does_not_claim_dirty_target_or_write_ledger())


async def _test_worker_capacity_denied_does_not_claim_dirty_target_or_write_ledger() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(
        reservation=AgentCapacityReservation(
            lane=EQUITY_EVENT_BRIEF_LANE,
            acquired=False,
            reason=AgentExecutionErrorClass.CAPACITY_DENIED,
        )
    )
    worker = EquityEventBriefWorker(
        name="equity_event_brief",
        settings=SimpleNamespace(
            batch_size=5,
            max_attempts=3,
            backpressure_cooldown_ms=60_000,
            statement_timeout_seconds=30,
        ),
        db=db,
        telemetry=object(),
        provider=provider,
        clock_ms=lambda: NOW_MS,
    )

    result = await worker.run_once()

    assert provider.reserve_calls == [EQUITY_EVENT_BRIEF_LANE]
    assert provider.reserve_rate_units == [1]
    assert provider.execution_calls == 0
    assert db.dirty.claim_calls == []
    assert db.equity_events.loaded_event_ids == []
    assert db.equity_events.runs == []
    assert db.equity_events.briefs == []
    assert db.equity_events.brief_states == []
    assert db.dirty.done == []
    assert db.dirty.errors == []
    assert result.processed == 0
    assert result.failed == 0
    assert result.skipped == 1
    assert result.notes["claimed"] == 0
    assert result.notes["backpressure"] == 1
    assert result.notes["backpressure_capacity_denied"] == 1


def test_worker_execute_no_start_rate_limit_does_not_write_business_ledger() -> None:
    asyncio.run(_test_worker_execute_no_start_rate_limit_does_not_write_business_ledger())


async def _test_worker_execute_no_start_rate_limit_does_not_write_business_ledger() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(
        reservation=AgentCapacityReservation(lane=EQUITY_EVENT_BRIEF_LANE, acquired=True),
        brief_error=AgentExecutionError(
            AgentExecutionErrorClass.RATE_LIMITED,
            "rpm denied before provider start",
            execution_started=False,
        ),
    )
    worker = EquityEventBriefWorker(
        name="equity_event_brief",
        settings=SimpleNamespace(
            batch_size=5,
            max_attempts=3,
            backpressure_cooldown_ms=60_000,
            statement_timeout_seconds=30,
        ),
        db=db,
        telemetry=object(),
        provider=provider,
        clock_ms=lambda: NOW_MS,
    )

    result = await worker.run_once()

    assert provider.execution_calls == 1
    assert db.equity_events.runs == []
    assert db.equity_events.briefs == []
    assert db.equity_events.brief_states == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[-1]["count_attempt"] is False
    assert result.processed == 0
    assert result.failed == 0
    assert result.skipped == 1
    assert result.notes["backpressure"] == 1
    assert result.notes["backpressure_rate_limited"] == 1


def test_worker_request_audit_error_requeues_without_business_ledger_or_current_write() -> None:
    asyncio.run(_test_worker_request_audit_error_requeues_without_business_ledger_or_current_write())


async def _test_worker_request_audit_error_requeues_without_business_ledger_or_current_write() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(
        reservation=AgentCapacityReservation(lane=EQUITY_EVENT_BRIEF_LANE, acquired=True),
        audit_error=RuntimeError("audit exploded"),
    )
    worker = EquityEventBriefWorker(
        name="equity_event_brief",
        settings=SimpleNamespace(
            batch_size=5,
            max_attempts=3,
            backpressure_cooldown_ms=60_000,
            statement_timeout_seconds=30,
        ),
        db=db,
        telemetry=object(),
        provider=provider,
        clock_ms=lambda: NOW_MS,
    )

    result = await worker.run_once()

    assert provider.reserve_calls == [EQUITY_EVENT_BRIEF_LANE]
    assert provider.execution_calls == 0
    assert db.equity_events.runs == []
    assert db.equity_events.briefs == []
    assert db.equity_events.brief_states == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[-1]["count_attempt"] is False
    assert result.processed == 0
    assert result.failed == 0
    assert result.skipped == 1
    assert result.notes["backpressure"] == 1
    assert result.notes["request_audit_failed"] == 1


def _candidate() -> dict[str, Any]:
    return {
        "event": {
            "company_event_id": "event-1",
            "company_id": "market_instrument:us_equity:MSFT",
            "ticker": "MSFT",
            "company_name": "Microsoft Corporation",
            "event_type": "quarterly_report",
            "priority": "P0",
            "source_role": "official_regulator",
            "event_time_ms": NOW_MS - 1_000,
            "discovered_at_ms": NOW_MS - 900,
            "fiscal_period": "2026Q1",
            "lifecycle_status": "processed",
            "validation_status": "accepted",
            "primary_document_id": "doc-1",
            "summary": "Microsoft reported quarterly revenue growth.",
            "updated_at_ms": NOW_MS - 500,
        },
        "story": None,
        "story_members": [],
        "source_documents": [
            {
                "event_document_id": "doc-1",
                "source_role": "official_regulator",
                "document_type": "sec_filing",
                "form_type": "10-Q",
                "document_url": "https://www.sec.gov/Archives/edgar/data/789019/doc.htm",
                "content_hash": "sha256:doc",
            }
        ],
        "source_spans": [
            {
                "span_id": "span-1",
                "event_document_id": "doc-1",
                "span_type": "financial_metric",
                "span_start": 100,
                "span_end": 160,
                "evidence_quote": "Revenue was $63.0 billion.",
                "confidence": 0.98,
            }
        ],
        "fact_candidates": [
            {
                "fact_candidate_id": "fact-1",
                "source_span_id": "span-1",
                "fact_type": "revenue_actual",
                "metric_name": "revenue",
                "value_numeric": 63.0,
                "value_unit": "USD_billion",
                "period": "2026Q1",
                "direction": "up",
                "claim": "Revenue was $63.0 billion.",
                "evidence_quote": "Revenue was $63.0 billion.",
                "validation_status": "accepted",
                "source_role": "official_regulator",
            }
        ],
        "current_brief": None,
        "latest_run": None,
        "source_updated_at_ms": NOW_MS - 500,
    }


class FakeBriefProvider:
    provider = "openai"
    model = "gpt-5-mini"
    artifact_version_hash = "artifact-hash-1"

    def __init__(
        self,
        *,
        reservation: AgentCapacityReservation,
        audit_error: Exception | None = None,
        brief_error: Exception | None = None,
    ) -> None:
        self.reservation = reservation
        self.audit_error = audit_error
        self.brief_error = brief_error
        self.reserve_calls: list[str] = []
        self.reserve_rate_units: list[int] = []
        self.execution_calls = 0

    def try_reserve_execution(self, lane: str, *, rate_units: int = 1) -> AgentCapacityReservation:
        self.reserve_calls.append(lane)
        self.reserve_rate_units.append(rate_units)
        if self.reservation.acquired:
            self.reservation.rate_units = rate_units
        return self.reservation

    def request_audit(self, *, run_id: str, packet: Any) -> dict[str, Any]:
        if self.audit_error is not None:
            raise self.audit_error
        return {
            "provider": self.provider,
            "backend": "openai_agents_sdk",
            "model": self.model,
            "lane": EQUITY_EVENT_BRIEF_LANE,
            "stage": "equity_event_brief",
            "workflow_name": "gmgn-twitter-intel.equity_event_brief",
            "agent_name": "EquityEventBriefAgent",
            "sdk_trace_id": f"trace-{run_id}",
            "group_id": "equity_event:event-1",
            "prompt_version": packet.prompt_version,
            "schema_version": packet.schema_version,
            "artifact_version_hash": self.artifact_version_hash,
            "input_hash": packet.input_hash,
            "execution_started": False,
            "usage": {},
            "trace_metadata": {},
        }

    async def brief_event(self, *, run_id: str, packet: Any, reservation: Any | None = None) -> dict[str, Any]:
        del run_id, packet, reservation
        self.execution_calls += 1
        if self.brief_error is not None:
            raise self.brief_error
        return {}


class FakeDB:
    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self.equity_events = FakeEquityEventRepository(candidates)
        self.dirty = FakeDirtyRepository(
            [
                {
                    "projection_name": "brief_input",
                    "target_kind": "company_event",
                    "target_id": str(candidate["event"]["company_event_id"]),
                    "payload_hash": f"payload:{candidate['event']['company_event_id']}",
                    "lease_owner": "equity_event_brief",
                    "attempt_count": 1,
                }
                for candidate in candidates
            ]
        )
        self.conn = FakeConn()

    def worker_session(self, worker_name: str, statement_timeout_seconds: float | None = None) -> FakeSession:
        del worker_name, statement_timeout_seconds
        return FakeSession(self)


class FakeSession:
    def __init__(self, db: FakeDB) -> None:
        self.equity_events = db.equity_events
        self.equity_projection_dirty_targets = db.dirty
        self.conn = db.conn

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class FakeEquityEventRepository:
    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self.candidates = candidates
        self.loaded_event_ids: list[list[str]] = []
        self.runs: list[dict[str, Any]] = []
        self.briefs: list[dict[str, Any]] = []
        self.brief_states: list[dict[str, Any]] = []

    def load_events_for_brief_targets(self, *, company_event_ids: list[str]) -> list[dict[str, Any]]:
        self.loaded_event_ids.append(list(company_event_ids))
        by_id = {str(candidate["event"]["company_event_id"]): candidate for candidate in self.candidates}
        return [by_id[event_id] for event_id in company_event_ids if event_id in by_id]

    def insert_equity_event_agent_run(self, **payload: Any) -> dict[str, Any]:
        self.runs.append(dict(payload))
        return dict(payload)

    def upsert_equity_event_agent_brief(self, **payload: Any) -> dict[str, Any]:
        self.briefs.append(dict(payload))
        return dict(payload)

    def upsert_brief_state(self, **payload: Any) -> dict[str, Any]:
        self.brief_states.append(dict(payload))
        return dict(payload)


class FakeDirtyRepository:
    def __init__(self, targets: list[dict[str, Any]]) -> None:
        self.targets = [dict(target) for target in targets]
        self.claim_calls: list[dict[str, Any]] = []
        self.done: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.error_kwargs: list[dict[str, Any]] = []

    def claim_due(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.claim_calls.append(dict(kwargs))
        limit = int(kwargs.get("limit") or len(self.targets) or 1)
        claimed = self.targets[:limit]
        self.targets = self.targets[limit:]
        return [dict(target) for target in claimed]

    def queue_depth(self, *, now_ms: int, projection_name: str | None = None) -> int:
        del now_ms
        if projection_name is None:
            return len(self.targets)
        return sum(1 for target in self.targets if target.get("projection_name") == projection_name)

    def mark_done(self, keys: list[dict[str, Any]], **kwargs: Any) -> int:
        del kwargs
        self.done.extend(dict(key) for key in keys)
        return len(keys)

    def mark_error(self, keys: list[dict[str, Any]], **kwargs: Any) -> int:
        self.errors.extend(dict(key) for key in keys)
        self.error_kwargs.append(dict(kwargs))
        return len(keys)


class FakeConn:
    def commit(self) -> None:
        return None

    @contextmanager
    def transaction(self):
        yield
