from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from gmgn_twitter_intel.app.runtime.provider_wiring.equity_events import EquityDocumentProviderFetchResult
from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
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
    company_event = postgres_conn.execute("SELECT * FROM equity_company_events").fetchone()
    source_spans = postgres_conn.execute("SELECT * FROM equity_event_source_spans").fetchall()
    fact_candidates = postgres_conn.execute("SELECT * FROM equity_event_fact_candidates").fetchall()
    story_group = postgres_conn.execute("SELECT * FROM equity_event_story_groups").fetchone()
    story_member = postgres_conn.execute("SELECT * FROM equity_event_story_members").fetchone()

    assert process_result.processed == 1
    assert processed_document["lifecycle_status"] == "processed"
    assert company_event["event_type"] == "quarterly_report"
    assert company_event["priority"] == "P0"
    assert len(source_spans) == 1
    assert {candidate["fact_type"] for candidate in fact_candidates} == {"revenue_actual", "eps_actual"}
    assert {candidate["source_span_id"] for candidate in fact_candidates} == {source_spans[0]["span_id"]}
    revenue_candidate = next(candidate for candidate in fact_candidates if candidate["fact_type"] == "revenue_actual")
    assert revenue_candidate["metric_name"] == "revenue"
    assert revenue_candidate["value_numeric"] == 62.0
    assert revenue_candidate["value_unit"] == "USD_billion"
    assert revenue_candidate["period"] == "2026Q1"
    assert revenue_candidate["evidence_span_end"] > revenue_candidate["evidence_span_start"]
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
        row["ticker"]: row
        for row in postgres_conn.execute("SELECT * FROM equity_event_universe_members").fetchall()
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
    assert row["updated_at_ms"] == NOW_MS + 60_000
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
    assert fetch_run["status"] == "failed"
    assert fetch_run["http_status"] == 503
    assert fetch_run["error"] == "missing_sec_user_agent"
    assert fetch_run["extra_json"]["error_code"] == "missing_sec_user_agent"
    assert fetch_run["extra_json"]["provider_document"]["status"] == "failed"


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
        raw_payload_json={
            "title": "Results of Operations and Financial Condition",
            "body_text": "Revenue was $62.0 billion.",
        },
    )

    _process_worker(db, now_ms=NOW_MS + 1_000).run_once_sync()
    _story_worker(db, now_ms=NOW_MS + 2_000).run_once_sync()
    postgres_conn.execute("DELETE FROM equity_event_story_members")
    postgres_conn.commit()

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
    assert first_result.processed == 1
    assert len(page_rows) == 1
    assert page_rows[0]["headline"] == "MSFT 2026Q1 quarterly report"
    assert len(calendar_rows) == 1
    assert calendar_rows[0]["status"] == "matched"
    assert len(alert_rows) == 1
    assert alert_rows[0]["ticker"] == "MSFT"
    assert len(timeline_rows) == 1
    assert timeline_rows[0]["company_event_id"] == page_rows[0]["company_event_id"]

    postgres_conn.execute("DELETE FROM equity_event_page_rows")
    postgres_conn.commit()

    rebuild_result = _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 4_000).run_once_sync()

    rebuilt_rows = postgres_conn.execute("SELECT * FROM equity_event_page_rows").fetchall()
    assert rebuild_result.processed == 1
    assert len(rebuilt_rows) == 1
    assert rebuilt_rows[0]["company_event_id"] == page_rows[0]["company_event_id"]
    assert wake_bus.pages_updated == [1, 1]


def test_page_projection_worker_is_idle_when_read_models_are_current(postgres_conn) -> None:
    db = _WorkerDb(postgres_conn)
    wake_bus = _RecordingWakeBus()
    _seed_page_projection_source(postgres_conn)

    first_result = _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 3_000, batch_size=10).run_once_sync()
    idle_result = _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 4_000, batch_size=10).run_once_sync()

    assert first_result.processed == 1
    assert idle_result.processed == 0
    assert wake_bus.pages_updated == [1]


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
    postgres_conn.commit()

    result = _page_worker(db, wake_bus=wake_bus, now_ms=NOW_MS + 5_000, batch_size=10).run_once_sync()

    calendar_row = postgres_conn.execute(
        "SELECT * FROM equity_event_calendar_rows WHERE expected_event_id = %s",
        ("expected:MSFT:2026Q1",),
    ).fetchone()
    assert result.processed == 1
    assert calendar_row is None
    assert wake_bus.pages_updated == [1, 1]


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
        self.documents_written: list[tuple[str, int]] = []
        self.events_processed: list[int] = []
        self.stories_updated: list[int] = []
        self.pages_updated: list[int] = []

    def notify_equity_event_sources_reconciled(self, *, count: int) -> None:
        self.sources_reconciled.append(count)

    def notify_equity_event_document_written(self, *, source_id: str, count: int) -> None:
        self.documents_written.append((source_id, count))

    def notify_equity_event_processed(self, *, count: int) -> None:
        self.events_processed.append(count)

    def notify_equity_event_story_updated(self, *, count: int) -> None:
        self.stories_updated.append(count)

    def notify_equity_event_page_updated(self, *, count: int) -> None:
        self.pages_updated.append(count)


class _FakeEquityDocumentProvider:
    def __init__(self, db: _WorkerDb) -> None:
        self.db = db
        self.calls: list[dict[str, Any]] = []
        self.called_while_db_session_active: bool | None = None

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


def _process_worker(db: _WorkerDb, *, now_ms: int) -> EquityEventProcessWorker:
    return EquityEventProcessWorker(
        name="equity_event_process",
        settings=Settings().workers.equity_event_process,
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


def _company_event_id_for_document(conn: Any, event_document_id: str) -> str:
    row = conn.execute(
        "SELECT company_event_id FROM equity_company_events WHERE primary_document_id = %s",
        (event_document_id,),
    ).fetchone()
    assert row is not None
    return str(row["company_event_id"])


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
    fiscal_period: str = "2026Q1",
    raw_payload_json: dict[str, Any] | None = None,
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
    )
    return provider


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


def _universe_payload(symbol: str, *, active: bool) -> dict[str, Any]:
    return {
        "company_id": f"market_instrument:us_equity:{symbol}",
        "ticker": symbol,
        "company_name": symbol,
        "active": active,
        "priority": "P3",
        "config_json": {"identity_status": "confirmed"},
    }
