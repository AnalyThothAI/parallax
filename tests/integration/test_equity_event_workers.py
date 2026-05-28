from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from types import SimpleNamespace
from typing import Any

import pytest

from gmgn_twitter_intel.app.runtime.provider_wiring.equity_events import EquityDocumentProviderFetchResult
from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_brief_worker import EquityEventBriefWorker
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_evidence_hydration_worker import (
    EquityEventEvidenceHydrationWorker,
    _evidence_document_status,
)
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_fetch_worker import EquityEventFetchWorker
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_page_projection_worker import (
    EquityEventPageProjectionWorker,
)
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_process_worker import EquityEventProcessWorker
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_source_reconcile_worker import (
    EquityEventSourceReconcileWorker,
)
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_story_projection_worker import (
    EquityEventStoryProjectionWorker,
)
from gmgn_twitter_intel.domains.equity_event_intel.services.sec_evidence import (
    build_failed_evidence_artifact,
    build_ready_html_text_artifact,
    build_unavailable_evidence_artifact,
)
from gmgn_twitter_intel.domains.equity_event_intel.types import EQUITY_EVENT_BRIEF_LANE, EquityEvidenceHydrationResult
from gmgn_twitter_intel.platform.agent_execution import AgentCapacityReservation
from gmgn_twitter_intel.platform.config.settings import Settings
from tests.postgres_test_utils import connect_postgres_test, reset_postgres_schema

NOW_MS = 1_765_900_000_000


@pytest.fixture
def postgres_conn(tmp_path) -> Iterator[object]:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        reset_postgres_schema(conn)
        yield conn
    finally:
        conn.close()


