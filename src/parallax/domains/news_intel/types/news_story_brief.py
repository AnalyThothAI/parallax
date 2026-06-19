from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from parallax.domains.news_intel._constants import (
    NEWS_STORY_BRIEF_GUARDRAIL_VERSION,
    NEWS_STORY_BRIEF_PROMPT_VERSION,
    NEWS_STORY_BRIEF_SCHEMA_VERSION,
    NEWS_STORY_BRIEF_VALIDATOR_VERSION,
)
from parallax.domains.news_intel.types.news_item_brief import (
    NewsItemBriefConstraints,
    NewsItemBriefEntityLane,
    NewsItemBriefFactLane,
    NewsItemBriefNewsItem,
    NewsMarketDomain,
)
from parallax.platform.agent_hashing import text_sha256

NEWS_STORY_BRIEF_WORKFLOW_NAME = "parallax.news_story_brief"
NEWS_STORY_BRIEF_AGENT_NAME = "NewsStoryBriefAgent"
NEWS_STORY_BRIEF_LANE = "news.story_brief"


class NewsStoryBriefMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    news_item_id: str = Field(min_length=1, max_length=160)
    title: str = Field(default="", max_length=500)
    summary: str = Field(default="", max_length=800)
    source_domain: str = Field(default="", max_length=255)
    source_role: str = Field(default="", max_length=64)
    trust_tier: str = Field(default="", max_length=64)
    published_at_ms: int = Field(default=0, ge=0)
    content_hash: str = Field(default="", max_length=160)


class NewsStoryBriefInputPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packet_id: str = Field(min_length=1, max_length=160)
    story_brief_key: str = Field(min_length=1, max_length=160)
    story_key: str = Field(min_length=1, max_length=300)
    story_identity_version: str = Field(min_length=1, max_length=128)
    story_identity: dict[str, object] = Field(default_factory=dict, max_length=32)
    representative_news_item_id: str = Field(min_length=1, max_length=160)
    member_news_item_ids: list[Annotated[str, Field(min_length=1, max_length=160)]] = Field(
        default_factory=list,
        max_length=80,
    )
    representative_item: NewsItemBriefNewsItem
    member_items: list[NewsStoryBriefMember] = Field(default_factory=list, max_length=80)
    event_type: str | None = Field(default=None, max_length=80)
    entity_lanes: list[NewsItemBriefEntityLane] = Field(default_factory=list, max_length=50)
    fact_lanes: list[NewsItemBriefFactLane] = Field(default_factory=list, max_length=50)
    market_scope: list[NewsMarketDomain] = Field(default_factory=list, max_length=12)
    agent_admission: dict[str, object] = Field(default_factory=dict, max_length=32)
    similarity: dict[str, object] = Field(default_factory=dict, max_length=32)
    material_delta: dict[str, object] = Field(default_factory=dict, max_length=32)
    evidence_refs: list[Annotated[str, Field(min_length=1, max_length=160)]] = Field(
        default_factory=list,
        max_length=160,
    )
    constraints: NewsItemBriefConstraints = Field(default_factory=NewsItemBriefConstraints)
    prompt_version: str = Field(min_length=1, max_length=128)
    schema_version: str = Field(min_length=1, max_length=128)
    input_hash: str = Field(default="", max_length=128)


class NewsStoryBriefAgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_name: str = NEWS_STORY_BRIEF_WORKFLOW_NAME
    agent_name: str = NEWS_STORY_BRIEF_AGENT_NAME
    lane: str = NEWS_STORY_BRIEF_LANE
    provider: str = Field(default="litellm", max_length=64)
    model: str = Field(min_length=1, max_length=120)
    artifact_version_hash: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(min_length=1, max_length=128)
    schema_version: str = Field(min_length=1, max_length=128)
    validator_version: str = Field(min_length=1, max_length=128)
    guardrail_version: str = Field(min_length=1, max_length=128)


def story_brief_key_for(*, story_identity_version: str, story_key: str) -> str:
    return text_sha256(f"news-story-brief|{story_identity_version}|{story_key}")


def default_news_story_brief_agent_config(*, model: str, artifact_version_hash: str) -> NewsStoryBriefAgentConfig:
    return NewsStoryBriefAgentConfig(
        model=model,
        artifact_version_hash=artifact_version_hash,
        prompt_version=NEWS_STORY_BRIEF_PROMPT_VERSION,
        schema_version=NEWS_STORY_BRIEF_SCHEMA_VERSION,
        validator_version=NEWS_STORY_BRIEF_VALIDATOR_VERSION,
        guardrail_version=NEWS_STORY_BRIEF_GUARDRAIL_VERSION,
    )


__all__ = [
    "NEWS_STORY_BRIEF_AGENT_NAME",
    "NEWS_STORY_BRIEF_LANE",
    "NEWS_STORY_BRIEF_WORKFLOW_NAME",
    "NewsStoryBriefAgentConfig",
    "NewsStoryBriefInputPacket",
    "NewsStoryBriefMember",
    "default_news_story_brief_agent_config",
    "story_brief_key_for",
]
