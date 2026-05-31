from __future__ import annotations

from typing import Any, Protocol

from parallax.domains.narrative_intel.types.discussion_digest import (
    DiscussionDigestRequest,
    DiscussionDigestResult,
)
from parallax.domains.narrative_intel.types.mention_semantics import (
    MentionSemanticsBatchRequest,
    MentionSemanticsBatchResult,
)
from parallax.platform.agent_execution import AgentCapacityReservation


class NarrativeIntelProvider(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def artifact_version_hash(self) -> str: ...

    def try_reserve_execution(self, lane: str, *, rate_units: int = 1) -> AgentCapacityReservation: ...

    async def label_mentions(
        self,
        *,
        run_id: str,
        request: MentionSemanticsBatchRequest,
        reservation: AgentCapacityReservation | None = None,
    ) -> MentionSemanticsBatchResult: ...

    def request_audit_for_label_mentions(self, **kwargs: Any) -> dict[str, Any]: ...

    async def summarize_discussion(
        self,
        *,
        run_id: str,
        request: DiscussionDigestRequest,
        reservation: AgentCapacityReservation | None = None,
    ) -> DiscussionDigestResult: ...

    def request_audit_for_summarize_discussion(self, **kwargs: Any) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...
