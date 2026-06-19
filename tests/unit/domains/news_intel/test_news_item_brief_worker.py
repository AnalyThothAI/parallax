from __future__ import annotations

import asyncio
import threading
from contextlib import contextmanager
from typing import Any

import pytest

from parallax.domains.news_intel.runtime import news_item_brief_worker as worker_module
from parallax.domains.news_intel.runtime.news_item_brief_worker import (
    NewsItemBriefWorker,
    _agent_admission_payload,
    _audit_dict,
    _provider_error_audit,
)
from parallax.domains.news_intel.services.news_item_brief_validation import NewsItemBriefValidationResult
from parallax.domains.news_intel.types.news_item_agent_admission import NewsItemAgentAdmission
from parallax.domains.news_intel.types.news_item_brief import NEWS_ITEM_BRIEF_LANE, NewsItemBriefPayload
from parallax.platform.agent_execution import (
    AgentCapacityReservation,
    AgentExecutionError,
    AgentExecutionErrorClass,
    AgentExecutionRequestAudit,
)
from parallax.platform.config.settings import NewsItemBriefWorkerSettings

NOW_MS = 1_779_000_000_000


def _news_item_brief_settings(**overrides: Any) -> NewsItemBriefWorkerSettings:
    payload = {
        "batch_size": 5,
        "lease_ms": 120_000,
        "retry_ms": 60_000,
        "backpressure_cooldown_ms": 60_000,
        "statement_timeout_seconds": 30,
    }
    payload.update(overrides)
    return NewsItemBriefWorkerSettings(**payload)


def test_worker_writes_ready_brief_and_emits_wake() -> None:
    asyncio.run(_test_worker_writes_ready_brief_and_emits_wake())


def test_worker_canonicalizes_run_artifact_hash_to_worker_config() -> None:
    asyncio.run(_test_worker_canonicalizes_run_artifact_hash_to_worker_config())


def test_worker_publishes_market_wide_proxy_brief_without_domain_validation_failure() -> None:
    asyncio.run(_test_worker_publishes_market_wide_proxy_brief_without_domain_validation_failure())


def test_worker_processes_provider_signal_target_without_provider_context_in_packet() -> None:
    asyncio.run(_test_worker_processes_provider_signal_target_without_provider_context_in_packet())


def test_worker_does_not_restore_packet_context_from_admission_basis() -> None:
    asyncio.run(_test_worker_does_not_restore_packet_context_from_admission_basis())


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("entities", "[]", "news_item_brief_candidate_entities_array_required"),
        ("token_mentions", {"mention_id": "bad"}, "news_item_brief_candidate_token_mentions_array_required"),
        ("fact_candidates", ["bad"], "news_item_brief_candidate_fact_candidates_row_object_required"),
    ),
)
def test_news_item_brief_worker_packet_rejects_malformed_candidate_arrays(
    field: str,
    value: object,
    error: str,
) -> None:
    candidate = _candidate()
    candidate[field] = value
    from parallax.domains.news_intel.runtime.news_item_brief_worker import _packet_from_candidate

    with pytest.raises(RuntimeError, match=error):
        _packet_from_candidate(candidate, agent_config=FakeBriefProvider().agent_config())


def test_worker_skips_fresh_current_even_when_source_updated_is_noisy() -> None:
    asyncio.run(_test_worker_skips_fresh_current_even_when_source_updated_is_noisy())


def test_worker_preserves_item_current_from_target_loader_when_admission_context_has_no_current_brief() -> None:
    asyncio.run(_test_worker_preserves_item_current_from_target_loader_when_admission_context_has_no_current_brief())


@pytest.mark.parametrize(
    ("field_name", "expected_error"),
    [
        ("status", "news_item_brief_current_status_required"),
        ("input_hash", "news_item_brief_current_input_hash_required"),
        ("artifact_version_hash", "news_item_brief_current_artifact_version_hash_required"),
        ("prompt_version", "news_item_brief_current_prompt_version_required"),
        ("schema_version", "news_item_brief_current_schema_version_required"),
        ("validator_version", "news_item_brief_current_validator_version_required"),
    ],
)
def test_worker_rejects_current_brief_missing_identity_before_second_model_call(
    field_name: str,
    expected_error: str,
) -> None:
    asyncio.run(
        _test_worker_rejects_current_brief_missing_identity_before_second_model_call(field_name, expected_error)
    )


def test_worker_restores_current_from_completed_run_without_second_model_call() -> None:
    asyncio.run(_test_worker_restores_current_from_completed_run_without_second_model_call())


@pytest.mark.parametrize("finished_at_ms", [True, "1778999970000", 1_778_999_970_000.5, 0])
def test_worker_rejects_completed_run_malformed_finished_at_without_clock_fallback(finished_at_ms: object) -> None:
    asyncio.run(_test_worker_rejects_completed_run_malformed_finished_at_without_clock_fallback(finished_at_ms))


def test_worker_skips_failed_current_when_input_hash_matches() -> None:
    asyncio.run(_test_worker_skips_failed_current_when_input_hash_matches())


def test_worker_policy_skips_claimed_target_with_low_provider_rating() -> None:
    asyncio.run(_test_worker_policy_skips_claimed_target_with_low_provider_rating())


def test_worker_requires_repository_session_transaction_for_policy_skip_completion() -> None:
    asyncio.run(_test_worker_requires_repository_session_transaction_for_policy_skip_completion())


def test_worker_reads_formal_settings_for_claim_session_retry_and_backpressure() -> None:
    asyncio.run(_test_worker_reads_formal_settings_for_claim_session_retry_and_backpressure())


def test_worker_processes_high_score_target_older_than_brief_window() -> None:
    asyncio.run(_test_worker_processes_high_score_target_older_than_brief_window())


def test_worker_policy_skip_exact_duplicate_does_not_call_model() -> None:
    asyncio.run(_test_worker_policy_skip_exact_duplicate_does_not_call_model())


def test_worker_rejects_claim_missing_target_id_without_marking_done() -> None:
    asyncio.run(_test_worker_rejects_claim_missing_target_id_without_marking_done())


def test_worker_rejects_loaded_candidate_missing_item_identity_without_marking_target_done() -> None:
    asyncio.run(_test_worker_rejects_loaded_candidate_missing_item_identity_without_marking_target_done())


