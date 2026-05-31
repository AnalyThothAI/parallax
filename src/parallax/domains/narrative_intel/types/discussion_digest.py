from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

DigestStatus = Literal["ready", "pending", "insufficient", "semantic_unavailable", "stale"]


class NarrativeCluster(BaseModel):
    cluster_key: str
    label_zh: str | None = None
    summary_zh: str | None = None
    stance_mix: dict[str, float] = Field(default_factory=dict)
    attention_valence_mix: dict[str, float] = Field(default_factory=dict)
    claim_type_mix: dict[str, float] = Field(default_factory=dict)
    top_authors: list[dict[str, Any]] = Field(default_factory=list)
    representative_event_ids: list[str] = Field(default_factory=list)
    first_seen_ms: int | None = None
    last_seen_ms: int | None = None
    velocity: float | None = None
    co_targets: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.0
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, value: Any) -> float:
        return max(0.0, min(1.0, float(value or 0.0)))


class ReflexivityRead(BaseModel):
    loop_state: str = "unknown"
    attention_leads_price: bool | None = None
    price_leads_attention: bool | None = None
    primary_reflexive_driver: str = "unknown"
    crowd_memory: str | None = None
    late_risk: str | None = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class DigestArgument(BaseModel):
    summary_zh: str | None = None
    strength: str | None = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class TokenDiscussionDigest(BaseModel):
    target_type: str
    target_id: str
    window: str
    scope: str
    schema_version: str
    model_version: str
    status: DigestStatus
    is_current: bool = True
    epoch_id: str | None = None
    epoch_policy_version: str | None = None
    source_event_ids: list[str] = Field(default_factory=list)
    source_window_start_ms: int | None = None
    source_window_end_ms: int | None = None
    epoch_closed_at_ms: int | None = None
    display_current_until_ms: int | None = None
    refresh_reason: str | None = None
    source_fingerprint: str | None = None
    label_fingerprint: str | None = None
    headline_zh: str | None = None
    dominant_narratives: list[NarrativeCluster] = Field(default_factory=list)
    bull_view: DigestArgument = Field(default_factory=DigestArgument)
    bear_view: DigestArgument = Field(default_factory=DigestArgument)
    stance_mix: dict[str, float] = Field(default_factory=dict)
    attention_valence_mix: dict[str, float] = Field(default_factory=dict)
    propagation_read: dict[str, Any] = Field(default_factory=dict)
    reflexivity_read: ReflexivityRead | dict[str, Any] = Field(default_factory=ReflexivityRead)
    watch_triggers: list[Any] = Field(default_factory=list)
    invalidation_conditions: list[Any] = Field(default_factory=list)
    data_gaps: list[dict[str, Any]] = Field(default_factory=list)
    semantic_coverage: float = 0.0
    source_event_count: int = 0
    labeled_event_count: int = 0
    independent_author_count: int = 0
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    model_run_id: str | None = None
    computed_at_ms: int
    expires_at_ms: int | None = None
    superseded_at_ms: int | None = None

    @field_validator("semantic_coverage", mode="before")
    @classmethod
    def clamp_coverage(cls, value: Any) -> float:
        return max(0.0, min(1.0, float(value or 0.0)))

    @model_validator(mode="after")
    def validate_public_claims(self) -> TokenDiscussionDigest:
        if self.status == "ready":
            has_argument_refs = bool(self.bull_view.evidence_refs or self.bear_view.evidence_refs)
            if not self.evidence_refs or not self.dominant_narratives or not has_argument_refs:
                raise ValueError("ready digest requires narratives and evidence refs")
            if self.semantic_coverage <= 0:
                raise ValueError("ready digest requires semantic coverage above zero")
        if self.status == "insufficient" and not self.data_gaps:
            raise ValueError("insufficient digest requires data gaps")
        return self


class DiscussionDigestRequest(BaseModel):
    run_id: str
    schema_version: str
    prompt_version: str
    target_type: str
    target_id: str
    window: str
    scope: str
    mentions: list[dict[str, Any]]
    context: dict[str, Any] = Field(default_factory=dict)
    allowed_refs: list[dict[str, Any]] = Field(default_factory=list)


class DiscussionDigestResult(BaseModel):
    run_id: str
    schema_version: str
    prompt_version: str
    digest: dict[str, Any] | TokenDiscussionDigest
    raw_response: dict[str, Any] = Field(default_factory=dict)
    agent_run_audit: dict[str, Any] = Field(default_factory=dict)
