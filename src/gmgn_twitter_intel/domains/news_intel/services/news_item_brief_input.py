from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from gmgn_twitter_intel.domains.news_intel.types.news_item_brief import (
    NewsItemBriefAgentConfig,
    NewsItemBriefConstraints,
    NewsItemBriefFactLane,
    NewsItemBriefInputPacket,
    NewsItemBriefNewsItem,
    NewsItemBriefSource,
    NewsItemBriefStoryContext,
    NewsItemBriefStoryMember,
    NewsItemBriefTokenLane,
)
from gmgn_twitter_intel.platform.agent_hashing import json_sha256

BODY_EXCERPT_MAX_CHARS = 2000
MAX_TOKEN_LANES = 50
MAX_FACT_LANES = 50
MAX_STORY_MEMBERS = 8


def build_news_item_brief_input_packet(
    *,
    item: Mapping[str, Any],
    story: Mapping[str, Any] | None,
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
    story_members: Sequence[Mapping[str, Any]],
    agent_config: NewsItemBriefAgentConfig,
) -> NewsItemBriefInputPacket:
    news_item = NewsItemBriefNewsItem(
        news_item_id=_str(item.get("news_item_id")),
        title=_bounded(item.get("title"), 500),
        summary=_bounded(item.get("summary"), 2000),
        body_excerpt=_bounded(item.get("body_text") or item.get("body_excerpt"), BODY_EXCERPT_MAX_CHARS),
        canonical_url=_bounded(item.get("canonical_url"), 2000),
        published_at_ms=_int(item.get("published_at_ms")),
        fetched_at_ms=_optional_int(item.get("fetched_at_ms")),
        content_hash=_bounded(item.get("content_hash"), 160),
        source=NewsItemBriefSource(
            source_domain=_bounded(item.get("source_domain"), 255),
            source_name=_bounded(item.get("source_name"), 255),
            source_role=_bounded(item.get("source_role"), 64),
            trust_tier=_bounded(item.get("trust_tier"), 64),
        ),
    )
    token_lanes = [_token_lane(row) for row in sorted(token_mentions, key=_mention_sort_key)[:MAX_TOKEN_LANES]]
    fact_lanes = [_fact_lane(row) for row in sorted(fact_candidates, key=_fact_sort_key)[:MAX_FACT_LANES]]
    story_context = _story_context(
        story=story,
        story_members=story_members,
        current_news_item_id=news_item.news_item_id,
    )
    evidence_refs = _evidence_refs(
        news_item=news_item,
        token_lanes=token_lanes,
        fact_lanes=fact_lanes,
        story_context=story_context,
    )
    packet_id = _packet_id(
        news_item=news_item,
        story_context=story_context,
        token_lanes=token_lanes,
        fact_lanes=fact_lanes,
        agent_config=agent_config,
    )
    packet = NewsItemBriefInputPacket(
        packet_id=packet_id,
        news_item=news_item,
        story_context=story_context,
        token_lanes=token_lanes,
        fact_lanes=fact_lanes,
        evidence_refs=evidence_refs,
        constraints=NewsItemBriefConstraints(),
        prompt_version=agent_config.prompt_version,
        schema_version=agent_config.schema_version,
    )
    return packet.model_copy(update={"input_hash": json_sha256(packet.model_dump(mode="json", exclude={"input_hash"}))})


def _token_lane(row: Mapping[str, Any]) -> NewsItemBriefTokenLane:
    return NewsItemBriefTokenLane(
        mention_id=_str(row.get("mention_id")),
        observed_symbol=_bounded(row.get("observed_symbol"), 64),
        resolution_status=_bounded(row.get("resolution_status"), 64),
        target_type=_optional_bounded(row.get("target_type"), 80),
        target_id=_optional_bounded(row.get("target_id"), 160),
        display_symbol=_bounded(row.get("display_symbol") or row.get("observed_symbol"), 64),
        display_name=_optional_bounded(row.get("display_name"), 160),
        reason_codes=[_bounded(value, 80) for value in _json_list(row.get("reason_codes_json"))[:12]],
        candidate_targets=[_json_object(value) for value in _json_list(row.get("candidate_targets_json"))[:12]],
        evidence_strength=_optional_bounded(row.get("evidence_strength"), 64),
        confidence=_optional_float(row.get("confidence")),
    )


