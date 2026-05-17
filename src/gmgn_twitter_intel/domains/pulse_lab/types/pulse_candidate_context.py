from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.interfaces import PULSE_VERSION


@dataclass(frozen=True)
class PulseCandidateContext:
    candidate_id: str
    candidate_type: str
    subject_key: str
    window: str
    scope: str
    trigger_signature: str
    timeline_signature: str
    priority: int
    target_type: str | None
    target_id: str | None
    symbol: str | None
    factor_snapshot: dict[str, Any]
    selected_posts: list[dict[str, Any]]
    gate_result: dict[str, Any] | None
    edge_state: dict[str, Any] | None
    edge_events: tuple[str, ...]
    source_event_ids: list[str]
    evidence_event_ids: list[str]

    def agent_context(self) -> dict[str, Any]:
        return {
            "pulse_version": PULSE_VERSION,
            "candidate_id": self.candidate_id,
            "candidate_type": self.candidate_type,
            "subject_key": self.subject_key,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "symbol": self.symbol,
            "window": self.window,
            "scope": self.scope,
            "trigger_signature": self.trigger_signature,
            "timeline_signature": self.timeline_signature,
            "factor_snapshot": self.factor_snapshot,
            "gate_result": self.gate_result or {},
            "edge_state": self.edge_state or {},
            "edge_events": list(self.edge_events),
            "selected_posts": self.selected_posts,
            "source_event_ids": self.source_event_ids,
            "evidence_event_ids": self.evidence_event_ids,
        }
