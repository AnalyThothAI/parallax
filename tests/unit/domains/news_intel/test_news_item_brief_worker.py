from __future__ import annotations

import asyncio
import threading
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from parallax.domains.news_intel.runtime.news_item_brief_worker import NewsItemBriefWorker
from parallax.domains.news_intel.types.news_item_brief import NEWS_ITEM_BRIEF_LANE, NewsItemBriefPayload
from parallax.platform.agent_execution import (
    AgentCapacityReservation,
    AgentExecutionError,
    AgentExecutionErrorClass,
)

NOW_MS = 1_779_000_000_000


def test_worker_writes_ready_brief_and_emits_wake() -> None:
    asyncio.run(_test_worker_writes_ready_brief_and_emits_wake())


def test_worker_processes_provider_signal_target_with_llm_context() -> None:
    asyncio.run(_test_worker_processes_provider_signal_target_with_llm_context())


def test_worker_skips_fresh_current_even_when_source_updated_is_noisy() -> None:
    asyncio.run(_test_worker_skips_fresh_current_even_when_source_updated_is_noisy())


def test_worker_reprocesses_failed_current_even_when_input_hash_matches() -> None:
    asyncio.run(_test_worker_reprocesses_failed_current_even_when_input_hash_matches())


def test_worker_skips_claimed_target_below_current_provider_score_floor() -> None:
    asyncio.run(_test_worker_skips_claimed_target_below_current_provider_score_floor())


def test_worker_processes_high_score_target_older_than_brief_window() -> None:
    asyncio.run(_test_worker_processes_high_score_target_older_than_brief_window())


def test_worker_policy_skip_exact_duplicate_does_not_call_model() -> None:
    asyncio.run(_test_worker_policy_skip_exact_duplicate_does_not_call_model())


async def _test_worker_writes_ready_brief_and_emits_wake() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(payload=_ready_payload())
    wake_bus = FakeWakeBus()
    worker = _worker(db=db, provider=provider, wake_bus=wake_bus)

    result = await worker.run_once()

    assert provider.reserve_calls == [NEWS_ITEM_BRIEF_LANE]
    assert provider.reserve_rate_units == [1]
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


async def _test_worker_processes_provider_signal_target_with_llm_context() -> None:
    candidate = _candidate()
    candidate["item"]["provider_signal_json"] = {
        "source": "provider",
        "provider": "opennews",
        "status": "ready",
        "direction": "bullish",
        "score": 88,
        "grade": "A",
    }
    candidate["item"]["provider_token_impacts_json"] = [{"symbol": "SOL", "score": 88, "signal": "long", "grade": "A"}]
    db = FakeDB([candidate])
    provider = FakeBriefProvider(payload=_ready_payload())
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.reserve_calls == [NEWS_ITEM_BRIEF_LANE]
    assert provider.reserve_rate_units == [1]
    assert provider.execution_calls == 1
    assert provider.seen_packets[0].provider_signal_evidence.score == 88
    assert provider.seen_packets[0].provider_signal_evidence.token_impacts[0].symbol == "SOL"
    assert db.news.runs[0]["status"] == "completed"
    assert db.news.briefs[0]["status"] == "ready"
    assert len(db.dirty.done) == 1
    assert result.processed == 1
    assert result.skipped == 0
    assert "provider_signal_skip" not in result.notes


async def _test_worker_skips_fresh_current_even_when_source_updated_is_noisy() -> None:
    candidate = _candidate()
    provider = FakeBriefProvider(payload=_ready_payload())
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["source_updated_at_ms"] = NOW_MS + 60_000
    candidate["current_brief"] = {
        "news_item_id": candidate["item"]["news_item_id"],
        "status": "ready",
        "input_hash": packet.input_hash,
        "artifact_version_hash": provider.artifact_version_hash,
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "validator_version": agent_config.validator_version,
        "computed_at_ms": NOW_MS - 60_000,
        "brief_json": _ready_payload(),
    }
    db = FakeDB([candidate])
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.reserve_calls == [NEWS_ITEM_BRIEF_LANE]
    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert len(db.dirty.done) == 1
    assert result.skipped == 1


