from __future__ import annotations

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