def test_worker_rejects_malformed_admission_context_evidence_without_candidate_fallback() -> None:
    asyncio.run(_test_worker_rejects_malformed_admission_context_evidence_without_candidate_fallback())


def test_worker_rejects_publishable_validation_missing_payload_without_empty_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        worker_module,
        "validate_news_item_brief_output",
        lambda **_: NewsItemBriefValidationResult(publishable=True, status="ready"),
    )
    asyncio.run(_test_worker_rejects_publishable_validation_missing_payload_without_empty_default())


async def _test_worker_writes_ready_brief_and_emits_wake() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(payload=_ready_payload())
    wake_bus = FakeWakeBus()
    worker = _worker(db=db, provider=provider, wake_emitter=wake_bus)

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
    assert db.dirty.enqueued == []
    assert wake_bus.brief_updates == [1]
    assert result.processed == 1
    assert result.failed == 0
    assert result.notes["ready"] == 1
    assert result.notes["claimed"] == 1


async def _test_worker_canonicalizes_run_artifact_hash_to_worker_config() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(payload=_ready_payload(), audit_artifact_version_hash="agent-audit-hash")
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert result.processed == 1
    assert db.news.runs[0]["artifact_version_hash"] == provider.artifact_version_hash
    assert db.news.briefs[0]["artifact_version_hash"] == provider.artifact_version_hash


async def _test_worker_publishes_market_wide_proxy_brief_without_domain_validation_failure() -> None:
    db = FakeDB([_energy_candidate(provider_score=90)])
    provider = FakeBriefProvider(payload=_energy_ready_payload())
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.reserve_calls == [NEWS_ITEM_BRIEF_LANE]
    assert provider.execution_calls == 1
    assert provider.seen_packets[0].market_scope == ["energy_geopolitics", "commodity", "crypto"]
    assert result.processed == 1
    assert result.failed == 0
    assert db.news.runs[0]["status"] == "completed"
    assert db.news.runs[0]["outcome"] == "ready"
    assert db.news.runs[0]["validation_errors_json"] == []
    assert db.news.briefs[0]["status"] == "ready"
    assert db.news.briefs[0]["brief_json"]["event_type"] == "geopolitical_supply"


async def _test_worker_processes_provider_signal_target_without_provider_context_in_packet() -> None:
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
    assert not hasattr(provider.seen_packets[0], "provider_signal_evidence")
    assert all(not ref.startswith("provider:") for ref in provider.seen_packets[0].evidence_refs)
    assert db.news.runs[0]["status"] == "completed"
    assert db.news.briefs[0]["status"] == "ready"
    assert len(db.dirty.done) == 1
    assert result.processed == 1
    assert result.skipped == 0
    assert "provider_signal_skip" not in result.notes


async def _test_worker_does_not_restore_packet_context_from_admission_basis() -> None:
    candidate = _candidate()
    candidate["item"]["story_key"] = "story:sol-etf"
    candidate["story_candidates"] = [
        {
            **candidate["item"],
            "news_item_id": "news-item-representative",
            "story_key": "story:sol-etf",
            "entities": [],
            "fact_candidates": [],
        }
    ]
    db = FakeDB([candidate])

    def load_agent_admission_contexts(*, news_item_ids: list[str], now_ms: int) -> list[dict[str, Any]]:
        del now_ms
        assert news_item_ids == ["news-item-1"]
        context = _agent_admission_context_for_candidate(candidate)
        context["material_delta"] = {
            "has_delta": True,
            "reasons": ["new_fact"],
            "evidence": {"fact_candidate_ids": ["fact-new"]},
        }
        return [context]

    db.news.load_agent_admission_contexts = load_agent_admission_contexts  # type: ignore[method-assign]
    provider = FakeBriefProvider(payload=_ready_payload())
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert result.processed == 1
    assert provider.execution_calls == 1
    assert provider.seen_packets[0].similarity == {}
    assert provider.seen_packets[0].material_delta == {}


async def _test_worker_rejects_publishable_validation_missing_payload_without_empty_default() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(payload=_ready_payload())
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.execution_calls == 1
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == "news_item_brief_validation_payload_required"
    assert result.failed == 1


async def _test_worker_rejects_loaded_candidate_missing_item_identity_without_marking_target_done() -> None:
    target = {
        "projection_name": "brief_input",
        "target_kind": "news_item",
        "target_id": "news-item-1",
        "window": "",
        "payload_hash": "payload:news-item-1",
        "lease_owner": "news_item_brief",
        "attempt_count": 1,
    }
    db = FakeDB([], targets=[target])

    def load_items_for_brief_targets(*, news_item_ids: list[str]) -> list[dict[str, Any]]:
        db.news.loaded_target_ids.append(list(news_item_ids))
        return [{"item": {"news_item_id": ""}}]

    def load_agent_admission_contexts(*, news_item_ids: list[str], now_ms: int) -> list[dict[str, Any]]:
        del now_ms
        db.news.loaded_admission_target_ids.append(list(news_item_ids))
        return []

    db.news.load_items_for_brief_targets = load_items_for_brief_targets  # type: ignore[method-assign]
    db.news.load_agent_admission_contexts = load_agent_admission_contexts  # type: ignore[method-assign]
    provider = FakeBriefProvider(payload=_ready_payload())
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == "news_item_brief_candidate_news_item_id_required:load_candidate"
    assert result.failed == 1
    assert result.notes["load_failed"] == 1


async def _test_worker_rejects_malformed_admission_context_evidence_without_candidate_fallback() -> None:
    candidate = _candidate()
    db = FakeDB([candidate])

    def load_agent_admission_contexts(*, news_item_ids: list[str], now_ms: int) -> list[dict[str, Any]]:
        del now_ms
        db.news.loaded_admission_target_ids.append(list(news_item_ids))
        context = _agent_admission_context_for_candidate(candidate)
        context["token_mentions"] = "not-a-formal-list"
        return [context]

    db.news.load_agent_admission_contexts = load_agent_admission_contexts  # type: ignore[method-assign]
    provider = FakeBriefProvider(payload=_ready_payload())
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == (
        "news_item_brief_admission_context_token_mentions_required:load_candidate"
    )
    assert result.failed == 1
    assert result.notes["load_failed"] == 1


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


