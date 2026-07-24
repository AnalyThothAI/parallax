from __future__ import annotations

import hashlib

from tracefold.market import TextSurface, extract_entities_from_surfaces
from tracefold.news.ingest.extraction_contracts import NewsEntity
from tracefold.news.projection.constants import NEWS_ENTITY_POLICY_VERSION


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
    return _dedupe_by_repository_identity(
        [
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
    )


def _dedupe_by_repository_identity(entities: list[NewsEntity]) -> list[NewsEntity]:
    deduped: list[NewsEntity] = []
    seen: set[tuple[str, str, str, str, int, int]] = set()
    for entity in entities:
        key = (
            entity.news_item_id,
            entity.entity_type,
            entity.normalized_value,
            entity.chain or "",
            int(entity.span_start),
            int(entity.span_end),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entity)
    return deduped


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
