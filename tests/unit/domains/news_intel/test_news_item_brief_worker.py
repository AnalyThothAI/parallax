from __future__ import annotations

import asyncio
import threading
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.domains.news_intel.runtime.news_item_brief_worker import NewsItemBriefWorker
from gmgn_twitter_intel.domains.news_intel.types.news_item_brief import NEWS_ITEM_BRIEF_LANE
from gmgn_twitter_intel.platform.agent_execution import (
    AgentCapacityReservation,
    AgentExecutionError,
    AgentExecutionErrorClass,
)

NOW_MS = 1_779_000_000_000


def test_worker_writes_ready_brief_and_emits_wake() -> None:
    asyncio.run(_test_worker_writes_ready_brief_and_emits_wake())


def test_worker_marks_opennews_provider_signal_target_done_without_llm() -> None:
    asyncio.run(_test_worker_marks_opennews_provider_signal_target_done_without_llm())


async def _test_worker_writes_ready_brief_and_emits_wake() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(payload=_ready_payload())
    wake_bus = FakeWakeBus()
    worker = _worker(db=db, provider=provider, wake_bus=wake_bus)

    result = await worker.run_once()

    assert provider.reserve_calls == [NEWS_ITEM_BRIEF_LANE]
    assert provider.execution_calls == 1
    assert provider.saw_db_session_during_execution is False
    assert db.news.runs[0]["status"] == "completed"
    assert db.news.runs[0]["outcome"] == "ready"
    assert db.news.runs[0]["execution_started"] is True
    assert db.news.briefs[0]["status"] == "ready"
    assert db.news.briefs[0]["brief_json"]["summary_zh"] == "SOL ETF filing boosts attention."
    assert wake_bus.brief_updates == [1]
    assert result.processed == 1
    assert result.failed == 0
    assert result.notes["ready"] == 1
    assert result.notes["claimed"] == 1


async def _test_worker_marks_opennews_provider_signal_target_done_without_llm() -> None:
    candidate = _candidate()
    candidate["item"]["provider_signal_json"] = {
        "source": "provider",
        "provider": "opennews",
        "status": "ready",
        "direction": "bullish",
    }
    db = FakeDB([candidate])
    provider = FakeBriefProvider(payload=_ready_payload())
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.reserve_calls == [NEWS_ITEM_BRIEF_LANE]
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert len(db.dirty.done) == 1
    assert result.processed == 0
    assert result.skipped == 1
    assert result.notes["provider_signal_skip"] == 1


def test_worker_claims_dirty_targets_off_event_loop_thread() -> None:
    asyncio.run(_test_worker_claims_dirty_targets_off_event_loop_thread())


async def _test_worker_claims_dirty_targets_off_event_loop_thread() -> None:
    candidate = _candidate()
    candidate["item"]["provider_signal_json"] = {"source": "provider", "status": "ready"}
    db = FakeDB([candidate])
    provider = FakeBriefProvider()
    worker = _worker(db=db, provider=provider)
    event_loop_thread_id = threading.get_ident()

    result = await worker.run_once()

    assert result.skipped == 1
    assert db.dirty.claim_thread_ids
    assert db.dirty.claim_thread_ids[0] != event_loop_thread_id
    assert db.news.loaded_target_ids == [["news-item-1"]]


def test_worker_capacity_denied_does_not_claim_dirty_target_or_write_ledger() -> None:
    asyncio.run(_test_worker_capacity_denied_does_not_claim_dirty_target_or_write_ledger())


async def _test_worker_capacity_denied_does_not_claim_dirty_target_or_write_ledger() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(
        reservation=AgentCapacityReservation(
            lane=NEWS_ITEM_BRIEF_LANE,
            acquired=False,
            reason=AgentExecutionErrorClass.CAPACITY_DENIED,
        )
    )
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.reserve_calls == [NEWS_ITEM_BRIEF_LANE]
    assert provider.execution_calls == 0
    assert db.dirty.claim_thread_ids == []
    assert db.news.loaded_target_ids == []
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert db.dirty.errors == []
    assert result.processed == 0
    assert result.skipped == 1
    assert result.notes["claimed"] == 0
    assert result.notes["backpressure"] == 1
    assert result.notes["backpressure_capacity_denied"] == 1


def test_worker_execute_no_start_rate_limit_does_not_upsert_failed_current() -> None:
    asyncio.run(_test_worker_execute_no_start_rate_limit_does_not_upsert_failed_current())


