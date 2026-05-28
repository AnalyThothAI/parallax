from __future__ import annotations

from collections.abc import Iterator

import pytest
from alembic import command

from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.platform.db.postgres_migrations import alembic_config
from tests.postgres_test_utils import (
    connect_postgres_test,
    reset_postgres_schema,
)
from tests.postgres_test_utils import (
    test_postgres_dsn as postgres_test_dsn,
)

NOW_MS = 1_765_900_000_000


@pytest.fixture
def postgres_conn(tmp_path) -> Iterator[object]:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        reset_postgres_schema(conn)
        yield conn
    finally:
        conn.close()


def test_equity_event_repository_reconciles_source_and_expected_event(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)

    source = repos.equity_events.upsert_source(
        source_id="sec:AAPL",
        provider_type="sec_submissions",
        company_id="market_instrument:us_equity:AAPL",
        ticker="AAPL",
        cik="0000320193",
        source_role="official_regulator",
        trust_tier="official",
        refresh_interval_seconds=300,
        enabled=True,
        now_ms=NOW_MS,
    )
    expected = repos.equity_events.upsert_expected_event(
        expected_event_id="expected:AAPL:2026Q1",
        company_id="market_instrument:us_equity:AAPL",
        ticker="AAPL",
        event_type="earnings_release",
        fiscal_period="2026Q1",
        expected_at_ms=NOW_MS + 86_400_000,
        source_id="config:earnings",
        source_role="calendar",
        now_ms=NOW_MS,
    )

    assert source["source_id"] == "sec:AAPL"
    assert expected["status"] == "expected"
    assert repos.equity_events.list_source_status()[0]["source_id"] == "sec:AAPL"