async def _test_worker_reprocesses_failed_current_even_when_input_hash_matches() -> None:
    candidate = _candidate()
    provider = FakeBriefProvider(payload=_ready_payload())
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["current_brief"] = {
        "news_item_id": candidate["item"]["news_item_id"],
        "status": "failed",
        "input_hash": packet.input_hash,
        "artifact_version_hash": provider.artifact_version_hash,
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "validator_version": agent_config.validator_version,
        "computed_at_ms": NOW_MS - 60_000,
        "brief_json": {
            "status": "failed",
            "data_gaps": [{"description_zh": "终止失败已记录。", "severity": "high"}],
        },
    }
    db = FakeDB([candidate])
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls
    assert provider.execution_calls == 1
    assert db.news.runs[0]["status"] == "completed"
    assert db.news.briefs[0]["status"] == "ready"
    assert len(db.dirty.done) == 1
    assert result.processed == 1


async def _test_worker_skips_claimed_target_below_current_provider_score_floor() -> None:
    candidate = _candidate(provider_score=64)
    db = FakeDB([candidate])
    provider = FakeBriefProvider(payload=_ready_payload())
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.reserve_calls == [NEWS_ITEM_BRIEF_LANE]
    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert len(db.dirty.done) == 1
    assert result.processed == 0
    assert result.skipped == 1
    assert result.notes["policy_skipped"] == 1


async def _test_worker_processes_high_score_target_older_than_brief_window() -> None:
    candidate = _candidate(provider_score=95)
    candidate["item"]["published_at_ms"] = NOW_MS - (8 * 3_600_000) - 1
    db = FakeDB([candidate])
    provider = FakeBriefProvider(payload=_ready_payload())
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.reserve_calls == [NEWS_ITEM_BRIEF_LANE]
    assert provider.execution_calls == 1
    assert db.news.runs[0]["status"] == "completed"
    assert db.news.runs[0]["outcome"] == "ready"
    assert db.news.briefs[0]["status"] == "ready"
    assert len(db.dirty.done) == 1
    assert result.processed == 1
    assert result.skipped == 0


async def _test_worker_policy_skip_exact_duplicate_does_not_call_model() -> None:
    candidate = _candidate(provider_score=95)
    candidate["item"]["provider_article_keys_json"] = ["opennews:123"]
    candidate["exact_duplicate_candidates"] = [
        {
            "news_item_id": "news-rep",
            "provider_article_keys": ["opennews:123"],
            "published_at_ms": NOW_MS - 2_000,
            "lifecycle_status": "processed",
            "agent_admission_status": "eligible",
        }
    ]
    db = FakeDB([candidate])
    provider = FakeBriefProvider(payload=_ready_payload())
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.reserve_calls == [NEWS_ITEM_BRIEF_LANE]
    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.news.agent_admission_updates[0]["admission"].status == "exact_duplicate"
    assert db.dirty.done[0]["target_id"] == "news-item-1"
    assert db.dirty.enqueued[0]["rows"][0]["projection_name"] == "page"
    assert result.processed == 0
    assert result.skipped == 1
    assert result.notes["policy_skipped"] == 1


def test_worker_claims_dirty_targets_off_event_loop_thread() -> None:
    asyncio.run(_test_worker_claims_dirty_targets_off_event_loop_thread())


def test_worker_status_payload_reads_current_queue_depth() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider()
    worker = _worker(db=db, provider=provider)

    payload = worker.status_payload()

    assert payload["queue_depth"] == 1


async def _test_worker_claims_dirty_targets_off_event_loop_thread() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider()
    worker = _worker(db=db, provider=provider)
    event_loop_thread_id = threading.get_ident()

    result = await worker.run_once()

    assert result.processed == 1
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
    assert provider.reserve_rate_units == [1]
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


def test_worker_execute_no_start_rate_limit_does_not_write_business_ledger() -> None:
    asyncio.run(_test_worker_execute_no_start_rate_limit_does_not_write_business_ledger())


async def _test_worker_execute_no_start_rate_limit_does_not_write_business_ledger() -> None:
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
    assert db.news.runs == []
    assert db.news.briefs == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[-1]["count_attempt"] is False
    assert result.processed == 0
    assert result.failed == 0
    assert result.skipped == 1
    assert result.notes["backpressure"] == 1
    assert result.notes["backpressure_rate_limited"] == 1


def test_worker_quota_exhausted_does_not_write_failed_current_or_attempt() -> None:
    asyncio.run(_test_worker_quota_exhausted_does_not_write_failed_current_or_attempt())


