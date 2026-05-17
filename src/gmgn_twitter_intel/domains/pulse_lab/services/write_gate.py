from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import FinalDecision


@dataclass(frozen=True, slots=True)
class PulseWriteGateDecision:
    public_write_allowed: bool
    playbook_write_allowed: bool
    reason: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "public_write_allowed": self.public_write_allowed,
            "playbook_write_allowed": self.playbook_write_allowed,
            "reason": self.reason,
        }


class PulseWriteGate:
    def evaluate(
        self,
        *,
        final_decision: FinalDecision,
        eval_result: dict[str, Any],
        gate: Any,
    ) -> PulseWriteGateDecision:
        eval_status = str(eval_result.get("status") or "")
        if eval_status != "pass":
            return PulseWriteGateDecision(
                public_write_allowed=False,
                playbook_write_allowed=False,
                reason="deterministic_eval_failed",
            )
        if final_decision.recommendation == "abstain":
            return PulseWriteGateDecision(
                public_write_allowed=True,
                playbook_write_allowed=False,
                reason="abstain_no_playbook",
            )
        if final_decision.recommendation == "ignore":
            return PulseWriteGateDecision(
                public_write_allowed=True,
                playbook_write_allowed=False,
                reason="ignore_no_playbook",
            )
        playbook_allowed = bool(
            str(getattr(gate, "pulse_status", "") or "") in {"trade_candidate", "token_watch"}
            and final_decision.playbook.has_playbook
        )
        return PulseWriteGateDecision(
            public_write_allowed=True,
            playbook_write_allowed=playbook_allowed,
            reason=None if playbook_allowed else "playbook_not_allowed",
        )


__all__ = ["PulseWriteGate", "PulseWriteGateDecision"]
