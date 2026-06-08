from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from parallax.domains.narrative_intel._constants import (
    DISCUSSION_DIGEST_PROMPT_VERSION,
    NARRATIVE_SCHEMA_VERSION,
)
from parallax.domains.narrative_intel.types.discussion_digest import (
    DiscussionDigestRequest,
    TokenDiscussionDigest,
)

MAX_MENTION_TEXT_CHARS = 360
MAX_MENTION_REFS = 8
MAX_CO_MENTIONS = 12
DEFAULT_MAX_MENTIONS_PER_DIGEST = 24
PENDING_SEMANTIC_STATUSES = {"queued", "retryable_error", "stale"}


class DigestRefreshDecision(BaseModel):
    should_refresh: bool
    reason: str
    status_if_not_refresh: Literal["pending", "insufficient", "semantic_unavailable", "stale"]


class DiscussionDigestService:
    def __init__(
        self,
        *,
        min_source_mentions: int = 3,
        min_independent_authors: int = 2,
        min_semantic_coverage: float = 0.35,
        max_pending_semantic_rows_for_digest: int = 5,
        max_mentions_per_digest: int = DEFAULT_MAX_MENTIONS_PER_DIGEST,
    ) -> None:
        self.min_source_mentions = max(1, int(min_source_mentions))
        self.min_independent_authors = max(1, int(min_independent_authors))
        self.min_semantic_coverage = max(0.0, min(1.0, float(min_semantic_coverage)))
        self.max_pending_semantic_rows_for_digest = max(0, int(max_pending_semantic_rows_for_digest))
        self.max_mentions_per_digest = max(1, int(max_mentions_per_digest))

    def refresh_decision(self, context: dict[str, Any]) -> DigestRefreshDecision:
        source_count = int(context.get("source_event_count") or 0)
        authors = int(context.get("independent_author_count") or _author_count(context.get("mentions") or []))
        semantic_row_count = int(context.get("semantic_row_count") or 0)
        missing_semantic_count = int(context.get("missing_semantic_count") or 0)
        pending_semantic_count = int(context.get("pending_semantic_count") or 0)
        retryable_semantic_count = int(context.get("retryable_semantic_count") or 0)
        terminal_unavailable_count = int(context.get("terminal_unavailable_count") or 0)
        labeled = int(context.get("labeled_event_count") or 0)
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
        pending_tail = missing_semantic_count + pending_semantic_count + retryable_semantic_count
        if pending_tail > self.max_pending_semantic_rows_for_digest:
            return DigestRefreshDecision(
                should_refresh=False,
                reason="semantic_labeling_pending",
                status_if_not_refresh="pending",
            )
        if coverage < self.min_semantic_coverage:
            if (
                source_count > 0
                and semantic_row_count == source_count
                and terminal_unavailable_count > 0
                and labeled + terminal_unavailable_count == semantic_row_count
            ):
                return DigestRefreshDecision(
                    should_refresh=False,
                    reason="semantic_provider_unavailable",
                    status_if_not_refresh="semantic_unavailable",
                )
            return DigestRefreshDecision(
                should_refresh=False,
                reason="low_semantic_coverage",
                status_if_not_refresh="insufficient",
            )
        reason = "thresholds_met_partial_semantic_tail" if pending_tail > 0 else "thresholds_met"
        return DigestRefreshDecision(should_refresh=True, reason=reason, status_if_not_refresh="pending")

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
        return self.build_status_digest(
            target_type=target_type,
            target_id=target_id,
            window=window,
            scope=scope,
            context=context,
            reason=reason,
            now_ms=now_ms,
            status="insufficient",
            schema_version=schema_version,
            model_version=model_version,
        )

    def build_status_digest(
        self,
        *,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        context: dict[str, Any],
        reason: str,
        now_ms: int,
        status: Literal["pending", "insufficient", "semantic_unavailable", "stale"] = "pending",
        schema_version: str = NARRATIVE_SCHEMA_VERSION,
        model_version: str = "deterministic:not_ready",
    ) -> TokenDiscussionDigest:
        source_count = int(context.get("source_event_count") or len(context.get("mentions") or []))
        semantic_rows = list(context.get("semantic_rows") or context.get("mentions") or [])
        explicit_labeled_count = _int_or_none(context.get("labeled_event_count"))
        labeled_count = (
            explicit_labeled_count
            if explicit_labeled_count is not None
            else sum(1 for row in semantic_rows if str(row.get("status") or "") == "labeled")
        )
        return TokenDiscussionDigest(
            target_type=target_type,
            target_id=target_id,
            window=window,
            scope=scope,
            schema_version=schema_version,
            model_version=model_version,
            status=status,
            epoch_id=context.get("epoch_id"),
            epoch_policy_version=context.get("epoch_policy_version"),
            source_event_ids=_json_list(context.get("source_event_ids") or context.get("source_event_ids_json")),
            source_window_start_ms=_int_or_none(context.get("source_window_start_ms")),
            source_window_end_ms=_int_or_none(context.get("source_window_end_ms")),
            epoch_closed_at_ms=_int_or_none(context.get("epoch_closed_at_ms")),
            display_current_until_ms=_int_or_none(context.get("display_current_until_ms")),
            refresh_reason=context.get("refresh_reason") or reason,
            data_gaps=[{"reason": reason}],
            semantic_coverage=0.0 if source_count == 0 else labeled_count / source_count,
            source_event_count=source_count,
            source_fingerprint=context.get("source_fingerprint"),
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
        labeled_rows = [row for row in list(context.get("mentions") or []) if str(row.get("status") or "") == "labeled"]
        mentions = [_compact_mention(row) for row in labeled_rows[: self.max_mentions_per_digest]]
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

    def publish_ready_digest(
        self,
        digest: TokenDiscussionDigest | dict[str, Any],
        *,
        context: dict[str, Any],
        now_ms: int,
    ) -> TokenDiscussionDigest:
        source_count = int(context.get("source_event_count") or len(context.get("mentions") or []))
        explicit_labeled_count = _int_or_none(context.get("labeled_event_count"))
        labeled_count = (
            explicit_labeled_count
            if explicit_labeled_count is not None
            else sum(1 for row in list(context.get("semantic_rows") or []) if str(row.get("status") or "") == "labeled")
        )
        payload = digest.model_dump(mode="json") if isinstance(digest, TokenDiscussionDigest) else dict(digest or {})
        payload.update(
            {
                "status": "ready",
                "epoch_id": context.get("epoch_id") or payload.get("epoch_id"),
                "epoch_policy_version": context.get("epoch_policy_version") or payload.get("epoch_policy_version"),
                "source_event_ids": _json_list(
                    context.get("source_event_ids")
                    or context.get("source_event_ids_json")
                    or payload.get("source_event_ids")
                ),
                "source_window_start_ms": _int_or_none(
                    context.get("source_window_start_ms") or payload.get("source_window_start_ms")
                ),
                "source_window_end_ms": _int_or_none(
                    context.get("source_window_end_ms") or payload.get("source_window_end_ms")
                ),
                "epoch_closed_at_ms": _int_or_none(
                    context.get("epoch_closed_at_ms") or payload.get("epoch_closed_at_ms")
                ),
                "display_current_until_ms": _int_or_none(
                    context.get("display_current_until_ms") or payload.get("display_current_until_ms")
                ),
                "refresh_reason": context.get("refresh_reason") or payload.get("refresh_reason"),
                "semantic_coverage": 0.0 if source_count == 0 else labeled_count / source_count,
                "source_event_count": source_count,
                "source_fingerprint": context.get("source_fingerprint"),
                "labeled_event_count": labeled_count,
                "independent_author_count": int(
                    context.get("independent_author_count") or _author_count(context.get("mentions") or [])
                ),
                "computed_at_ms": int(now_ms),
            }
        )
        _normalize_ready_evidence_refs(payload)
        return TokenDiscussionDigest.model_validate(payload)


def _author_count(mentions: list[dict[str, Any]]) -> int:
    return len({str(row.get("author_handle") or "") for row in mentions if str(row.get("author_handle") or "")})


def _compact_context(context: dict[str, Any], *, mention_count_sent: int, mention_limit: int) -> dict[str, Any]:
    source_count = int(context.get("source_event_count") or 0)
    labeled_count = int(context.get("labeled_event_count") or 0)
    return {
        "source_event_count": source_count,
        "semantic_row_count": int(context.get("semantic_row_count") or 0),
        "missing_semantic_count": int(context.get("missing_semantic_count") or 0),
        "pending_semantic_count": int(context.get("pending_semantic_count") or 0),
        "retryable_semantic_count": int(context.get("retryable_semantic_count") or 0),
        "terminal_unavailable_count": int(context.get("terminal_unavailable_count") or 0),
        "labeled_event_count": labeled_count,
        "independent_author_count": int(context.get("independent_author_count") or 0),
        "semantic_coverage": 0.0 if source_count == 0 else labeled_count / source_count,
        "mention_count_sent": int(mention_count_sent),
        "mention_limit": int(mention_limit),
        "prompt_mention_count": int(mention_count_sent),
        "prompt_mention_limit": int(mention_limit),
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


def _normalize_ready_evidence_refs(payload: dict[str, Any]) -> None:
    refs: list[Any] = list(payload.get("evidence_refs") or [])
    for cluster in list(payload.get("dominant_narratives") or []):
        cluster_payload = _payload_dict(cluster)
        refs.extend(list(cluster_payload.get("evidence_refs") or []))
    for key in ("bull_view", "bear_view", "reflexivity_read"):
        view_payload = _payload_dict(payload.get(key))
        refs.extend(list(view_payload.get("evidence_refs") or []))
    deduped = _dedupe_ref_payloads(refs)
    if deduped:
        payload["evidence_refs"] = deduped[:6]


def _payload_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return {}


def _dedupe_ref_payloads(refs: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        ref_id = _clean_str(ref.get("ref_id"))
        if not ref_id or ref_id in seen:
            continue
        seen.add(ref_id)
        result.append({key: value for key, value in ref.items() if value not in (None, "")})
    return result


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
