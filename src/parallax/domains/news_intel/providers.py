from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from parallax.domains.news_intel.types.news_story_brief import NewsStoryBriefInputPacket
from parallax.domains.news_intel.types.source_provider import (
    NewsProviderFetchResult,
    NewsSourceHttpCache,
    NewsSourceSnapshot,
)
from parallax.platform.agent_execution import AgentCapacityReservation


class NewsSourceProviderError(RuntimeError):
    def __init__(self, error_code: str, *, status_code: int | None = None, terminal: bool = False) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.status_code = status_code
        self.terminal = terminal


class NewsSourceProvider(Protocol):
    @property
    def provider_type(self) -> str: ...

    def fetch(
        self,
        source: NewsSourceSnapshot,
        *,
        since_ms: int | None = None,
        cursor: Mapping[str, Any] | None = None,
        cache: NewsSourceHttpCache | None = None,
        limit: int | None = None,
    ) -> NewsProviderFetchResult: ...

    def close(self) -> None: ...


class NewsStoryBriefProvider(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def artifact_version_hash(self) -> str: ...

    def try_reserve_execution(self, lane: str, *, rate_units: int = 1) -> AgentCapacityReservation: ...

    def request_audit(self, *, run_id: str, packet: NewsStoryBriefInputPacket) -> dict[str, Any]: ...

    async def brief_story(
        self,
        *,
        run_id: str,
        packet: NewsStoryBriefInputPacket,
        reservation: AgentCapacityReservation | None = None,
    ) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


__all__ = ["NewsSourceProvider", "NewsSourceProviderError", "NewsStoryBriefProvider"]
