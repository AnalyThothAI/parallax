from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.news_intel.services.news_item_brief_input import (
    BODY_EXCERPT_MAX_CHARS,
    MAX_ENTITY_LANES,
    MAX_FACT_LANES,
    _bounded,
    _entity_lanes,
    _fact_lane,
    _fact_sort_key,
    _market_scope,
    _optional_bounded,
    _required_bounded_json_object,
    _stable_unique,
    _str,
)
from parallax.domains.news_intel.types.news_item_brief import (
    NewsItemBriefConstraints,
    NewsItemBriefNewsItem,
    NewsItemBriefSource,
)
from parallax.domains.news_intel.types.news_story_brief import (
    NewsStoryBriefAgentConfig,
    NewsStoryBriefInputPacket,
    NewsStoryBriefMember,
    story_brief_key_for,
)
from parallax.platform.agent_hashing import json_sha256


def build_news_story_brief_input_packet(
    *,
    story: Mapping[str, Any],
    representative_item: Mapping[str, Any],
    member_items: Sequence[Mapping[str, Any]],
    entities: Sequence[Mapping[str, Any]],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
    agent_config: NewsStoryBriefAgentConfig,
) -> NewsStoryBriefInputPacket:
    story_key = _required_text(story, "story_key")
    story_identity_version = _required_text(story, "story_identity_version")
    story_brief_key = story_brief_key_for(
        story_identity_version=story_identity_version,
        story_key=story_key,
    )
    representative = _news_item(representative_item)
    members = _members(_required_member_rows(member_items))
    if not members:
        raise ValueError("news_story_brief_member_items_required")
    if representative.news_item_id not in {member.news_item_id for member in members}:
        raise ValueError("news_story_brief_representative_member_required")
    member_ids = [member.news_item_id for member in members]
    entity_lanes = _entity_lanes(entities=entities, token_mentions=token_mentions)
    fact_lanes = [_fact_lane(row) for row in sorted(fact_candidates, key=_fact_sort_key)[:MAX_FACT_LANES]]
    agent_admission = _required_context_object(story, "agent_admission_json", alias_key="agent_admission")
    similarity = _optional_context_object(story, "similarity_json", alias_key="similarity")
    material_delta = _optional_context_object(story, "material_delta_json", alias_key="material_delta")
    event_type = _optional_bounded(story.get("event_type"), 80)
    story_market_scope = _required_market_scope(story)
    market_scope = _market_scope(
        item={**representative_item, "market_scope_json": story_market_scope},
        entity_lanes=entity_lanes,
    )
    if not market_scope:
        raise ValueError("news_story_brief_market_scope_json_required")
    evidence_refs = _evidence_refs(
        representative=representative,
        members=members,
        fact_lanes=fact_lanes,
        entity_lanes=entity_lanes,
    )
    packet_id = _packet_id(
        story_brief_key=story_brief_key,
        member_news_item_ids=member_ids,
        representative_news_item_id=representative.news_item_id,
        fact_ids=[row.fact_candidate_id for row in fact_lanes],
        entity_ids=[row.entity_id for row in entity_lanes],
        agent_config=agent_config,
    )
    packet = NewsStoryBriefInputPacket(
        packet_id=packet_id,
        story_brief_key=story_brief_key,
        story_key=story_key,
        story_identity_version=story_identity_version,
        story_identity=_required_context_object(story, "story_identity_json", alias_key="story_identity"),
        representative_news_item_id=representative.news_item_id,
        member_news_item_ids=member_ids,
        representative_item=representative,
        member_items=members,
        event_type=event_type,
        entity_lanes=entity_lanes[:MAX_ENTITY_LANES],
        fact_lanes=fact_lanes,
        market_scope=market_scope,
        agent_admission=agent_admission,
        similarity=similarity,
        material_delta=material_delta,
        evidence_refs=evidence_refs,
        constraints=NewsItemBriefConstraints(),
        prompt_version=agent_config.prompt_version,
        schema_version=agent_config.schema_version,
    )
    return packet.model_copy(update={"input_hash": news_story_brief_material_input_hash(packet)})


def news_story_brief_material_input_payload(packet: NewsStoryBriefInputPacket) -> dict[str, Any]:
    return packet.model_dump(mode="json", exclude={"input_hash"})


def news_story_brief_material_input_hash(packet: NewsStoryBriefInputPacket) -> str:
    return json_sha256(news_story_brief_material_input_payload(packet))


def _news_item(item: Mapping[str, Any]) -> NewsItemBriefNewsItem:
    return NewsItemBriefNewsItem(
        news_item_id=_str(item.get("news_item_id")),
        title=_bounded(item.get("title"), 500),
        summary=_bounded(item.get("summary"), 2000),
        body_excerpt=_bounded(item.get("body_text"), BODY_EXCERPT_MAX_CHARS),
        canonical_url=_bounded(item.get("canonical_url"), 2000),
        published_at_ms=_required_positive_int(
            item,
            "published_at_ms",
            error_code="news_story_brief_representative_published_at_ms_required",
        ),
        content_hash=_bounded(item.get("content_hash"), 160),
        source=NewsItemBriefSource(
            source_domain=_bounded(item.get("source_domain"), 255),
            source_name=_bounded(item.get("source_name"), 255),
            source_role=_bounded(item.get("source_role"), 64),
            trust_tier=_bounded(item.get("trust_tier"), 64),
        ),
    )