async def _test_worker_execute_no_start_rate_limit_does_not_upsert_failed_current() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(
        brief_error=AgentExecutionError(
            AgentExecutionErrorClass.RATE_LIMITED,
            "rpm denied before provider start",
            execution_started=False,
        )
    )
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.execution_calls == 1
    assert db.news.runs[0]["status"] == "backpressure"
    assert db.news.runs[0]["outcome"] == "backpressure_rate_limited"
    assert db.news.runs[0]["execution_started"] is False
    assert db.news.runs[0]["error_class"] == "rate_limited"
    assert db.news.runs[0]["response_json"] is None
    assert db.news.briefs == []
    assert result.processed == 0
    assert result.failed == 0
    assert result.skipped == 1
    assert result.notes["backpressure"] == 1
    assert result.notes["backpressure_rate_limited"] == 1


def test_worker_request_audit_error_records_failed_current_and_emits_wake() -> None:
    asyncio.run(_test_worker_request_audit_error_records_failed_current_and_emits_wake())


async def _test_worker_request_audit_error_records_failed_current_and_emits_wake() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(audit_error=RuntimeError("audit exploded"))
    wake_bus = FakeWakeBus()
    worker = _worker(db=db, provider=provider, wake_bus=wake_bus)

    result = await worker.run_once()

    assert provider.reserve_calls == [NEWS_ITEM_BRIEF_LANE]
    assert provider.execution_calls == 0
    assert db.news.runs[0]["status"] == "failed"
    assert db.news.runs[0]["outcome"] == "failed"
    assert db.news.runs[0]["execution_started"] is False
    assert db.news.runs[0]["error_class"] == "RuntimeError"
    assert db.news.runs[0]["provider"] == "openai"
    assert db.news.runs[0]["model"] == "gpt-5-mini"
    assert db.news.runs[0]["backend"] == "openai_agents_sdk"
    assert db.news.runs[0]["workflow_name"] == "gmgn-twitter-intel.news_item_brief"
    assert db.news.runs[0]["agent_name"] == "NewsItemBriefAgent"
    assert db.news.runs[0]["lane"] == NEWS_ITEM_BRIEF_LANE
    assert db.news.runs[0]["input_hash"]
    assert db.news.runs[0]["request_json"]["audit"]["execution_started"] is False
    assert db.news.runs[0]["trace_metadata_json"] == {}
    assert db.news.runs[0]["usage_json"] == {}
    assert db.news.briefs[0]["status"] == "failed"
    assert db.news.briefs[0]["brief_json"]["data_gaps"][0]["severity"] == "high"
    assert wake_bus.brief_updates == [1]
    assert result.failed == 1
    assert result.notes["failed"] == 1


def test_worker_reserve_error_does_not_claim_dirty_target_or_write_ledger() -> None:
    asyncio.run(_test_worker_reserve_error_does_not_claim_dirty_target_or_write_ledger())


async def _test_worker_reserve_error_does_not_claim_dirty_target_or_write_ledger() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(reserve_error=RuntimeError("reserve exploded"))
    wake_bus = FakeWakeBus()
    worker = _worker(db=db, provider=provider, wake_bus=wake_bus)

    result = await worker.run_once()

    assert provider.reserve_calls == [NEWS_ITEM_BRIEF_LANE]
    assert provider.execution_calls == 0
    assert db.dirty.claim_thread_ids == []
    assert db.news.loaded_target_ids == []
    assert db.news.runs == []
    assert db.news.briefs == []
    assert wake_bus.brief_updates == []
    assert result.failed == 0
    assert result.skipped == 1
    assert result.notes["claimed"] == 0
    assert result.notes["backpressure"] == 1
    assert result.notes["agent_reservation_error"] == "RuntimeError"


def test_worker_provider_error_releases_acquired_reservation() -> None:
    asyncio.run(_test_worker_provider_error_releases_acquired_reservation())


async def _test_worker_provider_error_releases_acquired_reservation() -> None:
    release_calls = 0

    def release() -> None:
        nonlocal release_calls
        release_calls += 1

    db = FakeDB([_candidate()])
    reservation = AgentCapacityReservation(lane=NEWS_ITEM_BRIEF_LANE, acquired=True, _release=release)
    provider = FakeBriefProvider(reservation=reservation, brief_error=RuntimeError("provider exploded"))
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.execution_calls == 1
    assert release_calls == 1
    assert reservation.acquired is False
    assert db.news.runs[0]["status"] == "failed"
    assert db.news.runs[0]["execution_started"] is True
    assert result.failed == 1


def test_worker_validation_failure_records_failed_current_without_ready_publish() -> None:
    asyncio.run(_test_worker_validation_failure_records_failed_current_without_ready_publish())


