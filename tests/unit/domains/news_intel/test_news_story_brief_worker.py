from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from parallax.domains.news_intel._constants import NEWS_STORY_IDENTITY_VERSION
from parallax.domains.news_intel.runtime import news_story_brief_worker as worker_module
from parallax.domains.news_intel.runtime.news_story_brief_worker import NewsStoryBriefWorker
from parallax.domains.news_intel.services.news_story_brief_input import build_news_story_brief_input_packet
from parallax.domains.news_intel.types.news_story_brief import (
    NEWS_STORY_BRIEF_LANE,
    default_news_story_brief_agent_config,
)
from parallax.platform.agent_execution import (
    AgentCapacityReservation,
    AgentExecutionError,
    AgentExecutionErrorClass,
    AgentExecutionResultAudit,
    AgentExecutionStatus,
)
from parallax.platform.config.settings import NewsStoryBriefWorkerSettings

NOW_MS = 1_779_000_000_000


def _news_story_brief_settings(**overrides: Any) -> NewsStoryBriefWorkerSettings:
    payload = {
        "batch_size": 5,
        "lease_ms": 120_000,
        "retry_ms": 60_000,
        "backpressure_cooldown_ms": 60_000,
        "statement_timeout_seconds": 30,
    }
    payload.update(overrides)
    return NewsStoryBriefWorkerSettings(**payload)


def test_worker_restores_completed_story_run_without_second_model_call() -> None:
    asyncio.run(_test_worker_restores_completed_story_run_without_second_model_call())


def test_worker_rejects_completed_story_run_missing_finished_at_without_clock_fallback() -> None:
    asyncio.run(_test_worker_rejects_completed_story_run_missing_finished_at_without_clock_fallback())


@pytest.mark.parametrize("finished_at_ms", [True, "1778999970000", 1_778_999_970_000.5, 0])
def test_worker_rejects_completed_story_run_malformed_finished_at_without_clock_fallback(
    finished_at_ms: object,
) -> None:
    asyncio.run(_test_worker_rejects_completed_story_run_malformed_finished_at_without_clock_fallback(finished_at_ms))


def test_worker_rejects_completed_story_run_missing_outcome_before_second_model_call() -> None:
    asyncio.run(_test_worker_rejects_completed_story_run_missing_outcome_before_second_model_call())


def test_worker_rejects_completed_story_run_missing_response_before_second_model_call() -> None:
    asyncio.run(_test_worker_rejects_completed_story_run_missing_response_before_second_model_call())


def test_worker_rejects_completed_story_run_missing_input_hash_before_second_model_call() -> None:
    asyncio.run(_test_worker_rejects_completed_story_run_missing_input_hash_before_second_model_call())


def test_worker_rejects_completed_story_run_ready_payload_missing_summary_before_second_model_call() -> None:
    asyncio.run(_test_worker_rejects_completed_story_run_ready_payload_missing_summary_before_second_model_call())


def test_worker_rejects_completed_story_run_ready_payload_summary_missing_without_market_read_fallback() -> None:
    asyncio.run(_test_worker_rejects_completed_story_run_ready_payload_summary_missing_without_market_read_fallback())


def test_worker_rejects_current_story_brief_missing_status_before_second_model_call() -> None:
    asyncio.run(_test_worker_rejects_current_story_brief_missing_status_before_second_model_call())


def test_worker_rejects_current_story_brief_missing_input_hash_before_second_model_call() -> None:
    asyncio.run(_test_worker_rejects_current_story_brief_missing_input_hash_before_second_model_call())


def test_worker_restores_failed_current_from_started_failed_story_run_without_second_model_call() -> None:
    asyncio.run(_test_worker_restores_failed_current_from_started_failed_story_run_without_second_model_call())


def test_worker_rejects_failed_story_run_missing_outcome_before_restore_or_model_call() -> None:
    asyncio.run(_test_worker_rejects_failed_story_run_missing_outcome_before_restore_or_model_call())


def test_worker_rejects_failed_story_run_missing_run_id_before_restore_or_model_call() -> None:
    asyncio.run(_test_worker_rejects_failed_story_run_missing_run_id_before_restore_or_model_call())


def test_worker_rejects_failed_story_run_missing_story_brief_key_before_restore_or_model_call() -> None:
    asyncio.run(_test_worker_rejects_failed_story_run_missing_story_brief_key_before_restore_or_model_call())


def test_worker_rejects_failed_story_run_missing_error_class_before_restore_or_model_call() -> None:
    asyncio.run(_test_worker_rejects_failed_story_run_missing_error_class_before_restore_or_model_call())


def test_worker_rejects_failed_story_run_missing_error_before_restore_or_model_call() -> None:
    asyncio.run(_test_worker_rejects_failed_story_run_missing_error_before_restore_or_model_call())


def test_worker_rejects_failed_story_run_missing_execution_started_before_restore_or_model_call() -> None:
    asyncio.run(_test_worker_rejects_failed_story_run_missing_execution_started_before_restore_or_model_call())


def test_worker_writes_ready_story_brief() -> None:
    asyncio.run(_test_worker_writes_ready_story_brief())


