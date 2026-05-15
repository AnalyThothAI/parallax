from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DecisionRoute = Literal["cex", "meme", "research_only"]
DecisionRecommendation = Literal["high_conviction", "trade_candidate", "watchlist", "ignore", "abstain"]
StageName = Literal["analyst", "critic", "judge", "research_only_gate"]
StageStatus = Literal["ok", "failed", "timeout", "skipped"]

_FORBIDDEN_EXECUTION_RE = re.compile(
    r"买入|卖出|开仓|做多|做空|仓位|杠杆|目标价|止损|止盈|"
    r"\b(?:buy|sell|leverage|position\s+sizing?|stop[-\s]+loss|take[-\s]+profit|target\s+price)\b|"
    r"\b(?:go|enter|open)\s+(?:long|short)\b|"
    r"\b(?:long|short)\s+position\b",
    re.IGNORECASE,
)


class AnalystOpinion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: DecisionRoute
    recommendation: Literal["trade_candidate", "watchlist", "ignore"]
    confidence: float = Field(ge=0, le=1)
    summary_zh: str
    evidence: list[str]

    @field_validator("summary_zh", mode="after")
    @classmethod
    def _strip_summary(cls, value: str) -> str:
        return _clean_text(value)

    @model_validator(mode="after")
    def _reject_execution_language(self) -> AnalystOpinion:
        _reject_execution_language(self.model_dump(mode="json"))
        return self


class CritiqueReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: DecisionRoute
    weaknesses: list[str]
    missing_fact_impacts: list[str]
    confidence_ceiling: float = Field(ge=0, le=1)
    should_abstain: bool

    @model_validator(mode="after")
    def _reject_execution_language(self) -> CritiqueReport:
        _reject_execution_language(self.model_dump(mode="json"))
        return self


class FinalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: DecisionRoute
    recommendation: DecisionRecommendation
    confidence: float = Field(ge=0, le=1)
    abstain_reason: str | None
    summary_zh: str
    invalidation_conditions: list[str]
    residual_risks: list[str]
    evidence_event_ids: list[str]

    @field_validator("summary_zh", mode="after")
    @classmethod
    def _strip_summary(cls, value: str) -> str:
        return _clean_text(value)

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
        if self.recommendation == "abstain" and not _clean_text(self.abstain_reason or ""):
            raise ValueError("abstain_reason is required when recommendation is abstain")
        if self.recommendation != "abstain" and not (self.evidence_event_ids or self.residual_risks):
            raise ValueError("non-abstain decisions require evidence_event_ids or residual_risks")
        _reject_execution_language(self.model_dump(mode="json"))
        return self


class StageRunAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


class PulseDecisionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


def _clean_text(value: str) -> str:
    return value.strip()


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
    "AnalystOpinion",
    "CritiqueReport",
    "DecisionRecommendation",
    "DecisionRoute",
    "FinalDecision",
    "PulseDecisionPayload",
    "PulseStageFailure",
    "StageName",
    "StageRunAudit",
    "StageStatus",
    "contains_trading_execution_instruction",
]