async def _test_worker_preserves_item_current_from_target_loader_when_admission_context_has_no_current_brief() -> None:
    candidate = _candidate()
    provider = FakeBriefProvider(payload=_ready_payload())
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
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

    def load_agent_admission_contexts(*, news_item_ids: list[str], now_ms: int) -> list[dict[str, Any]]:
        del now_ms
        db.news.loaded_admission_target_ids.append(list(news_item_ids))
        context = _agent_admission_context_for_candidate(candidate)
        return [context]

    db.news.load_agent_admission_contexts = load_agent_admission_contexts  # type: ignore[method-assign]
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert len(db.dirty.done) == 1
    assert result.skipped == 1


async def _test_worker_rejects_current_brief_missing_identity_before_second_model_call(
    field_name: str,
    expected_error: str,
) -> None:
    candidate = _candidate()
    provider = FakeBriefProvider(payload=_ready_payload())
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
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
    candidate["current_brief"].pop(field_name)
    db = FakeDB([candidate])
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == expected_error
    assert result.failed == 1


async def _test_worker_restores_current_from_completed_run_without_second_model_call() -> None:
    candidate = _candidate()
    provider = FakeBriefProvider(payload=_ready_payload())
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "run-existing-ready",
        "news_item_id": candidate["item"]["news_item_id"],
        "status": "completed",
        "outcome": "ready",
        "execution_started": True,
        "input_hash": packet.input_hash,
        "artifact_version_hash": provider.artifact_version_hash,
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "validator_version": agent_config.validator_version,
        "finished_at_ms": NOW_MS - 30_000,
        "response_json": _ready_payload(),
    }
    db = FakeDB([candidate])
    wake_bus = FakeWakeBus()
    worker = _worker(db=db, provider=provider, wake_emitter=wake_bus)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs[0]["agent_run_id"] == "run-existing-ready"
    assert db.news.briefs[0]["status"] == "ready"
    assert len(db.dirty.done) == 1
    assert wake_bus.brief_updates == [1]
    assert result.processed == 1
    assert result.notes["ready"] == 1
    assert result.notes["restored_from_completed_run"] == 1


async def _test_worker_skips_failed_current_when_input_hash_matches() -> None:
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

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert len(db.dirty.done) == 1
    assert result.processed == 0
    assert result.skipped == 1


def test_worker_revalidates_completed_run_before_restoring_current() -> None:
    asyncio.run(_test_worker_revalidates_completed_run_before_restoring_current())


def test_worker_rejects_completed_run_missing_run_id_before_restore_or_model_call() -> None:
    asyncio.run(_test_worker_rejects_completed_run_missing_run_id_before_restore_or_model_call())


def test_worker_rejects_completed_run_missing_outcome_before_restore_or_model_call() -> None:
    asyncio.run(_test_worker_rejects_completed_run_missing_outcome_before_restore_or_model_call())


def test_worker_rejects_completed_run_missing_finished_at_without_clock_fallback() -> None:
    asyncio.run(_test_worker_rejects_completed_run_missing_finished_at_without_clock_fallback())


@pytest.mark.parametrize(
    ("field_name", "expected_error"),
    [
        ("provider", "news_item_brief_run_provider_required:invalid_completed_source_run"),
        ("model", "news_item_brief_run_model_required:invalid_completed_source_run"),
    ],
)
def test_worker_rejects_invalid_completed_run_missing_source_identity_before_audit_repair(
    field_name: str,
    expected_error: str,
) -> None:
    asyncio.run(
        _test_worker_rejects_invalid_completed_run_missing_source_identity_before_audit_repair(
            field_name,
            expected_error,
        )
    )


async def _test_worker_revalidates_completed_run_before_restoring_current() -> None:
    candidate = _candidate()
    provider = FakeBriefProvider(payload=_ready_payload())
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    invalid_ready_payload = _ready_payload()
    invalid_ready_payload["summary_zh"] = ""
    invalid_ready_payload["market_read_zh"] = ""
    candidate["latest_run"] = {
        "run_id": "run-existing-invalid-ready",
        "news_item_id": candidate["item"]["news_item_id"],
        "status": "completed",
        "outcome": "ready",
        "provider": "openai",
        "model": "gpt-test",
        "execution_started": True,
        "input_hash": packet.input_hash,
        "artifact_version_hash": provider.artifact_version_hash,
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "validator_version": agent_config.validator_version,
        "finished_at_ms": NOW_MS - 30_000,
        "response_json": invalid_ready_payload,
    }
    db = FakeDB([candidate])
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs[0]["status"] == "failed"
    assert db.news.runs[0]["error_class"] == "domain_validation_failed"
    assert db.news.runs[0]["execution_started"] is False
    assert db.news.briefs[0]["agent_run_id"] == db.news.runs[0]["run_id"]
    assert db.news.briefs[0]["status"] == "failed"
    assert len(db.dirty.done) == 1
    assert result.processed == 0
    assert result.notes["invalid_completed_run"] == 1


async def _test_worker_rejects_completed_run_missing_run_id_before_restore_or_model_call() -> None:
    candidate = _candidate()
    provider = FakeBriefProvider(payload=_ready_payload())
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "news_item_id": candidate["item"]["news_item_id"],
        "status": "completed",
        "outcome": "ready",
        "execution_started": True,
        "input_hash": packet.input_hash,
        "artifact_version_hash": provider.artifact_version_hash,
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "validator_version": agent_config.validator_version,
        "finished_at_ms": NOW_MS - 30_000,
        "response_json": _ready_payload(),
    }
    db = FakeDB([candidate])
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == "news_item_brief_run_id_required:completed_run"
    assert result.failed == 1


async def _test_worker_rejects_completed_run_missing_outcome_before_restore_or_model_call() -> None:
    candidate = _candidate()
    provider = FakeBriefProvider(payload=_ready_payload())
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "run-existing-ready",
        "news_item_id": candidate["item"]["news_item_id"],
        "status": "completed",
        "execution_started": True,
        "input_hash": packet.input_hash,
        "artifact_version_hash": provider.artifact_version_hash,
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "validator_version": agent_config.validator_version,
        "finished_at_ms": NOW_MS - 30_000,
        "response_json": _ready_payload(),
    }
    db = FakeDB([candidate])
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == "news_item_brief_run_outcome_required:completed_run"
    assert result.failed == 1


