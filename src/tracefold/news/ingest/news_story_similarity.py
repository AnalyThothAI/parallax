from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class NewsSimilarityEvidence:
    exact_duplicate: bool
    similar_story: bool
    reason: str
    representative_news_item_id: str
    story_key: str
    evidence: dict[str, Any]


def decide_news_story_similarity(
    *,
    item: Mapping[str, Any],
    exact_duplicate_candidates: Sequence[Mapping[str, Any]],
    story_candidates: Sequence[Mapping[str, Any]],
) -> NewsSimilarityEvidence:
    exact = _exact_duplicate(item=item, candidates=exact_duplicate_candidates)
    if exact is not None:
        return exact
    similar = _similar_story(item=item, candidates=story_candidates)
    if similar is not None:
        return similar
    return NewsSimilarityEvidence(
        exact_duplicate=False,
        similar_story=False,
        reason="unique_story",
        representative_news_item_id=str(item.get("news_item_id") or ""),
        story_key=str(item.get("story_key") or ""),
        evidence={},
    )


def _exact_duplicate(
    *,
    item: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> NewsSimilarityEvidence | None:
    item_provider_keys = set(_provider_article_keys(item))
    item_url = _article_url(item)
    item_content_hash = _text(item.get("content_hash"))
    item_canonical_key = _text(item.get("canonical_item_key"))
    for candidate in candidates:
        candidate_id = _text(candidate.get("news_item_id"))
        candidate_provider_keys = set(_provider_article_keys(candidate))
        if item_provider_keys and item_provider_keys & candidate_provider_keys:
            return _evidence(
                exact=True,
                similar=False,
                reason="same_provider_article_id",
                representative_news_item_id=candidate_id,
                story_key=_text(candidate.get("story_key") or item.get("story_key")),
                evidence={"provider_article_keys": sorted(item_provider_keys & candidate_provider_keys)},
            )
        candidate_url = _article_url(candidate)
        if item_url and candidate_url and item_url == candidate_url:
            return _evidence(
                exact=True,
                similar=False,
                reason="same_article_url",
                representative_news_item_id=candidate_id,
                story_key=_text(candidate.get("story_key") or item.get("story_key")),
                evidence={"canonical_url": item_url},
            )
        candidate_content_hash = _text(candidate.get("content_hash"))
        if item_content_hash and item_content_hash == candidate_content_hash:
            return _evidence(
                exact=True,
                similar=False,
                reason="same_content_hash",
                representative_news_item_id=candidate_id,
                story_key=_text(candidate.get("story_key") or item.get("story_key")),
                evidence={"content_hash": item_content_hash},
            )
        candidate_canonical_key = _text(candidate.get("canonical_item_key"))
        if item_canonical_key and item_canonical_key == candidate_canonical_key and _canonical_key_is_article(item):
            return _evidence(
                exact=True,
                similar=False,
                reason="same_article_url",
                representative_news_item_id=candidate_id,
                story_key=_text(candidate.get("story_key") or item.get("story_key")),
                evidence={"canonical_item_key": item_canonical_key},
            )
    return None


def _similar_story(
    *,
    item: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> NewsSimilarityEvidence | None:
    item_story_key = _text(item.get("story_key"))
    item_title_fingerprint = _text(item.get("title_fingerprint"))
    for candidate in candidates:
        candidate_id = _text(candidate.get("news_item_id"))
        candidate_story_key = _text(candidate.get("story_key"))
        if item_story_key and item_story_key == candidate_story_key:
            return _evidence(
                exact=False,
                similar=True,
                reason="same_story_key",
                representative_news_item_id=candidate_id,
                story_key=item_story_key,
                evidence={"story_key": item_story_key},
            )
        candidate_title_fingerprint = _text(candidate.get("title_fingerprint"))
        if item_title_fingerprint and item_title_fingerprint == candidate_title_fingerprint:
            return _evidence(
                exact=False,
                similar=True,
                reason="same_material_title_bucket",
                representative_news_item_id=candidate_id,
                story_key=candidate_story_key or item_story_key,
                evidence={"title_fingerprint": item_title_fingerprint},
            )
    return None


def _evidence(
    *,
    exact: bool,
    similar: bool,
    reason: str,
    representative_news_item_id: str,
    story_key: str,
    evidence: dict[str, Any],
) -> NewsSimilarityEvidence:
    return NewsSimilarityEvidence(
        exact_duplicate=exact,
        similar_story=similar,
        reason=reason,
        representative_news_item_id=representative_news_item_id,
        story_key=story_key,
        evidence=evidence,
    )


def _provider_article_keys(row: Mapping[str, Any]) -> list[str]:
    keys: list[str] = []
    keys.extend(_optional_provider_key_list(row, "provider_article_keys"))
    keys.extend(_optional_provider_key_list(row, "provider_article_keys_json"))
    return list(dict.fromkeys(keys))


def _optional_provider_key_list(row: Mapping[str, Any], field_name: str) -> list[str]:
    if field_name not in row:
        return []
    value = row.get(field_name)
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"news_story_similarity_{field_name}_required")
    keys: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"news_story_similarity_{field_name}_required")
        text = item.strip()
        if text:
            keys.append(text)
    return keys


def _article_url(row: Mapping[str, Any]) -> str:
    url = _text(row.get("canonical_url"))
    if not url:
        return ""
    if str(row.get("url_identity_kind") or "").strip().lower() == "article":
        return url
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not parsed.netloc or not path:
        return ""
    if path.lower() in {"live", "news", "business", "markets"}:
        return ""
    if "/live/" in f"/{path.lower()}/":
        return ""
    return url


def _canonical_key_is_article(row: Mapping[str, Any]) -> bool:
    kind = str(row.get("url_identity_kind") or "").strip().lower()
    if kind:
        return kind == "article"
    return bool(_article_url(row))


def _text(value: Any) -> str:
    return str(value or "").strip()


__all__ = ["NewsSimilarityEvidence", "decide_news_story_similarity"]
