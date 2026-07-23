from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DAILY_MACRO_JUDGMENT_SCHEMA_VERSION: Literal["daily_macro_judgment_v1"] = "daily_macro_judgment_v1"
DAILY_MACRO_JUDGMENT_RENDERER_VERSION: Literal["daily_macro_judgment_zh_v1"] = "daily_macro_judgment_zh_v1"
MACRO_EVIDENCE_PACK_SCHEMA_VERSION: Literal["macro_evidence_pack_v1"] = "macro_evidence_pack_v1"
MACRO_EVIDENCE_SELECTION_POLICY_VERSION: Literal["macro_point_in_time_v1"] = "macro_point_in_time_v1"
EXPERIMENTAL_MARKER: Literal["experimental_shadow_research"] = "experimental_shadow_research"

MACRO_PAGE_IDS = (
    "overview",
    "cross_asset",
    "rates_inflation",
    "growth_labor",
    "liquidity_funding",
    "credit",
)
_FORBIDDEN_KEYS = frozenset(
    {
        "score",
        "pressure_score",
        "probability",
        "confidence",
        "expected_return",
        "position",
        "position_size",
        "allocation",
        "entry",
        "entry_price",
        "stop",
        "stop_loss",
        "target",
        "target_price",
        "leverage",
    }
)
_FORBIDDEN_INSTRUCTION_FRAGMENTS = (
    "买入",
    "卖出",
    "开仓",
    "平仓",
    "止损",
    "目标价",
    "仓位",
    "position size",
    "buy ",
    "sell ",
    "stop loss",
    "target price",
)


class ExactDomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class JudgmentDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    RANGE = "range"
    NO_CALL = "no_call"


class MacroPressureAxis(StrEnum):
    GROWTH = "growth"
    INFLATION = "inflation"
    POLICY_REAL_RATES = "policy_real_rates"
    TERM_PREMIUM_SUPPLY = "term_premium_supply"
    LIQUIDITY_FUNDING = "liquidity_funding"
    CREDIT = "credit"


class EvidenceAvailability(StrEnum):
    EXACT_TIMESTAMP = "exact_timestamp"
    PRIOR_DATE = "prior_date"
    SESSION_CLOSE = "session_close"


class EvidencePackHealthStatus(StrEnum):
    READY = "ready"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


class EvidenceExclusion(ExactDomainModel):
    source_name: str
    concept_key: str | None = None
    series_key: str | None = None
    reason: str


class MacroEvidenceItem(ExactDomainModel):
    evidence_ref: str
    page_id: Literal[
        "overview",
        "cross_asset",
        "rates_inflation",
        "growth_labor",
        "liquidity_funding",
        "credit",
    ]
    source_name: str
    concept_key: str
    series_key: str
    observed_at: date
    available_at_ms: int = Field(ge=0)
    availability: EvidenceAvailability
    source_timestamp: str
    ingested_at_ms: int = Field(ge=0)
    data_quality: str
    selection_rule: str
    content_hash: str
    content: dict[str, Any]


class MacroTextEvidence(ExactDomainModel):
    evidence_ref: str
    source_id: str
    source_name: str
    trust_tier: Literal["official", "high"]
    source_quality: Literal["healthy", "degraded"]
    published_at_ms: int = Field(ge=0)
    fetched_at_ms: int = Field(ge=0)
    title: str
    summary: str
    body_text: str
    canonical_url: str
    source_content_hash: str
    content_hash: str
    selection_rule: str


class EvidencePackHealth(ExactDomainModel):
    status: EvidencePackHealthStatus
    global_reasons: tuple[str, ...] = ()
    local_reasons: tuple[str, ...] = ()
    no_call_horizons: tuple[Literal[5, 20], ...] = ()

    @model_validator(mode="after")
    def validate_health(self) -> EvidencePackHealth:
        if self.status is EvidencePackHealthStatus.BLOCKED and not self.global_reasons:
            raise ValueError("macro_evidence_pack_block_reason_required")
        if self.status is EvidencePackHealthStatus.READY and (
            self.global_reasons or self.local_reasons or self.no_call_horizons
        ):
            raise ValueError("macro_evidence_pack_ready_must_have_no_degradation")
        return self