async def _test_worker_quota_exhausted_does_not_write_failed_current_or_attempt() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(
        brief_error=AgentExecutionError(
            AgentExecutionErrorClass.QUOTA_EXHAUSTED,
            "Insufficient Balance",
            execution_started=False,
        )
    )
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.execution_calls == 1
    assert db.news.runs == []
    assert db.news.briefs == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[-1]["count_attempt"] is False
    assert result.notes["backpressure_quota_exhausted"] == 1


def test_worker_request_audit_error_requeues_without_business_ledger_or_current_write() -> None:
    asyncio.run(_test_worker_request_audit_error_requeues_without_business_ledger_or_current_write())


async def _test_worker_request_audit_error_requeues_without_business_ledger_or_current_write() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(audit_error=RuntimeError("audit exploded"))
    wake_bus = FakeWakeBus()
    worker = _worker(db=db, provider=provider, wake_bus=wake_bus)

    result = await worker.run_once()

    assert provider.reserve_calls == [NEWS_ITEM_BRIEF_LANE]
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[-1]["count_attempt"] is False
    assert wake_bus.brief_updates == []
    assert result.failed == 0
    assert result.skipped == 1
    assert result.notes["backpressure"] == 1
    assert result.notes["request_audit_failed"] == 1


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


def test_worker_validation_failure_requeues_without_terminal_current() -> None:
    asyncio.run(_test_worker_validation_failure_requeues_without_terminal_current())


async def _test_worker_validation_failure_requeues_without_terminal_current() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(payload={"status": "ready"})
    wake_bus = FakeWakeBus()
    worker = _worker(db=db, provider=provider, wake_bus=wake_bus)

    result = await worker.run_once()

    assert provider.execution_calls == 1
    assert db.news.runs[0]["status"] == "failed"
    assert db.news.runs[0]["outcome"] == "failed"
    assert db.news.runs[0]["validation_errors_json"][0]["code"] == "schema_invalid"
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[-1]["count_attempt"] is True
    assert db.dirty.terminalized == []
    assert db.news.briefs == []
    assert wake_bus.brief_updates == []
    assert result.failed == 1
    assert result.notes["validation_failed"] == 1
    assert result.notes["ready"] == 0


def test_worker_terminalizes_after_max_attempts_without_permanent_dirty_failure() -> None:
    asyncio.run(_test_worker_terminalizes_after_max_attempts_without_permanent_dirty_failure())


async def _test_worker_terminalizes_after_max_attempts_without_permanent_dirty_failure() -> None:
    target = _dirty_target(attempt_count=2)
    db = FakeDB([_candidate()], targets=[target])
    provider = FakeBriefProvider(brief_error=RuntimeError("provider bad output"))
    worker = _worker(db=db, provider=provider, settings=SimpleNamespace(batch_size=1, max_attempts=3))

    result = await worker.run_once()

    assert provider.execution_calls == 1
    assert db.dirty.errors == []
    assert len(db.dirty.terminalized) == 1
    assert db.dirty.terminalized[0]["terminal_attempt_count"] == 3
    assert db.dirty.done == []
    assert db.news.briefs[0]["status"] == "failed"
    assert "terminal" not in db.news.briefs[0]["brief_json"]
    assert db.news.briefs[0]["brief_json"]["data_gaps"][0]["severity"] == "high"
    assert result.failed == 1


def test_worker_skips_terminal_current_when_terminalize_claim_is_stale() -> None:
    asyncio.run(_test_worker_skips_terminal_current_when_terminalize_claim_is_stale())


async def _test_worker_skips_terminal_current_when_terminalize_claim_is_stale() -> None:
    target = _dirty_target(attempt_count=2)
    db = FakeDB([_candidate()], targets=[target], terminalize_return_count=0)
    provider = FakeBriefProvider(brief_error=RuntimeError("provider bad output"))
    worker = _worker(db=db, provider=provider, settings=SimpleNamespace(batch_size=1, max_attempts=3))

    result = await worker.run_once()

    assert provider.execution_calls == 1
    assert db.dirty.errors == []
    assert len(db.dirty.terminalized) == 1
    assert db.dirty.terminalized[0]["terminal_attempt_count"] == 3
    assert db.news.briefs == []
    assert result.failed == 1


