from __future__ import annotations

from typing import Any, Protocol

from gmgn_twitter_intel.platform.agent_execution import AgentCapacityReservation


class SocialEventEnrichmentProvider(Protocol):
    provider: str
    model: str
    timeout_seconds: float

    def try_reserve_execution(self, lane: str) -> AgentCapacityReservation: ...

    def request_audit(
        self,
        *,
        event: dict[str, Any],
        entities: list[dict[str, Any]],
        run_id: str,
        job: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def enrich_event(
        self,
        *,
        event: dict[str, Any],
        entities: list[dict[str, Any]],
        run_id: str,
        job: dict[str, Any],
        reservation: AgentCapacityReservation | None = None,
    ) -> Any: ...


__all__ = ["SocialEventEnrichmentProvider"]
