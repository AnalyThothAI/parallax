from __future__ import annotations

from gmgn_twitter_intel.domains.equity_event_intel._constants import (
    EQUITY_EVENT_CALENDAR_PROJECTION_VERSION,
    EQUITY_EVENT_PAGE_PROJECTION_VERSION,
)
from gmgn_twitter_intel.domains.equity_event_intel.services.page_projection import (
    build_equity_company_timeline_row,
    build_equity_event_alert_candidate,
    build_equity_event_calendar_row,
    build_equity_event_page_row,
)

NOW_MS = 1_765_900_000_000


def test_build_equity_event_page_row_includes_frontend_payload() -> None:
    row = build_equity_event_page_row(
        event=_event(evidence_status="ready", evidence_reason=""),
        company=_company(),
        story={"story_id": "story-msft-q1", "representative_headline": "MSFT reports Q1"},
        facts=[
            {
                "fact_candidate_id": "fact-revenue",
                "fact_type": "revenue_actual",
                "metric_name": "revenue",
                "value_numeric": 62.0,
                "value_unit": "USD_billion",
                "period": "2026Q1",
                "direction": "actual",
                "claim": "Revenue was $62.0 billion.",
                "evidence_quote": "Revenue was $62.0 billion.",
                "source_role": "official_regulator",
                "validation_status": "accepted",
                "updated_at_ms": NOW_MS + 500,
                "rejection_reasons_json": [],
            }
        ],
        documents=[
            {
                "event_document_id": "doc-msft-q1",
                "document_type": "sec_filing",
                "form_type": "10-Q",
                "accession_number": "0000789019-26-000001",
                "document_url": "https://sec.test/msft-q1.htm",
                "fiscal_period": "2026Q1",
                "event_time_ms": NOW_MS,
                "source_id": "sec:MSFT",
                "evidence_status": "ready",
                "evidence_reason": "",
                "evidence_ready_at_ms": NOW_MS + 200,
                "fact_extraction_status": "ready",
                "fact_extraction_reason": "",
                "fact_extracted_at_ms": NOW_MS + 300,
                "updated_at_ms": NOW_MS + 400,
            }
        ],
        brief={
            "brief_readiness_status": "ready",
            "reason_code": "brief_ready",
            "reason_detail": "brief generation completed with status ready",
            "updated_at_ms": NOW_MS + 600,
        },
        computed_at_ms=NOW_MS + 1_000,
    )

    assert {
        "ticker": row["ticker"],
        "event_type": row["event_type"],
        "priority": row["priority"],
        "lifecycle_status": row["lifecycle_status"],
        "headline": row["headline"],
        "brief_json": row["brief_json"],
        "projection_version": row["projection_version"],
    } == {
        "ticker": "MSFT",
        "event_type": "quarterly_report",
        "priority": "P0",
        "lifecycle_status": "processed",
        "headline": "MSFT 2026Q1 quarterly report",
        "brief_json": {
            "status": "ready",
            "reason_code": "brief_ready",
            "reason_detail": "brief generation completed with status ready",
            "updated_at_ms": NOW_MS + 600,
        },
        "projection_version": "equity_event_page_rows_v1",
    }
    assert row["row_id"] != row["company_event_id"]
    assert row["company_name"] == "Microsoft Corporation"
    assert row["story_id"] == "story-msft-q1"
    assert row["facts_json"] == [
        {
            "fact_candidate_id": "fact-revenue",
            "fact_type": "revenue_actual",
            "metric_name": "revenue",
            "value_numeric": 62.0,
            "value_unit": "USD_billion",
            "period": "2026Q1",
            "direction": "actual",
            "claim": "Revenue was $62.0 billion.",
            "evidence_quote": "Revenue was $62.0 billion.",
            "source_role": "official_regulator",
            "validation_status": "accepted",
            "rejection_reasons": [],
        }
    ]
    assert row["documents_json"][0]["event_document_id"] == "doc-msft-q1"
    assert row["documents_json"][0]["source_id"] == "sec:MSFT"
    assert row["evidence_status"] == "ready"
    assert row["fact_extraction_status"] == "ready"
    assert row["computed_at_ms"] == NOW_MS + 1_000
    assert row["source_watermark_ms"] == NOW_MS + 1_000
    assert row["freshness_json"] == {
        "material_event_at_ms": NOW_MS,
        "document_updated_at_ms": NOW_MS + 400,
        "evidence_ready_at_ms": NOW_MS + 200,
        "fact_extracted_at_ms": NOW_MS + 300,
        "brief_updated_at_ms": NOW_MS + 600,
        "projection_at_ms": NOW_MS + 1_000,
    }
    assert row["projection_version"] == EQUITY_EVENT_PAGE_PROJECTION_VERSION
    assert row["payload_hash"]