async def _test_worker_validation_failure_records_failed_current_without_ready_publish() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(payload={**_ready_payload(), "evidence_refs": ["fact:unknown"]})
    wake_bus = FakeWakeBus()
    worker = _worker(db=db, provider=provider, wake_bus=wake_bus)

    result = await worker.run_once()

    assert provider.execution_calls == 1
    assert db.news.runs[0]["status"] == "failed"
    assert db.news.runs[0]["outcome"] == "failed"
    assert db.news.runs[0]["validation_errors_json"][0]["code"] == "unknown_evidence_ref"
    assert db.news.briefs[0]["status"] == "failed"
    assert db.news.briefs[0]["direction"] == "neutral"
    assert db.news.briefs[0]["decision_class"] == "discard"
    assert db.news.briefs[0]["brief_json"]["data_gaps"][0]["severity"] == "high"
    assert wake_bus.brief_updates == [1]
    assert result.failed == 1
    assert result.notes["validation_failed"] == 1
    assert result.notes["ready"] == 0


def _worker(*, db: FakeDB, provider: FakeBriefProvider, wake_bus: Any | None = None) -> NewsItemBriefWorker:
    provider.db = db
    return NewsItemBriefWorker(
        name="news_item_brief",
        settings=SimpleNamespace(
            batch_size=5,
            max_attempts=3,
            backpressure_cooldown_ms=60_000,
            statement_timeout_seconds=30,
        ),
        db=db,
        telemetry=object(),
        provider=provider,
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )


def _candidate() -> dict[str, Any]:
    return {
        "item": {
            "news_item_id": "news-item-1",
            "title": "SOL ETF filing",
            "summary": "Issuer files for a SOL ETF.",
            "body_text": "Issuer files for a SOL ETF.",
            "canonical_url": "https://example.com/sol-etf",
            "published_at_ms": NOW_MS - 1_000,
            "fetched_at_ms": NOW_MS - 900,
            "content_hash": "content-hash-1",
            "source_domain": "example.com",
            "source_name": "Example",
            "source_role": "observed_source",
            "trust_tier": "standard",
        },
        "story": None,
        "token_mentions": [],
        "fact_candidates": [],
        "story_members": [],
        "current_brief": None,
        "latest_run": None,
        "source_updated_at_ms": NOW_MS - 500,
    }


def _ready_payload() -> dict[str, Any]:
    return {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "summary_zh": "SOL ETF filing boosts attention.",
        "market_read_zh": "SOL ETF 申请强化监管叙事，但审批时间仍不确定。",
        "bull_view": {
            "strength": "moderate",
            "thesis_zh": "ETF 申请可能带来持续关注。",
            "evidence_refs": ["item:summary"],
        },
        "bear_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
        "affected_assets": [
            {
                "symbol": "SOL",
                "name": "Solana",
                "resolution_status": "unknown",
                "target_type": None,
                "target_id": None,
                "impact_direction": "bullish",
                "reason_zh": "新闻直接提到 SOL ETF。",
                "evidence_refs": ["item:summary"],
            }
        ],
        "watch_triggers": ["后续监管文件更新"],
        "invalidation_conditions": ["申请撤回"],
        "data_gaps": [],
        "evidence_refs": ["item:summary"],
    }


class FakeBriefProvider:
    provider = "openai"
    model = "gpt-5-mini"
    artifact_version_hash = "artifact-hash-1"

    def __init__(
        self,
        *,
        payload: dict[str, Any] | None = None,
        reservation: AgentCapacityReservation | None = None,
        audit_error: Exception | None = None,
        reserve_error: Exception | None = None,
        brief_error: Exception | None = None,
    ) -> None:
        self.payload = payload or _ready_payload()
        self.reservation = reservation or AgentCapacityReservation(lane=NEWS_ITEM_BRIEF_LANE, acquired=True)
        self.audit_error = audit_error
        self.reserve_error = reserve_error
        self.brief_error = brief_error
        self.reserve_calls: list[str] = []
        self.execution_calls = 0
        self.saw_db_session_during_execution: bool | None = None
        self.db: FakeDB | None = None

    def try_reserve_execution(self, lane: str) -> AgentCapacityReservation:
        assert self.db is None or self.db.in_session is False
        self.reserve_calls.append(lane)
        if self.reserve_error is not None:
            raise self.reserve_error
        return self.reservation

    def request_audit(self, *, run_id: str, packet: Any) -> dict[str, Any]:
        assert self.db is None or self.db.in_session is False
        if self.audit_error is not None:
            raise self.audit_error
        return _audit(run_id=run_id, packet=packet, execution_started=False)

    async def brief_item(self, *, run_id: str, packet: Any, reservation: Any | None = None) -> dict[str, Any]:
        self.execution_calls += 1
        self.saw_db_session_during_execution = bool(self.db and self.db.in_session)
        assert self.saw_db_session_during_execution is False
        if self.brief_error is not None:
            raise self.brief_error
        return {
            "payload": self.payload,
            "agent_run_audit": _audit(run_id=run_id, packet=packet, execution_started=True),
        }


