from __future__ import annotations

from typing import Any, Protocol

from gmgn_twitter_intel.platform.agent_execution import AgentCapacityReservation


class HandleTopicSummaryProvider(Protocol):
    provider: str
    model: str
    timeout_seconds: float

    def try_reserve_execution(self, lane: str) -> AgentCapacityReservation: ...

    def request_audit(
        self,
        *,
        handle: str,
        events: list[dict[str, Any]],
        run_id: str,
        job: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def summarize_handle(
        self,
        *,
        handle: str,
        events: list[dict[str, Any]],
        run_id: str,
        job: dict[str, Any],
        context: dict[str, Any],
        reservation: AgentCapacityReservation | None = None,
    ) -> dict[str, Any]: ...


__all__ = ["HandleTopicSummaryProvider"]