def _fact_lane(row: Mapping[str, Any]) -> NewsItemBriefFactLane:
    return NewsItemBriefFactLane(
        fact_candidate_id=_str(row.get("fact_candidate_id")),
        event_type=_bounded(row.get("event_type"), 80),
        claim=_bounded(row.get("claim"), 800),
        realis=_bounded(row.get("realis"), 64),
        validation_status=_bounded(row.get("validation_status"), 64),
        affected_targets=[_json_object(value) for value in _json_list(row.get("affected_targets_json"))[:20]],
        rejection_reasons=[_bounded(value, 120) for value in _json_list(row.get("rejection_reasons_json"))[:12]],
        evidence_quote=_bounded(row.get("evidence_quote"), 500),
    )


def _story_context(
    *,
    story: Mapping[str, Any] | None,
    story_members: Sequence[Mapping[str, Any]],
    current_news_item_id: str,
) -> NewsItemBriefStoryContext | None:
    if story is None or not _str(story.get("story_id")):
        return None
    members = [
        NewsItemBriefStoryMember(
            news_item_id=_str(row.get("news_item_id")),
            source_domain=_bounded(row.get("source_domain"), 255),
            title=_bounded(row.get("title") or row.get("representative_title"), 500),
            published_at_ms=_int(row.get("published_at_ms") or row.get("created_at_ms")),
        )
        for row in sorted(story_members, key=_story_member_sort_key)
        if _str(row.get("news_item_id")) and _str(row.get("news_item_id")) != current_news_item_id
    ][:MAX_STORY_MEMBERS]
    return NewsItemBriefStoryContext(
        story_id=_str(story.get("story_id")),
        item_count=_int(story.get("item_count")),
        source_count=_int(story.get("source_count")),
        representative_title=_bounded(story.get("representative_title"), 500),
        members=members,
    )


def _evidence_refs(
    *,
    news_item: NewsItemBriefNewsItem,
    token_lanes: list[NewsItemBriefTokenLane],
    fact_lanes: list[NewsItemBriefFactLane],
    story_context: NewsItemBriefStoryContext | None,
) -> list[str]:
    refs: list[str] = []
    if news_item.title:
        refs.append("item:title")
    if news_item.summary:
        refs.append("item:summary")
    if news_item.body_excerpt:
        refs.append("item:body_excerpt")
    refs.extend(f"fact:{row.fact_candidate_id}" for row in fact_lanes if row.fact_candidate_id)
    refs.extend(f"token:{row.mention_id}" for row in token_lanes if row.mention_id)
    if story_context is not None:
        refs.extend(f"story:{row.news_item_id}" for row in story_context.members if row.news_item_id)
    return _stable_unique(refs)


def _packet_id(
    *,
    news_item: NewsItemBriefNewsItem,
    story_context: NewsItemBriefStoryContext | None,
    token_lanes: list[NewsItemBriefTokenLane],
    fact_lanes: list[NewsItemBriefFactLane],
    agent_config: NewsItemBriefAgentConfig,
) -> str:
    digest = json_sha256(
        {
            "news_item_id": news_item.news_item_id,
            "content_hash": news_item.content_hash,
            "story_id": story_context.story_id if story_context is not None else "",
            "story_members": [row.news_item_id for row in story_context.members] if story_context is not None else [],
            "tokens": [row.mention_id for row in token_lanes],
            "facts": [row.fact_candidate_id for row in fact_lanes],
            "prompt_version": agent_config.prompt_version,
            "schema_version": agent_config.schema_version,
        }
    )
    return f"news-item-brief:{news_item.news_item_id}:{digest.removeprefix('sha256:')[:16]}"


def _mention_sort_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return (_str(row.get("mention_id")), _str(row.get("observed_symbol")))


def _fact_sort_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return (_str(row.get("fact_candidate_id")), _str(row.get("claim")))


def _story_member_sort_key(row: Mapping[str, Any]) -> tuple[int, str]:
    return (-_int(row.get("published_at_ms") or row.get("created_at_ms")), _str(row.get("news_item_id")))


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    return []


def _json_object(value: Any) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(key): child for key, child in value.items() if child is not None}
    return {}


def _stable_unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _str(value: Any) -> str:
    return str(value or "").strip()


def _bounded(value: Any, max_length: int) -> str:
    return _str(value)[:max_length]


def _optional_bounded(value: Any, max_length: int) -> str | None:
    cleaned = _bounded(value, max_length)
    return cleaned or None


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _optional_int(value: Any) -> int | None:
    parsed = _int(value)
    return parsed if parsed else None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, parsed))


__all__ = ["BODY_EXCERPT_MAX_CHARS", "build_news_item_brief_input_packet"]
