from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from gmgn_twitter_intel.domains.pulse_lab.types.pulse_recommendation import PulseRecommendationPayload


@dataclass(frozen=True, slots=True)
class PulseRecommendationResult:
    payload: PulseRecommendationPayload
    agent_run_audit: dict[str, Any]


class PulseRecommendationProvider(Protocol):
    provider: str
    model: str
    timeout_seconds: float

    def request_audit(self, *, context: dict[str, Any], run_id: str, job: dict[str, Any]) -> dict[str, Any]: ...

    async def write_recommendation(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
    ) -> PulseRecommendationResult: ...


__all__ = ["PulseRecommendationProvider", "PulseRecommendationResult"]
