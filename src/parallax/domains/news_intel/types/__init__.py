from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from parallax.domains.news_intel.types.source_classification import ProviderType, SourceRole

TrustTier = Literal["official", "high", "standard", "low"]
FetchRunStatus = Literal["running", "success", "failed"]
UpsertStatus = Literal["inserted", "updated", "duplicate"]


@dataclass(frozen=True, slots=True)
class NewsSourceConfig:
    source_id: str
    provider_type: ProviderType
    feed_url: str
    source_domain: str
    source_name: str
    source_role: SourceRole = "observed_source"
    trust_tier: TrustTier = "standard"
    managed_by_config: bool = True
    enabled: bool = True
    refresh_interval_seconds: int = 300
    coverage_tags: tuple[str, ...] = ()
    asset_universe: tuple[str, ...] = ()
    authority_scope: dict[str, Any] = field(default_factory=dict)
    fetch_policy: dict[str, Any] = field(default_factory=dict)
    context_policy: dict[str, Any] = field(default_factory=dict)
    cost_policy: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NormalizedNewsItem:
    source_item_key: str
    canonical_url: str
    title: str
    summary: str
    body_text: str
    language: str
    published_at_ms: int
    raw_payload: dict[str, Any]


class UpsertResult(TypedDict):
    status: UpsertStatus
    provider_item_id: str


class NewsItemUpsertResult(TypedDict):
    status: UpsertStatus
    news_item_id: str


JsonObject = dict[str, Any]
