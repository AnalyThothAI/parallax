from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from parallax.domains.pulse_lab.services.evidence_completeness_gate import (
    EvidenceCompletenessGateResult,
)
from parallax.domains.pulse_lab.types.agent_decision import (
    DecisionRoute,
    FinalDecision,
    StageRunAudit,
)
from parallax.domains.pulse_lab.types.evidence_packet import PulseEvidencePacket
from parallax.platform.agent_execution import PULSE_DECISION_LANE, AgentCapacityReservation


@dataclass(frozen=True, slots=True)
class PulseDecisionStageSpec:
    stage: str
    prompt_text: str
    input_payload: dict[str, Any]
    knowledge_refs: tuple[str, ...] = ()
    read_only_tool_refs: tuple[str, ...] = ()


_DEFAULT_STAGE_NAMES = ("pulse_decision",)
_DEFAULT_VALIDATORS_ENABLED = (
    "pydantic_final_decision_schema",
    "runtime_evidence_ref_subset",
    "deterministic_completeness_gate",
)
_DEFAULT_FAILURE_TAXONOMY_VERSION = "pulse-failure-taxonomy-v1"


@dataclass(frozen=True, slots=True)
class PulseAgentRuntimeContract:
    stage_names: tuple[str, ...] = _DEFAULT_STAGE_NAMES
    validators_enabled: tuple[str, ...] = _DEFAULT_VALIDATORS_ENABLED
    failure_taxonomy_version: str = _DEFAULT_FAILURE_TAXONOMY_VERSION
    evidence_packet_schema_version: str = "pulse-evidence-packet-v1"

    def manifest_kwargs(self) -> dict[str, Any]:
        return {
            "stage_names": tuple(self.stage_names),
            "validators_enabled": tuple(self.validators_enabled),
            "failure_taxonomy_version": str(self.failure_taxonomy_version),
            "evidence_packet_schema_version": str(self.evidence_packet_schema_version),
        }


DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT = PulseAgentRuntimeContract()


class PulseDecisionRuntime(Protocol):
    def prompt_text_hash(self) -> str: ...

    def pulse_decision_stage_spec(
        self,
        *,
        route: DecisionRoute,
        evidence_packet: PulseEvidencePacket,
        evidence_gate: EvidenceCompletenessGateResult,
        recommendation_constraints: dict[str, Any],
    ) -> PulseDecisionStageSpec: ...

    def validate_final_evidence_refs(
        self,
        final: FinalDecision,
        *,
        evidence_packet: PulseEvidencePacket,
    ) -> None: ...

    def normalize_stage_output(
        self,
        *,
        output_type: type[Any],
        raw_output: Any,
        evidence_packet: Any,
    ) -> Any: ...

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
    ) -> PulseDecisionResult: ...


__all__ = [
    "DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT",
    "PULSE_DECISION_LANE",
    "EvidenceCompletenessGateResult",
    "PulseAgentRuntimeContract",
    "PulseDecisionProvider",
    "PulseDecisionResult",
    "PulseDecisionRuntime",
    "PulseDecisionStageSpec",
    "PulseEvidencePacket",
]
