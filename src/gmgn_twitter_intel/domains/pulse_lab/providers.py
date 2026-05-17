from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    DecisionRoute,
    FinalDecision,
    InvestigationReport,
    StageName,
    StageRunAudit,
)


class ToolBudgetExceeded(RuntimeError):
    """Investigator tool call budget was exceeded for the route."""


class PulseAgentToolRuntime(Protocol):
    tool_calls_count: int
    investigator_max_tool_calls: int
    contributed_event_ids: set[str]

    def get_target_recent_tweets(self, *, target_id: str, limit: int = 15) -> dict[str, Any]: ...

    def get_target_price_action(self, *, target_id: str, hours: int = 24) -> dict[str, Any]: ...

    def get_official_token_profile(self, *, target_id: str) -> dict[str, Any]: ...


class PulseAgentToolRuntimeFactory(Protocol):
    def __call__(self, *, investigator_max_tool_calls: int) -> PulseAgentToolRuntime: ...


@dataclass(frozen=True, slots=True)
class PulseDecisionStageSpec:
    stage: StageName
    prompt_text: str
    input_payload: dict[str, Any]


_DEFAULT_STAGE_NAMES = ("investigator", "decision_maker")
_DEFAULT_MAX_TURNS_PER_STAGE = {"investigator": 5, "decision_maker": 3}
_DEFAULT_TOOL_NAMES_BY_STAGE = {
    "investigator": (
        "get_target_recent_tweets",
        "get_target_price_action",
        "get_official_token_profile",
    ),
    "decision_maker": ("get_target_recent_tweets",),
}
_DEFAULT_ROUTE_TOOL_BUDGETS = {"cex": 3, "meme": 5, "research_only": 3}
_DEFAULT_VALIDATORS_ENABLED = (
    "pydantic_final_decision_schema",
    "runtime_evidence_id_subset",
    "deterministic_completeness_gate",
)
_DEFAULT_FAILURE_TAXONOMY_VERSION = "pulse-failure-taxonomy-v1"


@dataclass(frozen=True, slots=True)
class PulseAgentHarnessContract:
    stage_names: tuple[str, ...] = _DEFAULT_STAGE_NAMES
    max_turns_per_stage: dict[str, int] = field(default_factory=lambda: dict(_DEFAULT_MAX_TURNS_PER_STAGE))
    tool_names_by_stage: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: dict(_DEFAULT_TOOL_NAMES_BY_STAGE)
    )
    route_tool_budgets: dict[str, int] = field(default_factory=lambda: dict(_DEFAULT_ROUTE_TOOL_BUDGETS))
    decision_maker_fallback_tool_enabled: bool = True
    safety_net_enabled: bool = False
    validators_enabled: tuple[str, ...] = _DEFAULT_VALIDATORS_ENABLED
    failure_taxonomy_version: str = _DEFAULT_FAILURE_TAXONOMY_VERSION

    def manifest_kwargs(self) -> dict[str, Any]:
        return {
            "stage_names": tuple(self.stage_names),
            "max_turns_per_stage": dict(self.max_turns_per_stage),
            "tool_names_by_stage": {
                str(stage): tuple(names) for stage, names in self.tool_names_by_stage.items()
            },
            "route_tool_budgets": dict(self.route_tool_budgets),
            "safety_net_enabled": bool(self.safety_net_enabled),
            "validators_enabled": tuple(self.validators_enabled),
            "failure_taxonomy_version": str(self.failure_taxonomy_version),
        }


DEFAULT_PULSE_AGENT_HARNESS_CONTRACT = PulseAgentHarnessContract()


class PulseDecisionRuntime(Protocol):
    def tool_budget_for_route(self, *, route: DecisionRoute, budgets: dict[str, int] | None) -> int: ...

    def investigator_stage_spec(
        self,
        *,
        route: DecisionRoute,
        context: dict[str, Any],
        completeness: dict[str, Any],
    ) -> PulseDecisionStageSpec: ...

    def decision_maker_stage_spec(
        self,
        *,
        route: DecisionRoute,
        context: dict[str, Any],
        completeness: dict[str, Any],
        investigation: InvestigationReport,
    ) -> PulseDecisionStageSpec: ...

    def validate_supporting_ids(
        self,
        investigation: InvestigationReport,
        *,
        tool_runtime: PulseAgentToolRuntime,
        context: dict[str, Any],
    ) -> None: ...

    def validate_final_evidence_ids(
        self,
        final: FinalDecision,
        *,
        investigation: InvestigationReport,
        tool_runtime: PulseAgentToolRuntime,
        context: dict[str, Any],
    ) -> None: ...

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
        harness: dict[str, Any],
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
    def harness_contract(self) -> PulseAgentHarnessContract: ...

    def request_audit(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: dict[str, Any],
        harness: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def run_decision_pipeline(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: dict[str, Any],
        harness: dict[str, Any],
    ) -> PulseDecisionResult: ...


__all__ = [
    "DEFAULT_PULSE_AGENT_HARNESS_CONTRACT",
    "PulseAgentHarnessContract",
    "PulseAgentToolRuntime",
    "PulseAgentToolRuntimeFactory",
    "PulseDecisionProvider",
    "PulseDecisionResult",
    "PulseDecisionRuntime",
    "PulseDecisionStageSpec",
    "ToolBudgetExceeded",
]
