from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ..models import TokenSnapshot
from .entity_extractor import ExtractedEntity


@dataclass(frozen=True, slots=True)
class TokenEvidenceInput:
    evidence_id: str
    event_id: str
    source_kind: str
    source_id: str
    evidence_type: str
    raw_value: str
    normalized_symbol: str | None
    chain_hint: str | None
    address_hint: str | None
    provider: str | None
    provider_ref: str | None
    text_surface: str
    span_start: int
    span_end: int
    sentence_id: int
    local_group_key: str
    strength: str
    confidence: float
    created_at_ms: int


def build_token_evidence(
    *,
    event_id: str,
    entities: list[ExtractedEntity],
    token_snapshot: TokenSnapshot | None,
    created_at_ms: int,
) -> list[TokenEvidenceInput]:
    evidence: list[TokenEvidenceInput] = []
    for entity in entities:
        if entity.entity_type == "ca":
            evidence.append(_from_ca_entity(event_id=event_id, entity=entity, created_at_ms=created_at_ms))
        elif entity.entity_type == "symbol":
            evidence.append(_from_symbol_entity(event_id=event_id, entity=entity, created_at_ms=created_at_ms))
    if token_snapshot is not None:
        evidence.append(_from_gmgn_payload(event_id=event_id, snapshot=token_snapshot, created_at_ms=created_at_ms))
    return _unique(evidence)


def _from_ca_entity(*, event_id: str, entity: ExtractedEntity, created_at_ms: int) -> TokenEvidenceInput:
    source_id = _entity_source_id(event_id, entity)
    return TokenEvidenceInput(
        evidence_id=_evidence_id(
            event_id,
            "entity",
            source_id,
            "ca",
            entity.raw_value,
            entity.span_start,
            entity.span_end,
        ),
        event_id=event_id,
        source_kind="entity",
        source_id=source_id,
        evidence_type="ca",
        raw_value=entity.raw_value,
        normalized_symbol=None,
        chain_hint=_clean_chain(entity.chain),
        address_hint=entity.normalized_value,
        provider=None,
        provider_ref=None,
        text_surface=entity.text_surface,
        span_start=entity.span_start,
        span_end=entity.span_end,
        sentence_id=entity.sentence_id,
        local_group_key=entity.local_group_key,
        strength="strong",
        confidence=entity.confidence,
        created_at_ms=created_at_ms,
    )


def _from_symbol_entity(*, event_id: str, entity: ExtractedEntity, created_at_ms: int) -> TokenEvidenceInput:
    source_id = _entity_source_id(event_id, entity)
    return TokenEvidenceInput(
        evidence_id=_evidence_id(
            event_id, "entity", source_id, "cashtag", entity.raw_value, entity.span_start, entity.span_end
        ),
        event_id=event_id,
        source_kind="entity",
        source_id=source_id,
        evidence_type="cashtag",
        raw_value=entity.raw_value,
        normalized_symbol=_normalize_symbol(entity.normalized_value),
        chain_hint=None,
        address_hint=None,
        provider=None,
        provider_ref=None,
        text_surface=entity.text_surface,
        span_start=entity.span_start,
        span_end=entity.span_end,
        sentence_id=entity.sentence_id,
        local_group_key=entity.local_group_key,
        strength="medium",
        confidence=entity.confidence,
        created_at_ms=created_at_ms,
    )


def _from_gmgn_payload(*, event_id: str, snapshot: TokenSnapshot, created_at_ms: int) -> TokenEvidenceInput:
    chain = _clean_chain(snapshot.chain)
    address = snapshot.address.strip()
    source_id = _stable_id("gmgn-payload", event_id, chain or "", address.lower())
    return TokenEvidenceInput(
        evidence_id=_evidence_id(event_id, "gmgn_payload", source_id, "gmgn_token_payload", address, 0, 0),
        event_id=event_id,
        source_kind="gmgn_payload",
        source_id=source_id,
        evidence_type="gmgn_token_payload",
        raw_value=snapshot.symbol,
        normalized_symbol=_normalize_symbol(snapshot.symbol),
        chain_hint=chain,
        address_hint=address,
        provider="gmgn",
        provider_ref=address,
        text_surface="payload",
        span_start=0,
        span_end=0,
        sentence_id=0,
        local_group_key="payload:0",
        strength="strong",
        confidence=1.0,
        created_at_ms=created_at_ms,
    )


def _entity_source_id(event_id: str, entity: ExtractedEntity) -> str:
    return _stable_id(
        "event-entity",
        event_id,
        entity.entity_type,
        entity.normalized_value,
        entity.chain or "",
        entity.text_surface,
        str(entity.span_start),
        str(entity.span_end),
    )


def _evidence_id(
    event_id: str,
    source_kind: str,
    source_id: str,
    evidence_type: str,
    raw_value: str,
    span_start: int,
    span_end: int,
) -> str:
    return _stable_id(
        "token-evidence",
        event_id,
        source_kind,
        source_id,
        evidence_type,
        raw_value,
        str(span_start),
        str(span_end),
    )


def _unique(items: list[TokenEvidenceInput]) -> list[TokenEvidenceInput]:
    out: list[TokenEvidenceInput] = []
    seen: set[str] = set()
    for item in items:
        if item.evidence_id in seen:
            continue
        seen.add(item.evidence_id)
        out.append(item)
    return out


def _normalize_symbol(symbol: str | None) -> str | None:
    if symbol is None:
        return None
    stripped = symbol.strip().lstrip("$")
    return stripped.upper() if stripped and stripped.isascii() else stripped or None


def _clean_chain(chain: str | None) -> str | None:
    if chain is None:
        return None
    normalized = chain.strip().lower()
    return None if normalized in {"", "unknown", "evm", "evm_unknown"} else normalized


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