async def _test_worker_rejects_completed_run_missing_finished_at_without_clock_fallback() -> None:
    candidate = _candidate()
    provider = FakeBriefProvider(payload=_ready_payload())
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "run-existing-ready",
        "news_item_id": candidate["item"]["news_item_id"],
        "status": "completed",
        "outcome": "ready",
        "execution_started": True,
        "input_hash": packet.input_hash,
        "artifact_version_hash": provider.artifact_version_hash,
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "validator_version": agent_config.validator_version,
        "response_json": _ready_payload(),
    }
    db = FakeDB([candidate])
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == "news_item_brief_run_finished_at_ms_required:completed_run"
    assert result.failed == 1


async def _test_worker_rejects_completed_run_malformed_finished_at_without_clock_fallback(
    finished_at_ms: object,
) -> None:
    candidate = _candidate()
    provider = FakeBriefProvider(payload=_ready_payload())
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "run-existing-ready",
        "news_item_id": candidate["item"]["news_item_id"],
        "status": "completed",
        "outcome": "ready",
        "execution_started": True,
        "input_hash": packet.input_hash,
        "artifact_version_hash": provider.artifact_version_hash,
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "validator_version": agent_config.validator_version,
        "finished_at_ms": finished_at_ms,
        "response_json": _ready_payload(),
    }
    db = FakeDB([candidate])
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == "news_item_brief_run_finished_at_ms_required:completed_run"
    assert result.failed == 1


async def _test_worker_rejects_invalid_completed_run_missing_source_identity_before_audit_repair(
    field_name: str,
    expected_error: str,
) -> None:
    candidate = _candidate()
    provider = FakeBriefProvider(payload=_ready_payload())
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    invalid_ready_payload = _ready_payload()
    invalid_ready_payload["summary_zh"] = ""
    invalid_ready_payload["market_read_zh"] = ""
    candidate["latest_run"] = {
        "run_id": "run-existing-invalid-ready",
        "news_item_id": candidate["item"]["news_item_id"],
        "status": "completed",
        "outcome": "ready",
        "provider": "openai",
        "model": "gpt-test",
        "execution_started": True,
        "input_hash": packet.input_hash,
        "artifact_version_hash": provider.artifact_version_hash,
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "validator_version": agent_config.validator_version,
        "finished_at_ms": NOW_MS - 30_000,
        "response_json": invalid_ready_payload,
    }
    candidate["latest_run"].pop(field_name)
    db = FakeDB([candidate])
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == expected_error
    assert result.failed == 1


def test_worker_restores_failed_current_from_started_failed_run_without_second_model_call() -> None:
    asyncio.run(_test_worker_restores_failed_current_from_started_failed_run_without_second_model_call())


def test_worker_rejects_failed_run_missing_run_id_before_restore_or_model_call() -> None:
    asyncio.run(_test_worker_rejects_failed_run_missing_run_id_before_restore_or_model_call())


@pytest.mark.parametrize(
    ("field_name", "expected_error"),
    [
        ("status", "news_item_brief_run_status_required:latest_run"),
        ("outcome", "news_item_brief_run_outcome_required:failed_run"),
        ("execution_started", "news_item_brief_run_execution_started_required:failed_run"),
        ("input_hash", "news_item_brief_run_input_hash_required:failed_run"),
        ("artifact_version_hash", "news_item_brief_run_artifact_version_hash_required:failed_run"),
        ("prompt_version", "news_item_brief_run_prompt_version_required:failed_run"),
        ("schema_version", "news_item_brief_run_schema_version_required:failed_run"),
        ("validator_version", "news_item_brief_run_validator_version_required:failed_run"),
        ("error_class", "news_item_brief_run_error_class_required:failed_run"),
        ("error", "news_item_brief_run_error_required:failed_run"),
    ],
)
def test_worker_rejects_failed_run_missing_identity_before_restore_or_model_call(
    field_name: str,
    expected_error: str,
) -> None:
    asyncio.run(
        _test_worker_rejects_failed_run_missing_identity_before_restore_or_model_call(field_name, expected_error)
    )


async def _test_worker_restores_failed_current_from_started_failed_run_without_second_model_call() -> None:
    candidate = _candidate()
    provider = FakeBriefProvider(payload=_ready_payload())
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "run-existing-timeout",
        "news_item_id": candidate["item"]["news_item_id"],
        "status": "failed",
        "outcome": "failed",
        "error_class": "timeout",
        "error": "model timed out",
        "execution_started": True,
        "input_hash": packet.input_hash,
        "artifact_version_hash": provider.artifact_version_hash,
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "validator_version": agent_config.validator_version,
        "finished_at_ms": NOW_MS - 30_000,
    }
    db = FakeDB([candidate])
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs[0]["agent_run_id"] == "run-existing-timeout"
    assert db.news.briefs[0]["status"] == "failed"
    assert db.news.briefs[0]["input_hash"] == packet.input_hash
    assert len(db.dirty.done) == 1
    assert db.dirty.errors == []
    assert result.processed == 0
    assert result.skipped == 1
    assert result.notes["restored_from_failed_run"] == 1


async def _test_worker_rejects_failed_run_missing_run_id_before_restore_or_model_call() -> None:
    candidate = _candidate()
    provider = FakeBriefProvider(payload=_ready_payload())
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "news_item_id": candidate["item"]["news_item_id"],
        "status": "failed",
        "outcome": "failed",
        "error_class": "timeout",
        "error": "model timed out",
        "execution_started": True,
        "input_hash": packet.input_hash,
        "artifact_version_hash": provider.artifact_version_hash,
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "validator_version": agent_config.validator_version,
        "finished_at_ms": NOW_MS - 30_000,
    }
    db = FakeDB([candidate])
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == "news_item_brief_run_id_required:failed_run"
    assert result.failed == 1