def test_equity_event_page_payload_hash_ignores_ack_timestamps() -> None:
    first = build_equity_event_page_row(
        event=_event(),
        company=_company(),
        story={"story_id": "story-msft-q1"},
        facts=[{"fact_candidate_id": "fact-1", "fact_type": "eps_actual", "validation_status": "accepted"}],
        documents=[],
        brief=None,
        computed_at_ms=NOW_MS,
    )
    second = build_equity_event_page_row(
        event=_event(),
        company=_company(),
        story={"story_id": "story-msft-q1"},
        facts=[{"fact_candidate_id": "fact-1", "fact_type": "eps_actual", "validation_status": "accepted"}],
        documents=[],
        brief=None,
        computed_at_ms=NOW_MS + 5_000,
    )
    source_ack_changed = build_equity_event_page_row(
        event=_event(source_watermark_ms=NOW_MS + 9_000),
        company=_company(),
        story={"story_id": "story-msft-q1"},
        facts=[{"fact_candidate_id": "fact-1", "fact_type": "eps_actual", "validation_status": "accepted"}],
        documents=[],
        brief=None,
        computed_at_ms=NOW_MS + 5_000,
    )
    changed = build_equity_event_page_row(
        event=_event(summary="Updated event summary."),
        company=_company(),
        story={"story_id": "story-msft-q1"},
        facts=[{"fact_candidate_id": "fact-1", "fact_type": "eps_actual", "validation_status": "accepted"}],
        documents=[],
        brief=None,
        computed_at_ms=NOW_MS + 5_000,
    )

    assert first["computed_at_ms"] != second["computed_at_ms"]
    assert first["source_watermark_ms"] != source_ack_changed["source_watermark_ms"]
    assert first["payload_hash"] == second["payload_hash"]
    assert first["payload_hash"] == source_ack_changed["payload_hash"]
    assert changed["payload_hash"] != first["payload_hash"]


def test_build_equity_event_calendar_row_marks_expected_future_event() -> None:
    row = build_equity_event_calendar_row(
        expected_event=_expected_event(expected_at_ms=NOW_MS + 86_400_000),
        observed_event=None,
        company=_company(priority="P1"),
        now_ms=NOW_MS,
        computed_at_ms=NOW_MS,
    )

    assert row["expected_event_id"] == "expected:MSFT:2026Q1"
    assert row["status"] == "expected"
    assert row["headline"] == "MSFT expected 2026Q1 earnings release"
    assert row["priority"] == "P1"
    assert row["calendar_json"]["observed_company_event_id"] is None
    assert row["projection_version"] == EQUITY_EVENT_CALENDAR_PROJECTION_VERSION
    assert row["payload_hash"]


def test_build_equity_event_calendar_row_marks_matching_observed_event() -> None:
    row = build_equity_event_calendar_row(
        expected_event=_expected_event(event_type="earnings_release", expected_at_ms=NOW_MS),
        observed_event=_event(event_type="quarterly_report"),
        company=_company(),
        now_ms=NOW_MS + 1_000,
        computed_at_ms=NOW_MS + 1_000,
    )

    assert row["status"] == "matched"
    assert row["calendar_json"]["observed_company_event_id"] == "event-msft-q1"
    assert row["calendar_json"]["observed_event_type"] == "quarterly_report"
    assert row["headline"] == "MSFT 2026Q1 earnings release matched"