def _worker(
    *,
    db: FakeDB,
    provider: FakeBriefProvider,
    wake_bus: Any | None = None,
    settings: SimpleNamespace | None = None,
) -> NewsItemBriefWorker:
    provider.db = db
    resolved_settings = SimpleNamespace(
        batch_size=5,
        max_attempts=3,
        backpressure_cooldown_ms=60_000,
        statement_timeout_seconds=30,
    )
    if settings is not None:
        resolved_settings.__dict__.update(settings.__dict__)
    return NewsItemBriefWorker(
        name="news_item_brief",
        settings=resolved_settings,
        db=db,
        telemetry=object(),
        provider=provider,
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )


def _candidate(*, provider_score: int = 88) -> dict[str, Any]:
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
            "lifecycle_status": "processed",
            "content_class": "crypto_market",
            "content_classification_json": {"policy_version": "news_content_classification_v1"},
            "analysis_admission_status": "admitted",
            "analysis_admission_reason": "crypto_native_evidence",
            "analysis_admission_json": {
                "status": "admitted",
                "reason": "crypto_native_evidence",
                "basis": {"crypto_evidence": ["resolved_crypto_target:cex:SOL"]},
                "version": "news_analysis_admission_v1",
            },
            "analysis_admission_version": "news_analysis_admission_v1",
            "source_domain": "example.com",
            "source_name": "Example",
            "source_role": "observed_source",
            "trust_tier": "standard",
            "provider_signal_json": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "bullish",
                "score": provider_score,
                "grade": "A",
            },
        },
        "token_mentions": [
            {
                "mention_id": "mention-news-item-1-sol",
                "observed_symbol": "SOL",
                "normalized_symbol": "SOL",
                "resolution_status": "known_symbol",
                "display_symbol": "SOL",
                "target_id": "cex:SOL",
            }
        ],
        "fact_candidates": [],
        "current_brief": None,
        "latest_run": None,
        "source_updated_at_ms": NOW_MS - 500,
    }


def _dirty_target(*, attempt_count: int = 1) -> dict[str, Any]:
    return {
        "projection_name": "brief_input",
        "target_kind": "news_item",
        "target_id": "news-item-1",
        "window": "",
        "payload_hash": "payload:news-item-1",
        "lease_owner": "news_item_brief",
        "attempt_count": attempt_count,
    }


