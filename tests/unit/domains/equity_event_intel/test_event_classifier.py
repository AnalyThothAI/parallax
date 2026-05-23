from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel.services.event_classifier import classify_equity_event


def test_classifier_maps_10q_to_p0_quarterly_report() -> None:
    event = classify_equity_event(document_payload(form_type="10-Q", ticker="MSFT", fiscal_period="2026Q1"))

    assert event.event_type == "quarterly_report"
    assert event.priority == "P0"
    assert event.lifecycle_status == "raw"


def test_classifier_maps_8k_earnings_release_to_p0() -> None:
    event = classify_equity_event(
        document_payload(form_type="8-K", title="Results of Operations and Financial Condition")
    )

    assert event.event_type == "earnings_release"
    assert event.priority == "P0"


def document_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event_document_id": "event-doc-1",
        "company_id": "market_instrument:us_equity:MSFT",
        "ticker": "MSFT",
        "source_role": "official_regulator",
        "form_type": "8-K",
        "accession_number": "0000789019-26-000001",
        "fiscal_period": None,
        "event_time_ms": 1_765_900_000_000,
        "discovered_at_ms": 1_765_900_000_000,
        "raw_payload_json": {},
    }
    payload.update(overrides)
    return payload
