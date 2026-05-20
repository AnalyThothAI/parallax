from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from gmgn_twitter_intel.domains.pulse_lab.services.evidence_completeness_gate import (
    EvidenceCompletenessGateResult,
)
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    BearCaseMemo,
    DecisionRoute,
    FinalDecision,
    SignalAnalystMemo,
    StageRunAudit,
)
from gmgn_twitter_intel.domains.pulse_lab.types.evidence_packet import PulseEvidencePacket
from gmgn_twitter_intel.platform.agent_execution import AgentCapacityReservation


@dataclass(frozen=True, slots=True)
class PulseDecisionStageSpec:
    stage: str
    prompt_text: str
    input_payload: dict[str, Any]


_DEFAULT_STAGE_NAMES = ("signal_analyst", "bear_case", "risk_portfolio_judge")
_DEFAULT_MAX_TURNS_PER_STAGE = {
    "signal_analyst": 1,
    "bear_case": 1,
    "risk_portfolio_judge": 1,
}
_DEFAULT_TOOL_NAMES_BY_STAGE = {
    "signal_analyst": (),
    "bear_case": (),
    "risk_portfolio_judge": (),
}
_DEFAULT_VALIDATORS_ENABLED = (
    "pydantic_final_decision_schema",
    "runtime_evidence_ref_subset",
    "deterministic_completeness_gate",
)
_DEFAULT_FAILURE_TAXONOMY_VERSION = "pulse-failure-taxonomy-v1"


@dataclass(frozen=True, slots=True)
class PulseAgentRuntimeContract:
    stage_names: tuple[str, ...] = _DEFAULT_STAGE_NAMES
    max_turns_per_stage: dict[str, int] = field(default_factory=lambda: dict(_DEFAULT_MAX_TURNS_PER_STAGE))
    tool_names_by_stage: dict[str, tuple[str, ...]] = field(default_factory=lambda: dict(_DEFAULT_TOOL_NAMES_BY_STAGE))
    safety_net_enabled: bool = False
    validators_enabled: tuple[str, ...] = _DEFAULT_VALIDATORS_ENABLED
    failure_taxonomy_version: str = _DEFAULT_FAILURE_TAXONOMY_VERSION
    evidence_packet_schema_version: str = "pulse-evidence-packet-v1"

    def manifest_kwargs(self) -> dict[str, Any]:
        return {
            "stage_names": tuple(self.stage_names),
            "max_turns_per_stage": dict(self.max_turns_per_stage),
            "tool_names_by_stage": {str(stage): tuple(names) for stage, names in self.tool_names_by_stage.items()},
            "safety_net_enabled": bool(self.safety_net_enabled),
            "validators_enabled": tuple(self.validators_enabled),
            "failure_taxonomy_version": str(self.failure_taxonomy_version),
            "evidence_packet_schema_version": str(self.evidence_packet_schema_version),
        }


DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT = PulseAgentRuntimeContract()


class PulseDecisionRuntime(Protocol):
    def signal_analyst_stage_spec(
        self,
        *,
        route: DecisionRoute,
        evidence_packet: PulseEvidencePacket,
        evidence_gate: EvidenceCompletenessGateResult,
    ) -> PulseDecisionStageSpec: ...

    def bear_case_stage_spec(
        self,
        *,
        route: DecisionRoute,
        evidence_packet: PulseEvidencePacket,
        evidence_gate: EvidenceCompletenessGateResult,
        signal_memo: SignalAnalystMemo,
    ) -> PulseDecisionStageSpec: ...

    def risk_portfolio_judge_stage_spec(
        self,
        *,
        route: DecisionRoute,
        evidence_packet: PulseEvidencePacket,
        evidence_gate: EvidenceCompletenessGateResult,
        signal_memo: SignalAnalystMemo,
        bear_memo: BearCaseMemo,
        recommendation_constraints: dict[str, Any],
    ) -> PulseDecisionStageSpec: ...

    def validate_signal_refs(
        self,
        signal_memo: SignalAnalystMemo,
        *,
        evidence_packet: PulseEvidencePacket,
    ) -> None: ...

    def validate_bear_refs(
        self,
        bear_memo: BearCaseMemo,
        *,
        evidence_packet: PulseEvidencePacket,
    ) -> None: ...

    def validate_final_evidence_refs(
        self,
        final: FinalDecision,
        *,
        evidence_packet: PulseEvidencePacket,
        signal_memo: SignalAnalystMemo,
        bear_memo: BearCaseMemo,
    ) -> None: ...

    def normalize_stage_output(
        self,
        *,
        output_type: type[Any],
        raw_output: Any,
        evidence_packet: Any,
    ) -> Any: ...

    def enrich_evidence_urls(self, final: FinalDecision) -> FinalDecision: ...

    def mark_step_failed(self, step: StageRunAudit, *, error: str) -> StageRunAudit: ...

    def request_audit(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: dict[str, Any],
        runtime_manifest: dict[str, Any],
        model: str,
        artifact_version_hash: str,
        workflow_name: str,
        agent_name: str,
    ) -> dict[str, Any]: ...

    def with_output_hash(self, audit: dict[str, Any], *, final: FinalDecision) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class PulseDecisionResult:
    final_decision: FinalDecision
    agent_run_audit: dict[str, Any]
    stage_audits: tuple[StageRunAudit, ...]


class PulseDecisionProvider(Protocol):
    provider: str
    model: str
    timeout_seconds: float

    @property
    def runtime_contract(self) -> PulseAgentRuntimeContract: ...

    def try_reserve_execution(
        self,
        lane: str,
        *,
        child_lanes: tuple[str, ...] = (),
        scope: str = "execution",
    ) -> AgentCapacityReservation: ...

    def request_audit(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: dict[str, Any],
        runtime_manifest: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def run_decision_pipeline(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: dict[str, Any],
        runtime_manifest: dict[str, Any],
        parent_reservation: AgentCapacityReservation | None = None,
    ) -> PulseDecisionResult: ...


__all__ = [
    "DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT",
    "BearCaseMemo",
    "EvidenceCompletenessGateResult",
    "PulseAgentRuntimeContract",
    "PulseDecisionProvider",
    "PulseDecisionResult",
    "PulseDecisionRuntime",
    "PulseDecisionStageSpec",
    "PulseEvidencePacket",
    "SignalAnalystMemo",
]