def _ready_payload() -> dict[str, Any]:
    payload = {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "event_type": "etf_filing",
        "summary_zh": "SOL ETF filing boosts attention.",
        "market_read_zh": "SOL ETF 申请强化监管叙事，但审批时间仍不确定。",
        "market_domains": ["crypto"],
        "transmission_paths": [
            {
                "market_domain": "crypto",
                "channel": "regulatory_attention",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "ETF 申请提升监管叙事关注度。",
                "evidence_refs": ["item:summary"],
            }
        ],
        "bull_view": {
            "strength": "moderate",
            "thesis_zh": "ETF 申请可能带来持续关注。",
            "evidence_refs": ["item:summary"],
        },
        "bear_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
        "affected_entities": [
            {
                "label": "SOL",
                "symbol": "SOL",
                "name": "Solana",
                "entity_type": "crypto_asset",
                "market_domain": "crypto",
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
    if "title_zh" in NewsItemBriefPayload.model_fields:
        payload["title_zh"] = "SOL ETF 申请"
    return payload


class FakeBriefProvider:
    provider = "litellm"
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
        self.reserve_rate_units: list[int] = []
        self.request_audit_calls: list[str] = []
        self.execution_calls = 0
        self.saw_db_session_during_execution: bool | None = None
        self.seen_packets: list[Any] = []
        self.db: FakeDB | None = None

    def try_reserve_execution(self, lane: str, *, rate_units: int = 1) -> AgentCapacityReservation:
        assert self.db is None or self.db.in_session is False
        self.reserve_calls.append(lane)
        self.reserve_rate_units.append(rate_units)
        if self.reserve_error is not None:
            raise self.reserve_error
        if self.reservation.acquired:
            self.reservation.rate_units = rate_units
        return self.reservation

    def request_audit(self, *, run_id: str, packet: Any) -> dict[str, Any]:
        assert self.db is None or self.db.in_session is False
        self.request_audit_calls.append(run_id)
        if self.audit_error is not None:
            raise self.audit_error
        return _audit(run_id=run_id, packet=packet, execution_started=False)

    async def brief_item(self, *, run_id: str, packet: Any, reservation: Any | None = None) -> dict[str, Any]:
        self.execution_calls += 1
        self.seen_packets.append(packet)
        self.saw_db_session_during_execution = bool(self.db and self.db.in_session)
        assert self.saw_db_session_during_execution is False
        if self.brief_error is not None:
            raise self.brief_error
        return {
            "payload": self.payload,
            "agent_run_audit": _audit(run_id=run_id, packet=packet, execution_started=True),
        }

    def packet_for_candidate(self, candidate: dict[str, Any]) -> Any:
        from parallax.domains.news_intel.runtime.news_item_brief_worker import (
            _admission_from_candidate,
            _candidate_with_agent_admission,
            _packet_from_candidate,
        )

        return _packet_from_candidate(
            _candidate_with_agent_admission(
                candidate,
                _admission_from_candidate(candidate, now_ms=NOW_MS),
            ),
            agent_config=self.agent_config(),
        )

    def agent_config(self) -> Any:
        from parallax.domains.news_intel.types.news_item_brief import (
            default_news_item_brief_agent_config,
        )

        return default_news_item_brief_agent_config(
            model=self.model,
            artifact_version_hash=self.artifact_version_hash,
        )


def _audit(*, run_id: str, packet: Any, execution_started: bool) -> dict[str, Any]:
    return {
        "provider": "litellm",
        "backend": "litellm_sdk",
        "model": "gpt-5-mini",
        "lane": NEWS_ITEM_BRIEF_LANE,
        "stage": "news_item_brief",
        "workflow_name": "parallax.news_item_brief",
        "agent_name": "NewsItemBriefAgent",
        "execution_trace_id": f"trace-{run_id}",
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
    def __init__(
        self,
        candidates: list[dict[str, Any]],
        *,
        targets: list[dict[str, Any]] | None = None,
        terminalize_return_count: int | None = None,
    ) -> None:
        self.news = FakeNewsRepository(candidates)
        self.conn = FakeConn()
        resolved_targets = (
            targets
            if targets is not None
            else [
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
        self.dirty = FakeDirtyRepository(
            resolved_targets,
            terminalize_return_count=terminalize_return_count,
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
        self.loaded_admission_target_ids: list[list[str]] = []
        self.agent_admission_updates: list[dict[str, Any]] = []

    def load_items_for_brief_targets(self, *, news_item_ids: list[str]) -> list[dict[str, Any]]:
        self.loaded_target_ids.append(list(news_item_ids))
        by_id = {str(candidate["item"]["news_item_id"]): candidate for candidate in self.candidates}
        return [by_id[item_id] for item_id in news_item_ids if item_id in by_id]

    def load_agent_admission_contexts(self, *, news_item_ids: list[str], now_ms: int) -> list[dict[str, Any]]:
        del now_ms
        self.loaded_admission_target_ids.append(list(news_item_ids))
        by_id = {str(candidate["item"]["news_item_id"]): candidate for candidate in self.candidates}
        contexts: list[dict[str, Any]] = []
        for item_id in news_item_ids:
            candidate = by_id.get(item_id)
            if candidate is None:
                continue
            contexts.append(
                {
                    "item": dict(candidate["item"]),
                    "entities": [dict(row) for row in candidate.get("entities", [])],
                    "token_mentions": [dict(row) for row in candidate.get("token_mentions", [])],
                    "fact_candidates": [dict(row) for row in candidate.get("fact_candidates", [])],
                    "current_brief": candidate.get("current_brief"),
                    "exact_duplicate_candidates": [
                        dict(row) for row in candidate.get("exact_duplicate_candidates", [])
                    ],
                    "story_candidates": [dict(row) for row in candidate.get("story_candidates", [])],
                }
            )
        return contexts

    def update_item_agent_admission(self, **payload: Any) -> int:
        self.agent_admission_updates.append(dict(payload))
        return 1

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
    def __init__(
        self,
        targets: list[dict[str, Any]] | None = None,
        *,
        terminalize_return_count: int | None = None,
    ) -> None:
        self.targets = [dict(target) for target in targets or []]
        self.terminalize_return_count = terminalize_return_count
        self.enqueued: list[dict[str, Any]] = []
        self.done: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.terminalized: list[dict[str, Any]] = []
        self.error_kwargs: list[dict[str, Any]] = []
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
        self.error_kwargs.append(dict(kwargs))
        return len(keys)

    def terminalize_targets(self, keys: list[dict[str, Any]], **kwargs: Any) -> int:
        self.terminalized.append({"keys": [dict(key) for key in keys], **dict(kwargs)})
        if self.terminalize_return_count is not None:
            return self.terminalize_return_count
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
