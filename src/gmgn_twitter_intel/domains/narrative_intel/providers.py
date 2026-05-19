from __future__ import annotations

from typing import Any, Protocol

from gmgn_twitter_intel.domains.narrative_intel.types.discussion_digest import (
    DiscussionDigestRequest,
    DiscussionDigestResult,
)
from gmgn_twitter_intel.domains.narrative_intel.types.mention_semantics import (
    MentionSemanticsBatchRequest,
    MentionSemanticsBatchResult,
)


class NarrativeIntelProvider(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def artifact_version_hash(self) -> str: ...

    async def label_mentions(
        self,
        *,
        run_id: str,
        request: MentionSemanticsBatchRequest,
    ) -> MentionSemanticsBatchResult: ...

    def request_audit_for_label_mentions(self, **kwargs: Any) -> dict[str, Any]: ...

    async def summarize_discussion(
        self,
        *,
        run_id: str,
        request: DiscussionDigestRequest,
    ) -> DiscussionDigestResult: ...

    def request_audit_for_summarize_discussion(self, **kwargs: Any) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...
