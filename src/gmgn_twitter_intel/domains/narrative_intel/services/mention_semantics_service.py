from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.narrative_intel._constants import (
    MENTION_SEMANTICS_PROMPT_VERSION,
    NARRATIVE_SCHEMA_VERSION,
)
from gmgn_twitter_intel.domains.narrative_intel.types.mention_semantics import (
    MentionSemanticsBatchRequest,
    MentionSemanticsBatchResult,
)


class MentionSemanticsService:
    def build_batch_request(
        self,
        rows: list[dict[str, Any]],
        *,
        run_id: str,
        schema_version: str = NARRATIVE_SCHEMA_VERSION,
        prompt_version: str = MENTION_SEMANTICS_PROMPT_VERSION,
    ) -> MentionSemanticsBatchRequest:
        mentions = [
            {
                "event_id": str(row.get("event_id") or ""),
                "target_type": str(row.get("target_type") or ""),
                "target_id": str(row.get("target_id") or ""),
                "text": str(row.get("text_clean") or row.get("text") or ""),
                "text_fingerprint": str(row.get("text_fingerprint") or ""),
                "allowed_refs": [{"ref_id": f"event:{row.get('event_id')}", "kind": "event"}],
            }
            for row in rows
        ]
        return MentionSemanticsBatchRequest(
            run_id=run_id,
            schema_version=schema_version,
            prompt_version=prompt_version,
            mentions=mentions,
            raw_request={"mention_count": len(mentions)},
        )

    def validate_batch_result(
        self,
        rows: list[dict[str, Any]],
        result: MentionSemanticsBatchResult,
    ) -> MentionSemanticsBatchResult:
        allowed = {(str(row.get("event_id")), str(row.get("target_type")), str(row.get("target_id"))) for row in rows}
        unknown = [
            label.event_id
            for label in result.labels
            if (label.event_id, label.target_type, label.target_id) not in allowed
        ]
        if unknown:
            raise ValueError(f"provider returned labels for unknown mentions: {', '.join(sorted(unknown))}")
        return result
