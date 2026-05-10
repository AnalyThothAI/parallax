from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from gmgn_twitter_intel.domains.pulse_lab.types.pulse_thesis import PulseThesisPayload


@dataclass(frozen=True, slots=True)
class PulseThesisResult:
    payload: PulseThesisPayload
    agent_run_audit: dict[str, Any]


class PulseThesisProvider(Protocol):
    provider: str
    model: str
    timeout_seconds: float

    def request_audit(self, *, context: dict[str, Any], run_id: str, job: dict[str, Any]) -> dict[str, Any]: ...

    async def write_thesis(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
    ) -> PulseThesisResult: ...


__all__ = ["PulseThesisProvider", "PulseThesisResult"]
