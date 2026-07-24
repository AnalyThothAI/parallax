from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NewsEntity:
    entity_id: str
    news_item_id: str
    entity_type: str
    raw_value: str
    normalized_value: str
    chain: str | None
    span_start: int
    span_end: int
    text_surface: str
    confidence: float
    extraction_policy_version: str
    created_at_ms: int


@dataclass(frozen=True, slots=True)
class NewsTokenMention:
    mention_id: str
    news_item_id: str
    entity_id: str | None
    observed_symbol: str | None
    chain_id: str | None
    address: str | None
    resolution_status: str
    target_type: str | None
    target_id: str | None
    display_symbol: str | None
    display_name: str | None
    reason_codes: list[str]
    candidate_targets: list[dict[str, object]]
    evidence_strength: str
    confidence: float
    created_at_ms: int


@dataclass(frozen=True, slots=True)
class NewsFactCandidate:
    fact_candidate_id: str
    news_item_id: str
    event_type: str
    claim: str
    realis: str
    evidence_quote: str
    evidence_span_start: int
    evidence_span_end: int
    source_role: str
    required_slots: dict[str, bool]
    affected_targets: list[dict[str, object]]
    validation_status: str
    rejection_reasons: list[str]
    extraction_method: str
    policy_version: str
    created_at_ms: int
    updated_at_ms: int