def test_reap_stale_evidence_jobs_returns_new_terminal_job_context(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    document = _seed_event_document(repos, event_document_id="event-doc-stale-evidence")
    repos.equity_events.enqueue_evidence_job(
        evidence_job_id="evidence-job-stale",
        event_document_id=document["event_document_id"],
        source_id="sec:MSFT",
        due_at_ms=NOW_MS,
        max_attempts=1,
        now_ms=NOW_MS,
    )
    repos.equity_events.claim_due_evidence_jobs(
        now_ms=NOW_MS + 1,
        limit=1,
        lease_owner="worker-a",
        lease_ms=1,
    )

    reaped = repos.equity_events.reap_stale_evidence_jobs(
        now_ms=NOW_MS + 3,
        limit=1,
        lease_owner="terminalizer-a",
        lease_ms=60_000,
    )
    hydration_input = repos.equity_events.load_evidence_hydration_input(evidence_job_id="evidence-job-stale")
    job = postgres_conn.execute(
        "SELECT * FROM equity_event_evidence_jobs WHERE evidence_job_id = %s",
        ("evidence-job-stale",),
    ).fetchone()

    assert [row["evidence_job_id"] for row in reaped] == ["evidence-job-stale"]
    assert reaped[0]["status"] == "running"
    assert reaped[0]["last_error"] == "evidence_job_lease_expired"
    assert job["status"] == "running"
    assert job["lease_owner"] == "terminalizer-a"
    assert job["leased_until_ms"] == NOW_MS + 60_003
    assert job["finished_at_ms"] is None
    assert hydration_input["document"]["event_document_id"] == "event-doc-stale-evidence"
    assert hydration_input["document"]["source_id"] == "sec:MSFT"


def test_reap_stale_evidence_jobs_is_bounded(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    for index in range(2):
        document = _seed_event_document(repos, event_document_id=f"event-doc-stale-{index}")
        repos.equity_events.enqueue_evidence_job(
            evidence_job_id=f"evidence-job-stale-{index}",
            event_document_id=document["event_document_id"],
            source_id="sec:MSFT",
            due_at_ms=NOW_MS,
            max_attempts=1,
            now_ms=NOW_MS,
        )
    repos.equity_events.claim_due_evidence_jobs(
        now_ms=NOW_MS + 1,
        limit=2,
        lease_owner="worker-a",
        lease_ms=1,
    )

    first_reap = repos.equity_events.reap_stale_evidence_jobs(
        now_ms=NOW_MS + 3,
        limit=1,
        lease_owner="terminalizer-a",
        lease_ms=60_000,
    )
    second_reap = repos.equity_events.reap_stale_evidence_jobs(
        now_ms=NOW_MS + 4,
        limit=1,
        lease_owner="terminalizer-b",
        lease_ms=60_000,
    )

    assert len(first_reap) == 1
    assert len(second_reap) == 1
    assert first_reap[0]["evidence_job_id"] != second_reap[0]["evidence_job_id"]


def test_reap_stale_fetch_runs_marks_retryable_and_releases_source(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    source_id = "sec:STALEFETCH"
    repos.equity_events.upsert_source(
        source_id=source_id,
        provider_type="sec_submissions",
        company_id="market_instrument:us_equity:STALEFETCH",
        ticker="STALEFETCH",
        cik="0000000003",
        source_role="official_regulator",
        refresh_interval_seconds=300,
        enabled=True,
        now_ms=NOW_MS - 2_000_000,
    )
    stale_run_id = repos.equity_events.start_fetch_run(
        source_id=source_id,
        started_at_ms=NOW_MS - 1_000_000,
    )
    fresh_run_id = repos.equity_events.start_fetch_run(
        source_id=source_id,
        started_at_ms=NOW_MS - 100_000,
    )
    postgres_conn.execute(
        "UPDATE equity_event_sources SET next_fetch_after_ms = %s WHERE source_id = %s",
        (NOW_MS + 60_000, source_id),
    )
    postgres_conn.commit()

    reaped = repos.equity_events.reap_stale_fetch_runs(
        stale_before_ms=NOW_MS - 900_000,
        now_ms=NOW_MS,
        limit=10,
    )
    runs = postgres_conn.execute(
        "SELECT * FROM equity_event_fetch_runs ORDER BY started_at_ms ASC",
    ).fetchall()
    source = postgres_conn.execute(
        "SELECT * FROM equity_event_sources WHERE source_id = %s",
        (source_id,),
    ).fetchone()

    assert [row["fetch_run_id"] for row in reaped] == [stale_run_id]
    assert runs[0]["status"] == "failed_retryable"
    assert runs[0]["finished_at_ms"] == NOW_MS
    assert runs[0]["error"] == "stale_fetch_run_timeout"
    assert runs[0]["extra_json"]["failure_reason"] == "stale_fetch_run_timeout"
    assert runs[0]["extra_json"]["stale_before_ms"] == NOW_MS - 900_000
    assert runs[1]["fetch_run_id"] == fresh_run_id
    assert runs[1]["status"] == "running"
    assert source["last_error"] == "stale_fetch_run_timeout"
    assert source["next_fetch_after_ms"] == NOW_MS


def test_finish_fetch_run_does_not_overwrite_reaped_stale_run(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    source_id = "sec:RACEFETCH"
    repos.equity_events.upsert_source(
        source_id=source_id,
        provider_type="sec_submissions",
        company_id="market_instrument:us_equity:RACEFETCH",
        ticker="RACEFETCH",
        cik="0000000004",
        source_role="official_regulator",
        refresh_interval_seconds=300,
        enabled=True,
        now_ms=NOW_MS - 2_000_000,
    )
    fetch_run_id = repos.equity_events.start_fetch_run(
        source_id=source_id,
        started_at_ms=NOW_MS - 1_000_000,
    )

    repos.equity_events.reap_stale_fetch_runs(
        stale_before_ms=NOW_MS - 900_000,
        now_ms=NOW_MS,
        limit=10,
    )
    late_finish = repos.equity_events.finish_fetch_run(
        fetch_run_id=fetch_run_id,
        source_id=source_id,
        status="success",
        finished_at_ms=NOW_MS + 1_000,
        fetched_count=1,
        inserted_count=1,
    )
    run = postgres_conn.execute(
        "SELECT * FROM equity_event_fetch_runs WHERE fetch_run_id = %s",
        (fetch_run_id,),
    ).fetchone()
    source = postgres_conn.execute(
        "SELECT * FROM equity_event_sources WHERE source_id = %s",
        (source_id,),
    ).fetchone()

    assert late_finish == {}
    assert run["status"] == "failed_retryable"
    assert run["finished_at_ms"] == NOW_MS
    assert run["inserted_count"] == 0
    assert source["last_success_at_ms"] is None


def test_finish_fetch_run_requires_matching_source_id(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    repos.equity_events.upsert_source(
        source_id="sec:RUNOWNER",
        provider_type="sec_submissions",
        company_id="market_instrument:us_equity:RUNOWNER",
        ticker="RUNOWNER",
        cik="0000000006",
        source_role="official_regulator",
        refresh_interval_seconds=300,
        enabled=True,
        now_ms=NOW_MS,
    )
    repos.equity_events.upsert_source(
        source_id="sec:WRONGOWNER",
        provider_type="sec_submissions",
        company_id="market_instrument:us_equity:WRONGOWNER",
        ticker="WRONGOWNER",
        cik="0000000007",
        source_role="official_regulator",
        refresh_interval_seconds=300,
        enabled=True,
        now_ms=NOW_MS,
    )
    fetch_run_id = repos.equity_events.start_fetch_run(source_id="sec:RUNOWNER", started_at_ms=NOW_MS)

    finished = repos.equity_events.finish_fetch_run(
        fetch_run_id=fetch_run_id,
        source_id="sec:WRONGOWNER",
        status="success",
        finished_at_ms=NOW_MS + 1,
    )
    run = postgres_conn.execute(
        "SELECT * FROM equity_event_fetch_runs WHERE fetch_run_id = %s",
        (fetch_run_id,),
    ).fetchone()
    wrong_source = postgres_conn.execute(
        "SELECT * FROM equity_event_sources WHERE source_id = %s",
        ("sec:WRONGOWNER",),
    ).fetchone()

    assert finished == {}
    assert run["status"] == "running"
    assert run["finished_at_ms"] == 0
    assert wrong_source["last_success_at_ms"] is None


def test_finish_fetch_run_rejects_legacy_failed_status(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    source_id = "sec:LEGACYFAILED"
    repos.equity_events.upsert_source(
        source_id=source_id,
        provider_type="sec_submissions",
        company_id="market_instrument:us_equity:LEGACYFAILED",
        ticker="LEGACYFAILED",
        cik="0000000005",
        source_role="official_regulator",
        refresh_interval_seconds=300,
        enabled=True,
        now_ms=NOW_MS,
    )
    fetch_run_id = repos.equity_events.start_fetch_run(source_id=source_id, started_at_ms=NOW_MS)

    with pytest.raises(ValueError, match="invalid_fetch_run_status:failed"):
        repos.equity_events.finish_fetch_run(
            fetch_run_id=fetch_run_id,
            source_id=source_id,
            status="failed",
            finished_at_ms=NOW_MS + 1,
        )


def test_equity_fetch_run_reaper_migration_upgrades_legacy_rows(postgres_conn) -> None:
    config = alembic_config()
    config.attributes["database_url"] = postgres_test_dsn()
    postgres_conn.commit()
    command.downgrade(config, "20260526_0109")
    postgres_conn.commit()
    db_now_ms = postgres_conn.execute(
        "SELECT (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::bigint AS now_ms",
    ).fetchone()["now_ms"]
    postgres_conn.execute(
        """
        INSERT INTO equity_event_sources (
          source_id, provider_type, company_id, ticker, cik, source_role, trust_tier,
          enabled, refresh_interval_seconds, created_at_ms, updated_at_ms
        )
        VALUES
          ('sec:MIGRATION', 'sec_submissions', 'market_instrument:us_equity:MIGRATION',
           'MIGRATION', '0000000008', 'official_regulator', 'official', true, 300, %s, %s)
        """,
        (db_now_ms, db_now_ms),
    )
    postgres_conn.execute(
        """
        INSERT INTO equity_event_fetch_runs (
          fetch_run_id, source_id, started_at_ms, finished_at_ms, status, error
        )
        VALUES
          ('fetch-migration-failed', 'sec:MIGRATION', %s, %s, 'failed', 'legacy_failed'),
          ('fetch-migration-stale', 'sec:MIGRATION', %s, 0, 'running', NULL),
          ('fetch-migration-fresh', 'sec:MIGRATION', %s, 0, 'running', NULL)
        """,
        (
            db_now_ms - 2_000_000,
            db_now_ms - 1_999_000,
            db_now_ms - 1_000_000,
            db_now_ms - 100_000,
        ),
    )
    postgres_conn.commit()

    command.upgrade(config, "20260526_0110")
    postgres_conn.commit()
    rows = postgres_conn.execute(
        "SELECT fetch_run_id, status, finished_at_ms, error, extra_json "
        "FROM equity_event_fetch_runs ORDER BY fetch_run_id",
    ).fetchall()
    source = postgres_conn.execute(
        "SELECT consecutive_failures, last_error FROM equity_event_sources WHERE source_id = %s",
        ("sec:MIGRATION",),
    ).fetchone()

    statuses = {row["fetch_run_id"]: row for row in rows}
    assert statuses["fetch-migration-failed"]["status"] == "failed_retryable"
    assert statuses["fetch-migration-failed"]["extra_json"]["migrated_from_status"] == "failed"
    assert statuses["fetch-migration-stale"]["status"] == "failed_retryable"
    assert statuses["fetch-migration-stale"]["error"] == "stale_fetch_run_timeout"
    assert statuses["fetch-migration-stale"]["finished_at_ms"] > 0
    assert statuses["fetch-migration-fresh"]["status"] == "running"
    assert source["consecutive_failures"] == 1
    assert source["last_error"] == "stale_fetch_run_timeout"
    with pytest.raises(Exception, match="equity_event_fetch_runs_status_check"):
        postgres_conn.execute(
            """
            INSERT INTO equity_event_fetch_runs (
              fetch_run_id, source_id, started_at_ms, status
            )
            VALUES ('fetch-migration-rejected', 'sec:MIGRATION', %s, 'failed')
            """,
            (db_now_ms,),
        )
    postgres_conn.rollback()


def test_evidence_job_claim_guard_rejects_reset_document_content(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    document = _seed_event_document(repos, event_document_id="event-doc-claim-guard")
    repos.equity_events.enqueue_evidence_job(
        evidence_job_id="evidence-job-claim-guard",
        event_document_id=document["event_document_id"],
        source_id="sec:MSFT",
        due_at_ms=NOW_MS,
        max_attempts=3,
        now_ms=NOW_MS,
    )
    claimed = repos.equity_events.claim_due_evidence_jobs(
        now_ms=NOW_MS + 1,
        limit=1,
        lease_owner="worker-a",
        lease_ms=60_000,
    )[0]
    repos.equity_events.upsert_event_document(
        event_document_id=document["event_document_id"],
        provider_document_id=document["provider_document_id"],
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
        discovered_at_ms=NOW_MS + 2,
        content_hash="content-reset",
        now_ms=NOW_MS + 2,
    )
    repos.equity_events.enqueue_evidence_job(
        evidence_job_id="evidence-job-claim-guard",
        event_document_id=document["event_document_id"],
        source_id="sec:MSFT",
        due_at_ms=NOW_MS + 2,
        max_attempts=3,
        now_ms=NOW_MS + 2,
    )

    current = repos.equity_events.evidence_job_claim_is_current(
        evidence_job_id="evidence-job-claim-guard",
        attempt_count=claimed["attempt_count"],
        lease_owner="worker-a",
        event_document_id=document["event_document_id"],
        content_hash=document["content_hash"],
    )
    finished = repos.equity_events.finish_evidence_job_success(
        evidence_job_id="evidence-job-claim-guard",
        finished_at_ms=NOW_MS + 3,
        attempt_count=claimed["attempt_count"],
        lease_owner="worker-a",
    )
    job = postgres_conn.execute(
        "SELECT * FROM equity_event_evidence_jobs WHERE evidence_job_id = %s",
        ("evidence-job-claim-guard",),
    ).fetchone()

    assert current is False
    assert finished is False
    assert job["status"] == "pending"
    assert job["attempt_count"] == 0


def test_evidence_job_retryable_finish_rejects_reset_document_content(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    document = _seed_event_document(repos, event_document_id="event-doc-retry-guard")
    repos.equity_events.enqueue_evidence_job(
        evidence_job_id="evidence-job-retry-guard",
        event_document_id=document["event_document_id"],
        source_id="sec:MSFT",
        due_at_ms=NOW_MS,
        max_attempts=3,
        now_ms=NOW_MS,
    )
    claimed = repos.equity_events.claim_due_evidence_jobs(
        now_ms=NOW_MS + 1,
        limit=1,
        lease_owner="equity_event_evidence_hydration",
        lease_ms=60_000,
    )[0]
    repos.equity_events.upsert_event_document(
        event_document_id=document["event_document_id"],
        provider_document_id=document["provider_document_id"],
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
        discovered_at_ms=NOW_MS + 2,
        content_hash="content-reset",
        now_ms=NOW_MS + 2,
    )

    finished = repos.equity_events.finish_evidence_job_retryable(
        evidence_job_id="evidence-job-retry-guard",
        error="evidence_hydration_exception:RuntimeError",
        due_at_ms=NOW_MS + 60_000,
        now_ms=NOW_MS + 3,
        attempt_count=claimed["attempt_count"],
        lease_owner="equity_event_evidence_hydration",
        event_document_id=document["event_document_id"],
        content_hash=document["content_hash"],
    )
    job = postgres_conn.execute(
        "SELECT * FROM equity_event_evidence_jobs WHERE evidence_job_id = %s",
        ("evidence-job-retry-guard",),
    ).fetchone()

    assert finished is False
    assert job["status"] == "running"
    assert job["attempt_count"] == claimed["attempt_count"]
    assert job["lease_owner"] == "equity_event_evidence_hydration"


def test_evidence_job_failure_finish_rejects_missing_content_hash_guard(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    document = _seed_event_document(repos, event_document_id="event-doc-missing-hash-guard")
    repos.equity_events.enqueue_evidence_job(
        evidence_job_id="evidence-job-missing-hash-guard",
        event_document_id=document["event_document_id"],
        source_id="sec:MSFT",
        due_at_ms=NOW_MS,
        max_attempts=3,
        now_ms=NOW_MS,
    )
    claimed = repos.equity_events.claim_due_evidence_jobs(
        now_ms=NOW_MS + 1,
        limit=1,
        lease_owner="equity_event_evidence_hydration",
        lease_ms=60_000,
    )[0]

    retryable_finished = repos.equity_events.finish_evidence_job_retryable(
        evidence_job_id="evidence-job-missing-hash-guard",
        error="evidence_hydration_exception:RuntimeError",
        due_at_ms=NOW_MS + 60_000,
        now_ms=NOW_MS + 2,
        attempt_count=claimed["attempt_count"],
        lease_owner="equity_event_evidence_hydration",
        event_document_id=document["event_document_id"],
        content_hash=None,
    )
    terminal_finished = repos.equity_events.finish_evidence_job_terminal(
        evidence_job_id="evidence-job-missing-hash-guard",
        finished_at_ms=NOW_MS + 3,
        error="evidence_hydration_exception:RuntimeError",
        attempt_count=claimed["attempt_count"],
        lease_owner="equity_event_evidence_hydration",
        event_document_id=document["event_document_id"],
        content_hash=None,
    )
    job = postgres_conn.execute(
        "SELECT * FROM equity_event_evidence_jobs WHERE evidence_job_id = %s",
        ("evidence-job-missing-hash-guard",),
    ).fetchone()

    assert retryable_finished is False
    assert terminal_finished is False
    assert job["status"] == "running"
    assert job["attempt_count"] == claimed["attempt_count"]
    assert job["lease_owner"] == "equity_event_evidence_hydration"


def test_equity_event_repository_writes_raw_document_event_and_page_row(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    repos.equity_events.upsert_source(
        source_id="sec:MSFT",
        provider_type="sec_submissions",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        cik="0000789019",
        source_role="official_regulator",
        trust_tier="official",
        refresh_interval_seconds=300,
        enabled=True,
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
        document_url="https://www.sec.gov/Archives/edgar/data/789019/000078901926000001/msft-20260331.htm",
        payload_hash="hash-1",
        raw_payload_json={"form": "10-Q"},
        fetched_at_ms=NOW_MS,
    )
    document = repos.equity_events.upsert_event_document(
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
        document_url="https://www.sec.gov/Archives/edgar/data/789019/000078901926000001/msft-20260331.htm",
        event_time_ms=NOW_MS,
        discovered_at_ms=NOW_MS,
        content_hash="content-1",
        now_ms=NOW_MS,
    )
    event = repos.equity_events.upsert_company_event(
        company_event_id="event-1",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        primary_document_id=document["event_document_id"],
        event_type="quarterly_report",
        priority="P0",
        source_role="official_regulator",
        fiscal_period="2026Q1",
        event_time_ms=NOW_MS,
        discovered_at_ms=NOW_MS,
        lifecycle_status="raw",
        now_ms=NOW_MS,
    )
    repos.equity_events.replace_page_rows(
        rows=[
            {
                "row_id": "row-1",
                "company_event_id": event["company_event_id"],
                "story_id": None,
                "company_id": "market_instrument:us_equity:MSFT",
                "ticker": "MSFT",
                "company_name": "Microsoft Corporation",
                "event_type": "quarterly_report",
                "priority": "P0",
                "source_role": "official_regulator",
                "latest_event_at_ms": NOW_MS,
                "lifecycle_status": "raw",
                "headline": "MSFT filed 10-Q for 2026Q1",
                "summary": "",
                "facts_json": [],
                "documents_json": [],
                "brief_json": {"status": "pending"},
                "computed_at_ms": NOW_MS,
                "projection_version": "equity_event_page_rows_v1",
            }
        ]
    )

    rows = repos.equity_events.list_event_page_rows(limit=10)
    assert rows[0]["ticker"] == "MSFT"
    assert rows[0]["lifecycle_status"] == "raw"


def test_equity_event_repository_replace_page_rows_preserves_unrelated_rows(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    repos.equity_events.upsert_company_event(
        company_event_id="event-preserve-1",
        company_id="market_instrument:us_equity:AAPL",
        ticker="AAPL",
        primary_document_id=None,
        event_type="earnings_release",
        priority="P1",
        source_role="calendar",
        fiscal_period="2026Q1",
        event_time_ms=NOW_MS,
        discovered_at_ms=NOW_MS,
        lifecycle_status="raw",
        now_ms=NOW_MS,
    )
    repos.equity_events.upsert_company_event(
        company_event_id="event-preserve-2",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        primary_document_id=None,
        event_type="quarterly_report",
        priority="P0",
        source_role="official_regulator",
        fiscal_period="2026Q1",
        event_time_ms=NOW_MS + 1_000,
        discovered_at_ms=NOW_MS + 1_000,
        lifecycle_status="raw",
        now_ms=NOW_MS,
    )
    repos.equity_events.replace_page_rows(
        rows=[
            _page_row("row-preserve-1", "event-preserve-1", "AAPL", NOW_MS),
            _page_row("row-preserve-2", "event-preserve-2", "MSFT", NOW_MS + 1_000),
        ]
    )

    repos.equity_events.replace_page_rows(
        company_event_ids=("event-preserve-1",),
        rows=[
            {
                **_page_row("row-preserve-1", "event-preserve-1", "AAPL", NOW_MS + 2_000),
                "headline": "AAPL event updated",
                "payload_hash": "payload:row-preserve-1:updated",
            }
        ],
    )

    rows_by_id = {row["row_id"]: row for row in repos.equity_events.list_event_page_rows(limit=10)}
    assert set(rows_by_id) == {"row-preserve-1", "row-preserve-2"}
    assert rows_by_id["row-preserve-1"]["headline"] == "AAPL event updated"
    assert rows_by_id["row-preserve-2"]["ticker"] == "MSFT"


def test_equity_event_repository_replace_page_rows_deletes_empty_scoped_results(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    repos.equity_events.upsert_company_event(
        company_event_id="event-empty-1",
        company_id="market_instrument:us_equity:AAPL",
        ticker="AAPL",
        primary_document_id=None,
        event_type="earnings_release",
        priority="P1",
        source_role="calendar",
        fiscal_period="2026Q1",
        event_time_ms=NOW_MS,
        discovered_at_ms=NOW_MS,
        lifecycle_status="raw",
        now_ms=NOW_MS,
    )
    repos.equity_events.upsert_company_event(
        company_event_id="event-empty-2",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        primary_document_id=None,
        event_type="quarterly_report",
        priority="P0",
        source_role="official_regulator",
        fiscal_period="2026Q1",
        event_time_ms=NOW_MS + 1_000,
        discovered_at_ms=NOW_MS + 1_000,
        lifecycle_status="raw",
        now_ms=NOW_MS,
    )
    repos.equity_events.replace_page_rows(
        rows=[
            _page_row("row-empty-1", "event-empty-1", "AAPL", NOW_MS),
            _page_row("row-empty-2", "event-empty-2", "MSFT", NOW_MS + 1_000),
        ]
    )

    repos.equity_events.replace_page_rows(rows=[], company_event_ids=("event-empty-1",))

    rows_by_id = {row["row_id"]: row for row in repos.equity_events.list_event_page_rows(limit=10)}
    assert set(rows_by_id) == {"row-empty-2"}
    assert rows_by_id["row-empty-2"]["company_event_id"] == "event-empty-2"


def test_equity_event_repository_provider_documents_are_idempotent_by_source_key(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    repos.equity_events.upsert_source(
        source_id="sec:NVDA",
        provider_type="sec_submissions",
        company_id="market_instrument:us_equity:NVDA",
        ticker="NVDA",
        cik="0001045810",
        source_role="official_regulator",
        trust_tier="official",
        refresh_interval_seconds=300,
        enabled=True,
        now_ms=NOW_MS,
    )
    first = repos.equity_events.upsert_provider_document(
        provider_document_id="provider-doc-original",
        source_id="sec:NVDA",
        fetch_run_id=None,
        provider_document_key="0001045810-26-000001:10-Q",
        company_id="market_instrument:us_equity:NVDA",
        ticker="NVDA",
        cik="0001045810",
        document_url="https://www.sec.gov/Archives/edgar/data/1045810/000104581026000001/nvda-20260331.htm",
        payload_hash="hash-original",
        raw_payload_json={"form": "10-Q", "version": 1},
        fetched_at_ms=NOW_MS,
    )

    second = repos.equity_events.upsert_provider_document(
        provider_document_id="provider-doc-duplicate-caller-id",
        source_id="sec:NVDA",
        fetch_run_id=None,
        provider_document_key="0001045810-26-000001:10-Q",
        company_id="market_instrument:us_equity:NVDA",
        ticker="NVDA",
        cik="0001045810",
        document_url="https://www.sec.gov/Archives/edgar/data/1045810/000104581026000001/nvda-20260331.htm",
        payload_hash="hash-updated",
        raw_payload_json={"form": "10-Q", "version": 2},
        fetched_at_ms=NOW_MS + 1_000,
    )

    assert second["provider_document_id"] == first["provider_document_id"]
    assert second["payload_hash"] == "hash-updated"
    assert second["raw_payload_json"]["version"] == 2


def test_equity_event_repository_duplicate_event_document_does_not_advance_updated_at(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    provider = _seed_source_and_provider_document(repos)

    first = repos.equity_events.upsert_event_document(
        event_document_id="event-doc-duplicate",
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
    duplicate = repos.equity_events.upsert_event_document(
        event_document_id="event-doc-duplicate",
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
        discovered_at_ms=NOW_MS + 10_000,
        content_hash="content-1",
        now_ms=NOW_MS + 10_000,
    )
    changed = repos.equity_events.upsert_event_document(
        event_document_id="event-doc-duplicate",
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
        document_url="https://www.sec.gov/Archives/edgar/data/789019/000078901926000001/msft-updated.htm",
        event_time_ms=NOW_MS,
        discovered_at_ms=NOW_MS + 20_000,
        content_hash="content-2",
        now_ms=NOW_MS + 20_000,
    )

    assert duplicate["status"] == "duplicate"
    assert duplicate["updated_at_ms"] == first["updated_at_ms"]
    assert duplicate["discovered_at_ms"] == first["discovered_at_ms"]
    assert changed["status"] == "updated"
    assert changed["updated_at_ms"] == NOW_MS + 20_000


def test_equity_event_repository_duplicate_event_document_ignores_provider_row_churn(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    first_provider = _seed_source_and_provider_document(repos)
    second_provider = repos.equity_events.upsert_provider_document(
        provider_document_id="provider-doc-event-duplicate-second",
        source_id="sec:MSFT",
        fetch_run_id=None,
        provider_document_key="0000789019-26-000001:10-Q:mirror",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        cik="0000789019",
        document_url="https://www.sec.gov/Archives/edgar/data/789019/000078901926000001/msft.htm",
        payload_hash="hash-1",
        raw_payload_json={"form": "10-Q", "mirror": True},
        fetched_at_ms=NOW_MS + 10_000,
    )

    first = repos.equity_events.upsert_event_document(
        event_document_id="event-doc-provider-churn",
        provider_document_id=first_provider["provider_document_id"],
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
    duplicate = repos.equity_events.upsert_event_document(
        event_document_id="event-doc-provider-churn",
        provider_document_id=second_provider["provider_document_id"],
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
        discovered_at_ms=NOW_MS + 10_000,
        content_hash="content-1",
        now_ms=NOW_MS + 10_000,
    )

    assert duplicate["status"] == "duplicate"
    assert duplicate["provider_document_id"] == first_provider["provider_document_id"]
    assert duplicate["updated_at_ms"] == first["updated_at_ms"]


def test_equity_event_repository_duplicate_company_event_does_not_advance_updated_at(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)

    first = repos.equity_events.upsert_company_event(
        company_event_id="event-company-duplicate",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        primary_document_id=None,
        event_type="quarterly_report",
        priority="P0",
        source_role="official_regulator",
        fiscal_period="2026Q1",
        event_time_ms=NOW_MS,
        discovered_at_ms=NOW_MS + 10_000,
        lifecycle_status="raw",
        validation_status="pending",
        summary="",
        now_ms=NOW_MS,
    )
    duplicate = repos.equity_events.upsert_company_event(
        company_event_id="event-company-duplicate",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        primary_document_id=None,
        event_type="quarterly_report",
        priority="P0",
        source_role="official_regulator",
        fiscal_period="2026Q1",
        event_time_ms=NOW_MS,
        discovered_at_ms=NOW_MS,
        lifecycle_status="raw",
        validation_status="pending",
        summary="",
        now_ms=NOW_MS + 10_000,
    )
    changed = repos.equity_events.upsert_company_event(
        company_event_id="event-company-duplicate",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        primary_document_id=None,
        event_type="quarterly_report",
        priority="P1",
        source_role="official_regulator",
        fiscal_period="2026Q1",
        event_time_ms=NOW_MS,
        discovered_at_ms=NOW_MS,
        lifecycle_status="raw",
        validation_status="pending",
        summary="",
        now_ms=NOW_MS + 20_000,
    )

    assert duplicate["status"] == "duplicate"
    assert duplicate["updated_at_ms"] == first["updated_at_ms"]
    assert changed["status"] == "updated"
    assert changed["updated_at_ms"] == NOW_MS + 20_000


def test_equity_event_repository_replace_page_rows_identical_payload_does_not_churn(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    repos.equity_events.upsert_company_event(
        company_event_id="event-page-stable",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        primary_document_id=None,
        event_type="quarterly_report",
        priority="P0",
        source_role="official_regulator",
        fiscal_period="2026Q1",
        event_time_ms=NOW_MS,
        discovered_at_ms=NOW_MS,
        lifecycle_status="raw",
        now_ms=NOW_MS,
    )
    repos.equity_events.replace_page_rows(rows=[_page_row("row-page-stable", "event-page-stable", "MSFT", NOW_MS)])
    before = postgres_conn.execute(
        "SELECT computed_at_ms, xmin::text AS xmin FROM equity_event_page_rows WHERE row_id = %s",
        ("row-page-stable",),
    ).fetchone()

    repos.equity_events.replace_page_rows(
        company_event_ids=("event-page-stable",),
        rows=[
            {
                **_page_row("row-page-stable", "event-page-stable", "MSFT", NOW_MS),
                "computed_at_ms": NOW_MS + 10_000,
            }
        ],
    )
    after = postgres_conn.execute(
        "SELECT computed_at_ms, xmin::text AS xmin FROM equity_event_page_rows WHERE row_id = %s",
        ("row-page-stable",),
    ).fetchone()

    assert after["computed_at_ms"] == before["computed_at_ms"]
    assert after["xmin"] == before["xmin"]


def test_equity_event_repository_replace_page_rows_advances_source_watermark_without_content_churn(
    postgres_conn,
) -> None:
    repos = repositories_for_connection(postgres_conn)
    repos.equity_events.upsert_company_event(
        company_event_id="event-page-ack",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        primary_document_id=None,
        event_type="quarterly_report",
        priority="P0",
        source_role="official_regulator",
        fiscal_period="2026Q1",
        event_time_ms=NOW_MS,
        discovered_at_ms=NOW_MS,
        lifecycle_status="raw",
        now_ms=NOW_MS,
    )
    repos.equity_events.replace_page_rows(rows=[_page_row("row-page-ack", "event-page-ack", "MSFT", NOW_MS)])
    before = postgres_conn.execute(
        """
        SELECT computed_at_ms, source_watermark_ms, payload_hash, xmin::text AS xmin
          FROM equity_event_page_rows
         WHERE row_id = %s
        """,
        ("row-page-ack",),
    ).fetchone()

    repos.equity_events.replace_page_rows(
        company_event_ids=("event-page-ack",),
        rows=[
            {
                **_page_row("row-page-ack", "event-page-ack", "MSFT", NOW_MS),
                "computed_at_ms": NOW_MS + 10_000,
                "source_watermark_ms": NOW_MS + 5_000,
            }
        ],
    )
    after = postgres_conn.execute(
        """
        SELECT computed_at_ms, source_watermark_ms, payload_hash, xmin::text AS xmin
          FROM equity_event_page_rows
         WHERE row_id = %s
        """,
        ("row-page-ack",),
    ).fetchone()

    assert after["source_watermark_ms"] == NOW_MS + 5_000
    assert after["computed_at_ms"] == before["computed_at_ms"]
    assert after["payload_hash"] == before["payload_hash"]
    assert after["xmin"] != before["xmin"]


def test_equity_event_repository_replaces_evidence_artifacts_for_document(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    _seed_event_document(repos, event_document_id="event-doc-evidence-replace")

    repos.equity_events.replace_evidence_artifacts(
        event_document_id="event-doc-evidence-replace",
        artifacts=[
            {
                "evidence_artifact_id": "artifact-old",
                "provider_document_id": "provider-doc-event-duplicate",
                "source_id": "sec:MSFT",
                "artifact_kind": "html_text",
                "extraction_status": "ready",
                "source_url": "https://example.test/old.htm",
                "content_hash": "hash-old",
                "content_text": "old revenue text",
                "content_json": {"version": 1},
                "excerpt_text": "old revenue",
                "fetched_at_ms": NOW_MS,
                "parsed_at_ms": NOW_MS + 1,
            }
        ],
        now_ms=NOW_MS + 2,
    )
    repos.equity_events.replace_evidence_artifacts(
        event_document_id="event-doc-evidence-replace",
        artifacts=[
            {
                "evidence_artifact_id": "artifact-new",
                "provider_document_id": "provider-doc-event-duplicate",
                "source_id": "sec:MSFT",
                "artifact_kind": "xbrl",
                "extraction_status": "ready",
                "source_url": "https://example.test/new.xml",
                "content_hash": "hash-new",
                "content_text": "new revenue text",
                "content_json": {"version": 2},
                "excerpt_text": "new revenue",
                "fetched_at_ms": NOW_MS + 3,
                "parsed_at_ms": NOW_MS + 4,
            }
        ],
        now_ms=NOW_MS + 5,
    )

    rows = repos.equity_events.list_event_evidence_artifacts("event-doc-evidence-replace")
    assert [row["evidence_artifact_id"] for row in rows] == ["artifact-new"]
    assert rows[0]["artifact_kind"] == "xbrl"
    assert rows[0]["content_json"] == {"version": 2}


def test_equity_event_repository_loads_ready_evidence_process_packets_for_claims(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    _seed_event_document(repos, event_document_id="event-doc-ready")
    _insert_evidence_artifact(
        postgres_conn,
        evidence_artifact_id="artifact-ready",
        event_document_id="event-doc-ready",
        content_hash="hash-ready",
        artifact_payload_hash="artifact-payload-ready",
    )
    repos.equity_events.mark_event_document_evidence_status(
        event_document_id="event-doc-ready",
        evidence_status="ready",
        evidence_reason="",
        evidence_ready_at_ms=NOW_MS + 2,
        now_ms=NOW_MS + 2,
    )

    repos.equity_events.enqueue_process_job_for_document(
        event_document_id="event-doc-ready",
        due_at_ms=NOW_MS + 3,
        now_ms=NOW_MS + 3,
    )
    claims = repos.equity_events.claim_due_process_jobs(
        now_ms=NOW_MS + 4,
        limit=10,
        lease_owner="process-worker-a",
        lease_ms=60_000,
    )
    rows = repos.equity_events.load_process_packets_for_claims(claims=claims)

    assert [row["event_document_id"] for row in rows] == ["event-doc-ready"]
    assert rows[0]["lease_owner"] == "process-worker-a"
    assert rows[0]["attempt_count"] == 1
    assert rows[0]["evidence_status"] == "ready"
    assert [artifact["evidence_artifact_id"] for artifact in rows[0]["evidence_artifacts"]] == ["artifact-ready"]


def test_enqueue_process_job_preserves_running_claim_when_input_hash_changes(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    event_document_id = "event-doc-process-running"
    _seed_event_document(repos, event_document_id=event_document_id)
    _insert_evidence_artifact(
        postgres_conn,
        evidence_artifact_id="artifact-process-running",
        event_document_id=event_document_id,
        content_hash="artifact-content-1",
        artifact_payload_hash="artifact-payload-1",
    )
    repos.equity_events.mark_event_document_evidence_status(
        event_document_id=event_document_id,
        evidence_status="ready",
        evidence_reason="",
        evidence_ready_at_ms=NOW_MS + 1,
        now_ms=NOW_MS + 1,
    )
    repos.equity_events.enqueue_process_job_for_document(
        event_document_id=event_document_id,
        due_at_ms=NOW_MS + 2,
        now_ms=NOW_MS + 2,
    )
    claimed = repos.equity_events.claim_due_process_jobs(
        now_ms=NOW_MS + 3,
        limit=1,
        lease_owner="process-worker-a",
        lease_ms=60_000,
    )
    running = claimed[0]

    postgres_conn.execute(
        """
        UPDATE equity_event_evidence_artifacts
           SET content_hash = %s,
               artifact_payload_hash = %s,
               updated_at_ms = %s
         WHERE evidence_artifact_id = %s
        """,
        ("artifact-content-2", "artifact-payload-2", NOW_MS + 4, "artifact-process-running"),
    )
    postgres_conn.commit()
    requeued = repos.equity_events.enqueue_process_job_for_document(
        event_document_id=event_document_id,
        due_at_ms=NOW_MS + 5,
        now_ms=NOW_MS + 5,
    )
    duplicate_claim = repos.equity_events.claim_due_process_jobs(
        now_ms=NOW_MS + 6,
        limit=1,
        lease_owner="process-worker-b",
        lease_ms=60_000,
    )
    stored = postgres_conn.execute(
        "SELECT * FROM equity_event_process_jobs WHERE event_document_id = %s",
        (event_document_id,),
    ).fetchone()

    assert duplicate_claim == []
    for row in (requeued, stored):
        assert row["status"] == "running"
        assert row["lease_owner"] == "process-worker-a"
        assert row["leased_until_ms"] == running["leased_until_ms"]
        assert row["attempt_count"] == running["attempt_count"]
        assert row["input_payload_hash"] == running["input_payload_hash"]


def test_equity_event_repository_loads_unavailable_evidence_process_packets_with_reason(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    _seed_event_document(repos, event_document_id="event-doc-unavailable")
    repos.equity_events.mark_event_document_evidence_status(
        event_document_id="event-doc-unavailable",
        evidence_status="unavailable",
        evidence_reason="sec_document_unavailable",
        evidence_ready_at_ms=NOW_MS + 2,
        now_ms=NOW_MS + 2,
    )

    repos.equity_events.enqueue_process_job_for_document(
        event_document_id="event-doc-unavailable",
        due_at_ms=NOW_MS + 3,
        now_ms=NOW_MS + 3,
    )
    claims = repos.equity_events.claim_due_process_jobs(
        now_ms=NOW_MS + 4,
        limit=10,
        lease_owner="process-worker-a",
        lease_ms=60_000,
    )
    rows = repos.equity_events.load_process_packets_for_claims(claims=claims)

    assert [row["event_document_id"] for row in rows] == ["event-doc-unavailable"]
    assert rows[0]["evidence_status"] == "unavailable"
    assert rows[0]["evidence_reason"] == "sec_document_unavailable"
    assert rows[0]["evidence_artifacts"] == []


def test_equity_event_repository_excludes_pending_evidence_documents_from_processing(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    _seed_event_document(repos, event_document_id="event-doc-pending")

    assert repos.equity_events.claim_due_process_jobs(
        now_ms=NOW_MS + 2,
        limit=10,
        lease_owner="process-worker-a",
        lease_ms=60_000,
    ) == []


def test_equity_event_repository_upserts_brief_state(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    repos.equity_events.upsert_company_event(
        company_event_id="event-brief-state",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        primary_document_id=None,
        event_type="quarterly_report",
        priority="P0",
        source_role="official_regulator",
        fiscal_period="2026Q1",
        event_time_ms=NOW_MS,
        discovered_at_ms=NOW_MS,
        lifecycle_status="raw",
        now_ms=NOW_MS,
    )

    inserted = repos.equity_events.upsert_brief_state(
        company_event_id="event-brief-state",
        brief_readiness_status="pending_due",
        reason_code="evidence_ready",
        reason_detail="evidence artifacts are ready",
        input_hash="input-1",
        source_updated_at_ms=NOW_MS,
        next_retry_after_ms=None,
        updated_at_ms=NOW_MS + 1,
    )
    updated = repos.equity_events.upsert_brief_state(
        company_event_id="event-brief-state",
        brief_readiness_status="failed_retryable",
        reason_code="agent_backpressure",
        reason_detail="retry after capacity frees",
        input_hash="input-2",
        source_updated_at_ms=NOW_MS + 2,
        next_retry_after_ms=NOW_MS + 60_000,
        updated_at_ms=NOW_MS + 3,
    )

    assert inserted["brief_readiness_status"] == "pending_due"
    assert updated["brief_readiness_status"] == "failed_retryable"
    assert updated["reason_code"] == "agent_backpressure"
    assert updated["input_hash"] == "input-2"
    assert updated["next_retry_after_ms"] == NOW_MS + 60_000


def test_equity_event_repository_updates_source_material_freshness_status(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    repos.equity_events.upsert_source(
        source_id="sec:FRESH",
        provider_type="sec_submissions",
        company_id="market_instrument:us_equity:FRESH",
        ticker="FRESH",
        cik="0000000001",
        source_role="official_regulator",
        trust_tier="official",
        refresh_interval_seconds=300,
        enabled=True,
        now_ms=NOW_MS,
    )
    repos.equity_events.update_source_material_freshness(
        source_id="sec:FRESH",
        material_document_at_ms=NOW_MS + 1,
        evidence_ready_at_ms=NOW_MS + 2,
        product_projection_at_ms=NOW_MS + 3,
        no_new_data_at_ms=NOW_MS + 4,
        actionable_error="temporary evidence failure",
        now_ms=NOW_MS + 5,
    )

    status = repos.equity_events.list_source_status(limit=10)[0]
    assert status["last_success_at_ms"] is None
    assert status["last_material_document_at_ms"] == NOW_MS + 1
    assert status["last_evidence_ready_at_ms"] == NOW_MS + 2
    assert status["last_product_projection_at_ms"] == NOW_MS + 3
    assert status["last_no_new_data_at_ms"] == NOW_MS + 4
    assert status["last_actionable_error"] == "temporary evidence failure"


def test_equity_event_repository_reports_calendar_configuration_and_empty_reason(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)

    assert repos.equity_events.calendar_configured() is False
    assert repos.equity_events.calendar_empty_reason() == "calendar_source_not_configured"

    repos.equity_events.upsert_source(
        source_id="calendar:configured",
        provider_type="configured_calendar",
        company_id="",
        ticker="",
        cik=None,
        source_role="calendar",
        trust_tier="official",
        refresh_interval_seconds=86_400,
        enabled=True,
        now_ms=NOW_MS,
    )

    assert repos.equity_events.calendar_configured() is True
    assert repos.equity_events.calendar_empty_reason() == "no_calendar_rows_in_window"


def test_equity_event_repository_summary_reports_product_status_counts(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    db_now_ms = postgres_conn.execute("SELECT (EXTRACT(EPOCH FROM now()) * 1000)::bigint AS now_ms").fetchone()[
        "now_ms"
    ]
    source_id = "sec:SUMMARY"
    company_id = "market_instrument:us_equity:SUMM"
    event_id = "event-summary-main"

    repos.equity_events.upsert_source(
        source_id=source_id,
        provider_type="sec_submissions",
        company_id=company_id,
        ticker="SUMM",
        cik="0000000002",
        source_role="official_regulator",
        trust_tier="official",
        refresh_interval_seconds=300,
        enabled=True,
        now_ms=db_now_ms,
    )
    fetch_run_id = repos.equity_events.start_fetch_run(source_id=source_id, started_at_ms=db_now_ms)
    repos.equity_events.finish_fetch_run(
        fetch_run_id=fetch_run_id,
        source_id=source_id,
        status="success",
        finished_at_ms=db_now_ms + 100,
        fetched_count=1,
        inserted_count=1,
    )
    repos.equity_events.update_source_material_freshness(
        source_id=source_id,
        material_document_at_ms=db_now_ms + 200,
        evidence_ready_at_ms=db_now_ms + 300,
        now_ms=db_now_ms + 300,
    )
    repos.equity_events.upsert_source(
        source_id="calendar:summary",
        provider_type="configured_calendar",
        company_id="",
        ticker="",
        cik=None,
        source_role="calendar",
        trust_tier="official",
        refresh_interval_seconds=86_400,
        enabled=True,
        now_ms=db_now_ms,
    )

    for current_event_id, readiness in (
        (event_id, "failed_retryable"),
        ("event-summary-stale", "stale"),
        ("event-summary-historical", "historical_unscheduled"),
    ):
        repos.equity_events.upsert_company_event(
            company_event_id=current_event_id,
            company_id=company_id,
            ticker="SUMM",
            primary_document_id=None,
            event_type="quarterly_report",
            priority="P0" if current_event_id == event_id else "P2",
            source_role="official_regulator",
            fiscal_period="2026Q1",
            event_time_ms=db_now_ms,
            discovered_at_ms=db_now_ms,
            lifecycle_status="raw",
            now_ms=db_now_ms,
        )
        repos.equity_events.upsert_brief_state(
            company_event_id=current_event_id,
            brief_readiness_status=readiness,
            reason_code=readiness,
            reason_detail="summary regression",
            input_hash=f"input:{current_event_id}",
            source_updated_at_ms=db_now_ms,
            next_retry_after_ms=db_now_ms + 60_000 if readiness == "failed_retryable" else None,
            updated_at_ms=db_now_ms + 400,
        )

    repos.equity_events.replace_page_rows(
        rows=[
            {
                **_page_row("row-summary-main", event_id, "SUMM", db_now_ms),
                "priority": "P0",
                "computed_at_ms": db_now_ms + 500,
                "source_watermark_ms": db_now_ms + 500,
            }
        ]
    )
    repos.equity_projection_dirty_targets.enqueue_targets(
        [
            {
                "projection_name": "brief_input",
                "target_kind": "company_event",
                "target_id": event_id,
                "payload_hash": "summary-brief-input",
                "source_watermark_ms": db_now_ms,
                "priority": 10,
            }
        ],
        reason="summary_regression",
        now_ms=db_now_ms,
        due_at_ms=db_now_ms - 1,
    )

    summary = repos.equity_events.summary()

    assert summary == {
        "p0_open_count": 1,
        "today_count": 1,
        "due_brief_queue_count": 1,
        "retryable_brief_failure_count": 1,
        "stale_brief_count": 1,
        "historical_backlog_count": 1,
        "latest_material_event_at_ms": db_now_ms,
        "latest_source_success_at_ms": db_now_ms + 100,
        "latest_evidence_ready_at_ms": db_now_ms + 300,
        "latest_projection_at_ms": db_now_ms + 500,
        "calendar_configured": True,
    }


def test_equity_event_repository_computes_missing_page_payload_hash(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    repos.equity_events.upsert_company_event(
        company_event_id="event-page-hashless",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        primary_document_id=None,
        event_type="quarterly_report",
        priority="P0",
        source_role="official_regulator",
        fiscal_period="2026Q1",
        event_time_ms=NOW_MS,
        discovered_at_ms=NOW_MS,
        lifecycle_status="raw",
        now_ms=NOW_MS,
    )
    first = _page_row("row-page-hashless", "event-page-hashless", "MSFT", NOW_MS)
    first.pop("payload_hash")
    repos.equity_events.replace_page_rows(rows=[first])
    before = postgres_conn.execute(
        "SELECT headline, payload_hash FROM equity_event_page_rows WHERE row_id = %s",
        ("row-page-hashless",),
    ).fetchone()

    changed = _page_row("row-page-hashless", "event-page-hashless", "MSFT", NOW_MS)
    changed.pop("payload_hash")
    changed["headline"] = "MSFT event updated without caller hash"
    changed["computed_at_ms"] = NOW_MS + 10_000
    changed["source_watermark_ms"] = NOW_MS + 10_000
    repos.equity_events.replace_page_rows(company_event_ids=("event-page-hashless",), rows=[changed])
    after = postgres_conn.execute(
        "SELECT headline, payload_hash FROM equity_event_page_rows WHERE row_id = %s",
        ("row-page-hashless",),
    ).fetchone()

    assert before["payload_hash"]
    assert after["payload_hash"] != before["payload_hash"]
    assert after["headline"] == "MSFT event updated without caller hash"


def test_equity_event_repository_replace_timeline_rows_identical_payload_does_not_churn(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    repos.equity_events.upsert_company_event(
        company_event_id="event-timeline",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        primary_document_id=None,
        event_type="quarterly_report",
        priority="P0",
        source_role="official_regulator",
        fiscal_period="2026Q1",
        event_time_ms=NOW_MS,
        discovered_at_ms=NOW_MS,
        lifecycle_status="raw",
        now_ms=NOW_MS,
    )

    repos.equity_events.replace_company_timeline_rows(rows=[_timeline_row("timeline-stable", "event-timeline")])
    before = postgres_conn.execute(
        "SELECT computed_at_ms, xmin::text AS xmin FROM equity_company_timeline_rows WHERE row_id = %s",
        ("timeline-stable",),
    ).fetchone()

    repos.equity_events.replace_company_timeline_rows(
        company_event_ids=("event-timeline",),
        rows=[{**_timeline_row("timeline-stable", "event-timeline"), "computed_at_ms": NOW_MS + 10_000}],
    )
    after = postgres_conn.execute(
        "SELECT computed_at_ms, xmin::text AS xmin FROM equity_company_timeline_rows WHERE row_id = %s",
        ("timeline-stable",),
    ).fetchone()

    assert after["computed_at_ms"] == before["computed_at_ms"]
    assert after["xmin"] == before["xmin"]


def test_changed_event_document_content_resets_failed_processing_attempts_for_retry(postgres_conn) -> None:
    repos = repositories_for_connection(postgres_conn)
    repos.equity_events.upsert_source(
        source_id="sec:MSFT",
        provider_type="sec_submissions",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        cik="0000789019",
        source_role="official_regulator",
        trust_tier="official",
        refresh_interval_seconds=300,
        enabled=True,
        now_ms=NOW_MS,
    )
    provider = repos.equity_events.upsert_provider_document(
        provider_document_id="provider-doc-retry",
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
        event_document_id="event-doc-retry",
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
    postgres_conn.execute(
        """
        UPDATE equity_event_documents
           SET lifecycle_status = 'process_failed',
               processing_attempts = 3,
               processing_error = 'exhausted',
               processed_at_ms = %s
         WHERE event_document_id = %s
        """,
        (NOW_MS + 1_000, "event-doc-retry"),
    )
    postgres_conn.commit()

    repos.equity_events.upsert_event_document(
        event_document_id="event-doc-retry",
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
        discovered_at_ms=NOW_MS + 2_000,
        content_hash="content-1",
        now_ms=NOW_MS + 2_000,
    )
    unchanged = postgres_conn.execute(
        "SELECT * FROM equity_event_documents WHERE event_document_id = %s",
        ("event-doc-retry",),
    ).fetchone()
    assert unchanged["lifecycle_status"] == "process_failed"
    assert unchanged["processing_attempts"] == 3
    assert unchanged["processing_error"] == "exhausted"
    assert unchanged["processed_at_ms"] == NOW_MS + 1_000
    assert repos.equity_events.claim_due_process_jobs(
        now_ms=NOW_MS + 2_500,
        limit=10,
        lease_owner="process-worker-a",
        lease_ms=60_000,
    ) == []

    repos.equity_events.upsert_event_document(
        event_document_id="event-doc-retry",
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
        discovered_at_ms=NOW_MS + 3_000,
        content_hash="content-2",
        now_ms=NOW_MS + 3_000,
    )
    repos.equity_events.mark_event_document_evidence_status(
        event_document_id="event-doc-retry",
        evidence_status="unavailable",
        evidence_reason="evidence_reset_for_retry",
        evidence_ready_at_ms=NOW_MS + 3_100,
        now_ms=NOW_MS + 3_100,
    )
    repos.equity_events.enqueue_process_job_for_document(
        event_document_id="event-doc-retry",
        due_at_ms=NOW_MS + 3_200,
        now_ms=NOW_MS + 3_200,
    )

    changed = postgres_conn.execute(
        "SELECT * FROM equity_event_documents WHERE event_document_id = %s",
        ("event-doc-retry",),
    ).fetchone()
    claims = repos.equity_events.claim_due_process_jobs(
        now_ms=NOW_MS + 3_300,
        limit=10,
        lease_owner="process-worker-a",
        lease_ms=60_000,
    )
    claimable = repos.equity_events.load_process_packets_for_claims(claims=claims)
    assert changed["lifecycle_status"] == "raw"
    assert changed["processing_attempts"] == 0
    assert changed["processing_error"] is None
    assert changed["processed_at_ms"] is None
    assert [row["event_document_id"] for row in claimable] == ["event-doc-retry"]


def _page_row(row_id: str, company_event_id: str, ticker: str, latest_event_at_ms: int) -> dict[str, object]:
    return {
        "row_id": row_id,
        "company_event_id": company_event_id,
        "story_id": None,
        "company_id": f"market_instrument:us_equity:{ticker}",
        "ticker": ticker,
        "company_name": f"{ticker} Inc.",
        "event_type": "quarterly_report",
        "priority": "P1",
        "source_role": "official_regulator",
        "latest_event_at_ms": latest_event_at_ms,
        "lifecycle_status": "raw",
        "headline": f"{ticker} event",
        "summary": "",
        "facts_json": [],
        "documents_json": [],
        "brief_json": {"status": "pending"},
        "computed_at_ms": latest_event_at_ms,
        "source_watermark_ms": latest_event_at_ms,
        "projection_version": "equity_event_page_rows_v1",
        "payload_hash": f"payload:{row_id}:stable",
    }


def _timeline_row(row_id: str, company_event_id: str) -> dict[str, object]:
    return {
        "row_id": row_id,
        "company_id": "market_instrument:us_equity:MSFT",
        "ticker": "MSFT",
        "company_event_id": company_event_id,
        "story_id": None,
        "event_type": "quarterly_report",
        "priority": "P0",
        "source_role": "official_regulator",
        "event_time_ms": NOW_MS,
        "lifecycle_status": "raw",
        "headline": "MSFT 2026Q1 quarterly report",
        "summary": "",
        "payload_json": {"status": "pending"},
        "computed_at_ms": NOW_MS,
        "source_watermark_ms": NOW_MS,
        "projection_version": "equity_company_timeline_rows_v1",
        "payload_hash": f"payload:{row_id}:stable",
    }


def _seed_source_and_provider_document(repos) -> dict[str, object]:
    repos.equity_events.upsert_source(
        source_id="sec:MSFT",
        provider_type="sec_submissions",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        cik="0000789019",
        source_role="official_regulator",
        trust_tier="official",
        refresh_interval_seconds=300,
        enabled=True,
        now_ms=NOW_MS,
    )
    return repos.equity_events.upsert_provider_document(
        provider_document_id="provider-doc-event-duplicate",
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


def _seed_event_document(repos, *, event_document_id: str) -> dict[str, object]:
    provider = _seed_source_and_provider_document(repos)
    return repos.equity_events.upsert_event_document(
        event_document_id=event_document_id,
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
        content_hash=f"content:{event_document_id}",
        now_ms=NOW_MS,
    )


def _insert_evidence_artifact(
    conn,
    *,
    evidence_artifact_id: str,
    event_document_id: str,
    content_hash: str,
    artifact_payload_hash: str,
) -> None:
    conn.execute(
        """
        INSERT INTO equity_event_evidence_artifacts (
          evidence_artifact_id, event_document_id, provider_document_id, source_id,
          artifact_kind, extraction_status, source_url, content_hash, content_text,
          content_json, excerpt_text, failure_reason, fetched_at_ms, parsed_at_ms,
          created_at_ms, updated_at_ms, artifact_payload_hash
        )
        VALUES (
          %s, %s, %s, %s,
          'html_text', 'ready', %s, %s, %s,
          '{}'::jsonb, %s, NULL, %s, %s,
          %s, %s, %s
        )
        """,
        (
            evidence_artifact_id,
            event_document_id,
            "provider-doc-event-duplicate",
            "sec:MSFT",
            "https://example.test/msft.htm",
            content_hash,
            "Revenue was $10.",
            "Revenue was $10.",
            NOW_MS,
            NOW_MS,
            NOW_MS,
            NOW_MS,
            artifact_payload_hash,
        ),
    )
    conn.commit()
