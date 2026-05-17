from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DecisionRoute = Literal["cex", "meme", "research_only"]
DecisionRecommendation = Literal["high_conviction", "trade_candidate", "watchlist", "ignore", "abstain"]
StageName = Literal["investigator", "decision_maker", "research_only_gate"]
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
    """Symmetric bull-or-bear opinion attached to InvestigationReport / FinalDecision.

    `strength="absent"` means the side is intentionally empty (no evidence at
    all). All other strengths must carry a non-empty thesis and at least one
    supporting event id so downstream UI cannot render a blank bullet.
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
            if not self.supporting_event_ids:
                raise ValueError("strength != absent requires at least one supporting_event_id")
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
            raise ValueError(
                "has_playbook=false requires empty watch_signals and exit_triggers",
            )
        _reject_execution_language(self.model_dump(mode="json"))
        return self


class InvestigationReport(BaseModel):
    """Phase-1 Investigator stage output.

    `narrative_archetype_candidate` is free-text in phase 1 (≤ 20 chars). Phase
    2 may tighten to a Literal enum. `narrative_observation_zh` is the
    investigator's compact prose summary (30-300 chars). No markdown_report,
    no tool_call_summary — tool metadata lives in
    `pulse_agent_run_steps.input_json.tool_calls` (worker-side, P1-1).
    """

    model_config = ConfigDict(extra="ignore")

    narrative_archetype_candidate: str = ""
    narrative_observation_zh: str
    bull_observation: BullBearView
    bear_observation: BullBearView
    data_gaps: list[str] = Field(default_factory=list)

    @field_validator("narrative_archetype_candidate", mode="after")
    @classmethod
    def _archetype_len(cls, value: str) -> str:
        cleaned = _clean_text(value)
        if len(cleaned) > 20:
            raise ValueError("narrative_archetype_candidate exceeds 20 chars")
        return cleaned

    @field_validator("narrative_observation_zh", mode="after")
    @classmethod
    def _observation_len(cls, value: str) -> str:
        cleaned = _clean_text(value)
        if not (30 <= len(cleaned) <= 300):
            raise ValueError("narrative_observation_zh must be 30-300 chars")
        return cleaned

    @model_validator(mode="after")
    def _archetype_observation_consistency(self) -> InvestigationReport:
        archetype_present = bool(self.narrative_archetype_candidate.strip())
        bull_present = self.bull_observation.strength != "absent"
        bear_present = self.bear_observation.strength != "absent"
        if archetype_present and not (bull_present or bear_present):
            raise ValueError(
                "non-empty archetype requires at least one non-absent observation",
            )
        _reject_execution_language(self.model_dump(mode="json"))
        return self


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

    @model_validator(mode="after")
    def _validate_decision(self) -> FinalDecision:
        if self.recommendation == "abstain":
            if not _clean_text(self.abstain_reason or ""):
                raise ValueError("abstain_reason is required when recommendation is abstain")
            if self.playbook.has_playbook:
                raise ValueError("recommendation=abstain requires playbook.has_playbook=false")
        elif not (self.evidence_event_ids or self.residual_risks):
            raise ValueError("non-abstain decisions require evidence_event_ids or residual_risks")
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


class PulseDecisionPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    final_decision: FinalDecision
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
    "FinalDecision",
    "InvestigationReport",
    "MonitoringHorizon",
    "PulseDecisionPayload",
    "PulseStageFailure",
    "StageName",
    "StageRunAudit",
    "StageStatus",
    "TradePlaybook",
    "contains_trading_execution_instruction",
]
