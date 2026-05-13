from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import DecisionRoute, FinalDecision, StageRunAudit


@dataclass(frozen=True, slots=True)
class PulseDecisionResult:
    final_decision: FinalDecision
    agent_run_audit: dict[str, Any]
    stage_audits: tuple[StageRunAudit, ...]


class PulseDecisionProvider(Protocol):
    provider: str
    model: str
    timeout_seconds: float

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


__all__ = ["PulseDecisionProvider", "PulseDecisionResult"]
