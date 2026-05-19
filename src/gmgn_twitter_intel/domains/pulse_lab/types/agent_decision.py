from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gmgn_twitter_intel.domains.pulse_lab.types.evidence_packet import PulseEvidencePacket

DecisionRoute = Literal["cex", "meme", "research_only"]
DecisionRecommendation = Literal["high_conviction", "trade_candidate", "watchlist", "ignore", "abstain"]
StageName = Literal[
    "evidence_pack",
    "evidence_completeness_gate",
    "evidence_debate",
    "claim_verifier",
    "decision_maker",
    "recommendation_clipper",
    "deterministic_eval",
    "write_gate",
]
StageStatus = Literal["ok", "failed", "timeout", "skipped"]

BullBearStrength = Literal["absent", "weak", "moderate", "strong"]
MonitoringHorizon = Literal["1h", "4h", "24h"]

_FORBIDDEN_EXECUTION_RE = re.compile(
    r"买入|卖出|开仓|做多|做空|仓位|杠杆|目标价|止损|止盈|"
    r"\b(?:buy|sell|leverage|position\s+sizing?|stop[-\s]+loss|take[-\s]+profit|target\s+price)\b|"
    r"\b(?:go|enter|open)\s+(?:long|short)\b|"
    r"\b(?:long|short)\s+position\b",
    re.IGNORECASE,
)


class BullBearView(BaseModel):
    """Symmetric bull-or-bear opinion attached to FinalDecision.

    `strength="absent"` means the side is intentionally empty (no evidence at
    all). All other strengths must carry a non-empty thesis. Event ids are best
    effort because the SDK response_format should not reject otherwise useful
    model output before the runtime can normalize refs.
    """

    model_config = ConfigDict(extra="ignore")

    strength: BullBearStrength
    thesis_zh: str = ""
    supporting_event_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _absent_must_be_empty(self) -> BullBearView:
        if self.strength == "absent":
            if _clean_text(self.thesis_zh):
                raise ValueError("strength=absent requires empty thesis_zh")
            if self.supporting_event_ids:
                raise ValueError("strength=absent requires empty supporting_event_ids")
        else:
            if not _clean_text(self.thesis_zh):
                raise ValueError("strength != absent requires non-empty thesis_zh")
        _reject_execution_language(self.model_dump(mode="json"))
        return self


class TradePlaybook(BaseModel):
    """Simplified v2 playbook: no sizing, no target price, no execution levels.

    `has_playbook=False` reserves the consistent shape for abstain / ignore
    surfaces; when False both watch_signals and exit_triggers must be empty
    so SurfaceCard rendering can degrade deterministically.
    """

    model_config = ConfigDict(extra="ignore")

    has_playbook: bool
    watch_signals: list[str] = Field(default_factory=list)
    exit_triggers: list[str] = Field(default_factory=list)
    monitoring_horizon: MonitoringHorizon

    @model_validator(mode="after")
    def _consistency(self) -> TradePlaybook:
        if self.has_playbook is False and (self.watch_signals or self.exit_triggers):
            self.watch_signals = []
            self.exit_triggers = []
        _reject_execution_language(self.model_dump(mode="json"))
        return self


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim: str = Field(max_length=180)
    evidence_refs: tuple[str, ...] = Field(max_length=3)
    stance: Literal["bull", "bear", "gap", "risk"]

    @field_validator("claim", mode="after")
    @classmethod
    def _clean_claim(cls, value: str) -> str:
        cleaned = _clean_text(value)
        if not cleaned:
            raise ValueError("claim is required")
        _reject_execution_language(cleaned)
        return cleaned

    @field_validator("evidence_refs", mode="after")
    @classmethod
    def _stable_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


class EvidenceDebateMemo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bull_claims: tuple[EvidenceClaim, ...] = Field(default=(), max_length=2)
    bear_claims: tuple[EvidenceClaim, ...] = Field(default=(), max_length=2)
    rebuttal_claims: tuple[EvidenceClaim, ...] = Field(default=(), max_length=2)
    data_gap_claims: tuple[EvidenceClaim, ...] = Field(default=(), max_length=2)
    summary_zh: str = Field(max_length=240)
    allowed_evidence_ref_ids: tuple[str, ...] = Field(default=(), max_length=16)

    @field_validator("summary_zh", mode="after")
    @classmethod
    def _clean_summary(cls, value: str) -> str:
        cleaned = _clean_text(value)
        if not cleaned:
            raise ValueError("summary_zh is required")
        _reject_execution_language(cleaned)
        return cleaned

    @field_validator("allowed_evidence_ref_ids", mode="after")
    @classmethod
    def _stable_allowed_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