def test_source_reconcile_and_fetch_workers_write_sec_documents_outside_db_session(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    provider = _FakeEquityDocumentProvider(db)
    settings = Settings(
        equity_event_intel={
            "enabled": True,
            "companies": [
                {
                    "symbol": "MSFT",
                    "cik": "0000789019",
                    "company_name": "Microsoft Corp",
                    "exchange": "NASDAQ",
                    "universe": "mega_cap_software",
                }
            ],
            "expected_events": [
                {
                    "expected_event_id": "expected:MSFT:2026Q1",
                    "symbol": "MSFT",
                    "event_type": "earnings_release",
                    "fiscal_period": "2026Q1",
                    "expected_at_ms": NOW_MS + 86_400_000,
                    "source_id": "config:earnings",
                }
            ],
        }
    )
    with db.worker_session("seed") as repos:
        repos.registry.upsert_us_equity_symbol(
            symbol="MSFT",
            exchange="NASDAQ",
            security_name="Microsoft Corporation Common Stock",
            instrument_type="equity",
            source="test",
            source_updated_at_ms=NOW_MS,
            raw_payload={"Symbol": "MSFT"},
            observed_at_ms=NOW_MS,
        )

    source_worker = EquityEventSourceReconcileWorker(
        name="equity_event_source_reconcile",
        settings=settings.workers.equity_event_source_reconcile,
        db=db,
        telemetry=SimpleNamespace(),
        equity_settings=settings.equity_event_intel,
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )
    source_result = source_worker.run_once_sync()

    with db.worker_session("assert-reconcile") as repos:
        sources = repos.equity_events.list_source_status(limit=10)
        universe = postgres_conn.execute(
            "SELECT * FROM equity_event_universe_members WHERE company_id = %s",
            ("market_instrument:us_equity:MSFT",),
        ).fetchone()
        expected = postgres_conn.execute(
            "SELECT * FROM equity_expected_events WHERE expected_event_id = %s",
            ("expected:MSFT:2026Q1",),
        ).fetchone()

    assert source_result.processed == 1
    assert sources[0]["source_id"] == "sec:MSFT"
    assert sources[0]["provider_type"] == "sec_submissions"
    assert universe["company_name"] == "Microsoft Corporation Common Stock"
    assert universe["config_json"]["identity_status"] == "confirmed"
    assert expected["source_role"] == "calendar"
    assert wake_bus.sources_reconciled == [1]

    fetch_worker = EquityEventFetchWorker(
        name="equity_event_fetch",
        settings=settings.workers.equity_event_fetch,
        db=db,
        telemetry=SimpleNamespace(),
        document_provider=provider,
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS + 1_000,
    )
    fetch_result = fetch_worker.run_once_sync()

    provider_documents = postgres_conn.execute("SELECT * FROM equity_provider_documents").fetchall()
    event_documents = postgres_conn.execute("SELECT * FROM equity_event_documents").fetchall()
    fetch_runs = postgres_conn.execute("SELECT * FROM equity_event_fetch_runs").fetchall()

    assert fetch_result.processed == 1
    assert provider.called_while_db_session_active is False
    assert provider.calls[0]["cik"] == "0000789019"
    assert len(provider_documents) == 1
    assert provider_documents[0]["provider_document_key"] == "0000789019-26-000001:10-Q"
    assert len(event_documents) == 1
    assert event_documents[0]["document_type"] == "sec_filing"
    assert event_documents[0]["form_type"] == "10-Q"
    assert event_documents[0]["fiscal_period"] == "2026Q1"
    assert fetch_runs[0]["status"] == "success"
    assert wake_bus.evidence_jobs_written == [("sec:MSFT", 1)]
    assert wake_bus.documents_written == []

    hydration_result = _hydration_worker(
        db,
        provider=provider,
        wake_bus=wake_bus,
        now_ms=NOW_MS + 1_500,
    ).run_once_sync()
    assert wake_bus.documents_written == [("sec:MSFT", 1)]

    process_worker = EquityEventProcessWorker(
        name="equity_event_process",
        settings=settings.workers.equity_event_process,
        db=db,
        telemetry=SimpleNamespace(),
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS + 2_000,
    )
    process_result = process_worker.run_once_sync()

    story_worker = EquityEventStoryProjectionWorker(
        name="equity_event_story_projection",
        settings=settings.workers.equity_event_story_projection,
        db=db,
        telemetry=SimpleNamespace(),
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS + 3_000,
    )
    story_result = story_worker.run_once_sync()

    processed_document = postgres_conn.execute("SELECT * FROM equity_event_documents").fetchone()
    evidence_artifacts = postgres_conn.execute("SELECT * FROM equity_event_evidence_artifacts").fetchall()
    company_event = postgres_conn.execute("SELECT * FROM equity_company_events").fetchone()
    story_group = postgres_conn.execute("SELECT * FROM equity_event_story_groups").fetchone()
    story_member = postgres_conn.execute("SELECT * FROM equity_event_story_members").fetchone()

    assert process_result.processed == 1
    assert hydration_result.processed == 1
    assert processed_document["lifecycle_status"] == "processed"
    assert processed_document["evidence_status"] == "ready"
    assert len(evidence_artifacts) == 1
    assert evidence_artifacts[0]["extraction_status"] == "ready"
    assert company_event["event_type"] == "quarterly_report"
    assert company_event["priority"] == "P0"
    assert wake_bus.events_processed == [1]
    assert story_result.processed == 1
    assert story_group["event_count"] == 1
    assert story_member["company_event_id"] == company_event["company_event_id"]
    assert story_member["match_reason"] == "new_story"
    assert wake_bus.stories_updated == [1]


def test_expected_event_reconcile_preserves_observed_and_stales_removed_config(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    observed_id = "expected:MSFT:2026Q1"
    removed_id = "expected:MSFT:2026Q2"
    for expected_event_id, period in ((observed_id, "2026Q1"), (removed_id, "2026Q2")):
        repos.equity_events.upsert_expected_event(
            expected_event_id=expected_event_id,
            company_id="market_instrument:us_equity:MSFT",
            ticker="MSFT",
            event_type="earnings_release",
            fiscal_period=period,
            expected_at_ms=NOW_MS,
            source_id="config:earnings",
            source_role="calendar",
            now_ms=NOW_MS,
        )
    postgres_conn.execute(
        "UPDATE equity_expected_events SET status = 'observed' WHERE expected_event_id = %s",
        (observed_id,),
    )
    postgres_conn.commit()

    repos.equity_events.reconcile_expected_events(
        expected_events=[
            {
                "expected_event_id": observed_id,
                "company_id": "market_instrument:us_equity:MSFT",
                "ticker": "MSFT",
                "event_type": "earnings_release",
                "fiscal_period": "2026Q1",
                "expected_at_ms": NOW_MS + 1_000,
                "source_id": "config:earnings",
                "source_role": "calendar",
            }
        ],
        now_ms=NOW_MS + 2_000,
    )

    rows = {
        row["expected_event_id"]: row
        for row in postgres_conn.execute("SELECT * FROM equity_expected_events").fetchall()
    }
    assert rows[observed_id]["status"] == "observed"
    assert rows[observed_id]["expected_at_ms"] == NOW_MS + 1_000
    assert rows[removed_id]["status"] == "stale"


def test_source_reconcile_stales_expected_events_when_config_list_is_empty(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    settings = Settings(
        equity_event_intel={
            "enabled": True,
            "companies": [{"symbol": "MSFT", "cik": "0000789019"}],
            "expected_events": [],
        }
    )
    with db.worker_session("seed") as repos:
        repos.equity_events.upsert_expected_event(
            expected_event_id="expected:MSFT:2026Q1",
            company_id="market_instrument:us_equity:MSFT",
            ticker="MSFT",
            event_type="earnings_release",
            fiscal_period="2026Q1",
            expected_at_ms=NOW_MS,
            source_id="config:earnings",
            source_role="calendar",
            now_ms=NOW_MS,
        )

    worker = EquityEventSourceReconcileWorker(
        name="equity_event_source_reconcile",
        settings=settings.workers.equity_event_source_reconcile,
        db=db,
        telemetry=SimpleNamespace(),
        equity_settings=settings.equity_event_intel,
        wake_bus=None,
        clock_ms=lambda: NOW_MS + 1_000,
    )
    worker.run_once_sync()

    row = postgres_conn.execute(
        "SELECT status FROM equity_expected_events WHERE expected_event_id = %s",
        ("expected:MSFT:2026Q1",),
    ).fetchone()
    assert row["status"] == "stale"


def test_reconcile_sources_deactivates_removed_universe_members(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    repos.equity_events.reconcile_sources(
        sources=[
            _source_payload("MSFT"),
            _source_payload("AAPL"),
        ],
        universe_members=[
            _universe_payload("MSFT", active=True),
            _universe_payload("AAPL", active=True),
        ],
        now_ms=NOW_MS,
    )

    repos.equity_events.reconcile_sources(
        sources=[_source_payload("MSFT")],
        universe_members=[_universe_payload("MSFT", active=True)],
        now_ms=NOW_MS + 1_000,
    )

    rows = {
        row["ticker"]: row for row in postgres_conn.execute("SELECT * FROM equity_event_universe_members").fetchall()
    }
    assert rows["MSFT"]["active"] is True
    assert rows["AAPL"]["active"] is False


def test_claim_due_sources_skips_unsupported_provider_types(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    repos.equity_events.upsert_source(
        source_id="sec:MSFT",
        provider_type="sec_submissions",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        cik="0000789019",
        source_role="official_regulator",
        now_ms=NOW_MS,
        commit=False,
    )
    repos.equity_events.upsert_source(
        source_id="ir:MSFT",
        provider_type="company_ir_rss",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        cik="0000789019",
        source_role="official_issuer",
        now_ms=NOW_MS,
        commit=False,
    )
    postgres_conn.commit()

    claimed = repos.equity_events.claim_due_sources(now_ms=NOW_MS, limit=10)

    assert [row["source_id"] for row in claimed] == ["sec:MSFT"]


def test_duplicate_event_document_keeps_original_discovered_at_ms(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    repos.equity_events.upsert_source(
        source_id="sec:MSFT",
        provider_type="sec_submissions",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        cik="0000789019",
        source_role="official_regulator",
        now_ms=NOW_MS,
    )
    provider = repos.equity_events.upsert_provider_document(
        provider_document_id="provider-doc-1",
        source_id="sec:MSFT",
        fetch_run_id=None,
        provider_document_key="0000789019-26-000001:10-Q",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        cik="0000789019",
        document_url="https://www.sec.gov/Archives/edgar/data/789019/000078901926000001/msft.htm",
        payload_hash="hash-1",
        raw_payload_json={"form": "10-Q"},
        fetched_at_ms=NOW_MS,
    )
    repos.equity_events.upsert_event_document(
        event_document_id="event-doc-1",
        provider_document_id=provider["provider_document_id"],
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        cik="0000789019",
        source_id="sec:MSFT",
        source_role="official_regulator",
        document_type="sec_filing",
        form_type="10-Q",
        accession_number="0000789019-26-000001",
        fiscal_period="2026Q1",
        document_url="https://www.sec.gov/Archives/edgar/data/789019/000078901926000001/msft.htm",
        event_time_ms=NOW_MS,
        discovered_at_ms=NOW_MS,
        content_hash="content-1",
        now_ms=NOW_MS,
    )

    repos.equity_events.upsert_event_document(
        event_document_id="event-doc-1",
        provider_document_id=provider["provider_document_id"],
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        cik="0000789019",
        source_id="sec:MSFT",
        source_role="official_regulator",
        document_type="sec_filing",
        form_type="10-Q",
        accession_number="0000789019-26-000001",
        fiscal_period="2026Q1",
        document_url="https://www.sec.gov/Archives/edgar/data/789019/000078901926000001/msft.htm",
        event_time_ms=NOW_MS,
        discovered_at_ms=NOW_MS + 60_000,
        content_hash="content-1",
        now_ms=NOW_MS + 60_000,
    )

    row = postgres_conn.execute(
        """
        SELECT discovered_at_ms, updated_at_ms, lifecycle_status
          FROM equity_event_documents
         WHERE event_document_id = %s
        """,
        ("event-doc-1",),
    ).fetchone()
    assert row["discovered_at_ms"] == NOW_MS
    assert row["updated_at_ms"] == NOW_MS
    assert row["lifecycle_status"] == "raw"


def test_fetch_worker_records_structured_provider_failure(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    provider = _FailingEquityDocumentProvider()
    with db.worker_session("seed") as repos:
        repos.equity_events.upsert_source(
            source_id="sec:MSFT",
            provider_type="sec_submissions",
            company_id="market_instrument:us_equity:MSFT",
            ticker="MSFT",
            cik="0000789019",
            source_role="official_regulator",
            now_ms=NOW_MS,
        )
    worker = EquityEventFetchWorker(
        name="equity_event_fetch",
        settings=Settings().workers.equity_event_fetch,
        db=db,
        telemetry=SimpleNamespace(),
        document_provider=provider,
        wake_bus=None,
        clock_ms=lambda: NOW_MS + 1_000,
    )

    result = worker.run_once_sync()

    fetch_run = postgres_conn.execute("SELECT * FROM equity_event_fetch_runs").fetchone()
    assert result.failed == 1
    assert fetch_run["status"] == "failed_retryable"
    assert fetch_run["http_status"] == 503
    assert fetch_run["error"] == "missing_sec_user_agent"
    assert fetch_run["extra_json"]["error_code"] == "missing_sec_user_agent"
    assert fetch_run["extra_json"]["provider_document"]["status"] == "failed"


def test_fetch_worker_hydrates_sec_document_text_and_marks_evidence_ready(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    provider = _FakeEquityDocumentProvider(db)
    _seed_sec_source(postgres_conn)
    worker = _fetch_worker(db, provider=provider, wake_bus=wake_bus, now_ms=NOW_MS + 1_000)

    result = worker.run_once_sync()
    hydration_result = _hydration_worker(
        db,
        provider=provider,
        wake_bus=wake_bus,
        now_ms=NOW_MS + 1_500,
    ).run_once_sync()

    event_document = postgres_conn.execute("SELECT * FROM equity_event_documents").fetchone()
    artifacts = postgres_conn.execute("SELECT * FROM equity_event_evidence_artifacts").fetchall()
    source = postgres_conn.execute("SELECT * FROM equity_event_sources WHERE source_id = %s", ("sec:MSFT",)).fetchone()
    assert result.processed == 1
    assert hydration_result.processed == 1
    assert len(provider.hydration_calls) == 1
    assert provider.hydration_calls[0]["event_document_id"] == event_document["event_document_id"]
    assert provider.hydration_calls[0]["provider_document_id"] == event_document["provider_document_id"]
    assert provider.hydration_calls[0]["called_while_db_session_active"] is False
    assert event_document["evidence_status"] == "ready"
    assert event_document["evidence_ready_at_ms"] == NOW_MS + 1_500
    assert event_document["evidence_reason"] == ""
    assert len(artifacts) == 1
    assert artifacts[0]["extraction_status"] == "ready"
    assert "Revenue was $62.0 billion" in artifacts[0]["content_text"]
    assert source["last_material_document_at_ms"] == NOW_MS + 1_000
    assert source["last_evidence_ready_at_ms"] == NOW_MS + 1_500
    assert source["last_no_new_data_at_ms"] is None
    assert wake_bus.evidence_jobs_written == [("sec:MSFT", 1)]
    assert wake_bus.documents_written == [("sec:MSFT", 1)]


def test_fetch_worker_marks_evidence_unavailable_for_empty_sec_document(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    provider = _FakeEquityDocumentProvider(db, hydration_text="")
    _seed_sec_source(postgres_conn)
    worker = _fetch_worker(db, provider=provider, wake_bus=wake_bus, now_ms=NOW_MS + 1_000)

    result = worker.run_once_sync()
    hydration_result = _hydration_worker(
        db,
        provider=provider,
        wake_bus=wake_bus,
        now_ms=NOW_MS + 1_500,
    ).run_once_sync()

    event_document = postgres_conn.execute("SELECT * FROM equity_event_documents").fetchone()
    artifacts = postgres_conn.execute("SELECT * FROM equity_event_evidence_artifacts").fetchall()
    source = postgres_conn.execute("SELECT * FROM equity_event_sources WHERE source_id = %s", ("sec:MSFT",)).fetchone()
    assert result.processed == 1
    assert hydration_result.processed == 1
    assert event_document["evidence_status"] == "unavailable"
    assert event_document["evidence_reason"] == "evidence_hydration_empty"
    assert event_document["evidence_ready_at_ms"] is None
    assert len(artifacts) == 1
    assert artifacts[0]["extraction_status"] == "unavailable"
    assert artifacts[0]["failure_reason"] == "evidence_hydration_empty"
    assert source["last_material_document_at_ms"] == NOW_MS + 1_000
    assert source["last_evidence_ready_at_ms"] is None
    assert wake_bus.evidence_jobs_written == [("sec:MSFT", 1)]
    assert wake_bus.documents_written == [("sec:MSFT", 1)]
    assert provider.hydration_calls[0]["called_while_db_session_active"] is False


def test_fetch_worker_records_no_new_data_for_duplicate_only_fetch(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    provider = _FakeEquityDocumentProvider(db)
    _seed_sec_source(postgres_conn)

    first = _fetch_worker(db, provider=provider, wake_bus=wake_bus, now_ms=NOW_MS + 1_000).run_once_sync()
    hydration = _hydration_worker(
        db,
        provider=provider,
        wake_bus=wake_bus,
        now_ms=NOW_MS + 1_500,
    ).run_once_sync()
    postgres_conn.execute(
        "UPDATE equity_event_sources SET next_fetch_after_ms = %s WHERE source_id = %s",
        (NOW_MS + 1_500, "sec:MSFT"),
    )
    postgres_conn.commit()
    second = _fetch_worker(db, provider=provider, wake_bus=wake_bus, now_ms=NOW_MS + 2_000).run_once_sync()

    fetch_runs = postgres_conn.execute("SELECT * FROM equity_event_fetch_runs ORDER BY started_at_ms ASC").fetchall()
    source = postgres_conn.execute("SELECT * FROM equity_event_sources WHERE source_id = %s", ("sec:MSFT",)).fetchone()
    assert first.processed == 1
    assert hydration.processed == 1
    assert second.processed == 0
    assert fetch_runs[0]["inserted_count"] == 1
    assert fetch_runs[0]["updated_count"] == 0
    assert fetch_runs[0]["duplicate_count"] == 0
    assert fetch_runs[1]["inserted_count"] == 0
    assert fetch_runs[1]["updated_count"] == 0
    assert fetch_runs[1]["duplicate_count"] == 1
    assert len(provider.hydration_calls) == 1
    assert source["last_material_document_at_ms"] == NOW_MS + 1_000
    assert source["last_evidence_ready_at_ms"] == NOW_MS + 1_500
    assert source["last_no_new_data_at_ms"] == NOW_MS + 2_000
    assert wake_bus.evidence_jobs_written == [("sec:MSFT", 1)]
    assert wake_bus.documents_written == [("sec:MSFT", 1)]


def test_fetch_worker_marks_hydration_exception_as_failed_evidence(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    provider = _FakeEquityDocumentProvider(db, hydration_exception=RuntimeError("boom"))
    _seed_sec_source(postgres_conn)

    first = _fetch_worker(db, provider=provider, wake_bus=wake_bus, now_ms=NOW_MS + 1_000).run_once_sync()
    hydration_1 = _hydration_worker(db, provider=provider, wake_bus=wake_bus, now_ms=NOW_MS + 1_500).run_once_sync()
    postgres_conn.execute(
        "UPDATE equity_event_sources SET next_fetch_after_ms = %s WHERE source_id = %s",
        (NOW_MS + 1_500, "sec:MSFT"),
    )
    postgres_conn.commit()
    second = _fetch_worker(db, provider=provider, wake_bus=wake_bus, now_ms=NOW_MS + 2_000).run_once_sync()
    hydration_2 = _hydration_worker(db, provider=provider, wake_bus=wake_bus, now_ms=NOW_MS + 62_000).run_once_sync()
    hydration_3 = _hydration_worker(db, provider=provider, wake_bus=wake_bus, now_ms=NOW_MS + 123_000).run_once_sync()

    event_document = postgres_conn.execute("SELECT * FROM equity_event_documents").fetchone()
    artifacts = postgres_conn.execute("SELECT * FROM equity_event_evidence_artifacts").fetchall()
    source = postgres_conn.execute("SELECT * FROM equity_event_sources WHERE source_id = %s", ("sec:MSFT",)).fetchone()
    fetch_runs = postgres_conn.execute("SELECT * FROM equity_event_fetch_runs ORDER BY started_at_ms ASC").fetchall()
    assert first.processed == 1
    assert first.failed == 0
    assert second.processed == 0
    assert hydration_1.failed == 1
    assert hydration_2.failed == 1
    assert hydration_3.processed == 1
    assert event_document["evidence_status"] == "failed"
    assert event_document["evidence_reason"] == "evidence_hydration_exception:RuntimeError"
    assert len(artifacts) == 1
    assert artifacts[0]["extraction_status"] == "failed"
    assert artifacts[0]["failure_reason"] == "evidence_hydration_exception:RuntimeError"
    assert source["last_actionable_error"] == "evidence_hydration_exception:RuntimeError"
    assert fetch_runs[0]["status"] == "success"
    assert fetch_runs[1]["duplicate_count"] == 1
    assert len(provider.hydration_calls) == 3
    assert wake_bus.evidence_jobs_written == [("sec:MSFT", 1)]
    assert wake_bus.documents_written == [("sec:MSFT", 1)]


def test_evidence_document_status_handles_mixed_artifacts() -> None:
    ready = build_ready_html_text_artifact(
        event_document_id="event-doc-status",
        source_url="https://example.test/doc.htm",
        content_text="Revenue was $62.0 billion.",
        fetched_at_ms=NOW_MS,
        parsed_at_ms=NOW_MS,
        now_ms=NOW_MS,
    )
    unavailable = build_unavailable_evidence_artifact(
        event_document_id="event-doc-status",
        artifact_kind="companyfacts",
        source_url="https://example.test/companyfacts.json",
        reason="companyfacts_missing",
        fetched_at_ms=NOW_MS,
        parsed_at_ms=NOW_MS,
        now_ms=NOW_MS,
    )
    failed = build_failed_evidence_artifact(
        event_document_id="event-doc-status",
        artifact_kind="html_text",
        source_url="https://example.test/doc.htm",
        reason="sec_transport_error",
        fetched_at_ms=NOW_MS,
        parsed_at_ms=NOW_MS,
        now_ms=NOW_MS,
    )

    assert _evidence_document_status([ready, unavailable], fetched_at_ms=NOW_MS) == ("ready", "", NOW_MS)
    assert _evidence_document_status([ready, failed], fetched_at_ms=NOW_MS) == ("ready", "", NOW_MS)
    assert _evidence_document_status([unavailable], fetched_at_ms=NOW_MS) == (
        "unavailable",
        "companyfacts_missing",
        None,
    )
    assert _evidence_document_status([failed], fetched_at_ms=NOW_MS) == ("failed", "sec_transport_error", None)
    assert _evidence_document_status([failed, unavailable], fetched_at_ms=NOW_MS) == (
        "unavailable",
        "sec_transport_error",
        None,
    )


def test_process_worker_marks_identity_mismatch_event_attention(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    _seed_processable_document(
        postgres_conn,
        company_id="not-a-market-instrument",
        ticker="MSFT",
        event_document_id="event-doc-identity",
        provider_document_id="provider-doc-identity",
    )

    result = _process_worker(db, now_ms=NOW_MS + 1_000).run_once_sync()

    event = postgres_conn.execute("SELECT * FROM equity_company_events").fetchone()
    assert result.processed == 1
    assert event["validation_status"] == "attention"


def test_process_worker_extracts_facts_from_ready_evidence_artifacts(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    _seed_processable_document(
        postgres_conn,
        event_document_id="event-doc-evidence-ready",
        provider_document_id="provider-doc-evidence-ready",
        evidence_text="Revenue was $64.0 billion for the quarter. EPS was $3.12.",
    )

    result = _process_worker(db, now_ms=NOW_MS + 1_000).run_once_sync()

    document = postgres_conn.execute("SELECT * FROM equity_event_documents").fetchone()
    spans = postgres_conn.execute("SELECT * FROM equity_event_source_spans").fetchall()
    facts = postgres_conn.execute("SELECT * FROM equity_event_fact_candidates ORDER BY fact_type").fetchall()
    assert result.processed == 1
    assert document["fact_extraction_status"] == "ready"
    assert document["fact_extraction_reason"] == ""
    assert document["fact_extracted_at_ms"] == NOW_MS + 1_000
    assert len(spans) == 1
    assert spans[0]["span_type"] == "evidence_artifact_text"
    assert {fact["fact_type"] for fact in facts} == {"eps_actual", "revenue_actual"}
    assert {fact["source_span_id"] for fact in facts} == {spans[0]["span_id"]}


def test_process_worker_ignores_raw_payload_text_without_ready_evidence(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    _seed_processable_document(
        postgres_conn,
        event_document_id="event-doc-raw-only",
        provider_document_id="provider-doc-raw-only",
        raw_payload_json={
            "title": "Quarterly report",
            "body_text": "Revenue was $99.0 billion. EPS was $9.99.",
        },
        evidence_status="ready",
        evidence_text="",
    )

    result = _process_worker(db, now_ms=NOW_MS + 1_000).run_once_sync()

    document = postgres_conn.execute("SELECT * FROM equity_event_documents").fetchone()
    spans = postgres_conn.execute("SELECT * FROM equity_event_source_spans").fetchall()
    facts = postgres_conn.execute("SELECT * FROM equity_event_fact_candidates").fetchall()
    assert result.processed == 1
    assert document["lifecycle_status"] == "processed"
    assert document["fact_extraction_status"] == "no_evidence"
    assert spans == []
    assert facts == []


@pytest.mark.parametrize("evidence_status", ["unavailable", "failed"])
def test_process_worker_keeps_event_for_missing_evidence_statuses(postgres_conn, evidence_status: str) -> None:
    db = _WorkerDb(postgres_conn)
    reason = f"{evidence_status}_reason"
    _seed_processable_document(
        postgres_conn,
        event_document_id=f"event-doc-{evidence_status}",
        provider_document_id=f"provider-doc-{evidence_status}",
        evidence_status=evidence_status,
        evidence_reason=reason,
        evidence_text="",
    )

    result = _process_worker(db, now_ms=NOW_MS + 1_000).run_once_sync()

    document = postgres_conn.execute("SELECT * FROM equity_event_documents").fetchone()
    event = postgres_conn.execute("SELECT * FROM equity_company_events").fetchone()
    dirty_targets = postgres_conn.execute(
        "SELECT projection_name FROM equity_event_projection_dirty_targets"
    ).fetchall()
    assert result.processed == 1
    assert document["lifecycle_status"] == "processed"
    assert document["fact_extraction_status"] == "no_evidence"
    assert document["fact_extraction_reason"] == reason
    assert event["evidence_status"] == evidence_status
    assert event["evidence_reason"] == reason
    assert {row["projection_name"] for row in dirty_targets} >= {
        "page",
        "timeline",
        "story",
        "brief_input",
        "alert",
    }


def test_process_worker_marks_no_extractable_facts_for_ready_evidence_without_metrics(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    _seed_processable_document(
        postgres_conn,
        event_document_id="event-doc-no-facts",
        provider_document_id="provider-doc-no-facts",
        evidence_text="Microsoft filed its quarterly report and discussed operating momentum.",
    )

    result = _process_worker(db, now_ms=NOW_MS + 1_000).run_once_sync()

    document = postgres_conn.execute("SELECT * FROM equity_event_documents").fetchone()
    spans = postgres_conn.execute("SELECT * FROM equity_event_source_spans").fetchall()
    facts = postgres_conn.execute("SELECT * FROM equity_event_fact_candidates").fetchall()
    assert result.processed == 1
    assert document["fact_extraction_status"] == "no_extractable_facts"
    assert document["fact_extraction_reason"] == "no_revenue_or_eps_facts"
    assert len(spans) == 1
    assert facts == []


def test_process_worker_marks_attention_candidates_as_fact_extraction_ready(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    _seed_processable_document(
        postgres_conn,
        event_document_id="event-doc-attention-fact",
        provider_document_id="provider-doc-attention-fact",
        fiscal_period=None,
        evidence_text="Revenue was $64.0 billion for the quarter.",
    )

    result = _process_worker(db, now_ms=NOW_MS + 1_000).run_once_sync()

    document = postgres_conn.execute("SELECT * FROM equity_event_documents").fetchone()
    facts = postgres_conn.execute("SELECT * FROM equity_event_fact_candidates").fetchall()
    assert result.processed == 1
    assert document["fact_extraction_status"] == "ready"
    assert document["fact_extracted_at_ms"] == NOW_MS + 1_000
    assert len(facts) == 1
    assert facts[0]["validation_status"] == "attention"
    assert facts[0]["rejection_reasons_json"] == ["missing_slot:period"]


def test_process_worker_retries_process_failed_documents(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    _seed_processable_document(
        postgres_conn,
        event_document_id="event-doc-retry",
        provider_document_id="provider-doc-retry",
    )
    postgres_conn.execute(
        """
        UPDATE equity_event_documents
           SET lifecycle_status = 'process_failed',
               processing_attempts = 1,
               processing_error = 'transient'
         WHERE event_document_id = %s
        """,
        ("event-doc-retry",),
    )
    postgres_conn.commit()

    result = _process_worker(db, now_ms=NOW_MS + 1_000).run_once_sync()

    document = postgres_conn.execute("SELECT * FROM equity_event_documents").fetchone()
    assert result.processed == 1
    assert document["lifecycle_status"] == "processed"
    assert document["processing_error"] is None


def test_process_worker_claims_newest_raw_documents_first(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    _seed_processable_document(
        postgres_conn,
        event_document_id="event-doc-old-backfill",
        provider_document_id="provider-doc-old-backfill",
        provider_document_key="0000789019-19-000001:10-Q",
        accession_number="0000789019-19-000001",
        content_hash="content-old-backfill",
        event_time_ms=NOW_MS - 7 * 365 * 24 * 60 * 60 * 1000,
    )
    _seed_processable_document(
        postgres_conn,
        event_document_id="event-doc-new-live",
        provider_document_id="provider-doc-new-live",
        provider_document_key="0000789019-26-000999:8-K",
        accession_number="0000789019-26-000999",
        form_type="8-K",
        provider_summary="Results of Operations and Financial Condition",
        raw_payload_json={
            "title": "Results of Operations and Financial Condition",
            "body_text": "Revenue was $63.0 billion.",
        },
        content_hash="content-new-live",
        event_time_ms=NOW_MS + 60_000,
    )

    result = _process_worker(db, now_ms=NOW_MS + 1_000, batch_size=1).run_once_sync()

    statuses = {
        row["event_document_id"]: row["lifecycle_status"]
        for row in postgres_conn.execute(
            """
            SELECT event_document_id, lifecycle_status
              FROM equity_event_documents
             WHERE event_document_id IN (%s, %s)
            """,
            ("event-doc-old-backfill", "event-doc-new-live"),
        ).fetchall()
    }
    event = postgres_conn.execute("SELECT * FROM equity_company_events").fetchone()
    assert result.processed == 1
    assert statuses == {"event-doc-old-backfill": "raw", "event-doc-new-live": "processed"}
    assert event["primary_document_id"] == "event-doc-new-live"


def test_reprocessing_updated_document_clears_stale_story_membership(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    repos = repositories_for_connection(postgres_conn)
    provider = _seed_processable_document(
        postgres_conn,
        event_document_id="event-doc-update",
        provider_document_id="provider-doc-update",
        provider_document_key="0000789019-26-000777:10-Q",
        accession_number="0000789019-26-000777",
        form_type="10-Q",
        raw_payload_json={"title": "Quarterly report", "body_text": "Revenue was $62.0 billion."},
        content_hash="content-original",
    )

    _process_worker(db, now_ms=NOW_MS + 1_000).run_once_sync()
    _story_worker(db, now_ms=NOW_MS + 2_000).run_once_sync()
    old_member = postgres_conn.execute("SELECT * FROM equity_event_story_members").fetchone()
    old_event_id = old_member["company_event_id"]

    repos.equity_events.upsert_provider_document(
        provider_document_id=provider["provider_document_id"],
        source_id="sec:MSFT",
        fetch_run_id=None,
        provider_document_key="0000789019-26-000777:10-Q",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        cik="0000789019",
        document_url="https://www.sec.gov/Archives/edgar/data/789019/000078901926000777/msft.htm",
        payload_hash="hash-updated",
        raw_payload_json={
            "title": "Results of Operations and Financial Condition",
            "body_text": "Revenue was $63.0 billion.",
        },
        fetched_at_ms=NOW_MS + 3_000,
    )
    repos.equity_events.upsert_event_document(
        event_document_id="event-doc-update",
        provider_document_id=provider["provider_document_id"],
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        cik="0000789019",
        source_id="sec:MSFT",
        source_role="official_regulator",
        document_type="sec_filing",
        form_type="8-K",
        accession_number="0000789019-26-000777",
        fiscal_period="2026Q1",
        document_url="https://www.sec.gov/Archives/edgar/data/789019/000078901926000777/msft.htm",
        event_time_ms=NOW_MS + 3_000,
        discovered_at_ms=NOW_MS + 3_000,
        content_hash="content-updated",
        now_ms=NOW_MS + 3_000,
        provider_title="MSFT 8-K",
        provider_summary="Results of Operations and Financial Condition",
    )
    repos.equity_events.mark_event_document_evidence_status(
        event_document_id="event-doc-update",
        evidence_status="ready",
        evidence_reason="",
        evidence_ready_at_ms=NOW_MS + 3_000,
        now_ms=NOW_MS + 3_000,
    )
    repos.equity_events.enqueue_process_job_for_document(
        event_document_id="event-doc-update",
        due_at_ms=NOW_MS + 3_000,
        now_ms=NOW_MS + 3_000,
    )

    _process_worker(db, now_ms=NOW_MS + 4_000).run_once_sync()
    _story_worker(db, now_ms=NOW_MS + 5_000).run_once_sync()

    members = postgres_conn.execute("SELECT * FROM equity_event_story_members").fetchall()
    assert old_event_id not in {member["company_event_id"] for member in members}
    assert len(members) == 1


def test_story_projection_rebuilds_members_after_partial_truncation(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    _seed_processable_document(
        postgres_conn,
        event_document_id="event-doc-story-1",
        provider_document_id="provider-doc-story-1",
        provider_document_key="0000789019-26-000101:10-Q",
        accession_number="0000789019-26-000101",
    )
    _seed_processable_document(
        postgres_conn,
        event_document_id="event-doc-story-2",
        provider_document_id="provider-doc-story-2",
        provider_document_key="0000789019-26-000102:8-K",
        accession_number="0000789019-26-000102",
        form_type="8-K",
        provider_summary="Results of Operations and Financial Condition",
        raw_payload_json={
            "title": "Results of Operations and Financial Condition",
            "body_text": "Revenue was $62.0 billion.",
        },
    )

    _process_worker(db, now_ms=NOW_MS + 1_000).run_once_sync()
    _story_worker(db, now_ms=NOW_MS + 2_000).run_once_sync()
    postgres_conn.execute("DELETE FROM equity_event_story_members")
    postgres_conn.commit()
    company_event_ids = [
        str(row["company_event_id"])
        for row in postgres_conn.execute(
            "SELECT company_event_id FROM equity_company_events ORDER BY company_event_id ASC"
        ).fetchall()
    ]
    _enqueue_company_event_projection_targets(
        postgres_conn,
        company_event_ids=company_event_ids,
        projection_names=["story"],
        now_ms=NOW_MS + 2_500,
    )

    result = _story_worker(db, now_ms=NOW_MS + 3_000).run_once_sync()

    members = postgres_conn.execute("SELECT * FROM equity_event_story_members").fetchall()
    assert result.processed == 2
    assert len(members) == 2
    assert len({member["story_id"] for member in members}) == 1


def test_page_projection_worker_rebuilds_read_models_after_page_truncation(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    _seed_page_projection_source(postgres_conn)

    first_result = _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 3_000, batch_size=10).run_once_sync()

    page_rows = postgres_conn.execute("SELECT * FROM equity_event_page_rows").fetchall()
    calendar_rows = postgres_conn.execute("SELECT * FROM equity_event_calendar_rows").fetchall()
    alert_rows = postgres_conn.execute("SELECT * FROM equity_event_alert_candidates").fetchall()
    timeline_rows = postgres_conn.execute("SELECT * FROM equity_company_timeline_rows").fetchall()
    assert first_result.processed == 2
    assert len(page_rows) == 1
    assert page_rows[0]["headline"] == "MSFT 2026Q1 quarterly report"
    assert len(calendar_rows) == 1
    assert calendar_rows[0]["status"] == "matched"
    assert len(alert_rows) == 1
    assert alert_rows[0]["ticker"] == "MSFT"
    assert len(timeline_rows) == 1
    assert timeline_rows[0]["company_event_id"] == page_rows[0]["company_event_id"]

    postgres_conn.execute("DELETE FROM equity_event_page_rows")
    _enqueue_company_event_projection_targets(
        postgres_conn,
        company_event_ids=[page_rows[0]["company_event_id"]],
        projection_names=["page"],
        now_ms=NOW_MS + 4_000,
    )
    postgres_conn.commit()

    rebuild_result = _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 4_000).run_once_sync()

    rebuilt_rows = postgres_conn.execute("SELECT * FROM equity_event_page_rows").fetchall()
    assert rebuild_result.processed == 1
    assert len(rebuilt_rows) == 1
    assert rebuilt_rows[0]["company_event_id"] == page_rows[0]["company_event_id"]
    assert wake_bus.pages_updated == [2, 1]


def test_page_projection_worker_is_idle_when_read_models_are_current(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    _seed_page_projection_source(postgres_conn)

    first_result = _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 3_000, batch_size=10).run_once_sync()
    idle_result = _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 4_000, batch_size=10).run_once_sync()

    assert first_result.processed == 2
    assert idle_result.processed == 0
    assert wake_bus.pages_updated == [2]


def test_page_projection_worker_rebuilds_expected_calendar_row_after_due_time_passes(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    _seed_future_expected_event(postgres_conn, expected_at_ms=NOW_MS + 5_000)

    first_result = _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 1_000, batch_size=10).run_once_sync()
    first_row = postgres_conn.execute(
        "SELECT status, computed_at_ms FROM equity_event_calendar_rows WHERE expected_event_id = %s",
        ("expected:MSFT:2026Q2",),
    ).fetchone()

    due_result = _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 6_000, batch_size=10).run_once_sync()
    due_row = postgres_conn.execute(
        "SELECT status, computed_at_ms FROM equity_event_calendar_rows WHERE expected_event_id = %s",
        ("expected:MSFT:2026Q2",),
    ).fetchone()

    assert first_result.processed == 1
    assert first_row["status"] == "expected"
    assert due_result.processed == 1
    assert due_row["status"] == "missed"
    assert due_row["computed_at_ms"] == NOW_MS + 6_000
    assert wake_bus.pages_updated == [1, 1]


def test_page_projection_worker_acknowledges_source_watermark_without_rescanning(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    _seed_page_projection_source(postgres_conn)

    first_result = _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 3_000, batch_size=10).run_once_sync()
    before = postgres_conn.execute(
        """
        SELECT company_event_id, computed_at_ms, source_watermark_ms, payload_hash
          FROM equity_event_page_rows
        """
    ).fetchone()
    postgres_conn.execute(
        """
        UPDATE equity_event_story_groups
           SET updated_at_ms = %s
        """,
        (NOW_MS + 9_000,),
    )
    _enqueue_company_event_projection_targets(
        postgres_conn,
        company_event_ids=[before["company_event_id"]],
        projection_names=["page"],
        now_ms=NOW_MS + 10_000,
    )
    postgres_conn.commit()

    ack_result = _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 10_000, batch_size=10).run_once_sync()
    after_ack = postgres_conn.execute(
        """
        SELECT computed_at_ms, source_watermark_ms, payload_hash
          FROM equity_event_page_rows
        """
    ).fetchone()
    idle_result = _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 11_000, batch_size=10).run_once_sync()

    assert first_result.processed == 2
    assert ack_result.processed == 1
    assert idle_result.processed == 0
    assert after_ack["source_watermark_ms"] == NOW_MS + 9_000
    assert after_ack["computed_at_ms"] == before["computed_at_ms"]
    assert after_ack["payload_hash"] == before["payload_hash"]
    assert wake_bus.pages_updated == [2, 1]


def test_page_projection_worker_wakes_for_matched_calendar_only_rebuild(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    _seed_page_projection_source(postgres_conn)
    _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 3_000, batch_size=10).run_once_sync()

    postgres_conn.execute(
        "DELETE FROM equity_event_calendar_rows WHERE expected_event_id = %s",
        ("expected:MSFT:2026Q1",),
    )
    _enqueue_expected_event_projection_targets(
        postgres_conn,
        expected_event_ids=["expected:MSFT:2026Q1"],
        now_ms=NOW_MS + 4_000,
    )
    postgres_conn.commit()

    result = _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 4_000, batch_size=10).run_once_sync()

    calendar_row = postgres_conn.execute(
        "SELECT * FROM equity_event_calendar_rows WHERE expected_event_id = %s",
        ("expected:MSFT:2026Q1",),
    ).fetchone()
    assert result.processed > 0
    assert calendar_row is not None
    assert calendar_row["status"] == "matched"
    assert wake_bus.pages_updated == [2, 1]


def test_page_projection_worker_rebuilds_missing_alert_candidate_for_older_current_page_row(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    _seed_page_projection_source(postgres_conn, include_newer_event=True)
    _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 3_000, batch_size=10).run_once_sync()
    older_event_id = _company_event_id_for_document(postgres_conn, "event-doc-page-msft")

    postgres_conn.execute(
        "DELETE FROM equity_event_alert_candidates WHERE company_event_id = %s",
        (older_event_id,),
    )
    _enqueue_company_event_projection_targets(
        postgres_conn,
        company_event_ids=[older_event_id],
        projection_names=["alert"],
        now_ms=NOW_MS + 4_000,
    )
    postgres_conn.commit()

    result = _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 4_000, batch_size=1).run_once_sync()

    rebuilt_alert = postgres_conn.execute(
        "SELECT * FROM equity_event_alert_candidates WHERE company_event_id = %s",
        (older_event_id,),
    ).fetchone()
    assert result.processed == 1
    assert rebuilt_alert is not None
    assert rebuilt_alert["ticker"] == "MSFT"


def test_page_projection_worker_rebuilds_missing_timeline_row_for_older_current_page_row(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    _seed_page_projection_source(postgres_conn, include_newer_event=True)
    _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 3_000, batch_size=10).run_once_sync()
    older_event_id = _company_event_id_for_document(postgres_conn, "event-doc-page-msft")

    postgres_conn.execute(
        "DELETE FROM equity_company_timeline_rows WHERE company_event_id = %s",
        (older_event_id,),
    )
    _enqueue_company_event_projection_targets(
        postgres_conn,
        company_event_ids=[older_event_id],
        projection_names=["timeline"],
        now_ms=NOW_MS + 4_000,
    )
    postgres_conn.commit()

    result = _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 4_000, batch_size=1).run_once_sync()

    rebuilt_timeline = postgres_conn.execute(
        "SELECT * FROM equity_company_timeline_rows WHERE company_event_id = %s",
        (older_event_id,),
    ).fetchone()
    assert result.processed == 1
    assert rebuilt_timeline is not None
    assert rebuilt_timeline["ticker"] == "MSFT"


def test_page_projection_worker_removes_calendar_row_for_stale_expected_event(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    _seed_page_projection_source(postgres_conn)
    _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 3_000, batch_size=10).run_once_sync()

    postgres_conn.execute(
        """
        UPDATE equity_expected_events
           SET status = 'stale',
               updated_at_ms = %s
         WHERE expected_event_id = %s
        """,
        (NOW_MS + 4_000, "expected:MSFT:2026Q1"),
    )
    _enqueue_expected_event_projection_targets(
        postgres_conn,
        expected_event_ids=["expected:MSFT:2026Q1"],
        now_ms=NOW_MS + 5_000,
    )
    postgres_conn.commit()

    result = _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 5_000, batch_size=10).run_once_sync()

    calendar_row = postgres_conn.execute(
        "SELECT * FROM equity_event_calendar_rows WHERE expected_event_id = %s",
        ("expected:MSFT:2026Q1",),
    ).fetchone()
    assert result.processed == 1
    assert calendar_row is None
    assert wake_bus.pages_updated == [2, 1]


def test_brief_worker_writes_cited_agent_run_current_brief_and_notifies(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    _seed_page_projection_source(postgres_conn)
    company_event_id = _company_event_id_for_document(postgres_conn, "event-doc-page-msft")
    provider = _FakeEquityBriefProvider(db)
    settings = Settings(workers={"equity_event_brief": {"batch_size": 10}})
    worker = EquityEventBriefWorker(
        name="equity_event_brief",
        settings=settings.workers.equity_event_brief,
        db=db,
        telemetry=SimpleNamespace(),
        provider=provider,
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS + 4_000,
        run_id_factory=lambda: "equity-agent-run-1",
    )

    result = worker.run_once_sync()

    run = postgres_conn.execute("SELECT * FROM equity_event_agent_runs").fetchone()
    brief = postgres_conn.execute("SELECT * FROM equity_event_agent_briefs").fetchone()
    brief_state = postgres_conn.execute("SELECT * FROM equity_event_brief_states").fetchone()
    event = postgres_conn.execute(
        "SELECT * FROM equity_company_events WHERE company_event_id = %s",
        (company_event_id,),
    ).fetchone()
    assert result.processed == 1
    assert provider.called_while_db_session_active is False
    assert provider.packet_evidence_refs[:2] == ["event:summary", "doc:event-doc-page-msft"]
    assert any(ref.startswith("span:") for ref in provider.packet_evidence_refs)
    assert any(ref.startswith("fact:") for ref in provider.packet_evidence_refs)
    assert run["run_id"] == "equity-agent-run-1"
    assert run["company_event_id"] == company_event_id
    assert run["lane"] == EQUITY_EVENT_BRIEF_LANE
    assert run["status"] == "completed"
    assert run["outcome"] == "ready"
    assert run["request_json"]["packet"]["current_event"]["company_event_id"] == company_event_id
    assert run["response_json"]["status"] == "ready"
    assert brief["company_event_id"] == company_event_id
    assert brief["status"] == "ready"
    assert brief["validation_status"] == "accepted"
    assert brief["brief_json"]["evidence_refs"] == provider.packet_evidence_refs
    assert brief["input_hash"] == run["input_hash"]
    assert brief_state["brief_readiness_status"] == "ready"
    assert brief_state["reason_code"] == "brief_ready"
    assert brief_state["input_hash"] == run["input_hash"]
    assert event["brief_readiness_status"] == "ready"
    assert event["brief_readiness_reason"] == "brief_ready"
    assert wake_bus.briefs_updated == [1]


def test_brief_worker_rejects_stale_packet_when_source_changes_during_provider_execution(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    _seed_page_projection_source(postgres_conn)
    company_event_id = _company_event_id_for_document(postgres_conn, "event-doc-page-msft")

    def update_source(packet: Any) -> None:
        postgres_conn.execute(
            """
            UPDATE equity_event_fact_candidates
               SET claim = claim || ' Updated after packet build.',
                   updated_at_ms = %s
             WHERE company_event_id = %s
            """,
            (NOW_MS + 9_000, packet.current_event.company_event_id),
        )
        postgres_conn.commit()

    provider = _FakeEquityBriefProvider(db, on_brief=update_source)
    worker = _brief_worker(
        db,
        provider=provider,
        wake_bus=wake_bus,
        now_ms=NOW_MS + 4_000,
        run_id_factory=lambda: "equity-agent-run-stale",
    )

    result = worker.run_once_sync()

    run = postgres_conn.execute("SELECT * FROM equity_event_agent_runs").fetchone()
    brief = postgres_conn.execute("SELECT * FROM equity_event_agent_briefs").fetchone()
    assert result.failed == 1
    assert run["company_event_id"] == company_event_id
    assert run["status"] == "failed"
    assert run["error_class"] == "source_changed_before_publish"
    assert brief["status"] == "failed"
    assert brief["validation_status"] == "rejected"
    assert brief["input_hash"] == run["input_hash"]
    assert brief["brief_json"]["status"] != "ready"
    assert wake_bus.briefs_updated == [1]


def test_brief_worker_retry_budget_allows_new_source_generation_after_old_failures(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    _seed_page_projection_source(postgres_conn)
    company_event_id = _company_event_id_for_document(postgres_conn, "event-doc-page-msft")
    repos = repositories_for_connection(postgres_conn)
    for index in range(3):
        repos.equity_events.insert_equity_event_agent_run(
            run_id=f"old-failed-run-{index}",
            company_event_id=company_event_id,
            provider="openai",
            model="gpt-equity",
            backend="openai_agents_sdk",
            sdk_trace_id=None,
            workflow_name="gmgn-twitter-intel.equity_event_brief",
            agent_name="EquityEventBriefAgent",
            lane=EQUITY_EVENT_BRIEF_LANE,
            artifact_version_hash="old-artifact",
            prompt_version="old-prompt",
            schema_version="old-schema",
            validator_version="old-validator",
            guardrail_version="old-guardrail",
            input_hash="old-input",
            output_hash=None,
            execution_started=True,
            status="failed",
            outcome="failed",
            error_class="provider_error",
            error="old failure",
            request_json={"packet": {"old": True}},
            response_json=None,
            validation_errors_json=[],
            trace_metadata_json={},
            usage_json={},
            latency_ms=0,
            started_at_ms=NOW_MS + 1_000,
            finished_at_ms=NOW_MS + 1_000,
            created_at_ms=NOW_MS + 1_000,
            commit=False,
        )
    postgres_conn.execute(
        """
        UPDATE equity_event_fact_candidates
           SET claim = claim || ' Fresh source generation.',
               updated_at_ms = %s
         WHERE company_event_id = %s
        """,
        (NOW_MS + 8_000, company_event_id),
    )
    postgres_conn.commit()

    provider = _FakeEquityBriefProvider(db)
    worker = _brief_worker(
        db,
        provider=provider,
        wake_bus=_RecordingWakeBus(),
        now_ms=NOW_MS + 9_000,
        max_attempts=3,
        run_id_factory=lambda: "new-generation-run",
    )

    result = worker.run_once_sync()

    run = postgres_conn.execute(
        "SELECT * FROM equity_event_agent_runs WHERE run_id = %s",
        ("new-generation-run",),
    ).fetchone()
    assert result.processed == 1
    assert run is not None
    assert run["status"] == "completed"
    assert run["outcome"] == "ready"


def test_brief_worker_retry_budget_ignores_stale_failure_started_before_source_refresh(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    _seed_page_projection_source(postgres_conn)
    company_event_id = _company_event_id_for_document(postgres_conn, "event-doc-page-msft")

    def update_source(packet: Any) -> None:
        postgres_conn.execute(
            """
            UPDATE equity_event_fact_candidates
               SET claim = claim || ' Refreshed while stale run was executing.',
                   updated_at_ms = %s
             WHERE company_event_id = %s
            """,
            (NOW_MS + 5_000, packet.current_event.company_event_id),
        )
        postgres_conn.commit()

    first_run_ids = iter(["stale-before-refresh-run"])
    first = _brief_worker(
        db,
        provider=_FakeEquityBriefProvider(db, on_brief=update_source),
        wake_bus=wake_bus,
        clock_ms=_SequenceClock([NOW_MS + 4_000, NOW_MS + 4_000, NOW_MS + 6_000]),
        max_attempts=1,
        run_id_factory=lambda: next(first_run_ids),
    ).run_once_sync()

    _enqueue_company_event_projection_targets(
        postgres_conn,
        company_event_ids=[company_event_id],
        projection_names=["brief_input"],
        now_ms=NOW_MS + 6_500,
    )
    second_run_ids = iter(["fresh-after-refresh-run"])
    second = _brief_worker(
        db,
        provider=_FakeEquityBriefProvider(db),
        wake_bus=wake_bus,
        now_ms=NOW_MS + 7_000,
        max_attempts=1,
        run_id_factory=lambda: next(second_run_ids),
    ).run_once_sync()

    runs = {
        row["run_id"]: row
        for row in postgres_conn.execute("SELECT * FROM equity_event_agent_runs ORDER BY run_id").fetchall()
    }
    brief = postgres_conn.execute(
        "SELECT * FROM equity_event_agent_briefs WHERE company_event_id = %s",
        (company_event_id,),
    ).fetchone()
    assert first.failed == 1
    assert runs["stale-before-refresh-run"]["error_class"] == "source_changed_before_publish"
    assert runs["stale-before-refresh-run"]["started_at_ms"] < NOW_MS + 5_000
    assert runs["stale-before-refresh-run"]["finished_at_ms"] > NOW_MS + 5_000
    assert second.processed == 1
    assert runs["fresh-after-refresh-run"]["status"] == "completed"
    assert runs["fresh-after-refresh-run"]["outcome"] == "ready"
    assert brief["agent_run_id"] == "fresh-after-refresh-run"
    assert brief["status"] == "ready"


def test_brief_worker_persists_insufficient_for_no_official_evidence_and_does_not_churn(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    event = _seed_non_official_event(postgres_conn)
    _enqueue_company_event_projection_targets(
        postgres_conn,
        company_event_ids=[event],
        projection_names=["brief_input"],
        now_ms=NOW_MS + 1_000,
    )
    provider = _FakeEquityBriefProvider(db)
    worker = _brief_worker(
        db,
        provider=provider,
        wake_bus=wake_bus,
        now_ms=NOW_MS + 2_000,
        run_id_factory=lambda: "no-evidence-run",
    )

    first = worker.run_once_sync()
    second = _brief_worker(
        db,
        provider=provider,
        wake_bus=wake_bus,
        now_ms=NOW_MS + 3_000,
        run_id_factory=lambda: "no-evidence-run-second",
    ).run_once_sync()

    runs = postgres_conn.execute("SELECT * FROM equity_event_agent_runs ORDER BY run_id").fetchall()
    brief = postgres_conn.execute(
        "SELECT * FROM equity_event_agent_briefs WHERE company_event_id = %s",
        (event,),
    ).fetchone()
    brief_state = postgres_conn.execute(
        "SELECT * FROM equity_event_brief_states WHERE company_event_id = %s",
        (event,),
    ).fetchone()
    company_event = postgres_conn.execute(
        "SELECT * FROM equity_company_events WHERE company_event_id = %s",
        (event,),
    ).fetchone()
    assert first.processed == 1
    assert first.notes["no_official_evidence"] == 1
    assert provider.called_while_db_session_active is None
    assert len(runs) == 1
    assert runs[0]["run_id"] == "no-evidence-run"
    assert runs[0]["status"] == "completed"
    assert runs[0]["outcome"] == "insufficient"
    assert runs[0]["execution_started"] is False
    assert brief["status"] == "insufficient"
    assert brief["validation_status"] == "attention"
    assert brief["brief_json"]["data_gaps"]
    assert brief_state["brief_readiness_status"] == "insufficient"
    assert brief_state["reason_code"] == "no_official_evidence"
    assert company_event["brief_readiness_status"] == "insufficient"
    assert company_event["brief_readiness_reason"] == "no_official_evidence"
    assert second.skipped == 1
    assert second.notes["reason"] == "no_due_brief_targets"
    assert wake_bus.briefs_updated == [1]


def test_brief_worker_marks_provider_failure_retryable_readiness(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    _seed_page_projection_source(postgres_conn)
    company_event_id = _company_event_id_for_document(postgres_conn, "event-doc-page-msft")
    worker = _brief_worker(
        db,
        provider=_FailingEquityBriefProvider(db),
        wake_bus=wake_bus,
        now_ms=NOW_MS + 4_000,
        run_id_factory=lambda: "equity-agent-run-provider-failed",
    )

    result = worker.run_once_sync()

    brief_state = postgres_conn.execute(
        "SELECT * FROM equity_event_brief_states WHERE company_event_id = %s",
        (company_event_id,),
    ).fetchone()
    company_event = postgres_conn.execute(
        "SELECT * FROM equity_company_events WHERE company_event_id = %s",
        (company_event_id,),
    ).fetchone()
    dirty_target = postgres_conn.execute(
        """
        SELECT * FROM equity_event_projection_dirty_targets
         WHERE projection_name = 'brief_input'
           AND target_id = %s
        ORDER BY updated_at_ms DESC
        LIMIT 1
        """,
        (company_event_id,),
    ).fetchone()
    assert result.failed == 1
    assert brief_state["brief_readiness_status"] == "failed_retryable"
    assert brief_state["reason_code"] == "RuntimeError"
    assert brief_state["next_retry_after_ms"] == NOW_MS + 64_000
    assert company_event["brief_readiness_status"] == "failed_retryable"
    assert company_event["brief_readiness_reason"] == "RuntimeError"
    assert dirty_target["due_at_ms"] == NOW_MS + 64_000
    assert dirty_target["last_error"] == "RuntimeError"


class _WorkerDb:
    def __init__(self, conn: Any) -> None:
        self.conn = conn
        self.session_active = False
        self.session_names: list[str] = []

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None) -> Iterator[Any]:
        del statement_timeout_seconds
        assert not self.session_active
        self.session_active = True
        self.session_names.append(name)
        try:
            yield repositories_for_connection(self.conn)
        finally:
            self.session_active = False


class _RecordingWakeBus:
    def __init__(self) -> None:
        self.sources_reconciled: list[int] = []
        self.evidence_jobs_written: list[tuple[str, int]] = []
        self.documents_written: list[tuple[str, int]] = []
        self.events_processed: list[int] = []
        self.stories_updated: list[int] = []
        self.briefs_updated: list[int] = []
        self.pages_updated: list[int] = []

    def notify_equity_event_sources_reconciled(self, *, count: int) -> None:
        self.sources_reconciled.append(count)

    def notify_equity_event_document_written(self, *, source_id: str, count: int) -> None:
        self.documents_written.append((source_id, count))

    def notify_equity_event_evidence_job_written(self, *, source_id: str, count: int) -> None:
        self.evidence_jobs_written.append((source_id, count))

    def notify_equity_event_processed(self, *, count: int) -> None:
        self.events_processed.append(count)

    def notify_equity_event_story_updated(self, *, count: int) -> None:
        self.stories_updated.append(count)

    def notify_equity_event_brief_updated(self, *, count: int) -> None:
        self.briefs_updated.append(count)

    def notify_equity_event_page_updated(self, *, count: int) -> None:
        self.pages_updated.append(count)


class _SequenceClock:
    def __init__(self, values: list[int]) -> None:
        self.values = list(values)
        self.last_value = int(values[-1])

    def __call__(self) -> int:
        if not self.values:
            return self.last_value
        self.last_value = int(self.values.pop(0))
        return self.last_value


class _FakeEquityDocumentProvider:
    def __init__(
        self,
        db: _WorkerDb,
        *,
        hydration_text: str | None = None,
        hydration_exception: Exception | None = None,
    ) -> None:
        self.db = db
        self.hydration_text = (
            "Revenue was $62.0 billion for the quarter. Diluted earnings per share were $2.94."
            if hydration_text is None
            else hydration_text
        )
        self.hydration_exception = hydration_exception
        self.calls: list[dict[str, Any]] = []
        self.hydration_calls: list[dict[str, Any]] = []
        self.called_while_db_session_active: bool | None = None
        self.hydration_called_while_db_session_active: bool | None = None

    def fetch_source(self, source: dict[str, Any]) -> EquityDocumentProviderFetchResult:
        self.calls.append(dict(source))
        self.called_while_db_session_active = self.db.session_active
        assert not self.db.session_active
        return EquityDocumentProviderFetchResult(
            status_code=200,
            documents=[
                {
                    "provider_type": "sec_submissions",
                    "source_id": source["source_id"],
                    "cik": source["cik"],
                    "payload": {
                        "cik": "0000789019",
                        "name": "MICROSOFT CORP",
                        "filings": {
                            "recent": {
                                "accessionNumber": ["0000789019-26-000001", "0000789019-26-000002"],
                                "form": ["10-Q", "4"],
                                "filingDate": ["2026-04-25", "2026-04-26"],
                                "reportDate": ["2026-03-31", ""],
                                "primaryDocument": ["msft-20260331.htm", "xslF345X05/doc4.xml"],
                                "title": ["Microsoft quarterly report", ""],
                                "body_text": [
                                    (
                                        "Revenue was $62.0 billion for the quarter. "
                                        "Diluted earnings per share were $2.94."
                                    ),
                                    "",
                                ],
                            }
                        },
                    },
                }
            ],
            etag='"test-etag"',
            last_modified="Sat, 25 Apr 2026 00:00:00 GMT",
            not_modified=False,
        )

    def hydrate_document_evidence(self, *, source: dict[str, Any], document: Any) -> EquityEvidenceHydrationResult:
        self.hydration_called_while_db_session_active = self.db.session_active
        self.hydration_calls.append(
            {
                "source_id": source["source_id"],
                "event_document_id": document.event_document_id,
                "provider_document_id": document.provider_document_id,
                "called_while_db_session_active": self.db.session_active,
            }
        )
        assert not self.db.session_active
        if self.hydration_exception is not None:
            raise self.hydration_exception
        if not self.hydration_text.strip():
            return EquityEvidenceHydrationResult(status_code=200, artifacts=[])
        return EquityEvidenceHydrationResult(
            status_code=200,
            artifacts=[
                build_ready_html_text_artifact(
                    event_document_id=str(document.event_document_id),
                    provider_document_id=document.provider_document_id,
                    source_id=str(source["source_id"]),
                    source_url=document.document_url,
                    content_text=self.hydration_text,
                    fetched_at_ms=document.fetched_at_ms,
                    parsed_at_ms=document.fetched_at_ms,
                    now_ms=document.fetched_at_ms,
                )
            ],
        )


class _FailingEquityDocumentProvider:
    def fetch_source(self, source: dict[str, Any]) -> EquityDocumentProviderFetchResult:
        return EquityDocumentProviderFetchResult(
            status_code=503,
            documents=[
                {
                    "status": "failed",
                    "error_code": "missing_sec_user_agent",
                    "provider_type": source["provider_type"],
                    "source_id": source["source_id"],
                }
            ],
        )


class _FakeEquityBriefProvider:
    provider = "openai"
    model = "gpt-equity"
    artifact_version_hash = "artifact-equity-v1"

    def __init__(self, db: _WorkerDb, *, on_brief=None) -> None:
        self.db = db
        self.on_brief = on_brief
        self.called_while_db_session_active: bool | None = None
        self.packet_evidence_refs: list[str] = []

    def try_reserve_execution(self, lane: str, *, rate_units: int = 1) -> AgentCapacityReservation:
        assert lane == EQUITY_EVENT_BRIEF_LANE
        return AgentCapacityReservation(lane=lane, acquired=True, rate_units=rate_units)

    def request_audit(self, *, run_id: str, packet: Any) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "backend": "openai_agents_sdk",
            "model": self.model,
            "lane": EQUITY_EVENT_BRIEF_LANE,
            "stage": "equity_event_brief",
            "workflow_name": "gmgn-twitter-intel.equity_event_brief",
            "agent_name": "EquityEventBriefAgent",
            "sdk_trace_id": "trace-equity-1",
            "group_id": (
                f"equity_event:"
                f"{packet.story_context.story_id if packet.story_context else packet.current_event.company_event_id}"
            ),
            "prompt_version": packet.prompt_version,
            "schema_version": packet.schema_version,
            "runtime_version": "agent-execution-plane-v1",
            "artifact_version_hash": self.artifact_version_hash,
            "input_hash": packet.input_hash,
            "output_hash": None,
            "latency_ms": None,
            "usage": {},
            "trace_metadata": {"run_id": run_id},
            "execution_started": False,
            "status": "planned",
            "error_class": None,
            "error_message": None,
        }

    async def brief_event(
        self,
        *,
        run_id: str,
        packet: Any,
        reservation: AgentCapacityReservation | None = None,
    ) -> dict[str, Any]:
        del run_id, reservation
        self.called_while_db_session_active = self.db.session_active
        assert not self.db.session_active
        self.packet_evidence_refs = list(packet.evidence_refs)
        if self.on_brief is not None:
            self.on_brief(packet)
        return {
            "payload": {
                "status": "ready",
                "direction": "bullish",
                "decision_class": "driver",
                "summary_zh": "微软季度收入和 EPS 均来自官方文件证据。",
                "event_read_zh": "该事件提供了可审计的基本面事实，但不包含交易执行建议。",
                "bull_view": {
                    "strength": "moderate",
                    "thesis_zh": "收入和 EPS 事实支持基本面关注度。",
                    "evidence_refs": packet.evidence_refs,
                },
                "bear_view": {
                    "strength": "weak",
                    "thesis_zh": "输入没有提供管理层指引证据。",
                    "evidence_refs": ["event:summary"],
                },
                "company_impacts": [
                    {
                        "ticker": packet.current_event.ticker,
                        "company_name": packet.current_event.company_name,
                        "impact_direction": "bullish",
                        "reason_zh": "官方文件包含收入和 EPS 事实。",
                        "evidence_refs": packet.evidence_refs,
                    }
                ],
                "watch_triggers": ["后续管理层指引"],
                "invalidation_conditions": ["官方文件更正关键指标"],
                "data_gaps": [],
                "evidence_refs": packet.evidence_refs,
            },
            "agent_run_audit": self.request_audit(run_id="ignored", packet=packet),
        }


class _FailingEquityBriefProvider(_FakeEquityBriefProvider):
    async def brief_event(
        self,
        *,
        run_id: str,
        packet: Any,
        reservation: AgentCapacityReservation | None = None,
    ) -> dict[str, Any]:
        del run_id, packet, reservation
        raise RuntimeError("brief provider failed")


def _brief_worker(
    db: _WorkerDb,
    *,
    provider: Any,
    wake_bus: Any | None,
    now_ms: int | None = None,
    clock_ms=None,
    run_id_factory,
    max_attempts: int = 3,
) -> EquityEventBriefWorker:
    if clock_ms is None:
        assert now_ms is not None

        def clock_ms() -> int:
            return now_ms

    settings = Settings(workers={"equity_event_brief": {"batch_size": 10, "max_attempts": max_attempts}})
    return EquityEventBriefWorker(
        name="equity_event_brief",
        settings=settings.workers.equity_event_brief,
        db=db,
        telemetry=SimpleNamespace(),
        provider=provider,
        wake_bus=wake_bus,
        clock_ms=clock_ms,
        run_id_factory=run_id_factory,
    )


def _process_worker(db: _WorkerDb, *, now_ms: int, batch_size: int = 100) -> EquityEventProcessWorker:
    settings = Settings(workers={"equity_event_process": {"batch_size": batch_size}})
    return EquityEventProcessWorker(
        name="equity_event_process",
        settings=settings.workers.equity_event_process,
        db=db,
        telemetry=SimpleNamespace(),
        wake_bus=None,
        clock_ms=lambda: now_ms,
    )


def _story_worker(db: _WorkerDb, *, now_ms: int) -> EquityEventStoryProjectionWorker:
    return EquityEventStoryProjectionWorker(
        name="equity_event_story_projection",
        settings=Settings().workers.equity_event_story_projection,
        db=db,
        telemetry=SimpleNamespace(),
        wake_bus=None,
        clock_ms=lambda: now_ms,
    )


def _page_worker(
    db: _WorkerDb,
    *,
    wake_bus: Any | None,
    now_ms: int,
    batch_size: int = 100,
) -> EquityEventPageProjectionWorker:
    settings = Settings(workers={"equity_event_page_projection": {"batch_size": batch_size}})
    return EquityEventPageProjectionWorker(
        name="equity_event_page_projection",
        settings=settings.workers.equity_event_page_projection,
        db=db,
        telemetry=SimpleNamespace(),
        wake_bus=wake_bus,
        clock_ms=lambda: now_ms,
    )


def _seed_page_projection_source(conn: Any, *, include_newer_event: bool = False) -> None:
    db = _WorkerDb(conn)
    repos = repositories_for_connection(conn)
    repos.equity_events.upsert_universe_member(
        {
            "company_id": "market_instrument:us_equity:MSFT",
            "ticker": "MSFT",
            "company_name": "Microsoft Corporation",
            "active": True,
            "priority": "P0",
        },
        now_ms=NOW_MS,
    )
    repos.equity_events.upsert_expected_event(
        expected_event_id="expected:MSFT:2026Q1",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        event_type="earnings_release",
        fiscal_period="2026Q1",
        expected_at_ms=NOW_MS - 1_000,
        source_id="config:earnings",
        source_role="calendar",
        now_ms=NOW_MS,
    )
    _seed_processable_document(
        conn,
        event_document_id="event-doc-page-msft",
        provider_document_id="provider-doc-page-msft",
    )
    if include_newer_event:
        repos.equity_events.upsert_universe_member(
            {
                "company_id": "market_instrument:us_equity:AAPL",
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "active": True,
                "priority": "P0",
            },
            now_ms=NOW_MS,
        )
        _seed_processable_document(
            conn,
            event_document_id="event-doc-page-aapl",
            provider_document_id="provider-doc-page-aapl",
            provider_document_key="0000320193-26-000001:10-Q",
            accession_number="0000320193-26-000001",
            company_id="market_instrument:us_equity:AAPL",
            ticker="AAPL",
            content_hash="content-aapl",
            event_time_ms=NOW_MS + 60_000,
        )
    _process_worker(db, now_ms=NOW_MS + 1_000).run_once_sync()
    _story_worker(db, now_ms=NOW_MS + 2_000).run_once_sync()


def _seed_future_expected_event(conn: Any, *, expected_at_ms: int) -> None:
    repos = repositories_for_connection(conn)
    repos.equity_events.upsert_universe_member(
        {
            "company_id": "market_instrument:us_equity:MSFT",
            "ticker": "MSFT",
            "company_name": "Microsoft Corporation",
            "active": True,
            "priority": "P0",
        },
        now_ms=NOW_MS,
    )
    repos.equity_events.upsert_expected_event(
        expected_event_id="expected:MSFT:2026Q2",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        event_type="earnings_release",
        fiscal_period="2026Q2",
        expected_at_ms=expected_at_ms,
        source_id="config:earnings",
        source_role="calendar",
        now_ms=NOW_MS,
    )
    _enqueue_expected_event_projection_targets(
        conn,
        expected_event_ids=["expected:MSFT:2026Q2"],
        now_ms=NOW_MS,
    )


def _company_event_id_for_document(conn: Any, event_document_id: str) -> str:
    row = conn.execute(
        "SELECT company_event_id FROM equity_company_events WHERE primary_document_id = %s",
        (event_document_id,),
    ).fetchone()
    assert row is not None
    return str(row["company_event_id"])


def _enqueue_company_event_projection_targets(
    conn: Any,
    *,
    company_event_ids: list[str],
    projection_names: list[str],
    now_ms: int,
) -> None:
    repos = repositories_for_connection(conn)
    repos.equity_projection_dirty_targets.enqueue_targets(
        [
            {
                "projection_name": projection_name,
                "target_kind": "company_event",
                "target_id": company_event_id,
                "source_watermark_ms": now_ms,
            }
            for company_event_id in company_event_ids
            for projection_name in projection_names
        ],
        reason="test_projection_dirty_target",
        now_ms=now_ms,
    )


def _enqueue_expected_event_projection_targets(
    conn: Any,
    *,
    expected_event_ids: list[str],
    now_ms: int,
    due_at_ms: int | None = None,
) -> None:
    repos = repositories_for_connection(conn)
    repos.equity_projection_dirty_targets.enqueue_targets(
        [
            {
                "projection_name": "calendar",
                "target_kind": "expected_event",
                "target_id": expected_event_id,
                "source_watermark_ms": now_ms,
            }
            for expected_event_id in expected_event_ids
        ],
        reason="test_projection_dirty_target",
        now_ms=now_ms,
        due_at_ms=due_at_ms,
    )


def _seed_processable_document(
    conn: Any,
    *,
    event_document_id: str,
    provider_document_id: str,
    provider_document_key: str = "0000789019-26-000001:10-Q",
    accession_number: str = "0000789019-26-000001",
    company_id: str = "market_instrument:us_equity:MSFT",
    ticker: str = "MSFT",
    form_type: str = "10-Q",
    fiscal_period: str | None = "2026Q1",
    raw_payload_json: dict[str, Any] | None = None,
    provider_title: str | None = None,
    provider_summary: str | None = None,
    primary_document_url: str | None = None,
    evidence_status: str = "ready",
    evidence_reason: str = "",
    evidence_text: str = "Revenue was $62.0 billion. EPS was $2.94.",
    content_hash: str = "content-1",
    event_time_ms: int = NOW_MS,
) -> dict[str, Any]:
    repos = repositories_for_connection(conn)
    source_id = f"sec:{ticker}"
    repos.equity_events.upsert_source(
        source_id=source_id,
        provider_type="sec_submissions",
        company_id=company_id,
        ticker=ticker,
        cik="0000789019",
        source_role="official_regulator",
        now_ms=NOW_MS,
    )
    provider = repos.equity_events.upsert_provider_document(
        provider_document_id=provider_document_id,
        source_id=source_id,
        fetch_run_id=None,
        provider_document_key=provider_document_key,
        company_id=company_id,
        ticker=ticker,
        cik="0000789019",
        document_url="https://www.sec.gov/Archives/edgar/data/789019/000078901926000001/msft.htm",
        payload_hash=content_hash,
        raw_payload_json=raw_payload_json
        or {"title": "Quarterly report", "body_text": "Revenue was $62.0 billion. EPS was $2.94."},
        fetched_at_ms=NOW_MS,
    )
    repos.equity_events.upsert_event_document(
        event_document_id=event_document_id,
        provider_document_id=provider["provider_document_id"],
        company_id=company_id,
        ticker=ticker,
        cik="0000789019",
        source_id=source_id,
        source_role="official_regulator",
        document_type="sec_filing",
        form_type=form_type,
        accession_number=accession_number,
        fiscal_period=fiscal_period,
        document_url="https://www.sec.gov/Archives/edgar/data/789019/000078901926000001/msft.htm",
        event_time_ms=event_time_ms,
        discovered_at_ms=NOW_MS,
        content_hash=content_hash,
        now_ms=NOW_MS,
        provider_title=provider_title or f"{ticker} {form_type}",
        provider_summary=provider_summary,
        primary_document_url=primary_document_url
        or "https://www.sec.gov/Archives/edgar/data/789019/000078901926000001/msft.htm",
        commit=False,
    )
    artifacts = []
    if evidence_status == "ready" and evidence_text.strip():
        artifacts.append(
            asdict(
                build_ready_html_text_artifact(
                    event_document_id=event_document_id,
                    provider_document_id=provider["provider_document_id"],
                    source_id=source_id,
                    source_url="https://www.sec.gov/Archives/edgar/data/789019/000078901926000001/msft.htm",
                    content_text=evidence_text,
                    fetched_at_ms=NOW_MS,
                    parsed_at_ms=NOW_MS,
                    now_ms=NOW_MS,
                )
            )
        )
    elif evidence_status == "unavailable":
        artifacts.append(
            asdict(
                build_unavailable_evidence_artifact(
                    event_document_id=event_document_id,
                    provider_document_id=provider["provider_document_id"],
                    source_id=source_id,
                    artifact_kind="html_text",
                    source_url="https://www.sec.gov/Archives/edgar/data/789019/000078901926000001/msft.htm",
                    reason=evidence_reason,
                    fetched_at_ms=NOW_MS,
                    parsed_at_ms=NOW_MS,
                    now_ms=NOW_MS,
                )
            )
        )
    elif evidence_status == "failed":
        artifacts.append(
            asdict(
                build_failed_evidence_artifact(
                    event_document_id=event_document_id,
                    provider_document_id=provider["provider_document_id"],
                    source_id=source_id,
                    artifact_kind="html_text",
                    source_url="https://www.sec.gov/Archives/edgar/data/789019/000078901926000001/msft.htm",
                    reason=evidence_reason,
                    fetched_at_ms=NOW_MS,
                    parsed_at_ms=NOW_MS,
                    now_ms=NOW_MS,
                )
            )
        )
    repos.equity_events.upsert_evidence_artifacts(
        event_document_id=event_document_id,
        artifacts=artifacts,
        now_ms=NOW_MS,
        commit=False,
    )
    repos.equity_events.mark_event_document_evidence_status(
        event_document_id=event_document_id,
        evidence_status=evidence_status,
        evidence_reason=evidence_reason,
        evidence_ready_at_ms=NOW_MS if evidence_status == "ready" else None,
        now_ms=NOW_MS,
        commit=False,
    )
    repos.equity_events.enqueue_process_job_for_document(
        event_document_id=event_document_id,
        due_at_ms=NOW_MS,
        now_ms=NOW_MS,
        commit=False,
    )
    conn.commit()
    return provider


def _seed_non_official_event(conn: Any) -> str:
    repos = repositories_for_connection(conn)
    company_event_id = "event:no-official:1"
    repos.equity_events.upsert_universe_member(
        {
            "company_id": "market_instrument:us_equity:MSFT",
            "ticker": "MSFT",
            "company_name": "Microsoft Corporation",
            "active": True,
            "priority": "P0",
        },
        now_ms=NOW_MS,
        commit=False,
    )
    repos.equity_events.upsert_company_event(
        company_event_id=company_event_id,
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        primary_document_id=None,
        event_type="specialist_note",
        priority="P2",
        source_role="specialist_media",
        fiscal_period=None,
        event_time_ms=NOW_MS,
        discovered_at_ms=NOW_MS,
        lifecycle_status="raw",
        validation_status="accepted",
        summary="Specialist media reported an unverified event.",
        now_ms=NOW_MS,
        commit=False,
    )
    conn.commit()
    return company_event_id


def _source_payload(symbol: str) -> dict[str, Any]:
    return {
        "source_id": f"sec:{symbol}",
        "provider_type": "sec_submissions",
        "company_id": f"market_instrument:us_equity:{symbol}",
        "ticker": symbol,
        "cik": "0000789019",
        "source_role": "official_regulator",
        "trust_tier": "official",
        "enabled": True,
    }


def _seed_sec_source(conn: Any) -> None:
    repos = repositories_for_connection(conn)
    repos.equity_events.upsert_source(
        source_id="sec:MSFT",
        provider_type="sec_submissions",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        cik="0000789019",
        source_role="official_regulator",
        trust_tier="official",
        now_ms=NOW_MS,
    )


def _fetch_worker(
    db: _WorkerDb,
    *,
    provider: Any,
    wake_bus: _RecordingWakeBus | None,
    now_ms: int,
) -> EquityEventFetchWorker:
    return EquityEventFetchWorker(
        name="equity_event_fetch",
        settings=Settings().workers.equity_event_fetch,
        db=db,
        telemetry=SimpleNamespace(),
        document_provider=provider,
        wake_bus=wake_bus,
        clock_ms=lambda: now_ms,
    )


def _hydration_worker(
    db: _WorkerDb,
    *,
    provider: Any,
    wake_bus: _RecordingWakeBus | None,
    now_ms: int,
) -> EquityEventEvidenceHydrationWorker:
    return EquityEventEvidenceHydrationWorker(
        name="equity_event_evidence_hydration",
        settings=Settings().workers.equity_event_evidence_hydration,
        db=db,
        telemetry=SimpleNamespace(),
        document_provider=provider,
        wake_bus=wake_bus,
        clock_ms=lambda: now_ms,
    )


def _universe_payload(symbol: str, *, active: bool) -> dict[str, Any]:
    return {
        "company_id": f"market_instrument:us_equity:{symbol}",
        "ticker": symbol,
        "company_name": symbol,
        "active": active,
        "priority": "P3",
        "config_json": {"identity_status": "confirmed"},
    }
