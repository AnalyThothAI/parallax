from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.news_intel.services.news_url_identity import (
    is_article_identity,
)
from gmgn_twitter_intel.domains.news_intel.services.news_url_identity import (
    url_identity_kind as classify_url_identity_kind,
)

CANONICAL_POLICY_VERSION = "news_canonical_item_v1"
_HOUR_MS = 3_600_000


@dataclass(frozen=True, slots=True)
class CanonicalIdentity:
    canonical_item_key: str
    news_item_id: str
    dedup_key_kind: str
    dedup_key_confidence: str
    url_identity_kind: str
    match_type: str
    match_confidence: str
    evidence: dict[str, Any]


def provider_article_key(*, provider_type: str, provider_article_id: str) -> str:
    """Return '<provider_type>:<provider_article_id>' when both values are present."""

    normalized_provider_type = str(provider_type or "").strip().lower()
    normalized_article_id = str(provider_article_id or "").strip()
    if not normalized_provider_type or not normalized_article_id:
        return ""
    return f"{normalized_provider_type}:{normalized_article_id}"


def canonical_identity_for_observation(
    *,
    provider_type: str,
    source_id: str,
    provider_article_id: str,
    canonical_url: str,
    content_hash: str,
    title_fingerprint: str,
    published_at_ms: int,
) -> CanonicalIdentity:
    """Choose provider article id, article URL, or content hash as the canonical hard key."""

    normalized_provider_type = str(provider_type or "").strip().lower()
    normalized_source_id = str(source_id or "").strip()
    normalized_article_id = str(provider_article_id or "").strip()
    normalized_url = str(canonical_url or "").strip()
    normalized_content_hash = str(content_hash or "").strip()
    normalized_title = str(title_fingerprint or "").strip()
    url_kind = classify_url_identity_kind(normalized_url)
    article_key = provider_article_key(
        provider_type=normalized_provider_type,
        provider_article_id=normalized_article_id,
    )

    if normalized_content_hash:
        return _identity(
            canonical_item_key=f"content-hash:{normalized_content_hash}",
            dedup_key_kind="content_hash",
            dedup_key_confidence="strong",
            url_identity_kind=url_kind,
            match_type="same_content_hash",
            match_confidence="strong",
            evidence={
                "content_hash": normalized_content_hash,
                "canonical_url": normalized_url,
                "url_identity_kind": url_kind,
                "source_id": normalized_source_id,
                "provider_type": normalized_provider_type,
                "provider_article_id": normalized_article_id or None,
                "provider_article_key": article_key or None,
            },
        )

    if normalized_provider_type == "opennews" and normalized_article_id:
        return _identity(
            canonical_item_key=f"provider:opennews:{normalized_article_id}",
            dedup_key_kind="provider_article_id",
            dedup_key_confidence="strong",
            url_identity_kind=url_kind,
            match_type="same_provider_article_id",
            match_confidence="strong",
            evidence={
                "provider_type": normalized_provider_type,
                "provider_article_id": normalized_article_id,
                "provider_article_key": article_key,
                "source_id": normalized_source_id,
            },
        )

    if is_article_identity(normalized_url, kind=url_kind):
        return _identity(
            canonical_item_key=f"article-url:{normalized_url}",
            dedup_key_kind="article_url",
            dedup_key_confidence="strong",
            url_identity_kind=url_kind,
            match_type="same_article_url",
            match_confidence="strong",
            evidence={
                "canonical_url": normalized_url,
                "url_identity_kind": url_kind,
                "source_id": normalized_source_id,
            },
        )

    published_hour_ms = _published_hour_ms(published_at_ms)
    return _identity(
        canonical_item_key=(f"weak-title-source-window:{normalized_source_id}:{published_hour_ms}:{normalized_title}"),
        dedup_key_kind="weak_title_time_source",
        dedup_key_confidence="weak",
        url_identity_kind=url_kind,
        match_type="weak_title_time_source",
        match_confidence="weak",
        evidence={
            "source_id": normalized_source_id,
            "published_hour_ms": published_hour_ms,
            "title_fingerprint": normalized_title,
            "canonical_url": normalized_url,
            "url_identity_kind": url_kind,
        },
    )


def stable_news_item_id(canonical_item_key: str) -> str:
    """Return 'news-item-' plus sha256(canonical_item_key) first 32 hex chars."""

    digest = hashlib.sha256(str(canonical_item_key or "").encode("utf-8")).hexdigest()
    return f"news-item-{digest[:32]}"


def _identity(
    *,
    canonical_item_key: str,
    dedup_key_kind: str,
    dedup_key_confidence: str,
    url_identity_kind: str,
    match_type: str,
    match_confidence: str,
    evidence: dict[str, Any],
) -> CanonicalIdentity:
    return CanonicalIdentity(
        canonical_item_key=canonical_item_key,
        news_item_id=stable_news_item_id(canonical_item_key),
        dedup_key_kind=dedup_key_kind,
        dedup_key_confidence=dedup_key_confidence,
        url_identity_kind=url_identity_kind,
        match_type=match_type,
        match_confidence=match_confidence,
        evidence={**evidence, "policy_version": CANONICAL_POLICY_VERSION},
    )


def _published_hour_ms(published_at_ms: int) -> int:
    try:
        value = int(published_at_ms)
    except (TypeError, ValueError):
        value = 0
    return max(value, 0) - (max(value, 0) % _HOUR_MS)