def test_build_equity_event_calendar_row_marks_missed_past_event() -> None:
    row = build_equity_event_calendar_row(
        expected_event=_expected_event(expected_at_ms=NOW_MS - 1),
        observed_event=None,
        company=_company(),
        now_ms=NOW_MS,
        computed_at_ms=NOW_MS,
    )

    assert row["status"] == "missed"
    assert row["headline"] == "MSFT missed 2026Q1 earnings release"


def test_build_equity_event_alert_candidate_only_emits_conservative_official_p0_events() -> None:
    page_row = build_equity_event_page_row(
        event=_event(),
        company=_company(),
        story=None,
        facts=[{"fact_candidate_id": "fact-1", "fact_type": "eps_actual", "validation_status": "accepted"}],
        documents=[],
        brief=None,
        computed_at_ms=NOW_MS,
    )

    alert = build_equity_event_alert_candidate(
        event=_event(),
        page_row=page_row,
        facts=page_row["facts_json"],
        computed_at_ms=NOW_MS + 1_000,
    )
    noisy = build_equity_event_alert_candidate(
        event=_event(priority="P3"),
        page_row={**page_row, "priority": "P3"},
        facts=page_row["facts_json"],
        computed_at_ms=NOW_MS + 1_000,
    )

    assert alert is not None
    assert alert["ticker"] == "MSFT"
    assert alert["alert_status"] == "pending"
    assert alert["reason_codes_json"] == ["official_p0_event", "actionable_fact"]
    assert alert["payload_hash"]
    assert noisy is None


def test_build_equity_company_timeline_row_compacts_page_context() -> None:
    page_row = build_equity_event_page_row(
        event=_event(summary="Revenue and EPS beat expectations."),
        company=_company(),
        story={"story_id": "story-msft-q1"},
        facts=[{"fact_candidate_id": "fact-1", "fact_type": "eps_actual", "validation_status": "attention"}],
        documents=[],
        brief={"brief_json": {"status": "ready", "summary_zh": "MSFT beats."}},
        computed_at_ms=NOW_MS,
    )

    row = build_equity_company_timeline_row(page_row=page_row, computed_at_ms=NOW_MS + 1_000)

    assert row["company_id"] == "market_instrument:us_equity:MSFT"
    assert row["story_id"] == "story-msft-q1"
    assert row["headline"] == "MSFT 2026Q1 quarterly report"
    assert row["payload_json"] == {
        "company_name": "Microsoft Corporation",
        "facts": [{"fact_candidate_id": "fact-1", "fact_type": "eps_actual", "validation_status": "attention"}],
        "documents": [],
        "brief": {"status": "ready", "summary_zh": "MSFT beats."},
    }
    assert row["payload_hash"]


def _event(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "company_event_id": "event-msft-q1",
        "company_id": "market_instrument:us_equity:MSFT",
        "ticker": "MSFT",
        "event_type": "quarterly_report",
        "priority": "P0",
        "source_role": "official_regulator",
        "event_time_ms": NOW_MS,
        "discovered_at_ms": NOW_MS,
        "lifecycle_status": "processed",
        "validation_status": "accepted",
        "fiscal_period": "2026Q1",
        "summary": "",
    }
    row.update(overrides)
    return row


def _company(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "company_id": "market_instrument:us_equity:MSFT",
        "ticker": "MSFT",
        "company_name": "Microsoft Corporation",
        "priority": "P0",
    }
    row.update(overrides)
    return row


def _expected_event(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "expected_event_id": "expected:MSFT:2026Q1",
        "company_id": "market_instrument:us_equity:MSFT",
        "ticker": "MSFT",
        "event_type": "earnings_release",
        "fiscal_period": "2026Q1",
        "expected_at_ms": NOW_MS,
        "source_id": "config:earnings",
        "source_role": "calendar",
        "status": "expected",
    }
    row.update(overrides)
    return row
