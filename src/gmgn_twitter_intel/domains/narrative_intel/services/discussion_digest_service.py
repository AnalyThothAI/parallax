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

MAX_MENTION_TEXT_CHARS = 600
MAX_MENTION_REFS = 8
MAX_CO_MENTIONS = 12


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
        mentions = [
            _compact_mention(row) for row in list(context.get("mentions") or [])[: self.max_mentions_per_digest]
        ]
        allowed_refs = _compact_allowed_refs(list(context.get("allowed_refs") or []), mentions)
        return DiscussionDigestRequest(
            run_id=run_id,
            schema_version=schema_version,
            prompt_version=prompt_version,
            target_type=target_type,
            target_id=target_id,
            window=window,
            scope=scope,
            mentions=mentions,
            context=_compact_context(
                context,
                mention_count_sent=len(mentions),
                mention_limit=self.max_mentions_per_digest,
            ),
            allowed_refs=allowed_refs,
        )


def _author_count(mentions: list[dict[str, Any]]) -> int:
    return len({str(row.get("author_handle") or "") for row in mentions if str(row.get("author_handle") or "")})


def _compact_context(context: dict[str, Any], *, mention_count_sent: int, mention_limit: int) -> dict[str, Any]:
    source_count = int(context.get("source_event_count") or 0)
    labeled_count = int(context.get("labeled_event_count") or 0)
    return {
        "source_event_count": source_count,
        "labeled_event_count": labeled_count,
        "independent_author_count": int(context.get("independent_author_count") or 0),
        "semantic_coverage": 0.0 if source_count == 0 else labeled_count / source_count,
        "mention_count_sent": int(mention_count_sent),
        "mention_limit": int(mention_limit),
    }


def _compact_mention(row: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "event_id": _clean_str(row.get("event_id")),
        "semantic_id": _clean_str(row.get("semantic_id")),
        "target_type": _clean_str(row.get("target_type")),
        "target_id": _clean_str(row.get("target_id")),
        "source_received_at_ms": _int_or_none(row.get("source_received_at_ms")),
        "author_handle": _clean_str(row.get("author_handle")),
        "tweet_id": _clean_str(row.get("tweet_id")),
        "text_clean": _truncate(_clean_str(row.get("text_clean") or row.get("text")), MAX_MENTION_TEXT_CHARS),
        "language": _clean_str(row.get("language")),
        "status": _clean_str(row.get("status")),
        "trade_stance": _clean_str(row.get("trade_stance")),
        "attention_valence": _clean_str(row.get("attention_valence")),
        "narrative_cluster_key": _clean_str(row.get("narrative_cluster_key")),
        "claim_type": _clean_str(row.get("claim_type")),
        "evidence_type": _clean_str(row.get("evidence_type")),
        "semantic_confidence": _float_or_none(row.get("semantic_confidence")),
        "co_mentioned_targets": _json_list(row.get("co_mentioned_targets_json"))[:MAX_CO_MENTIONS],
        "evidence_refs": _json_list(row.get("evidence_refs_json") or row.get("evidence_refs"))[:MAX_MENTION_REFS],
        "error": _clean_str(row.get("error")),
    }
    return {key: value for key, value in compact.items() if value not in (None, "", [])}


def _compact_allowed_refs(refs: list[Any], mentions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed_ids = set()
    for mention in mentions:
        if mention.get("event_id"):
            allowed_ids.add(f"event:{mention['event_id']}")
        if mention.get("semantic_id"):
            allowed_ids.add(f"semantic:{mention['semantic_id']}")
    compact_refs = []
    seen = set()
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        ref_id = _clean_str(ref.get("ref_id"))
        if not ref_id or ref_id not in allowed_ids or ref_id in seen:
            continue
        seen.add(ref_id)
        compact_refs.append(
            {
                key: value
                for key, value in {
                    "ref_id": ref_id,
                    "kind": _clean_str(ref.get("kind")),
                    "source_table": _clean_str(ref.get("source_table")),
                    "event_id": _clean_str(ref.get("event_id")),
                }.items()
                if value not in (None, "")
            }
        )
    return compact_refs


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None or len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _json_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
