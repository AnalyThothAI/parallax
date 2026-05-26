from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel.types import (
    EquityEventBriefAgentConfig,
    EquityEventBriefConstraints,
    EquityEventBriefCurrentEvent,
    EquityEventBriefFactLane,
    EquityEventBriefInputPacket,
    EquityEventBriefSourceDocument,
    EquityEventBriefSourceSpan,
    EquityEventBriefStoryContext,
    EquityEventBriefStoryMember,
)
from gmgn_twitter_intel.platform.agent_hashing import json_sha256

DOCUMENT_EXCERPT_MAX_CHARS = 2000
MAX_DOCUMENTS = 10
MAX_SOURCE_SPANS = 50
MAX_FACT_LANES = 50
MAX_STORY_MEMBERS = 8
PUBLISHABLE_FACT_STATUSES = {"accepted", "attention"}


def build_equity_event_brief_input_packet(
    *,
    event: Mapping[str, Any],
    story: Mapping[str, Any] | None,
    story_members: Sequence[Mapping[str, Any]],
    source_documents: Sequence[Mapping[str, Any]],
    source_spans: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
    agent_config: EquityEventBriefAgentConfig,
) -> EquityEventBriefInputPacket:
    current_event = _current_event(event)
    documents = [_source_document(row) for row in sorted(source_documents, key=_document_sort_key)[:MAX_DOCUMENTS]]
    spans = [_source_span(row) for row in sorted(source_spans, key=_span_sort_key)[:MAX_SOURCE_SPANS]]
    fact_lanes = [
        _fact_lane(row)
        for row in sorted(fact_candidates, key=_fact_sort_key)
        if _str(row.get("validation_status")).lower() in PUBLISHABLE_FACT_STATUSES
    ][:MAX_FACT_LANES]
    story_context = _story_context(
        story=story,
        story_members=story_members,
        current_company_event_id=current_event.company_event_id,
    )
    evidence_refs = _evidence_refs(
        current_event=current_event,
        documents=documents,
        spans=spans,
        fact_lanes=fact_lanes,
        story_context=story_context,
    )
    packet_id = _packet_id(
        current_event=current_event,
        story_context=story_context,
        documents=documents,
        spans=spans,
        fact_lanes=fact_lanes,
        agent_config=agent_config,
    )
    packet = EquityEventBriefInputPacket(
        packet_id=packet_id,
        current_event=current_event,
        story_context=story_context,
        source_documents=documents,
        source_spans=spans,
        fact_lanes=fact_lanes,
        evidence_refs=evidence_refs,
        constraints=EquityEventBriefConstraints(),
        prompt_version=agent_config.prompt_version,
        schema_version=agent_config.schema_version,
    )
    return packet.model_copy(update={"input_hash": json_sha256(packet.model_dump(mode="json", exclude={"input_hash"}))})


def _current_event(row: Mapping[str, Any]) -> EquityEventBriefCurrentEvent:
    return EquityEventBriefCurrentEvent(
        company_event_id=_str(row.get("company_event_id")),
        company_id=_bounded(row.get("company_id"), 200),
        ticker=_bounded(row.get("ticker"), 32),
        company_name=_bounded(row.get("company_name"), 180),
        event_type=_bounded(row.get("event_type"), 80),
        priority=_bounded(row.get("priority"), 16),
        source_role=_bounded(row.get("source_role"), 64),
        event_time_ms=_int(row.get("event_time_ms")),
        discovered_at_ms=_int(row.get("discovered_at_ms")),
        fiscal_period=_optional_bounded(row.get("fiscal_period"), 80),
        lifecycle_status=_bounded(row.get("lifecycle_status"), 64),
        validation_status=_bounded(row.get("validation_status"), 64),
        primary_document_id=_optional_bounded(row.get("primary_document_id"), 160),
        summary=_bounded(row.get("summary"), 2000),
        updated_at_ms=_int(row.get("updated_at_ms")),
    )


def _source_document(row: Mapping[str, Any]) -> EquityEventBriefSourceDocument:
    return EquityEventBriefSourceDocument(
        event_document_id=_str(row.get("event_document_id")),
        source_id=_bounded(row.get("source_id"), 160),
        source_role=_bounded(row.get("source_role"), 64),
        document_type=_bounded(row.get("document_type"), 80),
        form_type=_optional_bounded(row.get("form_type"), 40),
        accession_number=_optional_bounded(row.get("accession_number"), 120),
        fiscal_period=_optional_bounded(row.get("fiscal_period"), 80),
        document_url=_bounded(row.get("document_url"), 2000),
        event_time_ms=_int(row.get("event_time_ms")),
        content_hash=_bounded(row.get("content_hash"), 160),
        text_excerpt=_bounded(row.get("text_excerpt"), DOCUMENT_EXCERPT_MAX_CHARS),
    )


def _source_span(row: Mapping[str, Any]) -> EquityEventBriefSourceSpan:
    return EquityEventBriefSourceSpan(
        span_id=_str(row.get("span_id")),
        event_document_id=_optional_bounded(row.get("event_document_id"), 160),
        source_id=_optional_bounded(row.get("source_id"), 160),
        span_type=_bounded(row.get("span_type"), 80),
        section_key=_optional_bounded(row.get("section_key"), 120),
        span_start=_int(row.get("span_start")),
        span_end=_int(row.get("span_end")),
        evidence_quote=_bounded(row.get("evidence_quote"), 800),
        confidence=_optional_float(row.get("confidence")),
    )


