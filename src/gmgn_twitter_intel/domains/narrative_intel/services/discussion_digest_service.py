from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from gmgn_twitter_intel.domains.narrative_intel._constants import (
    DISCUSSION_DIGEST_PROMPT_VERSION,
    NARRATIVE_SCHEMA_VERSION,
)
from gmgn_twitter_intel.domains.narrative_intel.types.discussion_digest import (
    DiscussionDigestRequest,
    TokenDiscussionDigest,
)


class DigestRefreshDecision(BaseModel):
    should_refresh: bool
    reason: str
    status_if_not_refresh: Literal["pending", "insufficient", "ready", "stale"]


class DiscussionDigestService:
    def __init__(
        self,
        *,
        min_source_mentions: int = 3,
        min_independent_authors: int = 2,
        min_semantic_coverage: float = 0.35,
        max_mentions_per_digest: int = 120,
    ) -> None:
        self.min_source_mentions = max(1, int(min_source_mentions))
        self.min_independent_authors = max(1, int(min_independent_authors))
        self.min_semantic_coverage = max(0.0, min(1.0, float(min_semantic_coverage)))
        self.max_mentions_per_digest = max(1, int(max_mentions_per_digest))

    def refresh_decision(self, context: dict[str, Any]) -> DigestRefreshDecision:
        source_count = int(context.get("source_event_count") or len(context.get("mentions") or []))
        authors = int(context.get("independent_author_count") or _author_count(context.get("mentions") or []))
        labeled = int(context.get("labeled_event_count") or len(context.get("semantic_rows") or []))
        coverage = 0.0 if source_count == 0 else labeled / source_count
        if source_count < self.min_source_mentions:
            return DigestRefreshDecision(
                should_refresh=False,
                reason="low_source_volume",
                status_if_not_refresh="insufficient",
            )
        if authors < self.min_independent_authors:
            return DigestRefreshDecision(
                should_refresh=False,
                reason="low_independent_author_count",
                status_if_not_refresh="insufficient",
            )
        if coverage < self.min_semantic_coverage:
            return DigestRefreshDecision(
                should_refresh=False,
                reason="low_semantic_coverage",
                status_if_not_refresh="insufficient",
            )
        return DigestRefreshDecision(should_refresh=True, reason="thresholds_met", status_if_not_refresh="pending")

    def build_insufficient_digest(
        self,
        *,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        context: dict[str, Any],
        reason: str,
        now_ms: int,
        schema_version: str = NARRATIVE_SCHEMA_VERSION,
        model_version: str = "deterministic:insufficient",
    ) -> TokenDiscussionDigest:
        source_count = int(context.get("source_event_count") or len(context.get("mentions") or []))
        labeled_count = int(context.get("labeled_event_count") or len(context.get("semantic_rows") or []))
        return TokenDiscussionDigest(
            target_type=target_type,
            target_id=target_id,
            window=window,
            scope=scope,
            schema_version=schema_version,
            model_version=model_version,
            status="insufficient",
            data_gaps=[{"reason": reason}],
            semantic_coverage=0.0 if source_count == 0 else labeled_count / source_count,
            source_event_count=source_count,
            labeled_event_count=labeled_count,
            independent_author_count=int(
                context.get("independent_author_count") or _author_count(context.get("mentions") or [])
            ),
            computed_at_ms=now_ms,
        )

    def build_digest_request(
        self,
        *,
        run_id: str,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        context: dict[str, Any],
        schema_version: str = NARRATIVE_SCHEMA_VERSION,
        prompt_version: str = DISCUSSION_DIGEST_PROMPT_VERSION,
    ) -> DiscussionDigestRequest:
        mentions = list(context.get("mentions") or [])[: self.max_mentions_per_digest]
        allowed_refs = list(context.get("allowed_refs") or [])
        return DiscussionDigestRequest(
            run_id=run_id,
            schema_version=schema_version,
            prompt_version=prompt_version,
            target_type=target_type,
            target_id=target_id,
            window=window,
            scope=scope,
            mentions=mentions,
            context={key: value for key, value in context.items() if key != "mentions"},
            allowed_refs=allowed_refs,
        )


def _author_count(mentions: list[dict[str, Any]]) -> int:
    return len({str(row.get("author_handle") or "") for row in mentions if str(row.get("author_handle") or "")})
