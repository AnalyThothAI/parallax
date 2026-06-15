from __future__ import annotations

import hashlib
from typing import Any

from parallax.domains.news_intel._constants import NEWS_TOKEN_MENTION_POLICY_VERSION
from parallax.domains.news_intel.types.news_extraction import NewsEntity, NewsTokenMention
from parallax.domains.token_intel.interfaces import TokenIdentityLookup, TokenIdentityLookupResult

_V1_RESOLUTION_STATUSES = frozenset(
    {
        "exact_address",
        "known_symbol",
        "unique_by_context",
        "ambiguous_symbol",
        "unknown_attention",
        "non_crypto",
        "nil",
    }
)


def build_news_token_mentions(
    *,
    news_item_id: str,
    entities: list[NewsEntity],
    identity_lookup: TokenIdentityLookup,
    now_ms: int,
) -> list[NewsTokenMention]:
    mentions: list[NewsTokenMention] = []
    for entity in entities:
        if entity.entity_type == "ca":
            result = identity_lookup.resolve_address(chain_id=entity.chain, address=entity.normalized_value)
            mentions.append(
                _mention(
                    news_item_id=news_item_id,
                    entity=entity,
                    observed_symbol=result.display_symbol,
                    chain_id=entity.chain,
                    address=entity.normalized_value,
                    status=_status_from_identity(result.resolution_status, address=True),
                    result=result,
                    evidence_strength="strong",
                    now_ms=now_ms,
                )
            )
            continue
        if entity.entity_type == "symbol":
            symbol = entity.normalized_value.upper()
            result = identity_lookup.resolve_symbol(symbol=symbol)
            mentions.append(
                _mention(
                    news_item_id=news_item_id,
                    entity=entity,
                    observed_symbol=symbol,
                    chain_id=None,
                    address=None,
                    status=_status_from_identity(result.resolution_status, address=False),
                    result=result,
                    evidence_strength="medium",
                    now_ms=now_ms,
                )
            )
    return _dedupe(mentions)


def _status_from_identity(status: str, *, address: bool) -> str:
    raw = str(status or "").strip()
    if raw in _V1_RESOLUTION_STATUSES:
        return raw
    normalized = raw.upper()
    if address and normalized in {"EXACT", "UNIQUE_BY_CONTEXT"}:
        return "exact_address"
    if normalized == "EXACT":
        return "known_symbol"
    if normalized == "UNIQUE_BY_CONTEXT":
        return "unique_by_context"
    if normalized == "AMBIGUOUS":
        return "ambiguous_symbol"
    if normalized in {"UNKNOWN", "UNKNOWN_ATTENTION"}:
        return "unknown_attention"
    if normalized == "NON_CRYPTO":
        return "non_crypto"
    if normalized == "NIL":
        return "nil" if address else "unknown_attention"
    return "nil"


def _mention(
    *,
    news_item_id: str,
    entity: NewsEntity,
    observed_symbol: str | None,
    chain_id: str | None,
    address: str | None,
    status: str,
    result: TokenIdentityLookupResult,
    evidence_strength: str,
    now_ms: int,
) -> NewsTokenMention:
    return NewsTokenMention(
        mention_id=_stable_id(
            "news-token-mention",
            NEWS_TOKEN_MENTION_POLICY_VERSION,
            news_item_id,
            entity.entity_id,
            status,
        ),
        news_item_id=news_item_id,
        entity_id=entity.entity_id,
        observed_symbol=observed_symbol,
        chain_id=chain_id,
        address=address,
        resolution_status=status,
        target_type=result.target_type,
        target_id=result.target_id,
        display_symbol=result.display_symbol,
        display_name=result.display_name,
        reason_codes=list(result.reason_codes),
        candidate_targets=[_json_object(candidate) for candidate in result.candidate_targets],
        evidence_strength=evidence_strength,
        confidence=entity.confidence,
        created_at_ms=int(now_ms),
    )


def _dedupe(items: list[NewsTokenMention]) -> list[NewsTokenMention]:
    deduped: list[NewsTokenMention] = []
    seen: set[str] = set()
    for item in items:
        if item.mention_id in seen:
            continue
        seen.add(item.mention_id)
        deduped.append(item)
    return deduped


def _json_object(value: dict[str, object] | dict[str, Any]) -> dict[str, object]:
    return dict(value)


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
