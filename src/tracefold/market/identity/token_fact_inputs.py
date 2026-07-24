from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TokenEvidenceInput:
    evidence_id: str
    event_id: str
    source_kind: str
    source_id: str
    evidence_type: str
    raw_value: str
    normalized_symbol: str | None
    chain_hint: str | None
    address_hint: str | None
    provider: str | None
    provider_ref: str | None
    text_surface: str
    span_start: int
    span_end: int
    sentence_id: int
    local_group_key: str
    strength: str
    confidence: float
    created_at_ms: int


@dataclass(frozen=True, slots=True)
class TokenIntentEvidenceLink:
    evidence_id: str
    role: str


@dataclass(frozen=True, slots=True)
class TokenIntentInput:
    intent_id: str
    event_id: str
    intent_key: str
    construction_policy: str
    primary_evidence_id: str | None
    display_symbol: str | None
    display_name: str | None
    chain_hint: str | None
    address_hint: str | None
    intent_status: str
    intent_confidence: float
    created_at_ms: int
    updated_at_ms: int
    evidence_links: list[TokenIntentEvidenceLink] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MentionKeys:
    symbol: str | None = None
    chain_id: str | None = None
    address: str | None = None
    cex_pricefeed_id: str | None = None
    exchange: str | None = None
    dex_token_provider: str | None = None


@dataclass(frozen=True, slots=True)
class DeterministicResolution:
    intent_id: str
    event_id: str
    resolution_status: str
    target_type: str | None
    target_id: str | None
    pricefeed_id: str | None
    resolver_policy_version: str
    reason_codes: list[str]
    candidate_ids: list[str]
    lookup_keys: list[str]
    decision_time_ms: int
    created_at_ms: int


__all__ = [
    "DeterministicResolution",
    "MentionKeys",
    "TokenEvidenceInput",
    "TokenIntentEvidenceLink",
    "TokenIntentInput",
]