def test_worker_request_audit_failure_counts_as_failed_claim() -> None:
    asyncio.run(_test_worker_request_audit_failure_counts_as_failed_claim())


def test_worker_reservation_exception_fails_before_claim() -> None:
    asyncio.run(_test_worker_reservation_exception_fails_before_claim())


def test_worker_claim_failure_releases_reserved_capacity() -> None:
    asyncio.run(_test_worker_claim_failure_releases_reserved_capacity())


def test_worker_execute_no_start_backpressure_retries_without_run_or_attempt() -> None:
    asyncio.run(_test_worker_execute_no_start_backpressure_retries_without_run_or_attempt())


def test_worker_capacity_denied_requires_formal_agent_capacity_reservation() -> None:
    asyncio.run(_test_worker_capacity_denied_requires_formal_agent_capacity_reservation())


def test_worker_capacity_denied_requires_formal_reason_enum() -> None:
    asyncio.run(_test_worker_capacity_denied_requires_formal_reason_enum())


def test_worker_provider_error_class_requires_formal_enum_without_string_fallback() -> None:
    invalid_reason: Any = "rate_limited"
    with pytest.raises(RuntimeError, match="news_story_brief_agent_error_class_contract_required"):
        worker_module._reason_value(invalid_reason)


def test_worker_provider_started_failure_writes_failed_run_and_retries() -> None:
    asyncio.run(_test_worker_provider_started_failure_writes_failed_run_and_retries())


def test_worker_provider_error_audit_output_hash_does_not_repair_missing_explicit_output_hash() -> None:
    asyncio.run(_test_worker_provider_error_audit_output_hash_does_not_repair_missing_explicit_output_hash())


def test_worker_rejects_story_result_missing_latency_without_zero_default() -> None:
    asyncio.run(_test_worker_rejects_story_result_missing_latency_without_zero_default())


def test_worker_rejects_story_result_missing_usage_without_empty_default() -> None:
    asyncio.run(_test_worker_rejects_story_result_missing_usage_without_empty_default())


def test_worker_rejects_story_result_missing_trace_metadata_without_empty_default() -> None:
    asyncio.run(_test_worker_rejects_story_result_missing_trace_metadata_without_empty_default())


def test_worker_rejects_candidate_missing_member_items_without_model_call() -> None:
    asyncio.run(_test_worker_rejects_candidate_missing_member_items_without_model_call())


def test_worker_rejects_candidate_missing_story_key_without_marking_done() -> None:
    asyncio.run(_test_worker_rejects_candidate_missing_story_key_without_marking_done())


def test_worker_rejects_claim_missing_story_target_id_without_marking_done() -> None:
    asyncio.run(_test_worker_rejects_claim_missing_story_target_id_without_marking_done())


async def _test_worker_writes_ready_story_brief() -> None:
    db = FakeDB([_story_candidate()])
    provider = FakeStoryBriefProvider()
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.reserve_calls == 1
    assert provider.reserve_rate_units == [1]
    assert db.dirty.claim_kwargs[0]["limit"] == provider.reservation.rate_units
    assert provider.execution_calls == 1
    assert provider.reservation.acquired is False
    assert db.news.runs[0]["status"] == "completed"
    assert db.news.runs[0]["outcome"] == "ready"
    assert db.news.briefs[0]["status"] == "ready"
    assert db.news.briefs[0]["brief_json"]["summary_zh"] == "SOL ETF filing boosts attention."
    assert len(db.dirty.done) == 1
    assert result.processed == 1
    assert result.failed == 0
    assert result.notes["ready"] == 1


async def _test_worker_restores_completed_story_run_without_second_model_call() -> None:
    candidate = _story_candidate()
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "story-run-existing-ready",
        "story_brief_key": packet.story_brief_key,
        "story_key": packet.story_key,
        "story_identity_version": packet.story_identity_version,
        "representative_news_item_id": packet.representative_news_item_id,
        "member_news_item_ids_json": list(packet.member_news_item_ids),
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
    assert db.news.briefs[0]["agent_run_id"] == "story-run-existing-ready"
    assert db.news.briefs[0]["story_brief_key"] == packet.story_brief_key
    assert db.news.briefs[0]["member_news_item_ids_json"] == list(packet.member_news_item_ids)
    assert len(db.dirty.done) == 1
    assert db.dirty.enqueued == [
        {
            "rows": [
                {
                    "projection_name": "page",
                    "target_kind": "news_item",
                    "target_id": "news-item-1",
                    "source_watermark_ms": NOW_MS - 500,
                },
                {
                    "projection_name": "page",
                    "target_kind": "news_item",
                    "target_id": "news-item-2",
                    "source_watermark_ms": NOW_MS - 500,
                },
            ],
            "reason": "news_story_brief_updated",
            "now_ms": NOW_MS - 30_000,
        }
    ]
    assert result.processed == 1
    assert result.notes["ready"] == 1
    assert result.notes["restored_from_completed_run"] == 1


