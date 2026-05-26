from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class NewsSourceSnapshot:
    source_id: str
    provider_type: str
    feed_url: str
    source_domain: str
    source_name: str
    source_role: str
    trust_tier: str
    raw: dict[str, Any]
    now_ms: int

    @classmethod
    def from_row(cls, row: Mapping[str, Any], now_ms: int) -> NewsSourceSnapshot:
        return cls(
            source_id=str(row["source_id"]),
            provider_type=str(row.get("provider_type") or ""),
            feed_url=str(row.get("feed_url") or ""),
            source_domain=str(row.get("source_domain") or ""),
            source_name=str(row.get("source_name") or ""),
            source_role=str(row.get("source_role") or "observed_source"),
            trust_tier=str(row.get("trust_tier") or "standard"),
            raw=dict(row),
            now_ms=int(now_ms),
        )


@dataclass(frozen=True, slots=True)
class NewsSourceHttpCache:
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True, slots=True)
class NewsProviderObservation:
    source_item_key: str
    canonical_url: str
    title: str
    summary: str
    body_text: str
    language: str
    published_at_ms: int
    raw_payload: dict[str, Any]
    engagement: dict[str, Any] | None = None
    provider_tags: tuple[str, ...] = ()
    original_source_url: str | None = None
    original_source_domain: str | None = None
    provider_signal: dict[str, Any] | None = None
    provider_token_impacts: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class NewsProviderContextObservation:
    context_item_id: str
    parent_source_item_key: str
    context_type: str
    author: str | None
    canonical_url: str | None
    body_text: str
    published_at_ms: int | None
    engagement: dict[str, Any] | None
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class NewsProviderFetchResult:
    status_code: int
    observations: list[NewsProviderObservation]
    context_observations: list[NewsProviderContextObservation] = field(default_factory=list)
    etag: str | None = None
    last_modified: str | None = None
    next_cursor: dict[str, Any] = field(default_factory=dict)
    not_modified: bool = False
    provider_diagnostics: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "NewsProviderContextObservation",
    "NewsProviderFetchResult",
    "NewsProviderObservation",
    "NewsSourceHttpCache",
    "NewsSourceSnapshot",
]
