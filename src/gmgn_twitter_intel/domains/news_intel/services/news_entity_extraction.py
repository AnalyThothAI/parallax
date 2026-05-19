from __future__ import annotations

import hashlib
from dataclasses import dataclass

from gmgn_twitter_intel.domains.evidence.interfaces import TextSurface, extract_entities_from_surfaces
from gmgn_twitter_intel.domains.news_intel._constants import NEWS_ENTITY_POLICY_VERSION


@dataclass(frozen=True, slots=True)
class NewsEntity:
    entity_id: str
    news_item_id: str
    entity_type: str
    raw_value: str
    normalized_value: str
    chain: str | None
    span_start: int
    span_end: int
    text_surface: str
    confidence: float
    extraction_policy_version: str
    created_at_ms: int


def extract_news_entities(
    *,
    news_item_id: str,
    title: str,
    summary: str,
    body_text: str,
    now_ms: int,
) -> list[NewsEntity]:
    surfaces = [
        TextSurface("title", title),
        TextSurface("summary", summary),
        TextSurface("body", body_text),
    ]
    return [
        NewsEntity(
            entity_id=_stable_id(
                "news-entity",
                news_item_id,
                entity.entity_type,
                entity.normalized_value,
                entity.chain or "",
                entity.text_surface,
                str(entity.span_start),
                str(entity.span_end),
            ),
            news_item_id=news_item_id,
            entity_type=entity.entity_type,
            raw_value=entity.raw_value,
            normalized_value=entity.normalized_value,
            chain=entity.chain,
            span_start=entity.span_start,
            span_end=entity.span_end,
            text_surface=entity.text_surface,
            confidence=entity.confidence,
            extraction_policy_version=NEWS_ENTITY_POLICY_VERSION,
            created_at_ms=int(now_ms),
        )
        for entity in extract_entities_from_surfaces(surfaces)
    ]


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