class MacroEvidencePack(ExactDomainModel):
    schema_version: Literal["macro_evidence_pack_v1"] = MACRO_EVIDENCE_PACK_SCHEMA_VERSION
    selection_policy_version: Literal["macro_point_in_time_v1"] = MACRO_EVIDENCE_SELECTION_POLICY_VERSION
    session_date: date
    market_cutoff_ms: int = Field(ge=0)
    sealed_at_ms: int = Field(ge=0)
    projection_version: Literal["macro_decision_v2"]
    pages: dict[str, dict[str, Any]]
    evidence: tuple[MacroEvidenceItem, ...]
    texts: tuple[MacroTextEvidence, ...] = ()
    exclusions: tuple[EvidenceExclusion, ...] = ()
    health: EvidencePackHealth

    @field_validator("pages")
    @classmethod
    def validate_pages(cls, value: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        if set(value) != set(MACRO_PAGE_IDS):
            raise ValueError("macro_evidence_pack_exact_six_pages_required")
        return value

    @model_validator(mode="after")
    def validate_identity(self) -> MacroEvidencePack:
        if self.sealed_at_ms < self.market_cutoff_ms:
            raise ValueError("macro_evidence_pack_sealed_before_cutoff")
        refs = [item.evidence_ref for item in self.evidence]
        refs.extend(item.evidence_ref for item in self.texts)
        if len(refs) != len(set(refs)):
            raise ValueError("macro_evidence_pack_duplicate_ref")
        if any(item.available_at_ms > self.market_cutoff_ms for item in self.evidence):
            raise ValueError("macro_evidence_pack_future_fact")
        if any(item.published_at_ms > self.market_cutoff_ms for item in self.texts):
            raise ValueError("macro_evidence_pack_future_text")
        if any(item.ingested_at_ms > self.sealed_at_ms for item in self.evidence):
            raise ValueError("macro_evidence_pack_uningested_fact")
        if any(item.fetched_at_ms > self.sealed_at_ms for item in self.texts):
            raise ValueError("macro_evidence_pack_unfetched_text")
        return self

    @property
    def evidence_refs(self) -> frozenset[str]:
        refs = {item.evidence_ref for item in self.evidence}
        refs.update(item.evidence_ref for item in self.texts)
        return frozenset(refs)

    @property
    def pack_hash(self) -> str:
        return canonical_json_hash(self.model_dump(mode="json"))


class MacroPressure(ExactDomainModel):
    axis: MacroPressureAxis
    state: Literal["rising", "elevated", "easing", "neutral", "unclear"]
    mechanism: str
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class SpyHorizonCall(ExactDomainModel):
    horizon_sessions: Literal[5, 20]
    direction: JudgmentDirection
    thesis: str
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class JudgmentObservation(ExactDomainModel):
    statement: str
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class JudgmentAuditVersions(ExactDomainModel):
    evidence_pack_hash: str
    schema_version: Literal["daily_macro_judgment_v1"] = DAILY_MACRO_JUDGMENT_SCHEMA_VERSION
    prompt_version: str
    workflow_version: str


class DailyMacroJudgment(ExactDomainModel):
    experimental_marker: Literal["experimental_shadow_research"] = EXPERIMENTAL_MARKER
    session_date: date
    market_cutoff_ms: int = Field(ge=0)
    data_health: Literal["ready", "degraded"]
    macro_state: str = Field(min_length=1, max_length=1200)
    pressures: tuple[MacroPressure, ...] = Field(min_length=1, max_length=4)
    spy_5d: SpyHorizonCall
    spy_20d: SpyHorizonCall
    counterevidence: tuple[JudgmentObservation, ...] = Field(min_length=1, max_length=4)
    audit_versions: JudgmentAuditVersions

    @model_validator(mode="after")
    def validate_calls_and_pressures(self) -> DailyMacroJudgment:
        if self.spy_5d.horizon_sessions != 5 or self.spy_20d.horizon_sessions != 20:
            raise ValueError("daily_macro_judgment_horizon_mismatch")
        axes = [pressure.axis for pressure in self.pressures]
        if len(axes) != len(set(axes)):
            raise ValueError("daily_macro_judgment_duplicate_pressure_axis")
        return self

    @property
    def all_evidence_refs(self) -> frozenset[str]:
        values: list[str] = []
        for pressure in self.pressures:
            values.extend(pressure.evidence_refs)
        values.extend(self.spy_5d.evidence_refs)
        values.extend(self.spy_20d.evidence_refs)
        for observation in self.counterevidence:
            values.extend(observation.evidence_refs)
        return frozenset(values)


class ReviewerIssue(ExactDomainModel):
    code: Literal[
        "fact_mismatch",
        "reference_missing",
        "causal_jump",
        "contradiction_omitted",
        "scope_violation",
        "data_health_violation",
    ]
    message: str
    evidence_refs: tuple[str, ...] = ()


class ReviewerResult(ExactDomainModel):
    disposition: Literal["pass", "revise", "block"]
    issues: tuple[ReviewerIssue, ...] = ()

    @model_validator(mode="after")
    def validate_issues(self) -> ReviewerResult:
        if self.disposition == "pass" and self.issues:
            raise ValueError("daily_macro_reviewer_pass_has_issues")
        if self.disposition != "pass" and not self.issues:
            raise ValueError("daily_macro_reviewer_issues_required")
        return self


class DailyMacroOutcome(ExactDomainModel):
    session_date: date
    horizon_sessions: Literal[5, 20]
    target_session_date: date
    start_close: float = Field(gt=0)
    target_close: float = Field(gt=0)
    realized_return_pct: float
    source_evidence_refs: tuple[str, ...] = Field(min_length=2)
    computed_at_ms: int = Field(ge=0)


@dataclass(frozen=True, slots=True)
class MacroAgentAnalysis:
    judgment: DailyMacroJudgment
    reviewer: ReviewerResult
    audit: dict[str, Any]
    model_name: str
    prompt_version: str
    workflow_version: str


class MacroJudgmentAgent(Protocol):
    async def analyze(self, evidence_pack: MacroEvidencePack) -> MacroAgentAnalysis: ...


class JudgmentGateError(ValueError):
    pass


def validate_daily_macro_judgment(
    raw_judgment: Mapping[str, Any] | DailyMacroJudgment,
    *,
    evidence_pack: MacroEvidencePack,
    reviewer: ReviewerResult,
) -> DailyMacroJudgment:
    if evidence_pack.health.status is EvidencePackHealthStatus.BLOCKED:
        raise JudgmentGateError("daily_macro_judgment_pack_blocked")
    raw_payload = (
        raw_judgment.model_dump(mode="json") if isinstance(raw_judgment, DailyMacroJudgment) else dict(raw_judgment)
    )
    forbidden_keys = _find_forbidden_keys(raw_payload)
    if forbidden_keys:
        raise JudgmentGateError("daily_macro_judgment_forbidden_fields:" + ",".join(sorted(forbidden_keys)))
    try:
        judgment = DailyMacroJudgment.model_validate(raw_payload)
    except Exception as exc:
        raise JudgmentGateError(f"daily_macro_judgment_schema_invalid:{_safe_error(exc)}") from exc
    if reviewer.disposition != "pass":
        raise JudgmentGateError(f"daily_macro_judgment_reviewer_{reviewer.disposition}")
    if judgment.session_date != evidence_pack.session_date:
        raise JudgmentGateError("daily_macro_judgment_session_mismatch")
    if judgment.market_cutoff_ms != evidence_pack.market_cutoff_ms:
        raise JudgmentGateError("daily_macro_judgment_cutoff_mismatch")
    if judgment.audit_versions.evidence_pack_hash != evidence_pack.pack_hash:
        raise JudgmentGateError("daily_macro_judgment_pack_hash_mismatch")
    expected_health = "degraded" if evidence_pack.health.status is EvidencePackHealthStatus.DEGRADED else "ready"
    if judgment.data_health != expected_health:
        raise JudgmentGateError("daily_macro_judgment_data_health_mismatch")
    missing_refs = sorted(judgment.all_evidence_refs - evidence_pack.evidence_refs)
    if missing_refs:
        raise JudgmentGateError("daily_macro_judgment_unknown_evidence_refs:" + ",".join(missing_refs))
    for horizon in evidence_pack.health.no_call_horizons:
        call = judgment.spy_5d if horizon == 5 else judgment.spy_20d
        if call.direction is not JudgmentDirection.NO_CALL:
            raise JudgmentGateError(f"daily_macro_judgment_degraded_horizon_requires_no_call:{horizon}")
    forbidden_text = _find_forbidden_instruction(judgment)
    if forbidden_text is not None:
        raise JudgmentGateError(f"daily_macro_judgment_trade_instruction_forbidden:{forbidden_text}")
    return judgment


def render_daily_macro_judgment_zh(judgment: DailyMacroJudgment) -> str:
    health_label = "正常" if judgment.data_health == "ready" else "降级"
    pressure_lines = [
        f"- {pressure.axis.value}: {pressure.state}；{pressure.mechanism}" for pressure in judgment.pressures
    ]
    counterevidence_lines = [f"- {item.statement}" for item in judgment.counterevidence]
    return (
        "\n".join(
            [
                "# 每日宏观 SPY 研判",
                "",
                f"- 目标交易日：{judgment.session_date.isoformat()}",
                f"- 官方收盘 cutoff（UTC ms）：{judgment.market_cutoff_ms}",
                f"- 数据健康：{health_label}",
                "- 标记：experimental / shadow research",
                "",
                "## 宏观状态与主要压力",
                "",
                judgment.macro_state,
                *pressure_lines,
                "",
                "## SPY 5D / 20D",
                "",
                f"- 5D：{judgment.spy_5d.direction.value}；{judgment.spy_5d.thesis}",
                f"- 20D：{judgment.spy_20d.direction.value}；{judgment.spy_20d.thesis}",
                "",
                "## 关键反证",
                "",
                *counterevidence_lines,
            ]
        ).strip()
        + "\n"
    )


def require_renderer_consistency(judgment: DailyMacroJudgment, memo_text: str) -> None:
    if memo_text != render_daily_macro_judgment_zh(judgment):
        raise JudgmentGateError("daily_macro_judgment_renderer_mismatch")


def canonical_json_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _find_forbidden_keys(value: Any, *, path: tuple[str, ...] = ()) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_KEYS:
                found.add(".".join((*path, normalized)))
            found.update(_find_forbidden_keys(item, path=(*path, normalized)))
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for index, item in enumerate(value):
            found.update(_find_forbidden_keys(item, path=(*path, str(index))))
    return found


def _find_forbidden_instruction(judgment: DailyMacroJudgment) -> str | None:
    rendered = json.dumps(judgment.model_dump(mode="json"), ensure_ascii=False).lower()
    return next((fragment for fragment in _FORBIDDEN_INSTRUCTION_FRAGMENTS if fragment in rendered), None)


def _safe_error(exc: Exception) -> str:
    return str(exc).replace("\n", " ")[:500]


__all__ = [
    "DAILY_MACRO_JUDGMENT_RENDERER_VERSION",
    "DAILY_MACRO_JUDGMENT_SCHEMA_VERSION",
    "EXPERIMENTAL_MARKER",
    "MACRO_EVIDENCE_PACK_SCHEMA_VERSION",
    "MACRO_EVIDENCE_SELECTION_POLICY_VERSION",
    "DailyMacroJudgment",
    "DailyMacroOutcome",
    "EvidenceAvailability",
    "EvidenceExclusion",
    "EvidencePackHealth",
    "EvidencePackHealthStatus",
    "JudgmentAuditVersions",
    "JudgmentDirection",
    "JudgmentGateError",
    "JudgmentObservation",
    "MacroAgentAnalysis",
    "MacroEvidenceItem",
    "MacroEvidencePack",
    "MacroJudgmentAgent",
    "MacroPressure",
    "MacroPressureAxis",
    "MacroTextEvidence",
    "ReviewerIssue",
    "ReviewerResult",
    "SpyHorizonCall",
    "canonical_json_hash",
    "render_daily_macro_judgment_zh",
    "require_renderer_consistency",
    "validate_daily_macro_judgment",
]