async def _test_worker_rejects_failed_run_missing_identity_before_restore_or_model_call(
    field_name: str,
    expected_error: str,
) -> None:
    candidate = _candidate()
    provider = FakeBriefProvider(payload=_ready_payload())
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "run-existing-timeout",
        "news_item_id": candidate["item"]["news_item_id"],
        "status": "failed",
        "outcome": "failed",
        "error_class": "timeout",
        "error": "model timed out",
        "execution_started": True,
        "input_hash": packet.input_hash,
        "artifact_version_hash": provider.artifact_version_hash,
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "validator_version": agent_config.validator_version,
        "finished_at_ms": NOW_MS - 30_000,
    }
    candidate["latest_run"].pop(field_name)
    db = FakeDB([candidate])
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == expected_error
    assert result.failed == 1


async def _test_worker_policy_skips_claimed_target_with_low_provider_rating() -> None:
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
    assert db.news.agent_admission_updates[0]["admission"].status == "needs_review"
    assert db.news.agent_admission_updates[0]["admission"].reason == "provider_rating_below_threshold"
    assert len(db.dirty.done) == 1
    assert result.processed == 0
    assert result.skipped == 1
    assert result.notes["policy_skipped"] == 1


async def _test_worker_requires_repository_session_transaction_for_policy_skip_completion() -> None:
    candidate = _candidate(provider_score=64)
    db = FakeDB([candidate], expose_transaction=False)
    provider = FakeBriefProvider(payload=_ready_payload())
    worker = _worker(db=db, provider=provider)

    with pytest.raises(AttributeError, match="transaction"):
        await worker.run_once()

    assert db.news.agent_admission_updates == []
    assert db.dirty.done == []


async def _test_worker_reads_formal_settings_for_claim_session_retry_and_backpressure() -> None:
    targets = [
        {
            **_dirty_target(),
            "target_id": f"news-item-{index}",
            "payload_hash": f"payload:news-item-{index}",
        }
        for index in range(9)
    ]
    db = FakeDB([], targets=targets, expected_statement_timeout=17, load_error=RuntimeError("load failed"))
    provider = FakeBriefProvider()
    worker = _worker(
        db=db,
        provider=provider,
        settings=_news_item_brief_settings(
            batch_size=7,
            lease_ms=45_000,
            retry_ms=90_000,
            backpressure_cooldown_ms=12_000,
            statement_timeout_seconds=17,
        ),
    )

    result = await worker.run_once()

    assert provider.reserve_rate_units == [7]
    assert len(db.dirty.claim_kwargs) == 1
    assert db.dirty.claim_kwargs[0]["projection_name"] == "brief_input"
    assert db.dirty.claim_kwargs[0]["limit"] == 7
    assert db.dirty.claim_kwargs[0]["lease_ms"] == 45_000
    assert db.dirty.claim_kwargs[0]["now_ms"] == NOW_MS
    assert str(db.dirty.claim_kwargs[0]["lease_owner"]).startswith("news_item_brief:")
    assert db.dirty.error_kwargs == [
        {
            "error": "load failed",
            "retry_ms": 90_000,
            "now_ms": NOW_MS,
            "count_attempt": True,
            "commit": True,
        }
    ]
    assert worker._backpressure_cooldown_ms() == 12_000
    assert result.failed == 7
    assert result.notes["claimed"] == 7
    assert result.notes["load_failed"] == 1


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


async def _test_worker_rejects_claim_missing_target_id_without_marking_done() -> None:
    db = FakeDB([_candidate()])
    db.dirty.targets[0].pop("target_id")
    provider = FakeBriefProvider(payload=_ready_payload())
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.loaded_target_ids == []
    assert db.news.loaded_admission_target_ids == []
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == "news_item_brief_claim_target_id_required"
    assert db.dirty.error_kwargs[0]["count_attempt"] is True
    assert result.failed == 1
    assert result.notes["load_failed"] == 1


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
    worker = _worker(db=db, provider=provider, wake_emitter=wake_bus)

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
    worker = _worker(db=db, provider=provider, wake_emitter=wake_bus)

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


def test_worker_rejects_result_missing_latency_without_zero_default() -> None:
    asyncio.run(_test_worker_rejects_result_missing_latency_without_zero_default())


def test_worker_rejects_result_missing_usage_without_empty_default() -> None:
    asyncio.run(_test_worker_rejects_result_missing_usage_without_empty_default())


def test_worker_rejects_result_missing_trace_metadata_without_empty_default() -> None:
    asyncio.run(_test_worker_rejects_result_missing_trace_metadata_without_empty_default())


def test_worker_rejects_result_missing_agent_run_audit_without_request_audit_fallback() -> None:
    asyncio.run(_test_worker_rejects_result_missing_agent_run_audit_without_request_audit_fallback())


@pytest.mark.parametrize(
    ("field_name", "expected_error"),
    [
        ("provider", "news_item_brief_audit_provider_required"),
        ("model", "news_item_brief_audit_model_required"),
        ("backend", "news_item_brief_audit_backend_required"),
        ("workflow_name", "news_item_brief_audit_workflow_name_required"),
        ("agent_name", "news_item_brief_audit_agent_name_required"),
        ("lane", "news_item_brief_audit_lane_required"),
        ("prompt_version", "news_item_brief_audit_prompt_version_required"),
        ("schema_version", "news_item_brief_audit_schema_version_required"),
        ("input_hash", "news_item_brief_audit_input_hash_required"),
    ],
)
def test_worker_rejects_result_missing_audit_identity_without_defaults(
    field_name: str,
    expected_error: str,
) -> None:
    asyncio.run(_test_worker_rejects_result_missing_audit_identity_without_defaults(field_name, expected_error))


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


async def _test_worker_rejects_result_missing_latency_without_zero_default() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(payload=_ready_payload(), omit_result_latency=True)
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls
    assert provider.execution_calls == 1
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == "news_item_brief_audit_latency_ms_required"
    assert result.failed == 1


async def _test_worker_rejects_result_missing_usage_without_empty_default() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(payload=_ready_payload(), omit_result_usage=True)
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls
    assert provider.execution_calls == 1
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == "news_item_brief_audit_usage_required"
    assert result.failed == 1


async def _test_worker_rejects_result_missing_trace_metadata_without_empty_default() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(payload=_ready_payload(), omit_result_trace_metadata=True)
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls
    assert provider.execution_calls == 1
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == "news_item_brief_audit_trace_metadata_required"
    assert result.failed == 1


async def _test_worker_rejects_result_missing_agent_run_audit_without_request_audit_fallback() -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(payload=_ready_payload(), omit_result_audit=True)
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls
    assert provider.execution_calls == 1
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == "news_item_brief_agent_run_audit_contract_required"
    assert result.failed == 1