def _members(rows: Sequence[Mapping[str, Any]]) -> list[NewsStoryBriefMember]:
    by_id: dict[str, NewsStoryBriefMember] = {}
    for row in rows:
        news_item_id = _str(row.get("news_item_id"))
        if not news_item_id:
            raise ValueError("news_story_brief_member_news_item_id_required")
        if news_item_id in by_id:
            continue
        by_id[news_item_id] = NewsStoryBriefMember(
            news_item_id=news_item_id,
            title=_bounded(row.get("title"), 500),
            summary=_bounded(row.get("summary"), 800),
            source_domain=_bounded(row.get("source_domain"), 255),
            source_role=_bounded(row.get("source_role"), 64),
            trust_tier=_bounded(row.get("trust_tier"), 64),
            published_at_ms=_required_positive_int(
                row,
                "published_at_ms",
                error_code="news_story_brief_member_published_at_ms_required",
            ),
            content_hash=_bounded(row.get("content_hash"), 160),
        )
    return sorted(by_id.values(), key=lambda row: (row.published_at_ms, row.news_item_id))[:80]


def _required_positive_int(row: Mapping[str, Any], field_name: str, *, error_code: str) -> int:
    value = row.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(error_code)
    return value


def _optional_context_object(item: Mapping[str, Any], json_key: str, *, alias_key: str) -> dict[str, object]:
    if alias_key in item and item[alias_key] is not None:
        raise ValueError(f"news_story_brief_{json_key}_required")
    if json_key not in item or item[json_key] is None:
        return {}
    return _required_bounded_json_object(
        item[json_key],
        error_code=f"news_story_brief_{json_key}_required",
    )


def _required_context_object(item: Mapping[str, Any], json_key: str, *, alias_key: str) -> dict[str, object]:
    if alias_key in item and item[alias_key] is not None:
        raise ValueError(f"news_story_brief_{json_key}_required")
    if json_key not in item or item[json_key] is None:
        raise ValueError(f"news_story_brief_{json_key}_required")
    value = item[json_key]
    payload = _required_bounded_json_object(
        value,
        error_code=f"news_story_brief_{json_key}_required",
    )
    if not payload:
        raise ValueError(f"news_story_brief_{json_key}_required")
    return payload


def _required_market_scope(story: Mapping[str, Any]) -> object:
    if "market_scope_json" in story and story["market_scope_json"] is not None:
        value = story["market_scope_json"]
    else:
        raise ValueError("news_story_brief_market_scope_json_required")
    if not isinstance(value, Mapping):
        raise ValueError("news_story_brief_market_scope_json_required")
    scope = value.get("scope")
    primary = value.get("primary")
    if scope:
        return scope
    if primary:
        return [primary]
    raise ValueError("news_story_brief_market_scope_json_required")


def _required_member_rows(rows: Sequence[Mapping[str, Any]]) -> Sequence[Mapping[str, Any]]:
    if not rows:
        raise ValueError("news_story_brief_member_items_required")
    return rows


def _evidence_refs(
    *,
    representative: NewsItemBriefNewsItem,
    members: Sequence[NewsStoryBriefMember],
    fact_lanes: Sequence[Any],
    entity_lanes: Sequence[Any],
) -> list[str]:
    refs: list[str] = []
    if representative.title:
        refs.append("item:title")
    if representative.summary:
        refs.append("item:summary")
    if representative.body_excerpt:
        refs.append("item:body_excerpt")
    refs.extend(f"story:member:{member.news_item_id}" for member in members if member.news_item_id)
    refs.extend(f"fact:{row.fact_candidate_id}" for row in fact_lanes if row.fact_candidate_id)
    refs.extend(f"entity:{row.entity_id}" for row in entity_lanes if row.entity_id)
    return _stable_unique(refs)


def _packet_id(
    *,
    story_brief_key: str,
    member_news_item_ids: Sequence[str],
    representative_news_item_id: str,
    fact_ids: Sequence[str],
    entity_ids: Sequence[str],
    agent_config: NewsStoryBriefAgentConfig,
) -> str:
    digest = json_sha256(
        {
            "story_brief_key": story_brief_key,
            "member_news_item_ids": list(member_news_item_ids),
            "representative_news_item_id": representative_news_item_id,
            "fact_ids": list(fact_ids),
            "entity_ids": list(entity_ids),
            "prompt_version": agent_config.prompt_version,
            "schema_version": agent_config.schema_version,
        }
    )
    return f"news-story-brief:{digest.removeprefix('sha256:')[:24]}"


def _required_text(row: Mapping[str, Any], field_name: str) -> str:
    value = _str(row.get(field_name))
    if not value:
        raise ValueError(f"news_story_brief_{field_name}_required")
    return value


__all__ = [
    "build_news_story_brief_input_packet",
    "news_story_brief_material_input_hash",
    "news_story_brief_material_input_payload",
]
