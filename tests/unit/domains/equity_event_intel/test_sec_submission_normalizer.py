from __future__ import annotations

from datetime import UTC, datetime

from gmgn_twitter_intel.domains.equity_event_intel.services.sec_submission_normalizer import (
    normalize_sec_submission_documents,
)


def test_normalize_sec_submission_documents_filters_material_forms() -> None:
    payload = {
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
    }

    docs = normalize_sec_submission_documents(
        source={
            "source_id": "sec:MSFT",
            "ticker": "MSFT",
            "company_id": "market_instrument:us_equity:MSFT",
        },
        payload=payload,
        fetched_at_ms=1_765_900_000_000,
    )

    assert len(docs) == 1
    assert docs[0].provider_document_key == "0000789019-26-000001:10-Q"
    assert docs[0].form_type == "10-Q"
    assert docs[0].document_type == "sec_filing"
    assert docs[0].fiscal_period == "2026Q1"


def test_normalize_sec_submission_documents_prefers_acceptance_time() -> None:
    payload = {
        "cik": "CIK0000789019",
        "name": "MICROSOFT CORP",
        "filings": {
            "recent": {
                "accessionNumber": ["0000789019-26-000001"],
                "form": ["8-K"],
                "filingDate": ["2026-04-25"],
                "acceptanceDateTime": ["2026-04-25T14:30:15.000Z"],
                "reportDate": [""],
                "primaryDocument": ["msft-8k.htm"],
            }
        },
    }

    docs = normalize_sec_submission_documents(
        source={
            "source_id": "sec:MSFT",
            "ticker": "MSFT",
            "company_id": "market_instrument:us_equity:MSFT",
        },
        payload=payload,
        fetched_at_ms=1_765_900_000_000,
    )

    assert len(docs) == 1
    assert docs[0].event_time_ms == int(datetime(2026, 4, 25, 14, 30, 15, tzinfo=UTC).timestamp() * 1000)
    assert docs[0].document_url == (
        "https://www.sec.gov/Archives/edgar/data/789019/000078901926000001/msft-8k.htm"
    )


def test_normalize_sec_submission_documents_skips_rows_without_document_url() -> None:
    payload = {
        "cik": "",
        "filings": {
            "recent": {
                "accessionNumber": ["0000789019-26-000001", "0000789019-26-000002"],
                "form": ["10-Q", "8-K"],
                "filingDate": ["2026-04-25", "2026-04-25"],
                "reportDate": ["2026-03-31", "2026-04-25"],
                "primaryDocument": ["msft-20260331.htm", ""],
            }
        },
    }

    docs = normalize_sec_submission_documents(
        source={
            "source_id": "sec:MSFT",
            "ticker": "MSFT",
            "company_id": "market_instrument:us_equity:MSFT",
        },
        payload=payload,
        fetched_at_ms=1_765_900_000_000,
    )

    assert docs == []
