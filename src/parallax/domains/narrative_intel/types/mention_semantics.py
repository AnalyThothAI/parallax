from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

TradeStance = Literal["bullish", "bearish", "neutral", "skeptical", "exit-risk", "research-only", "unknown"]
AttentionValence = Literal[
    "positive",
    "negative",
    "mixed",
    "ironic",
    "hostile",
    "panic",
    "celebratory",
    "informational",
    "unknown",
]
MentionSemanticStatus = Literal["labeled", "semantic_unavailable"]


class MentionSemanticLabel(BaseModel):
    event_id: str
    target_type: str
    target_id: str
    language: str | None = None
    trade_stance: TradeStance
    attention_valence: AttentionValence
    narrative_cluster_key: str | None = None
    claim_type: str
    evidence_type: str
    semantic_confidence: float
    co_mentioned_targets: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    status: MentionSemanticStatus
    unavailable_reason: str | None = None

    @field_validator("trade_stance", mode="before")
    @classmethod
    def normalize_empty_stance(cls, value: Any) -> Any:
        return "unknown" if value is None or str(value).strip() == "" else value

    @field_validator("attention_valence", mode="before")
    @classmethod
    def normalize_empty_valence(cls, value: Any) -> Any:
        return "unknown" if value is None or str(value).strip() == "" else value

    @field_validator("semantic_confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, value: Any) -> float:
        return max(0.0, min(1.0, float(value or 0.0)))

    @model_validator(mode="after")
    def validate_evidence_refs(self) -> MentionSemanticLabel:
        if self.status == "labeled" and not self.evidence_refs:
            raise ValueError("labeled mention semantics require at least one evidence ref")
        return self


class MentionSemanticsBatchRequest(BaseModel):
    run_id: str
    schema_version: str
    prompt_version: str
    mentions: list[dict[str, Any]]
    raw_request: dict[str, Any] = Field(default_factory=dict)


class MentionSemanticsBatchResult(BaseModel):
    run_id: str
    schema_version: str
    prompt_version: str
    labels: list[MentionSemanticLabel] = Field(default_factory=list)
    failures: list[dict[str, Any]] = Field(default_factory=list)
    raw_response: dict[str, Any] = Field(default_factory=dict)
    agent_run_audit: dict[str, Any] = Field(default_factory=dict)
