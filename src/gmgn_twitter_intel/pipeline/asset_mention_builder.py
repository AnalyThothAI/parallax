from __future__ import annotations

from dataclasses import dataclass

from ..models import TokenSnapshot
from .entity_extractor import ExtractedEntity


@dataclass(frozen=True, slots=True)
class AssetMentionInput:
    event_id: str
    mention_type: str
    raw_value: str
    normalized_symbol: str | None
    chain_hint: str | None
    address_hint: str | None
    source_entity_id: str | None
    source: str
    mention_confidence: float
    created_at_ms: int


def build_asset_mentions(
    *,
    event_id: str,
    entities: list[ExtractedEntity],
    token_snapshot: TokenSnapshot | None,
    created_at_ms: int,
) -> list[AssetMentionInput]:
    mentions: list[AssetMentionInput] = []
    seen: set[tuple[str, str, str | None, str | None, str | None]] = set()

    for entity in entities:
        mention = _mention_from_entity(event_id=event_id, entity=entity, created_at_ms=created_at_ms)
        if mention is not None:
            _append_unique(mentions, seen, mention)

    if token_snapshot is not None:
        _append_unique(
            mentions,
            seen,
            AssetMentionInput(
                event_id=event_id,
                mention_type="gmgn_payload",
                raw_value=token_snapshot.symbol,
                normalized_symbol=_normalize_symbol(token_snapshot.symbol),
                chain_hint=_clean_chain(token_snapshot.chain),
                address_hint=token_snapshot.address,
                source_entity_id=None,
                source="gmgn_payload",
                mention_confidence=1.0,
                created_at_ms=created_at_ms,
            ),
        )

    return mentions


def _mention_from_entity(
    *,
    event_id: str,
    entity: ExtractedEntity,
    created_at_ms: int,
) -> AssetMentionInput | None:
    if entity.entity_type == "symbol":
        return AssetMentionInput(
            event_id=event_id,
            mention_type="cashtag",
            raw_value=entity.raw_value,
            normalized_symbol=_normalize_symbol(entity.normalized_value),
            chain_hint=None,
            address_hint=None,
            source_entity_id=None,
            source=entity.source,
            mention_confidence=entity.confidence,
            created_at_ms=created_at_ms,
        )
    if entity.entity_type == "ca":
        return AssetMentionInput(
            event_id=event_id,
            mention_type="ca",
            raw_value=entity.raw_value,
            normalized_symbol=None,
            chain_hint=_clean_chain(entity.chain),
            address_hint=entity.normalized_value,
            source_entity_id=None,
            source=entity.source,
            mention_confidence=entity.confidence,
            created_at_ms=created_at_ms,
        )
    return None


def _append_unique(
    mentions: list[AssetMentionInput],
    seen: set[tuple[str, str, str | None, str | None, str | None]],
    mention: AssetMentionInput,
) -> None:
    key = (
        mention.mention_type,
        mention.raw_value,
        mention.normalized_symbol,
        mention.chain_hint,
        mention.address_hint,
    )
    if key in seen:
        return
    seen.add(key)
    mentions.append(mention)


def _normalize_symbol(symbol: str | None) -> str | None:
    if symbol is None:
        return None
    stripped = symbol.strip().lstrip("$")
    if not stripped:
        return None
    return stripped.upper() if stripped.isascii() else stripped


def _clean_chain(chain: str | None) -> str | None:
    if chain is None:
        return None
    normalized = chain.strip().lower()
    if normalized in {"", "unknown", "evm", "evm_unknown"}:
        return None
    return normalized
