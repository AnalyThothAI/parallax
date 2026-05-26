from __future__ import annotations

import inspect

from gmgn_twitter_intel.domains.equity_event_intel.services.fact_candidates import (
    build_fact_candidates,
    build_source_spans,
    ready_evidence_texts,
)

NOW_MS = 1_765_900_000_000


def test_revenue_phrases_create_actual_candidate_with_evidence_quote() -> None:
    candidates = build_fact_candidates(
        company_event_id="event-1",
        event_document_id="doc-1",
        source_span_id="span-1",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        event_type="quarterly_report",
        period="2026Q1",
        source_role="official_issuer",
        evidence_text="Revenue was $62.0 billion for the quarter, up 17% year over year.",
        now_ms=NOW_MS,
    )

    assert [candidate.fact_type for candidate in candidates] == ["revenue_actual"]
    assert candidates[0].validation_status == "accepted"
    assert candidates[0].source_span_id == "span-1"
    assert "$62.0 billion" in candidates[0].evidence_quote
    assert candidates[0].company_id == "market_instrument:us_equity:MSFT"
    assert candidates[0].ticker == "MSFT"
    assert candidates[0].event_type == "quarterly_report"
    assert candidates[0].metric_name == "revenue"
    assert candidates[0].value_numeric == 62.0
    assert candidates[0].value_unit == "USD_billion"
    assert candidates[0].period == "2026Q1"
    assert candidates[0].direction == "actual"
    assert candidates[0].required_slots_json == {
        "metric_name": True,
        "value_numeric": True,
        "value_unit": True,
        "period": True,
    }
    assert candidates[0].evidence_span_start >= 0
    assert candidates[0].evidence_span_end > candidates[0].evidence_span_start


def test_eps_phrases_create_actual_candidate() -> None:
    candidates = build_fact_candidates(
        company_event_id="event-1",
        event_document_id="doc-1",
        source_span_id="span-1",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        event_type="quarterly_report",
        period="2026Q1",
        source_role="official_regulator",
        evidence_text="Diluted earnings per share were -$2.94 for the quarter.",
        now_ms=NOW_MS,
    )

    assert [candidate.fact_type for candidate in candidates] == ["eps_actual"]
    assert candidates[0].validation_status == "accepted"
    assert "-$2.94" in candidates[0].claim
    assert candidates[0].metric_name == "eps"
    assert candidates[0].value_numeric == -2.94
    assert candidates[0].value_unit == "USD_per_share"


def test_no_numeric_evidence_creates_no_accepted_fact() -> None:
    candidates = build_fact_candidates(
        company_event_id="event-1",
        event_document_id="doc-1",
        source_span_id="span-1",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        event_type="quarterly_report",
        period="2026Q1",
        source_role="official_issuer",
        evidence_text="Revenue increased and earnings per share improved for the quarter.",
        now_ms=NOW_MS,
    )

    assert [candidate for candidate in candidates if candidate.validation_status == "accepted"] == []


def test_revenue_percentage_without_money_unit_is_not_accepted() -> None:
    candidates = build_fact_candidates(
        company_event_id="event-1",
        event_document_id="doc-1",
        source_span_id="span-1",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        event_type="quarterly_report",
        period="2026Q1",
        source_role="official_issuer",
        evidence_text="Revenue increased 17 percent from the prior year.",
        now_ms=NOW_MS,
    )

    assert [candidate for candidate in candidates if candidate.fact_type == "revenue_actual"] == []


def test_media_source_creates_attention_candidate() -> None:
    candidates = build_fact_candidates(
        company_event_id="event-1",
        event_document_id="doc-1",
        source_span_id="span-1",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        event_type="quarterly_report",
        period="2026Q1",
        source_role="specialist_media",
        evidence_text="Revenue was $62.0 billion for the quarter.",
        now_ms=NOW_MS,
    )

    assert candidates[0].fact_type == "revenue_actual"
    assert candidates[0].validation_status == "attention"
    assert candidates[0].rejection_reasons_json == ["source_not_authoritative_for_acceptance"]


def test_fact_extraction_ignores_non_evidence_title_text() -> None:
    assert "title" not in inspect.signature(build_fact_candidates).parameters


def test_source_spans_use_ready_evidence_artifact_content_text_only() -> None:
    artifacts = [
        {
            "evidence_artifact_id": "artifact-ready",
            "source_id": "sec:MSFT",
            "artifact_kind": "html_text",
            "extraction_status": "ready",
            "content_text": "Revenue was $62.0 billion for the quarter.",
            "source_url": "https://example.test/msft.htm",
        },
        {
            "evidence_artifact_id": "artifact-failed",
            "source_id": "sec:MSFT",
            "artifact_kind": "html_text",
            "extraction_status": "failed",
            "content_text": "EPS was $2.94.",
            "source_url": "https://example.test/msft.htm",
        },
        {
            "evidence_artifact_id": "artifact-empty",
            "source_id": "sec:MSFT",
            "artifact_kind": "html_text",
            "extraction_status": "ready",
            "content_text": "   ",
            "source_url": "https://example.test/msft.htm",
        },
    ]

    texts = ready_evidence_texts(artifacts)
    spans = build_source_spans(
        company_event_id="event-1",
        event_document_id="doc-1",
        evidence_artifacts=artifacts,
        now_ms=NOW_MS,
    )

    assert [item["text"] for item in texts] == ["Revenue was $62.0 billion for the quarter."]
    assert len(spans) == 1
    assert spans[0].source_id == "sec:MSFT"
    assert spans[0].span_type == "evidence_artifact_text"
    assert spans[0].section_key == "html_text"
    assert spans[0].evidence_quote == "Revenue was $62.0 billion for the quarter."