async def _test_worker_rejects_result_missing_audit_identity_without_defaults(
    field_name: str,
    expected_error: str,
) -> None:
    db = FakeDB([_candidate()])
    provider = FakeBriefProvider(payload=_ready_payload(), omit_result_audit_fields={field_name})
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls
    assert provider.execution_calls == 1
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == expected_error
    assert result.failed == 1


def test_worker_validation_failure_writes_failed_current_without_retry_or_terminal_event() -> None:
    asyncio.run(_test_worker_validation_failure_writes_failed_current_without_retry_or_terminal_event())


async def _test_worker_validation_failure_writes_failed_current_without_retry_or_terminal_event() -> None:
    db = FakeDB([_candidate()])
    invalid_ready_payload = _ready_payload()
    invalid_ready_payload["summary_zh"] = ""
    invalid_ready_payload["market_read_zh"] = ""
    provider = FakeBriefProvider(payload=invalid_ready_payload)
    wake_bus = FakeWakeBus()
    worker = _worker(db=db, provider=provider, wake_emitter=wake_bus)

    result = await worker.run_once()

    assert provider.execution_calls == 1
    assert db.news.runs[0]["status"] == "failed"
    assert db.news.runs[0]["outcome"] == "failed"
    assert db.news.runs[0]["validation_errors_json"][0]["code"] == "missing_publishable_text"
    assert db.dirty.errors == []
    assert len(db.dirty.done) == 1
    assert db.news.briefs[0]["status"] == "failed"
    assert db.news.briefs[0]["agent_run_id"] == db.news.runs[0]["run_id"]
    assert wake_bus.brief_updates == []
    assert result.failed == 0
    assert result.notes["validation_failed"] == 1
    assert result.notes["ready"] == 0


def test_news_item_brief_worker_requires_mapping_agent_run_audit_contract() -> None:
    with pytest.raises(RuntimeError, match="news_item_brief_agent_run_audit_contract_required"):
        _audit_dict(object())


def test_news_item_brief_worker_provider_error_audit_requires_formal_agent_execution_audit() -> None:
    malformed_error = AgentExecutionError(
        AgentExecutionErrorClass.PROVIDER_ERROR,
        "provider failed",
        audit={"status": "failed"},  # type: ignore[arg-type]
        execution_started=True,
    )

    with pytest.raises(RuntimeError, match="news_item_brief_agent_error_audit_contract_required"):
        _provider_error_audit(malformed_error)

    packet = FakeBriefProvider().packet_for_candidate(_candidate())
    formal_audit = AgentExecutionRequestAudit(
        **_audit(run_id="run-formal", packet=packet, execution_started=False),
    )
    formal_error = AgentExecutionError(
        AgentExecutionErrorClass.PROVIDER_ERROR,
        "provider failed",
        audit=formal_audit,
        execution_started=False,
    )

    assert _provider_error_audit(formal_error)["execution_trace_id"] == "trace-run-formal"


def test_news_item_brief_worker_agent_admission_payload_requires_formal_admission_type() -> None:
    admission = NewsItemAgentAdmission(
        eligible=True,
        status="eligible",
        reason="eligible",
        representative_news_item_id="news-item-1",
        basis={"market_scope": ["crypto"]},
    )

    assert _agent_admission_payload(admission) == {
        "eligible": True,
        "status": "eligible",
        "reason": "eligible",
        "representative_news_item_id": "news-item-1",
        "basis": {"market_scope": ["crypto"]},
        "version": admission.version,
    }
    with pytest.raises(RuntimeError, match="news_item_brief_agent_admission_contract_required"):
        _agent_admission_payload({"eligible": True})  # type: ignore[arg-type]


def test_worker_provider_failure_writes_failed_current_without_retry_after_prior_attempts() -> None:
    asyncio.run(_test_worker_provider_failure_writes_failed_current_without_retry_after_prior_attempts())


async def _test_worker_provider_failure_writes_failed_current_without_retry_after_prior_attempts() -> None:
    target = _dirty_target(attempt_count=2)
    db = FakeDB([_candidate()], targets=[target])
    provider = FakeBriefProvider(brief_error=RuntimeError("provider bad output"))
    worker = _worker(db=db, provider=provider, settings=_news_item_brief_settings(batch_size=1))

    result = await worker.run_once()

    assert provider.execution_calls == 1
    assert db.dirty.errors == []
    assert len(db.dirty.done) == 1
    assert db.news.briefs[0]["status"] == "failed"
    assert "terminal" not in db.news.briefs[0]["brief_json"]
    assert "终态原因：RuntimeError" in db.news.briefs[0]["brief_json"]["data_gaps"][0]["description_zh"]
    assert db.news.briefs[0]["brief_json"]["data_gaps"][0]["severity"] == "high"
    assert result.failed == 1


def test_worker_provider_failure_hard_cuts_dirty_target_without_terminal_claim() -> None:
    asyncio.run(_test_worker_provider_failure_hard_cuts_dirty_target_without_terminal_claim())


async def _test_worker_provider_failure_hard_cuts_dirty_target_without_terminal_claim() -> None:
    target = _dirty_target(attempt_count=2)
    db = FakeDB([_candidate()], targets=[target])
    provider = FakeBriefProvider(brief_error=RuntimeError("provider bad output"))
    worker = _worker(db=db, provider=provider, settings=_news_item_brief_settings(batch_size=1))

    result = await worker.run_once()

    assert provider.execution_calls == 1
    assert db.dirty.errors == []
    assert len(db.dirty.done) == 1
    assert db.news.briefs[0]["agent_run_id"] == db.news.runs[0]["run_id"]
    assert db.news.briefs[0]["input_hash"] == db.news.runs[0]["input_hash"]
    assert result.failed == 1


