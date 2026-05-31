from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from parallax.domains.pulse_lab.services.evidence_completeness_gate import (
    EvidenceCompletenessGateResult,
)
from parallax.domains.pulse_lab.types.agent_decision import (
    BearCaseMemo,
    DecisionRoute,
    FinalDecision,
    SignalAnalystMemo,
    StageRunAudit,
)
from parallax.domains.pulse_lab.types.evidence_packet import PulseEvidencePacket
from parallax.platform.agent_execution import AgentCapacityReservation


@dataclass(frozen=True, slots=True)
class PulseDecisionStageSpec:
    stage: str
    prompt_text: str
    input_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PulseStagePlan:
    run_signal_analyst: bool
    run_bear_case: bool
    run_risk_portfolio_judge: bool
    signal_model: str
    bear_model: str
    judge_model: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            "run_signal_analyst": bool(self.run_signal_analyst),
            "run_bear_case": bool(self.run_bear_case),
            "run_risk_portfolio_judge": bool(self.run_risk_portfolio_judge),
            "signal_model": str(self.signal_model),
            "bear_model": str(self.bear_model),
            "judge_model": self.judge_model,
        }


_DEFAULT_STAGE_NAMES = ("signal_analyst", "bear_case", "risk_portfolio_judge")
_DEFAULT_VALIDATORS_ENABLED = (
    "pydantic_final_decision_schema",
    "runtime_evidence_ref_subset",
    "deterministic_completeness_gate",
)
_DEFAULT_FAILURE_TAXONOMY_VERSION = "pulse-failure-taxonomy-v1"


@dataclass(frozen=True, slots=True)
class PulseAgentRuntimeContract:
    stage_names: tuple[str, ...] = _DEFAULT_STAGE_NAMES
    safety_net_enabled: bool = False
    validators_enabled: tuple[str, ...] = _DEFAULT_VALIDATORS_ENABLED
    failure_taxonomy_version: str = _DEFAULT_FAILURE_TAXONOMY_VERSION
    evidence_packet_schema_version: str = "pulse-evidence-packet-v1"

    def manifest_kwargs(self) -> dict[str, Any]:
        return {
            "stage_names": tuple(self.stage_names),
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

    def model_for_lane(self, lane: str) -> str: ...

    def try_reserve_execution(
        self,
        lane: str,
        *,
        child_lanes: tuple[str, ...] = (),
        rate_units: int = 1,
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
        stage_plan: PulseStagePlan | None = None,
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
    "PulseStagePlan",
    "SignalAnalystMemo",
]
