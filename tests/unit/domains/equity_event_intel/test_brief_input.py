from __future__ import annotations

from gmgn_twitter_intel.domains.equity_event_intel.services.brief_input import (
    build_equity_event_brief_input_packet,
)
from gmgn_twitter_intel.domains.equity_event_intel.types import EquityEventBriefAgentConfig
from gmgn_twitter_intel.platform.agent_hashing import json_sha256


def _agent_config() -> EquityEventBriefAgentConfig:
    return EquityEventBriefAgentConfig(
        model="gpt-5-mini",
        artifact_version_hash="artifact-v1",
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        validator_version="validator-v1",
        guardrail_version="guardrail-v1",
    )


def test_packet_builds_current_event_official_evidence_refs_and_hash() -> None:
    packet = build_equity_event_brief_input_packet(
        event={
            "company_event_id": "event-1",
            "company_id": "market_instrument:us_equity:MSFT",
            "ticker": "MSFT",
            "company_name": "Microsoft Corporation",
            "event_type": "quarterly_report",
            "priority": "P0",
            "source_role": "official_regulator",
            "event_time_ms": 1_779_000_000_000,
            "fiscal_period": "2026Q1",
            "summary": "Microsoft reported quarterly revenue growth.",
            "updated_at_ms": 1_779_000_001_000,
            "raw_payload_json": {"must": "not leak"},
        },
        story={
            "story_id": "story-1",
            "event_count": 2,
            "representative_headline": "MSFT reports quarterly results",
        },
        story_members=[
            {
                "company_event_id": "event-2",
                "ticker": "MSFT",
                "event_type": "earnings_release",
                "headline": "MSFT earnings release",
                "event_time_ms": 1_779_000_000_500,
            }
        ],
        source_documents=[
            {
                "event_document_id": "doc-1",
                "source_role": "official_regulator",
                "document_type": "sec_filing",
                "form_type": "10-Q",
                "accession_number": "0000789019-26-000001",
                "document_url": "https://www.sec.gov/Archives/edgar/data/789019/doc.htm",
                "fiscal_period": "2026Q1",
                "content_hash": "sha256:doc",
                "raw_payload_json": {"body_text": "x" * 6000, "provider": "secret-ish"},
            }
        ],
        source_spans=[
            {
                "span_id": "span-2",
                "event_document_id": "doc-1",
                "span_type": "financial_metric",
                "section_key": "income_statement",
                "span_start": 200,
                "span_end": 260,
                "evidence_quote": "Revenue was $63.0 billion.",
                "confidence": 0.98,
            },
            {
                "span_id": "span-1",
                "event_document_id": "doc-1",
                "span_type": "financial_metric",
                "section_key": "income_statement",
                "span_start": 100,
                "span_end": 180,
                "evidence_quote": "Diluted EPS was $2.80.",
                "confidence": 0.97,
            },
        ],
        fact_candidates=[
            {
                "fact_candidate_id": "fact-rejected",
                "source_span_id": "span-2",
                "fact_type": "margin_actual",
                "claim": "Rejected claim.",
                "validation_status": "rejected",
                "source_role": "official_regulator",
            },
            {
                "fact_candidate_id": "fact-2",
                "source_span_id": "span-2",
                "fact_type": "revenue_actual",
                "metric_name": "revenue",
                "value_numeric": 63.0,
                "value_unit": "USD_billion",
                "period": "2026Q1",
                "direction": "up",
                "claim": "Revenue was $63.0 billion.",
                "evidence_quote": "Revenue was $63.0 billion.",
                "validation_status": "accepted",
                "source_role": "official_regulator",
            },
            {
                "fact_candidate_id": "fact-1",
                "source_span_id": "span-1",
                "fact_type": "eps_actual",
                "metric_name": "eps",
                "value_numeric": 2.8,
                "value_unit": "USD",
                "period": "2026Q1",
                "direction": "up",
                "claim": "Diluted EPS was $2.80.",
                "evidence_quote": "Diluted EPS was $2.80.",
                "validation_status": "attention",
                "source_role": "official_regulator",
            },
        ],
        agent_config=_agent_config(),
    )

    assert packet.current_event.company_event_id == "event-1"
    assert packet.source_documents[0].event_document_id == "doc-1"
    assert packet.source_documents[0].text_excerpt == ""
    assert [span.span_id for span in packet.source_spans] == ["span-1", "span-2"]
    assert [fact.fact_candidate_id for fact in packet.fact_lanes] == ["fact-1", "fact-2"]
    assert packet.evidence_refs == [
        "event:summary",
        "doc:doc-1",
        "span:span-1",
        "span:span-2",
        "fact:fact-1",
        "fact:fact-2",
        "story:event-2",
    ]
    assert packet.constraints.source_text_is_data is True
    assert "Do not fetch external data" in packet.constraints.no_external_fetch_rule
    assert packet.input_hash == json_sha256(packet.model_dump(mode="json", exclude={"input_hash"}))
    dumped = packet.model_dump_json()
    assert "raw_payload_json" not in dumped
    assert "provider" not in dumped
    assert "fact-rejected" not in dumped


def test_packet_truncates_evidence_after_stable_sort() -> None:
    base_event = {
        "company_event_id": "event-1",
        "company_id": "market_instrument:us_equity:MSFT",
        "ticker": "MSFT",
        "event_type": "quarterly_report",
        "priority": "P0",
        "source_role": "official_regulator",
        "event_time_ms": 1_779_000_000_000,
        "summary": "Quarterly report.",
    }
    spans = [
        {
            "span_id": f"span-{index:03d}",
            "event_document_id": "doc-1",
            "span_type": "metric",
            "span_start": index,
            "span_end": index + 1,
            "evidence_quote": f"Quote {index:03d}",
            "confidence": 1.0,
        }
        for index in range(69, -1, -1)
    ]
    facts = [
        {
            "fact_candidate_id": f"fact-{index:03d}",
            "source_span_id": f"span-{index:03d}",
            "fact_type": "metric",
            "claim": f"Fact {index:03d}",
            "evidence_quote": f"Quote {index:03d}",
            "validation_status": "accepted",
            "source_role": "official_regulator",
        }
        for index in range(69, -1, -1)
    ]

    packet = build_equity_event_brief_input_packet(
        event=base_event,
        story=None,
        story_members=[],
        source_documents=[],
        source_spans=spans,
        fact_candidates=facts,
        agent_config=_agent_config(),
    )
    repeat = build_equity_event_brief_input_packet(
        event=base_event,
        story=None,
        story_members=[],
        source_documents=[],
        source_spans=list(reversed(spans)),
        fact_candidates=list(reversed(facts)),
        agent_config=_agent_config(),
    )

    assert [span.span_id for span in packet.source_spans] == [f"span-{index:03d}" for index in range(50)]
    assert [fact.fact_candidate_id for fact in packet.fact_lanes] == [f"fact-{index:03d}" for index in range(50)]
    assert packet.input_hash == repeat.input_hash
    assert packet.packet_id == repeat.packet_id
