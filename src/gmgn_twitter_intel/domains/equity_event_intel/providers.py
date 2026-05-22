from __future__ import annotations

from typing import Any, Protocol

from gmgn_twitter_intel.domains.equity_event_intel.types import EquityEventBriefInputPacket
from gmgn_twitter_intel.platform.agent_execution import AgentCapacityReservation


class EquityDocumentFetchResult(Protocol):
    status_code: int
    documents: list[dict[str, Any]]
    etag: str | None
    last_modified: str | None
    not_modified: bool


class EquityEventDocumentProvider(Protocol):
    def fetch_source(self, source: dict[str, Any]) -> EquityDocumentFetchResult: ...

    def close(self) -> None: ...


class EquityEventBriefProvider(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def artifact_version_hash(self) -> str: ...

    def try_reserve_execution(self, lane: str) -> AgentCapacityReservation: ...

    def request_audit(self, *, run_id: str, packet: EquityEventBriefInputPacket) -> dict[str, Any]: ...

    async def brief_event(
        self,
        *,
        run_id: str,
        packet: EquityEventBriefInputPacket,
        reservation: AgentCapacityReservation | None = None,
    ) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


__all__ = ["EquityDocumentFetchResult", "EquityEventBriefProvider", "EquityEventDocumentProvider"]