def _fact_lane(row: Mapping[str, Any]) -> EquityEventBriefFactLane:
    return EquityEventBriefFactLane(
        fact_candidate_id=_str(row.get("fact_candidate_id")),
        source_span_id=_optional_bounded(row.get("source_span_id"), 160),
        event_document_id=_optional_bounded(row.get("event_document_id"), 160),
        fact_type=_bounded(row.get("fact_type"), 80),
        metric_name=_bounded(row.get("metric_name"), 80),
        value_numeric=_optional_float(row.get("value_numeric")),
        value_unit=_bounded(row.get("value_unit"), 80),
        period=_optional_bounded(row.get("period"), 80),
        direction=_bounded(row.get("direction"), 64),
        claim=_bounded(row.get("claim"), 900),
        evidence_quote=_bounded(row.get("evidence_quote"), 800),
        source_role=_bounded(row.get("source_role"), 64),
        validation_status=_bounded(row.get("validation_status"), 64),
        rejection_reasons=[_bounded(value, 120) for value in _json_list(row.get("rejection_reasons_json"))[:12]],
    )


def _story_context(
    *,
    story: Mapping[str, Any] | None,
    story_members: Sequence[Mapping[str, Any]],
    current_company_event_id: str,
) -> EquityEventBriefStoryContext | None:
    if story is None or not _str(story.get("story_id")):
        return None
    members = [
        EquityEventBriefStoryMember(
            company_event_id=_str(row.get("company_event_id")),
            ticker=_bounded(row.get("ticker"), 32),
            event_type=_bounded(row.get("event_type"), 80),
            headline=_bounded(row.get("headline") or row.get("representative_headline") or row.get("summary"), 500),
            event_time_ms=_int(row.get("event_time_ms") or row.get("latest_event_at_ms")),
        )
        for row in sorted(story_members, key=_story_member_sort_key)
        if _str(row.get("company_event_id")) and _str(row.get("company_event_id")) != current_company_event_id
    ][:MAX_STORY_MEMBERS]
    return EquityEventBriefStoryContext(
        story_id=_str(story.get("story_id")),
        event_count=_int(story.get("event_count")),
        representative_headline=_bounded(story.get("representative_headline"), 500),
        members=members,
    )


def _evidence_refs(
    *,
    current_event: EquityEventBriefCurrentEvent,
    documents: list[EquityEventBriefSourceDocument],
    spans: list[EquityEventBriefSourceSpan],
    fact_lanes: list[EquityEventBriefFactLane],
    story_context: EquityEventBriefStoryContext | None,
) -> list[str]:
    refs: list[str] = []
    if current_event.summary:
        refs.append("event:summary")
    refs.extend(f"doc:{row.event_document_id}" for row in documents if row.event_document_id)
    refs.extend(f"span:{row.span_id}" for row in spans if row.span_id)
    refs.extend(f"fact:{row.fact_candidate_id}" for row in fact_lanes if row.fact_candidate_id)
    if story_context is not None:
        refs.extend(f"story:{row.company_event_id}" for row in story_context.members if row.company_event_id)
    return _stable_unique(refs)


def _packet_id(
    *,
    current_event: EquityEventBriefCurrentEvent,
    story_context: EquityEventBriefStoryContext | None,
    documents: list[EquityEventBriefSourceDocument],
    spans: list[EquityEventBriefSourceSpan],
    fact_lanes: list[EquityEventBriefFactLane],
    agent_config: EquityEventBriefAgentConfig,
) -> str:
    digest = json_sha256(
        {
            "company_event_id": current_event.company_event_id,
            "primary_document_id": current_event.primary_document_id,
            "updated_at_ms": current_event.updated_at_ms,
            "story_id": story_context.story_id if story_context is not None else "",
            "story_members": (
                [row.company_event_id for row in story_context.members] if story_context is not None else []
            ),
            "documents": [row.event_document_id for row in documents],
            "spans": [row.span_id for row in spans],
            "facts": [row.fact_candidate_id for row in fact_lanes],
            "prompt_version": agent_config.prompt_version,
            "schema_version": agent_config.schema_version,
        }
    )
    return f"equity-event-brief:{current_event.company_event_id}:{digest.removeprefix('sha256:')[:16]}"


def _document_sort_key(row: Mapping[str, Any]) -> tuple[int, str]:
    return (-_int(row.get("event_time_ms")), _str(row.get("event_document_id")))


def _span_sort_key(row: Mapping[str, Any]) -> tuple[str, int, str]:
    return (_str(row.get("event_document_id")), _int(row.get("span_start")), _str(row.get("span_id")))


def _fact_sort_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return (_str(row.get("fact_candidate_id")), _str(row.get("claim")))


def _story_member_sort_key(row: Mapping[str, Any]) -> tuple[int, str]:
    return (-_int(row.get("event_time_ms") or row.get("latest_event_at_ms")), _str(row.get("company_event_id")))


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    return []


def _stable_unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _str(value: Any) -> str:
    return str(value or "").strip()


def _bounded(value: Any, max_length: int) -> str:
    return _str(value)[:max_length]


def _optional_bounded(value: Any, max_length: int) -> str | None:
    cleaned = _bounded(value, max_length)
    return cleaned or None


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = ["build_equity_event_brief_input_packet"]
