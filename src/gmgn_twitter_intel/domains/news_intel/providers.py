from __future__ import annotations

from typing import Any, Protocol

from gmgn_twitter_intel.domains.news_intel.types.news_item_brief import NewsItemBriefInputPacket
from gmgn_twitter_intel.platform.agent_execution import AgentCapacityReservation


class NewsFeedFetchResult(Protocol):
    status_code: int
    entries: list[dict[str, Any]]
    etag: str | None
    last_modified: str | None
    not_modified: bool


class NewsFeedProvider(Protocol):
    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> NewsFeedFetchResult: ...

    def close(self) -> None: ...


class NewsItemBriefProvider(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def artifact_version_hash(self) -> str: ...

    def try_reserve_execution(self, lane: str) -> AgentCapacityReservation: ...

    def request_audit(self, *, run_id: str, packet: NewsItemBriefInputPacket) -> dict[str, Any]: ...

    async def brief_item(
        self,
        *,
        run_id: str,
        packet: NewsItemBriefInputPacket,
        reservation: AgentCapacityReservation | None = None,
    ) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


__all__ = ["NewsFeedFetchResult", "NewsFeedProvider", "NewsItemBriefProvider"]