class FinalDecision(BaseModel):
    """v2 strict schema: extends v1 with narrative + bull/bear + playbook.

    `abstain_reason` defaults to None so abstain validation runs in the model
    validator (v1 had it required at schema level). All v2-specific hard
    constraints live in `_validate_decision` so a single failure surfaces a
    descriptive message.
    """

    model_config = ConfigDict(extra="ignore")

    route: DecisionRoute
    recommendation: DecisionRecommendation
    confidence: float = Field(ge=0, le=1)
    abstain_reason: str | None = None
    summary_zh: str
    narrative_archetype: str = ""
    narrative_thesis_zh: str
    bull_view: BullBearView
    bear_view: BullBearView
    playbook: TradePlaybook
    evidence_event_urls: dict[str, str] = Field(default_factory=dict)
    invalidation_conditions: list[str] = Field(default_factory=list)
    residual_risks: list[str] = Field(default_factory=list)
    evidence_event_ids: list[str] = Field(default_factory=list)
    supporting_evidence_refs: tuple[str, ...] = ()
    risk_evidence_refs: tuple[str, ...] = ()
    data_gap_refs: tuple[str, ...] = ()

    @field_validator("confidence", mode="after")
    @classmethod
    def _clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @field_validator("summary_zh", mode="after")
    @classmethod
    def _strip_summary(cls, value: str) -> str:
        return _clean_text(value)

    @field_validator("narrative_thesis_zh", mode="after")
    @classmethod
    def _strip_narrative(cls, value: str) -> str:
        cleaned = _clean_text(value)
        if not (30 <= len(cleaned) <= 300):
            raise ValueError("narrative_thesis_zh must be 30-300 chars")
        return cleaned

    @field_validator("narrative_archetype", mode="after")
    @classmethod
    def _archetype_len(cls, value: str) -> str:
        cleaned = _clean_text(value)
        if len(cleaned) > 20:
            raise ValueError("narrative_archetype exceeds 20 chars")
        return cleaned

    @field_validator("evidence_event_ids", mode="after")
    @classmethod
    def _stable_event_ids(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            cleaned = _clean_text(value)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                result.append(cleaned)
        return result

    @field_validator("supporting_evidence_refs", "risk_evidence_refs", "data_gap_refs", mode="after")
    @classmethod
    def _stable_ref_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))

    @model_validator(mode="after")
    def _validate_decision(self) -> FinalDecision:
        if self.recommendation == "abstain":
            if not _clean_text(self.abstain_reason or ""):
                raise ValueError("abstain_reason is required when recommendation is abstain")
            if self.playbook.has_playbook:
                raise ValueError("recommendation=abstain requires playbook.has_playbook=false")
        elif not self.supporting_evidence_refs:
            raise ValueError("non-abstain decisions require supporting_evidence_refs")
        if self.recommendation == "high_conviction":
            if self.bull_view.strength not in ("moderate", "strong"):
                raise ValueError("high_conviction requires bull_view.strength >= moderate")
            if self.bear_view.strength not in ("moderate", "strong"):
                raise ValueError("high_conviction requires bear_view.strength >= moderate")
            if len(self.evidence_event_ids) < 3:
                raise ValueError("high_conviction requires evidence_event_ids >= 3")
            archetype_clean = self.narrative_archetype.strip()
            if not archetype_clean or archetype_clean.lower() == "unclear":
                raise ValueError("high_conviction requires non-empty narrative_archetype")
        _reject_execution_language(self.model_dump(mode="json"))
        return self


class StageRunAudit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stage: StageName
    route: DecisionRoute
    attempt_index: int = Field(ge=0)
    input_json: dict[str, Any]
    prompt_text: str
    response_json: dict[str, Any] | None
    trace_metadata_json: dict[str, Any] = Field(default_factory=dict)
    usage_json: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = Field(ge=0)
    started_at_ms: int | None = Field(default=None, ge=0)
    finished_at_ms: int | None = Field(default=None, ge=0)
    status: StageStatus
    error: str | None = None
    # Promoted from trace_metadata_json jsonb to dedicated columns by migration
    # 20260516_0048. Clients keep dual-writing into trace_metadata_json for one
    # release cycle so a rollback can recover the values.
    safety_net_used: bool = False
    safety_net_retries: int = Field(default=0, ge=0)
    parse_mode: str = "strict"
    input_hash: str | None = None
    output_hash: str | None = None


class PulseDecisionPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    final_decision: FinalDecision
    stage_audits: tuple[StageRunAudit, ...]


class PulseAgentDecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_packet: PulseEvidencePacket
    evidence_gate: dict[str, Any]
    debate_memo: EvidenceDebateMemo
    final_decision: FinalDecision
    claim_verification: dict[str, Any]
    stage_audits: tuple[StageRunAudit, ...]


class PulseStageFailure(Exception):
    """Raised when an agent decision stage fails.

    Carries the audits collected up to and including the failed stage so the worker
    can persist them to pulse_agent_run_steps before marking the run failed.
    """

    def __init__(self, message: str, *, audits: tuple[StageRunAudit, ...]) -> None:
        super().__init__(message)
        self.audits = audits


def contains_trading_execution_instruction(text: str) -> bool:
    return bool(_FORBIDDEN_EXECUTION_RE.search(text))


_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _clean_text(value: str) -> str:
    return _THINK_BLOCK_RE.sub("", value).strip()


def _reject_execution_language(value: Any) -> None:
    if isinstance(value, str):
        if contains_trading_execution_instruction(value):
            raise ValueError("trading execution language is not allowed")
        return
    if isinstance(value, dict):
        for nested in value.values():
            _reject_execution_language(nested)
        return
    if isinstance(value, list | tuple):
        for nested in value:
            _reject_execution_language(nested)


__all__ = [
    "BullBearStrength",
    "BullBearView",
    "DecisionRecommendation",
    "DecisionRoute",
    "EvidenceClaim",
    "EvidenceDebateMemo",
    "FinalDecision",
    "MonitoringHorizon",
    "PulseAgentDecisionResult",
    "PulseDecisionPayload",
    "PulseStageFailure",
    "StageName",
    "StageRunAudit",
    "StageStatus",
    "TradePlaybook",
    "contains_trading_execution_instruction",
]
