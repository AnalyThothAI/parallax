from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gmgn_twitter_intel.domains.pulse_lab.types.pulse_state import EvidenceStatus

EvidenceRefType = Literal["event", "metric", "profile", "cluster", "market", "identity", "gate"]
EvidenceQuality = Literal["high", "medium", "low"]
MarketRoute = Literal["cex", "dex", "meme", "unknown"]
FreshnessStatus = Literal["fresh", "stale", "missing", "unknown"]


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ref_id: str
    ref_type: EvidenceRefType
    source_table: str
    source_id: str
    observed_at_ms: int = Field(ge=0)
    summary_zh: str
    quality: EvidenceQuality


class SocialEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: EvidenceStatus
    event_refs: tuple[str, ...] = ()
    cluster_refs: tuple[str, ...] = ()
    summary_zh: str = ""


class MarketEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: EvidenceStatus
    route: MarketRoute
    target_market_type: str
    price_usd: float | None = None
    venue_ref: str | None = None
    instrument_ref: str | None = None
    observed_at_ms: int | None = Field(default=None, ge=0)
    freshness_status: FreshnessStatus = "unknown"
    source_provider: str | None = None
    pricefeed_id: str | None = None
    volume_24h_usd: float | None = None
    open_interest_usd: float | None = None
    funding_rate: float | None = None
    liquidity_usd: float | None = None
    market_cap_usd: float | None = None
    market_refs: tuple[str, ...] = ()


class IdentityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: EvidenceStatus
    identity_refs: tuple[str, ...] = ()
    profile_refs: tuple[str, ...] = ()
    summary_zh: str = ""


class PulseEvidenceQualityMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ref_count: int = Field(ge=0)
    high_quality_ref_count: int = Field(ge=0)
    fresh_ref_count: int = Field(ge=0)
    stale_ref_count: int = Field(default=0, ge=0)
    completeness_score: float | None = Field(default=None, ge=0, le=1)


class PulseEvidenceDataGap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gap_id: str
    ref_type: EvidenceRefType | None = None
    severity: Literal["low", "medium", "high"] = "medium"
    summary_zh: str


class PulseEvidencePacket(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_packet_id: str
    run_id: str | None = None
    evidence_packet_hash: str
    schema_version: str
    candidate_id: str
    target_type: str
    target_id: str
    symbol: str
    window: str
    scope: str
    snapshot_at_ms: int = Field(ge=0)
    source_event_ids: tuple[str, ...]
    allowed_evidence_refs: tuple[EvidenceRef, ...]
    social_evidence: SocialEvidence
    market_evidence: MarketEvidence
    identity_evidence: IdentityEvidence
    quality_metrics: PulseEvidenceQualityMetrics
    data_gaps: tuple[PulseEvidenceDataGap, ...] = ()
    risk_flags: tuple[str, ...] = ()
    source_fingerprints: dict[str, Any] = Field(default_factory=dict)
    admission_context: dict[str, Any] = Field(default_factory=dict)
    summary_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_event_ids", "risk_flags", mode="after")
    @classmethod
    def _stable_unique_strings(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))

    @field_validator("allowed_evidence_refs", mode="after")
    @classmethod
    def _stable_refs(cls, values: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
        return tuple(sorted(values, key=lambda ref: ref.ref_id))

    @field_validator("data_gaps", mode="after")
    @classmethod
    def _stable_gaps(cls, values: tuple[PulseEvidenceDataGap, ...]) -> tuple[PulseEvidenceDataGap, ...]:
        return tuple(sorted(values, key=lambda gap: gap.gap_id))

    @property
    def source_fingerprints_json(self) -> dict[str, Any]:
        return self.source_fingerprints

    @property
    def packet_json(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"summary_json"})

    def canonical_hash_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", exclude={"evidence_packet_hash", "summary_json"})
        return _canonical_json_value(payload)

    def compute_packet_hash(self) -> str:
        payload = json.dumps(
            self.canonical_hash_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def sealed_copy(self) -> PulseEvidencePacket:
        return self.model_copy(update={"evidence_packet_hash": self.compute_packet_hash()})


def _canonical_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonical_json_value(value[key]) for key in sorted(value)}
    if isinstance(value, tuple | list):
        return [_canonical_json_value(item) for item in value]
    return value