def _worker(
    *,
    db: FakeDB,
    provider: FakeBriefProvider,
    wake_emitter: Any | None = None,
    settings: NewsItemBriefWorkerSettings | None = None,
) -> NewsItemBriefWorker:
    provider.db = db
    return NewsItemBriefWorker(
        name="news_item_brief",
        settings=settings or _news_item_brief_settings(),
        db=db,
        telemetry=object(),
        provider=provider,
        wake_emitter=wake_emitter,
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
            "market_scope_json": ["crypto"],
            "agent_admission_status": "eligible",
            "agent_admission_reason": "eligible",
            "agent_admission_json": {
                "eligible": True,
                "status": "eligible",
                "reason": "eligible",
                "representative_news_item_id": "news-item-1",
                "basis": {"market_scope": ["crypto"], "crypto_evidence": ["resolved_crypto_target:cex:SOL"]},
                "version": "news_item_agent_admission_market_v2",
            },
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
        "entities": [],
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


def _energy_candidate(*, provider_score: int = 90) -> dict[str, Any]:
    candidate = _candidate(provider_score=provider_score)
    candidate["item"].update(
        {
            "title": "U.S. attacks Iranian sites after Iran launches drones",
            "summary": "Gulf flare-up raised WTI crude supply concerns and risk assets.",
            "body_text": (
                "U.S. attacks on Iranian sites after Iran launched drones raised Gulf supply concerns, "
                "supported WTI crude futures risk premium, and pressured broader risk assets."
            ),
            "canonical_url": "https://example.com/gulf-energy-risk",
            "content_hash": "content-hash-energy-1",
            "content_class": "energy_geopolitics",
            "content_classification_json": {
                "policy_version": "news_content_classification_v1",
                "content_class": "energy_geopolitics",
            },
            "market_scope_json": ["energy_geopolitics", "commodity", "crypto"],
            "agent_admission_status": "eligible",
            "agent_admission_reason": "eligible",
            "agent_admission_json": {
                "eligible": True,
                "status": "eligible",
                "reason": "eligible",
                "representative_news_item_id": "news-item-1",
                "basis": {"market_scope": ["energy_geopolitics", "commodity", "crypto"]},
                "version": "news_item_agent_admission_market_v2",
            },
            "event_type": "geopolitical_supply",
            "provider_signal_json": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "mixed",
                "score": provider_score,
                "grade": "A",
                "summary_en": "Gulf flare-up lifted crude supply risk and weighed on risk sentiment.",
            },
            "provider_token_impacts_json": [
                {
                    "symbol": "BTC",
                    "market_type": "cex",
                    "score": 40,
                    "direction": "mixed",
                    "signal": "proxy",
                    "grade": "C",
                }
            ],
        }
    )
    candidate["entities"] = [
        {
            "entity_id": "entity-iran",
            "raw_value": "Iran",
            "normalized_value": "iran",
            "entity_type": "country",
            "confidence": 0.96,
        },
        {
            "entity_id": "entity-us",
            "raw_value": "U.S.",
            "normalized_value": "united states",
            "entity_type": "country",
            "confidence": 0.94,
        },
        {
            "entity_id": "entity-wti",
            "raw_value": "WTI crude futures",
            "normalized_value": "wti crude futures",
            "entity_type": "commodity",
            "confidence": 0.92,
        },
    ]
    candidate["token_mentions"] = []
    candidate["fact_candidates"] = [
        {
            "fact_candidate_id": "fact-gulf-supply",
            "event_type": "geopolitical_supply",
            "claim": "The Gulf flare-up raised WTI crude futures supply concerns and risk-asset pressure.",
            "realis": "actual",
            "validation_status": "accepted",
            "affected_targets_json": [{"label": "WTI crude futures", "symbol": "CL", "market_domain": "commodity"}],
            "evidence_quote": "raised Gulf supply concerns and supported WTI crude futures risk premium",
        }
    ]
    return candidate


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