def _audit(*, run_id: str, packet: Any, execution_started: bool) -> dict[str, Any]:
    return {
        "provider": "openai",
        "backend": "openai_agents_sdk",
        "model": "gpt-5-mini",
        "lane": NEWS_ITEM_BRIEF_LANE,
        "stage": "news_item_brief",
        "workflow_name": "gmgn-twitter-intel.news_item_brief",
        "agent_name": "NewsItemBriefAgent",
        "sdk_trace_id": f"trace-{run_id}",
        "group_id": "news_item:news-item-1",
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "runtime_version": "agent-execution-plane-v1",
        "artifact_version_hash": "artifact-hash-1",
        "input_hash": packet.input_hash,
        "output_hash": "output-hash-1" if execution_started else None,
        "latency_ms": 123 if execution_started else None,
        "usage": {"input_tokens": 100, "output_tokens": 80} if execution_started else {},
        "trace_metadata": {"run_id": run_id, "news_item_id": packet.news_item.news_item_id},
        "execution_started": execution_started,
        "status": "done" if execution_started else "planned",
        "error_class": None,
        "error_message": None,
    }


class FakeDB:
    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self.news = FakeNewsRepository(candidates)
        self.conn = FakeConn()
        self.dirty = FakeDirtyRepository(
            [
                {
                    "projection_name": "brief_input",
                    "target_kind": "news_item",
                    "target_id": str(candidate["item"]["news_item_id"]),
                    "window": "",
                    "payload_hash": f"payload:{candidate['item']['news_item_id']}",
                    "lease_owner": "news_item_brief",
                    "attempt_count": 1,
                }
                for candidate in candidates
            ]
        )
        self.in_session = False

    def worker_session(self, worker_name: str, statement_timeout_seconds: float | None = None) -> FakeSession:
        return FakeSession(self)


class FakeSession:
    def __init__(self, db: FakeDB) -> None:
        self.db = db
        self.news = db.news
        self.conn = db.conn
        self.news_projection_dirty_targets = db.dirty

    def __enter__(self) -> FakeSession:
        assert self.db.in_session is False
        self.db.in_session = True
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.db.in_session = False


class FakeNewsRepository:
    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self.candidates = candidates
        self.runs: list[dict[str, Any]] = []
        self.briefs: list[dict[str, Any]] = []
        self.loaded_target_ids: list[list[str]] = []

    def load_items_for_brief_targets(self, *, news_item_ids: list[str]) -> list[dict[str, Any]]:
        self.loaded_target_ids.append(list(news_item_ids))
        by_id = {str(candidate["item"]["news_item_id"]): candidate for candidate in self.candidates}
        return [by_id[item_id] for item_id in news_item_ids if item_id in by_id]

    def insert_news_item_agent_run(self, **payload: Any) -> dict[str, Any]:
        self.runs.append(dict(payload))
        return dict(payload)

    def upsert_news_item_agent_brief(self, **payload: Any) -> dict[str, Any]:
        self.briefs.append(dict(payload))
        return dict(payload)

    def list_source_ids_for_news_items(self, *, news_item_ids: list[str]) -> list[str]:
        assert news_item_ids == ["news-item-1"]
        return ["source-1"]


class FakeDirtyRepository:
    def __init__(self, targets: list[dict[str, Any]] | None = None) -> None:
        self.targets = [dict(target) for target in targets or []]
        self.enqueued: list[dict[str, Any]] = []
        self.done: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.claim_thread_ids: list[int] = []

    def claim_due(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.claim_thread_ids.append(threading.get_ident())
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
        self.done.extend(dict(key) for key in keys)
        return len(keys)

    def mark_error(self, keys: list[dict[str, Any]], **kwargs: Any) -> int:
        self.errors.extend(dict(key) for key in keys)
        return len(keys)

    def enqueue_targets(self, rows: list[dict[str, Any]], *, reason: str, now_ms: int, commit: bool = True) -> int:
        self.enqueued.append(
            {
                "rows": [dict(row) for row in rows],
                "reason": reason,
                "now_ms": now_ms,
                "commit": commit,
            }
        )
        return len(rows)


class FakeConn:
    @contextmanager
    def transaction(self):
        yield


class FakeWakeBus:
    def __init__(self) -> None:
        self.brief_updates: list[int] = []

    def notify_news_item_brief_updated(self, *, count: int) -> None:
        self.brief_updates.append(count)
