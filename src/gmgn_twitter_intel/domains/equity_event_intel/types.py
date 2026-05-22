from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ProviderType = Literal["sec_submissions", "company_ir_rss", "company_ir_atom", "configured_calendar"]
SourceRole = Literal[
    "official_regulator",
    "official_issuer",
    "calendar",
    "transcript",
    "specialist_media",
    "observed_source",
]
TrustTier = Literal["official", "high", "standard", "low"]
Priority = Literal["P0", "P1", "P2", "P3"]
LifecycleStatus = Literal["raw", "processed", "process_failed", "brief_ready", "brief_stale"]
ValidationStatus = Literal["accepted", "attention", "rejected", "pending"]


@dataclass(frozen=True, slots=True)
class EquityEventCompanyConfig:
    company_id: str
    ticker: str
    company_name: str = ""
    cik: str | None = None
    exchange: str | None = None
    priority: Priority = "P3"
    active: bool = True
    config_json: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class EquityExpectedEventConfig:
    expected_event_id: str
    company_id: str
    ticker: str
    event_type: str
    expected_at_ms: int
    source_id: str
    source_role: SourceRole
    fiscal_period: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizedEquityDocument:
    provider_document_key: str
    company_id: str
    ticker: str
    document_url: str
    payload_hash: str
    raw_payload_json: dict[str, Any]
    fetched_at_ms: int
    cik: str | None = None


@dataclass(frozen=True, slots=True)
class EquitySourceSpan:
    span_id: str
    company_event_id: str
    span_type: str
    span_start: int
    span_end: int
    evidence_quote: str
    created_at_ms: int
    event_document_id: str | None = None
    source_id: str | None = None
    section_key: str | None = None
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class EquityFactCandidate:
    fact_candidate_id: str
    company_event_id: str
    fact_type: str
    claim: str
    evidence_quote: str
    source_role: SourceRole
    validation_status: ValidationStatus
    extraction_method: str
    policy_version: str
    created_at_ms: int
    updated_at_ms: int
    event_document_id: str | None = None
    rejection_reasons_json: list[str] | None = None


@dataclass(frozen=True, slots=True)
class EquityCompanyEvent:
    company_event_id: str
    company_id: str
    ticker: str
    event_type: str
    priority: Priority
    source_role: SourceRole
    event_time_ms: int
    discovered_at_ms: int
    lifecycle_status: LifecycleStatus = "raw"
    validation_status: ValidationStatus = "pending"
    primary_document_id: str | None = None
    fiscal_period: str | None = None
    summary: str = ""


@dataclass(frozen=True, slots=True)
class EquityPageRowPayload:
    row_id: str
    company_event_id: str
    company_id: str
    ticker: str
    company_name: str
    event_type: str
    priority: Priority
    source_role: SourceRole
    latest_event_at_ms: int
    lifecycle_status: LifecycleStatus
    headline: str
    computed_at_ms: int
    projection_version: str
    story_id: str | None = None
    summary: str = ""
    facts_json: list[dict[str, Any]] | None = None
    documents_json: list[dict[str, Any]] | None = None
    brief_json: dict[str, Any] | None = None