def _energy_ready_payload() -> dict[str, Any]:
    return {
        "status": "ready",
        "direction": "mixed",
        "decision_class": "driver",
        "event_type": "geopolitical_supply",
        "title_zh": "海湾冲突升级抬高原油供应风险",
        "summary_zh": "美国袭击伊朗相关地点、伊朗发射无人机后，海湾局势升温推高 WTI 原油供应担忧。",
        "market_read_zh": (
            "这是一条跨市场驱动：直接传导在能源和大宗商品风险溢价，"
            "对 BTC 只体现为风险情绪代理，而不是来源直接点名的加密资产事件。"
        ),
        "market_domains": ["energy_geopolitics", "commodity", "crypto"],
        "transmission_paths": [
            {
                "market_domain": "energy_geopolitics",
                "channel": "military_escalation",
                "direction": "mixed",
                "strength": "moderate",
                "explanation_zh": "美国与伊朗相关军事升级提高海湾供应链和政策不确定性。",
                "evidence_refs": ["item:title", "entity:entity-iran"],
            },
            {
                "market_domain": "commodity",
                "channel": "crude_supply_risk",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "报道直接提到海湾供应担忧和 WTI 原油期货风险溢价。",
                "evidence_refs": ["fact:fact-gulf-supply"],
            },
            {
                "market_domain": "crypto",
                "channel": "risk_sentiment_proxy",
                "direction": "mixed",
                "strength": "weak",
                "explanation_zh": "风险资产压力可能通过情绪渠道影响 crypto beta，但新闻没有直接点名具体加密资产。",
                "evidence_refs": ["item:summary"],
            },
        ],
        "bull_view": {
            "strength": "moderate",
            "thesis_zh": "WTI 原油期货的供给风险溢价上升，能源冲击可能继续牵动跨市场波动。",
            "evidence_refs": ["fact:fact-gulf-supply"],
        },
        "bear_view": {
            "strength": "weak",
            "thesis_zh": "报道尚未证明实际供应中断，BTC 影响仍是风险情绪代理而非直接基本面变化。",
            "evidence_refs": ["item:summary"],
        },
        "affected_entities": [
            {
                "label": "WTI crude futures",
                "symbol": "CL",
                "name": "WTI crude futures",
                "entity_type": "commodity",
                "market_domain": "commodity",
                "resolution_status": "observed",
                "target_type": None,
                "target_id": None,
                "impact_direction": "bullish",
                "reason_zh": "候选事实直接把 WTI 原油期货列为受海湾供应风险影响的商品。",
                "evidence_refs": ["fact:fact-gulf-supply"],
            },
        ],
        "watch_triggers": ["后续海湾航运、WTI 价格和风险资产波动是否继续扩大"],
        "invalidation_conditions": ["军事升级降温或原油供应风险被后续报道证伪"],
        "data_gaps": [],
        "evidence_refs": [
            "item:title",
            "item:summary",
            "item:body_excerpt",
            "fact:fact-gulf-supply",
        ],
    }


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
        audit_artifact_version_hash: str | None = None,
        omit_result_latency: bool = False,
        omit_result_usage: bool = False,
        omit_result_trace_metadata: bool = False,
        omit_result_audit: bool = False,
        omit_result_audit_fields: set[str] | None = None,
    ) -> None:
        self.payload = payload or _ready_payload()
        self.reservation = reservation or AgentCapacityReservation(lane=NEWS_ITEM_BRIEF_LANE, acquired=True)
        self.audit_error = audit_error
        self.reserve_error = reserve_error
        self.brief_error = brief_error
        self.audit_artifact_version_hash = audit_artifact_version_hash or self.artifact_version_hash
        self.omit_result_latency = omit_result_latency
        self.omit_result_usage = omit_result_usage
        self.omit_result_trace_metadata = omit_result_trace_metadata
        self.omit_result_audit = omit_result_audit
        self.omit_result_audit_fields = omit_result_audit_fields or set()
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
        return _audit(
            run_id=run_id,
            packet=packet,
            execution_started=False,
            artifact_version_hash=self.audit_artifact_version_hash,
        )

    async def brief_item(self, *, run_id: str, packet: Any, reservation: Any | None = None) -> dict[str, Any]:
        self.execution_calls += 1
        self.seen_packets.append(packet)
        self.saw_db_session_during_execution = bool(self.db and self.db.in_session)
        assert self.saw_db_session_during_execution is False
        if self.brief_error is not None:
            raise self.brief_error
        if self.omit_result_audit:
            return {"payload": self.payload}
        agent_run_audit = _audit(
            run_id=run_id,
            packet=packet,
            execution_started=True,
            artifact_version_hash=self.audit_artifact_version_hash,
        )
        if self.omit_result_latency:
            agent_run_audit.pop("latency_ms")
        if self.omit_result_usage:
            agent_run_audit.pop("usage")
        if self.omit_result_trace_metadata:
            agent_run_audit.pop("trace_metadata")
        for field_name in self.omit_result_audit_fields:
            agent_run_audit.pop(field_name)
        return {
            "payload": self.payload,
            "agent_run_audit": agent_run_audit,
        }

    def packet_for_candidate(self, candidate: dict[str, Any]) -> Any:
        from parallax.domains.news_intel.runtime.news_item_brief_worker import (
            _admission_from_candidate,
            _candidate_with_agent_admission,
            _packet_from_candidate,
        )

        candidate_with_context = {
            **candidate,
            "agent_admission_context": _agent_admission_context_for_candidate(candidate),
        }
        return _packet_from_candidate(
            _candidate_with_agent_admission(
                candidate_with_context,
                _admission_from_candidate(candidate_with_context, now_ms=NOW_MS),
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


def _audit(
    *,
    run_id: str,
    packet: Any,
    execution_started: bool,
    artifact_version_hash: str = "artifact-hash-1",
) -> dict[str, Any]:
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
        "artifact_version_hash": artifact_version_hash,
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
        expose_transaction: bool = True,
        expected_statement_timeout: float = 30,
        load_error: Exception | None = None,
    ) -> None:
        self.news = FakeNewsRepository(candidates, load_error=load_error)
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
        )
        self.in_session = False
        self.expose_transaction = expose_transaction
        self.expected_statement_timeout = expected_statement_timeout

    def worker_session(self, worker_name: str, statement_timeout_seconds: float | None = None) -> FakeSession:
        assert worker_name == "news_item_brief"
        assert statement_timeout_seconds == self.expected_statement_timeout
        return FakeSession(self)


class FakeSession:
    def __init__(self, db: FakeDB) -> None:
        self.db = db
        self.news = db.news
        self.conn = db.conn
        self.news_projection_dirty_targets = db.dirty
        if db.expose_transaction:
            self.transaction = db.conn.transaction

    def __enter__(self) -> FakeSession:
        assert self.db.in_session is False
        self.db.in_session = True
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.db.in_session = False


class FakeNewsRepository:
    def __init__(self, candidates: list[dict[str, Any]], *, load_error: Exception | None = None) -> None:
        self.candidates = candidates
        self.load_error = load_error
        self.runs: list[dict[str, Any]] = []
        self.briefs: list[dict[str, Any]] = []
        self.loaded_target_ids: list[list[str]] = []
        self.loaded_admission_target_ids: list[list[str]] = []
        self.agent_admission_updates: list[dict[str, Any]] = []

    def load_items_for_brief_targets(self, *, news_item_ids: list[str]) -> list[dict[str, Any]]:
        if self.load_error is not None:
            raise self.load_error
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
            contexts.append(_agent_admission_context_for_candidate(candidate))
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

    def servable_news_item_ids(self, news_item_ids: list[str]) -> list[str]:
        return [str(news_item_id) for news_item_id in news_item_ids if str(news_item_id)]


class FakeDirtyRepository:
    def __init__(
        self,
        targets: list[dict[str, Any]] | None = None,
    ) -> None:
        self.targets = [dict(target) for target in targets or []]
        self.enqueued: list[dict[str, Any]] = []
        self.done: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.error_kwargs: list[dict[str, Any]] = []
        self.claim_kwargs: list[dict[str, Any]] = []
        self.claim_thread_ids: list[int] = []

    def claim_due(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.claim_thread_ids.append(threading.get_ident())
        self.claim_kwargs.append(dict(kwargs))
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


def _agent_admission_context_for_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "item": dict(candidate["item"]),
        "entities": [dict(row) for row in candidate.get("entities", [])],
        "token_mentions": [dict(row) for row in candidate.get("token_mentions", [])],
        "fact_candidates": [dict(row) for row in candidate.get("fact_candidates", [])],
        "exact_duplicate_candidates": [dict(row) for row in candidate.get("exact_duplicate_candidates", [])],
        "story_candidates": [dict(row) for row in candidate.get("story_candidates", [])],
    }


class FakeWakeBus:
    def __init__(self) -> None:
        self.brief_updates: list[int] = []

    def notify_news_item_brief_updated(self, *, count: int) -> None:
        self.brief_updates.append(count)
