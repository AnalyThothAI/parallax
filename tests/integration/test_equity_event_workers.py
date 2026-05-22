from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from gmgn_twitter_intel.app.runtime.provider_wiring.equity_events import EquityDocumentProviderFetchResult
from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_fetch_worker import EquityEventFetchWorker
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_source_reconcile_worker import (
    EquityEventSourceReconcileWorker,
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

    def notify_equity_event_sources_reconciled(self, *, count: int) -> None:
        self.sources_reconciled.append(count)

    def notify_equity_event_document_written(self, *, source_id: str, count: int) -> None:
        self.documents_written.append((source_id, count))


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
                            }
                        },
                    },
                }
            ],
            etag='"test-etag"',
            last_modified="Sat, 25 Apr 2026 00:00:00 GMT",
            not_modified=False,
        )