async def _test_worker_rejects_completed_story_run_missing_finished_at_without_clock_fallback() -> None:
    candidate = _story_candidate()
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "story-run-existing-ready",
        "story_brief_key": packet.story_brief_key,
        "story_key": packet.story_key,
        "story_identity_version": packet.story_identity_version,
        "representative_news_item_id": packet.representative_news_item_id,
        "member_news_item_ids_json": list(packet.member_news_item_ids),
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
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_run_finished_at_ms_required:completed_run"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_completed_story_run_malformed_finished_at_without_clock_fallback(
    finished_at_ms: object,
) -> None:
    candidate = _story_candidate()
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "story-run-existing-ready",
        "story_brief_key": packet.story_brief_key,
        "story_key": packet.story_key,
        "story_identity_version": packet.story_identity_version,
        "representative_news_item_id": packet.representative_news_item_id,
        "member_news_item_ids_json": list(packet.member_news_item_ids),
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
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_run_finished_at_ms_required:completed_run"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_completed_story_run_missing_outcome_before_second_model_call() -> None:
    candidate = _story_candidate()
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "story-run-existing-ready",
        "story_brief_key": packet.story_brief_key,
        "story_key": packet.story_key,
        "story_identity_version": packet.story_identity_version,
        "representative_news_item_id": packet.representative_news_item_id,
        "member_news_item_ids_json": list(packet.member_news_item_ids),
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
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_run_outcome_required:completed_run"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_completed_story_run_missing_response_before_second_model_call() -> None:
    candidate = _story_candidate()
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "story-run-existing-ready",
        "story_brief_key": packet.story_brief_key,
        "story_key": packet.story_key,
        "story_identity_version": packet.story_identity_version,
        "representative_news_item_id": packet.representative_news_item_id,
        "member_news_item_ids_json": list(packet.member_news_item_ids),
        "status": "completed",
        "outcome": "ready",
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
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_run_response_json_required:completed_run"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_completed_story_run_missing_input_hash_before_second_model_call() -> None:
    candidate = _story_candidate()
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "story-run-existing-ready",
        "story_brief_key": packet.story_brief_key,
        "story_key": packet.story_key,
        "story_identity_version": packet.story_identity_version,
        "representative_news_item_id": packet.representative_news_item_id,
        "member_news_item_ids_json": list(packet.member_news_item_ids),
        "status": "completed",
        "outcome": "ready",
        "execution_started": True,
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
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_run_input_hash_required:completed_run"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_completed_story_run_ready_payload_missing_summary_before_second_model_call() -> None:
    candidate = _story_candidate()
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    response_json = _ready_payload()
    response_json["summary_zh"] = ""
    response_json["market_read_zh"] = ""
    candidate["latest_run"] = {
        "run_id": "story-run-existing-ready",
        "story_brief_key": packet.story_brief_key,
        "story_key": packet.story_key,
        "story_identity_version": packet.story_identity_version,
        "representative_news_item_id": packet.representative_news_item_id,
        "member_news_item_ids_json": list(packet.member_news_item_ids),
        "status": "completed",
        "outcome": "ready",
        "execution_started": True,
        "input_hash": packet.input_hash,
        "artifact_version_hash": provider.artifact_version_hash,
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "validator_version": agent_config.validator_version,
        "finished_at_ms": NOW_MS - 30_000,
        "response_json": response_json,
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
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_run_publishable_summary_required:completed_run"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_completed_story_run_ready_payload_summary_missing_without_market_read_fallback() -> None:
    candidate = _story_candidate()
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    response_json = _ready_payload()
    response_json["summary_zh"] = ""
    response_json["market_read_zh"] = "Market read alone is not the publishable summary."
    candidate["latest_run"] = {
        "run_id": "story-run-existing-ready",
        "story_brief_key": packet.story_brief_key,
        "story_key": packet.story_key,
        "story_identity_version": packet.story_identity_version,
        "representative_news_item_id": packet.representative_news_item_id,
        "member_news_item_ids_json": list(packet.member_news_item_ids),
        "status": "completed",
        "outcome": "ready",
        "execution_started": True,
        "input_hash": packet.input_hash,
        "artifact_version_hash": provider.artifact_version_hash,
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "validator_version": agent_config.validator_version,
        "finished_at_ms": NOW_MS - 30_000,
        "response_json": response_json,
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
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_run_publishable_summary_required:completed_run"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_current_story_brief_missing_status_before_second_model_call() -> None:
    candidate = _story_candidate()
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["current_brief"] = {
        "story_brief_key": packet.story_brief_key,
        "story_key": packet.story_key,
        "story_identity_version": packet.story_identity_version,
        "agent_run_id": "story-current-run",
        "input_hash": packet.input_hash,
        "artifact_version_hash": provider.artifact_version_hash,
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "validator_version": agent_config.validator_version,
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
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_current_status_required"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_current_story_brief_missing_input_hash_before_second_model_call() -> None:
    candidate = _story_candidate()
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["current_brief"] = {
        "story_brief_key": packet.story_brief_key,
        "story_key": packet.story_key,
        "story_identity_version": packet.story_identity_version,
        "agent_run_id": "story-current-run",
        "status": "ready",
        "artifact_version_hash": provider.artifact_version_hash,
        "prompt_version": packet.prompt_version,
        "schema_version": packet.schema_version,
        "validator_version": agent_config.validator_version,
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
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_current_input_hash_required"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_restores_failed_current_from_started_failed_story_run_without_second_model_call() -> None:
    candidate = _story_candidate()
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "story-run-existing-timeout",
        "story_brief_key": packet.story_brief_key,
        "story_key": packet.story_key,
        "story_identity_version": packet.story_identity_version,
        "representative_news_item_id": packet.representative_news_item_id,
        "member_news_item_ids_json": list(packet.member_news_item_ids),
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
    assert db.news.briefs[0]["agent_run_id"] == "story-run-existing-timeout"
    assert db.news.briefs[0]["status"] == "failed"
    assert db.news.briefs[0]["input_hash"] == packet.input_hash
    assert db.news.briefs[0]["brief_json"]["data_gaps"] == [
        {
            "description_zh": "新闻故事智能摘要不可发布，终态原因：timeout；原因：model timed out",
            "severity": "high",
        }
    ]
    assert len(db.dirty.done) == 1
    assert db.dirty.enqueued == [
        {
            "rows": [
                {
                    "projection_name": "page",
                    "target_kind": "news_item",
                    "target_id": "news-item-1",
                    "source_watermark_ms": NOW_MS - 500,
                },
                {
                    "projection_name": "page",
                    "target_kind": "news_item",
                    "target_id": "news-item-2",
                    "source_watermark_ms": NOW_MS - 500,
                },
            ],
            "reason": "news_story_brief_updated",
            "now_ms": NOW_MS - 30_000,
        }
    ]
    assert result.processed == 0
    assert result.failed == 0
    assert result.skipped == 1
    assert result.notes["failed"] == 0
    assert result.notes["restored_from_failed_run"] == 1


async def _test_worker_rejects_failed_story_run_missing_outcome_before_restore_or_model_call() -> None:
    candidate = _story_candidate()
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "story-run-existing-timeout",
        "story_brief_key": packet.story_brief_key,
        "story_key": packet.story_key,
        "story_identity_version": packet.story_identity_version,
        "representative_news_item_id": packet.representative_news_item_id,
        "member_news_item_ids_json": list(packet.member_news_item_ids),
        "status": "failed",
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
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_run_outcome_required:failed_run"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_failed_story_run_missing_run_id_before_restore_or_model_call() -> None:
    candidate = _story_candidate()
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "story_brief_key": packet.story_brief_key,
        "story_key": packet.story_key,
        "story_identity_version": packet.story_identity_version,
        "representative_news_item_id": packet.representative_news_item_id,
        "member_news_item_ids_json": list(packet.member_news_item_ids),
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
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_run_id_required:failed_run"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_failed_story_run_missing_story_brief_key_before_restore_or_model_call() -> None:
    candidate = _story_candidate()
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "story-run-existing-timeout",
        "story_key": packet.story_key,
        "story_identity_version": packet.story_identity_version,
        "representative_news_item_id": packet.representative_news_item_id,
        "member_news_item_ids_json": list(packet.member_news_item_ids),
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
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_run_story_brief_key_required:failed_run"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_failed_story_run_missing_error_class_before_restore_or_model_call() -> None:
    candidate = _story_candidate()
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "story-run-existing-timeout",
        "story_brief_key": packet.story_brief_key,
        "story_key": packet.story_key,
        "story_identity_version": packet.story_identity_version,
        "representative_news_item_id": packet.representative_news_item_id,
        "member_news_item_ids_json": list(packet.member_news_item_ids),
        "status": "failed",
        "outcome": "failed",
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
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_run_error_class_required:failed_run"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_failed_story_run_missing_error_before_restore_or_model_call() -> None:
    candidate = _story_candidate()
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "story-run-existing-timeout",
        "story_brief_key": packet.story_brief_key,
        "story_key": packet.story_key,
        "story_identity_version": packet.story_identity_version,
        "representative_news_item_id": packet.representative_news_item_id,
        "member_news_item_ids_json": list(packet.member_news_item_ids),
        "status": "failed",
        "outcome": "failed",
        "error_class": "timeout",
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
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_run_error_required:failed_run"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_failed_story_run_missing_execution_started_before_restore_or_model_call() -> None:
    candidate = _story_candidate()
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    agent_config = provider.agent_config()
    candidate["latest_run"] = {
        "run_id": "story-run-existing-timeout",
        "story_brief_key": packet.story_brief_key,
        "story_key": packet.story_key,
        "story_identity_version": packet.story_identity_version,
        "representative_news_item_id": packet.representative_news_item_id,
        "member_news_item_ids_json": list(packet.member_news_item_ids),
        "status": "failed",
        "outcome": "failed",
        "error_class": "timeout",
        "error": "model timed out",
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
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_run_execution_started_required:failed_run"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_request_audit_failure_counts_as_failed_claim() -> None:
    db = FakeDB([_story_candidate()])
    provider = FakeStoryBriefProvider(request_error=RuntimeError("audit down"))
    worker = _worker(
        db=db,
        provider=provider,
        settings=_news_story_brief_settings(backpressure_cooldown_ms=12_000),
    )

    result = await worker.run_once()

    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["retry_ms"] == 60_000
    assert db.dirty.error_kwargs[0]["count_attempt"] is True
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_request_audit_failed"
    assert result.failed == 1
    assert result.skipped == 0
    assert result.notes["failed"] == 1
    assert result.notes["backpressure"] == 0


async def _test_worker_reservation_exception_fails_before_claim() -> None:
    db = FakeDB([_story_candidate()])
    provider = FakeStoryBriefProvider(reserve_error=RuntimeError("reserve exploded"))
    worker = _worker(db=db, provider=provider)

    with pytest.raises(RuntimeError, match="reserve exploded"):
        await worker.run_once()

    assert provider.reserve_calls == 1
    assert provider.execution_calls == 0
    assert db.dirty.claim_thread_ids == []
    assert db.news.runs == []
    assert db.news.briefs == []


async def _test_worker_claim_failure_releases_reserved_capacity() -> None:
    released: list[bool] = []
    reservation = AgentCapacityReservation(
        acquired=True,
        _release=lambda: released.append(True),
    )
    db = FakeDB([_story_candidate()])
    provider = FakeStoryBriefProvider(reservation=reservation)
    worker = _worker(db=db, provider=provider)

    def fail_claim(**kwargs: Any) -> list[dict[str, Any]]:
        del kwargs
        raise RuntimeError("claim failed")

    db.dirty.claim_due = fail_claim  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="claim failed"):
        await worker.run_once()

    assert released == [True]
    assert reservation.acquired is False
    assert provider.execution_calls == 0


async def _test_worker_execute_no_start_backpressure_retries_without_run_or_attempt() -> None:
    db = FakeDB([_story_candidate()])
    provider = FakeStoryBriefProvider(
        brief_error=AgentExecutionError(
            AgentExecutionErrorClass.RATE_LIMITED,
            "rate limited before provider start",
            execution_started=False,
        )
    )
    worker = _worker(
        db=db,
        provider=provider,
        settings=_news_story_brief_settings(backpressure_cooldown_ms=12_000),
    )

    result = await worker.run_once()

    assert provider.request_audit_calls
    assert provider.execution_calls == 1
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["retry_ms"] == 12_000
    assert db.dirty.error_kwargs[0]["count_attempt"] is False
    assert result.failed == 0
    assert result.skipped == 1
    assert result.notes["backpressure"] == 1
    assert result.notes["backpressure_rate_limited"] == 1


async def _test_worker_capacity_denied_requires_formal_agent_capacity_reservation() -> None:
    class LooseReservation:
        acquired = False
        reason = AgentExecutionErrorClass.CAPACITY_DENIED
        rate_units = 1

    db = FakeDB([_story_candidate()])
    loose_reservation: Any = LooseReservation()
    provider = FakeStoryBriefProvider(reservation=loose_reservation)
    worker = _worker(db=db, provider=provider)

    with pytest.raises(RuntimeError, match="news_story_brief_agent_reservation_contract_required"):
        await worker.run_once()


async def _test_worker_capacity_denied_requires_formal_reason_enum() -> None:
    db = FakeDB([_story_candidate()])
    reservation = AgentCapacityReservation(acquired=False)
    reservation.reason = "rate_limited"  # type: ignore[assignment]
    provider = FakeStoryBriefProvider(reservation=reservation)
    worker = _worker(db=db, provider=provider)

    with pytest.raises(RuntimeError, match="news_story_brief_agent_reservation_reason_contract_required"):
        await worker.run_once()


async def _test_worker_provider_started_failure_writes_failed_run_and_retries() -> None:
    db = FakeDB([_story_candidate()])
    provider = FakeStoryBriefProvider(brief_error=RuntimeError("provider broke after start"))
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls
    assert provider.execution_calls == 1
    assert len(db.news.runs) == 1
    assert db.news.runs[0]["status"] == "failed"
    assert db.news.runs[0]["outcome"] == "failed"
    assert db.news.runs[0]["error_class"] == "RuntimeError"
    assert db.news.runs[0]["execution_started"] is True
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["count_attempt"] is True
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_provider_error_audit_output_hash_does_not_repair_missing_explicit_output_hash() -> None:
    candidate = _story_candidate()
    db = FakeDB([candidate])
    provider = FakeStoryBriefProvider()
    packet = provider.packet_for_candidate(candidate)
    audit = AgentExecutionResultAudit(
        **provider._audit(run_id="run-story-error", packet=packet),
        status=AgentExecutionStatus.FAILED,
        output_hash="sha256:legacy-error-output",
        latency_ms=321.0,
        execution_started=True,
        error_class=AgentExecutionErrorClass.PROVIDER_ERROR,
        error_message="provider failed after start",
    )
    provider.brief_error = AgentExecutionError(
        AgentExecutionErrorClass.PROVIDER_ERROR,
        "provider failed after start",
        audit=audit,
        execution_started=True,
    )
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls
    assert provider.execution_calls == 1
    assert len(db.news.runs) == 1
    assert db.news.runs[0]["status"] == "failed"
    assert db.news.runs[0]["execution_started"] is True
    assert db.news.runs[0]["output_hash"] is None
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_story_result_missing_latency_without_zero_default() -> None:
    db = FakeDB([_story_candidate()])
    provider = FakeStoryBriefProvider(omit_result_latency=True)
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls
    assert provider.execution_calls == 1
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_audit_latency_ms_required"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_story_result_missing_usage_without_empty_default() -> None:
    db = FakeDB([_story_candidate()])
    provider = FakeStoryBriefProvider(omit_result_usage=True)
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls
    assert provider.execution_calls == 1
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_audit_usage_required"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_story_result_missing_trace_metadata_without_empty_default() -> None:
    db = FakeDB([_story_candidate()])
    provider = FakeStoryBriefProvider(omit_result_trace_metadata=True)
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls
    assert provider.execution_calls == 1
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_audit_trace_metadata_required"
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_candidate_missing_member_items_without_model_call() -> None:
    candidate = _story_candidate()
    candidate.pop("member_items")
    db = FakeDB([candidate])
    provider = FakeStoryBriefProvider()
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["count_attempt"] is True
    assert result.failed == 1
    assert result.notes["failed"] == 1


async def _test_worker_rejects_candidate_missing_story_key_without_marking_done() -> None:
    candidate = _story_candidate()
    db = FakeDB([candidate])
    db.news.candidates[0]["story"] = {}
    provider = FakeStoryBriefProvider()
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert result.failed == 1
    assert result.notes["load_failed"] == 1


async def _test_worker_rejects_claim_missing_story_target_id_without_marking_done() -> None:
    db = FakeDB([_story_candidate()])
    db.dirty.targets[0].pop("target_id")
    provider = FakeStoryBriefProvider()
    worker = _worker(db=db, provider=provider)

    result = await worker.run_once()

    assert provider.request_audit_calls == []
    assert provider.execution_calls == 0
    assert db.news.loaded_story_keys == []
    assert db.news.runs == []
    assert db.news.briefs == []
    assert db.dirty.done == []
    assert len(db.dirty.errors) == 1
    assert db.dirty.error_kwargs[0]["error"] == "news_story_brief_claim_target_id_required"
    assert db.dirty.error_kwargs[0]["count_attempt"] is True
    assert result.failed == 1
    assert result.notes["load_failed"] == 1


def test_worker_rejects_malformed_queue_depth_without_reserving_or_claiming() -> None:
    asyncio.run(_test_worker_rejects_malformed_queue_depth_without_reserving_or_claiming())


def test_worker_prunes_unreferenced_story_runs_at_most_once_per_hour() -> None:
    asyncio.run(_test_worker_prunes_unreferenced_story_runs_at_most_once_per_hour())


async def _test_worker_prunes_unreferenced_story_runs_at_most_once_per_hour() -> None:
    db = FakeDB([])
    db.news.pruned_story_runs = 2
    times = iter((NOW_MS, NOW_MS + 3_599_999, NOW_MS + 3_600_000))
    worker = NewsStoryBriefWorker(
        name="news_story_brief",
        settings=_news_story_brief_settings(batch_size=3),
        db=db,
        telemetry=object(),
        provider=FakeStoryBriefProvider(),
        clock_ms=lambda: next(times),
    )

    first = await worker.run_once()
    await worker.run_once()
    third = await worker.run_once()

    retention_ms = 180 * 24 * 60 * 60 * 1_000
    assert db.news.story_run_prune_calls == [
        {"cutoff_ms": NOW_MS - retention_ms, "limit": 500},
        {"cutoff_ms": NOW_MS + 3_600_000 - retention_ms, "limit": 500},
    ]
    assert first.notes["pruned_story_agent_runs"] == 2
    assert third.notes["pruned_story_agent_runs"] == 2


async def _test_worker_rejects_malformed_queue_depth_without_reserving_or_claiming() -> None:
    db = FakeDB([_story_candidate()])
    provider = FakeStoryBriefProvider()
    worker = _worker(db=db, provider=provider)

    def malformed_queue_depth(*, now_ms: int, projection_name: str | None = None) -> int:
        del now_ms, projection_name
        return -1

    db.dirty.queue_depth = malformed_queue_depth  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="news_story_brief_queue_depth_required"):
        await worker.run_once()

    assert provider.reserve_calls == 0
    assert db.dirty.claim_kwargs == []


@pytest.mark.parametrize("limit", [0, True, "1"])
def test_worker_rejects_malformed_claim_limit_before_session(limit: object) -> None:
    db = FakeDB([_story_candidate()])
    provider = FakeStoryBriefProvider()
    worker = _worker(db=db, provider=provider)

    with pytest.raises(RuntimeError, match="news_story_brief_claim_limit_required"):
        worker._claim_targets(now_ms=NOW_MS, limit=limit)  # type: ignore[arg-type]

    assert db.in_session is False
    assert db.dirty.claim_kwargs == []


def _worker(
    *,
    db: FakeDB,
    provider: FakeStoryBriefProvider,
    settings: NewsStoryBriefWorkerSettings | None = None,
) -> NewsStoryBriefWorker:
    provider.db = db
    return NewsStoryBriefWorker(
        name="news_story_brief",
        settings=settings or _news_story_brief_settings(),
        db=db,
        telemetry=object(),
        provider=provider,
        clock_ms=lambda: NOW_MS,
    )


def _story_candidate() -> dict[str, Any]:
    representative = {
        "news_item_id": "news-item-1",
        "title": "SOL ETF filing",
        "summary": "Issuer files for a SOL ETF.",
        "body_text": "Issuer files for a SOL ETF.",
        "canonical_url": "https://example.com/sol-etf",
        "published_at_ms": NOW_MS - 1_000,
        "fetched_at_ms": NOW_MS - 900,
        "content_hash": "content-hash-1",
        "market_scope_json": ["crypto"],
        "source_domain": "example.com",
        "source_name": "Example",
        "source_role": "observed_source",
        "trust_tier": "standard",
        "agent_admission_json": {
            "eligible": True,
            "status": "eligible",
            "reason": "eligible",
            "representative_news_item_id": "news-item-1",
            "basis": {"market_scope": ["crypto"]},
            "version": "news_item_agent_admission_market_v2",
        },
    }
    member = {
        **representative,
        "news_item_id": "news-item-2",
        "title": "SOL ETF filing update",
        "canonical_url": "https://example.com/sol-etf-update",
        "published_at_ms": NOW_MS - 500,
        "content_hash": "content-hash-2",
    }
    return {
        "story": {
            "story_key": "news-story:crypto:sol-etf",
            "story_identity_version": NEWS_STORY_IDENTITY_VERSION,
            "story_identity_json": {"story_key": "news-story:crypto:sol-etf"},
            "market_scope_json": {"scope": ["crypto"], "primary": "crypto"},
            "agent_admission_json": representative["agent_admission_json"],
        },
        "item": representative,
        "member_items": [representative, member],
        "entities": [],
        "token_mentions": [],
        "fact_candidates": [],
        "current_brief": None,
        "latest_run": None,
        "source_updated_at_ms": NOW_MS - 500,
    }


def _ready_payload() -> dict[str, Any]:
    return {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "event_type": "etf_filing",
        "summary_zh": "SOL ETF filing boosts attention.",
        "market_read_zh": "SOL ETF filing strengthens the regulatory narrative while timing remains uncertain.",
        "market_domains": ["crypto"],
        "transmission_paths": [
            {
                "market_domain": "crypto",
                "channel": "regulatory_attention",
                "direction": "bullish",
                "strength": "moderate",
                "explanation_zh": "ETF filing increases attention on the regulatory narrative.",
                "evidence_refs": ["item:summary"],
            }
        ],
        "bull_view": {
            "strength": "moderate",
            "thesis_zh": "ETF filing may sustain attention.",
            "evidence_refs": ["item:summary"],
        },
        "bear_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
        "affected_entities": [],
        "watch_triggers": ["Follow-up regulatory file updates"],
        "invalidation_conditions": ["Filing withdrawal"],
        "data_gaps": [],
        "evidence_refs": ["item:summary"],
    }


class FakeStoryBriefProvider:
    provider = "litellm"
    model = "gpt-5-mini"
    artifact_version_hash = "artifact-story-1"

    def __init__(
        self,
        *,
        request_error: Exception | None = None,
        brief_error: Exception | None = None,
        reserve_error: Exception | None = None,
        reservation: Any | None = None,
        omit_result_latency: bool = False,
        omit_result_usage: bool = False,
        omit_result_trace_metadata: bool = False,
    ) -> None:
        self.reservation = reservation or AgentCapacityReservation(acquired=True)
        self.reserve_calls = 0
        self.reserve_rate_units: list[int] = []
        self.request_audit_calls: list[str] = []
        self.execution_calls = 0
        self.db: FakeDB | None = None
        self.request_error = request_error
        self.brief_error = brief_error
        self.reserve_error = reserve_error
        self.omit_result_latency = omit_result_latency
        self.omit_result_usage = omit_result_usage
        self.omit_result_trace_metadata = omit_result_trace_metadata

    def try_reserve_execution(self, *, rate_units: int = 1) -> AgentCapacityReservation:
        assert self.db is None or self.db.in_session is False
        self.reserve_calls += 1
        self.reserve_rate_units.append(rate_units)
        if self.reserve_error is not None:
            raise self.reserve_error
        self.reservation.rate_units = rate_units
        return self.reservation

    def request_audit(self, *, run_id: str, packet: Any) -> dict[str, Any]:
        assert self.db is None or self.db.in_session is False
        self.request_audit_calls.append(run_id)
        if self.request_error is not None:
            raise self.request_error
        return self._audit(run_id=run_id, packet=packet)

    async def brief_story(self, *, run_id: str, packet: Any, reservation: Any | None = None) -> dict[str, Any]:
        del reservation
        self.execution_calls += 1
        if self.brief_error is not None:
            raise self.brief_error
        agent_run_audit = {
            **self._audit(run_id=run_id, packet=packet),
            "status": "done",
            "output_hash": "sha256:story-output",
            "latency_ms": 321.0,
        }
        if self.omit_result_latency:
            agent_run_audit.pop("latency_ms")
        if self.omit_result_usage:
            agent_run_audit.pop("usage")
        if self.omit_result_trace_metadata:
            agent_run_audit.pop("trace_metadata")
        return {
            "payload": _ready_payload(),
            "agent_run_audit": agent_run_audit,
        }

    def _audit(self, *, run_id: str, packet: Any) -> dict[str, Any]:
        config = self.agent_config()
        return {
            "provider": self.provider,
            "backend": "litellm_sdk",
            "model": self.model,
            "lane": NEWS_STORY_BRIEF_LANE,
            "stage": "news_story_brief",
            "workflow_name": config.workflow_name,
            "agent_name": config.agent_name,
            "execution_trace_id": f"trace-{run_id}",
            "group_id": f"news_story:{packet.story_key}",
            "prompt_version": packet.prompt_version,
            "schema_version": packet.schema_version,
            "artifact_version_hash": self.artifact_version_hash,
            "input_hash": packet.input_hash,
            "usage": {},
            "trace_metadata": {"run_id": run_id, "story_key": packet.story_key},
        }

    def packet_for_candidate(self, candidate: dict[str, Any]) -> Any:
        return build_news_story_brief_input_packet(
            story=dict(candidate["story"]),
            representative_item=dict(candidate["item"]),
            member_items=[dict(row) for row in candidate["member_items"]],
            entities=[dict(row) for row in candidate.get("entities", [])],
            token_mentions=[dict(row) for row in candidate.get("token_mentions", [])],
            fact_candidates=[dict(row) for row in candidate.get("fact_candidates", [])],
            agent_config=self.agent_config(),
        )

    def agent_config(self) -> Any:
        return default_news_story_brief_agent_config(
            model=self.model,
            artifact_version_hash=self.artifact_version_hash,
        )


class FakeDB:
    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self.news = FakeNewsRepository(candidates)
        self.conn = FakeConn()
        self.dirty = FakeDirtyRepository(
            [
                {
                    "projection_name": "story_brief",
                    "target_kind": "story",
                    "target_id": str(candidate["story"]["story_key"]),
                    "window": "",
                    "source_watermark_ms": NOW_MS - 500,
                    "payload_hash": f"payload:{candidate['story']['story_key']}",
                    "lease_owner": "news_story_brief",
                    "attempt_count": 1,
                }
                for candidate in candidates
            ]
        )
        self.in_session = False

    def worker_session(self, worker_name: str, statement_timeout_seconds: float | None = None) -> FakeSession:
        assert worker_name == "news_story_brief"
        assert statement_timeout_seconds == 30
        return FakeSession(self)


class FakeSession:
    def __init__(self, db: FakeDB) -> None:
        self.db = db
        self.news_story_agents = db.news
        self.news_items = db.news
        self.conn = db.conn
        self.news_projection_dirty_targets = db.dirty
        self.transaction = db.conn.transaction

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
        self.loaded_story_keys: list[list[str]] = []
        self.story_run_prune_calls: list[dict[str, int]] = []
        self.pruned_story_runs = 0

    def prune_unreferenced_story_agent_runs(self, *, cutoff_ms: int, limit: int) -> int:
        self.story_run_prune_calls.append({"cutoff_ms": cutoff_ms, "limit": limit})
        return self.pruned_story_runs

    def load_story_brief_targets(self, *, story_keys: list[str]) -> list[dict[str, Any]]:
        self.loaded_story_keys.append(list(story_keys))
        by_key = {str(candidate["story"]["story_key"]): candidate for candidate in self.candidates}
        return [by_key[story_key] for story_key in story_keys if story_key in by_key]

    def insert_news_story_agent_run(self, **payload: Any) -> dict[str, Any]:
        self.runs.append(dict(payload))
        return dict(payload)

    def upsert_news_story_agent_brief(self, **payload: Any) -> dict[str, Any]:
        self.briefs.append(dict(payload))
        return dict(payload)

    def servable_news_item_ids(self, news_item_ids: list[str]) -> list[str]:
        return [str(news_item_id) for news_item_id in news_item_ids if str(news_item_id)]


class FakeDirtyRepository:
    def __init__(self, targets: list[dict[str, Any]]) -> None:
        self.targets = [dict(target) for target in targets]
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
        del kwargs
        self.done.extend(dict(key) for key in keys)
        return len(keys)

    def mark_error(self, keys: list[dict[str, Any]], **kwargs: Any) -> int:
        self.errors.extend(dict(key) for key in keys)
        self.error_kwargs.append(dict(kwargs))
        return len(keys)

    def enqueue_targets(self, rows: list[dict[str, Any]], *, reason: str, now_ms: int) -> int:
        self.enqueued.append(
            {
                "rows": [dict(row) for row in rows],
                "reason": reason,
                "now_ms": now_ms,
            }
        )
        return len(rows)


class FakeConn:
    @contextmanager
    def transaction(self) -> Iterator[None]:
        yield
