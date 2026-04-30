from __future__ import annotations

import re
from dataclasses import dataclass

from eth_utils import is_address, to_checksum_address
from solders.pubkey import Pubkey

from .tweet_text import extract_cashtags

EVM_CA_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
EVM_LIKE_RE = re.compile(r"\b0x[A-Za-z0-9]{32,48}\b")
SOLANA_CA_RE = re.compile(r"(?<![A-Za-z0-9])[1-9A-HJ-NP-Za-km-z]{32,44}(?![A-Za-z0-9])")


@dataclass(frozen=True, slots=True)
class TokenEntity:
    entity_type: str
    raw_value: str
    normalized_value: str
    chain: str | None
    token_resolution_status: str
    confidence: float
    source: str


def extract_token_entities(text: str | None) -> list[TokenEntity]:
    if not text:
        return []
    entities: list[TokenEntity] = []
    seen: set[tuple[str, str, str | None]] = set()

    for raw in EVM_CA_RE.findall(text):
        entity = _evm_entity(raw)
        _append_unique(entities, seen, entity)

    valid_evm = set(EVM_CA_RE.findall(text))
    for raw in EVM_LIKE_RE.findall(text):
        if raw in valid_evm:
            continue
        entity = TokenEntity(
            entity_type="ca",
            raw_value=raw,
            normalized_value=raw,
            chain="evm",
            token_resolution_status="invalid_candidate",
            confidence=0.2,
            source="regex",
        )
        _append_unique(entities, seen, entity)

    for raw in SOLANA_CA_RE.findall(text):
        if raw.startswith("0x"):
            continue
        entity = _solana_entity(raw)
        if entity:
            _append_unique(entities, seen, entity)

    for symbol in extract_cashtags(text):
        entity = TokenEntity(
            entity_type="symbol",
            raw_value=f"${symbol}",
            normalized_value=symbol,
            chain=None,
            token_resolution_status="unresolved",
            confidence=0.6,
            source="cashtag",
        )
        _append_unique(entities, seen, entity)

    return entities


def normalize_ca(value: str, *, chain: str | None = None) -> tuple[str, str]:
    text = value.strip()
    if chain in {None, "eth", "evm"} and is_address(text):
        return ("eth", to_checksum_address(text))
    try:
        pubkey = Pubkey.from_string(text)
    except ValueError as exc:
        raise ValueError(f"invalid token CA: {value}") from exc
    return ("solana", str(pubkey))


def _evm_entity(raw: str) -> TokenEntity:
    return TokenEntity(
        entity_type="ca",
        raw_value=raw,
        normalized_value=to_checksum_address(raw),
        chain="eth",
        token_resolution_status="resolved",
        confidence=1.0,
        source="regex",
    )


def _solana_entity(raw: str) -> TokenEntity | None:
    try:
        pubkey = Pubkey.from_string(raw)
    except ValueError:
        return None
    return TokenEntity(
        entity_type="ca",
        raw_value=raw,
        normalized_value=str(pubkey),
        chain="solana",
        token_resolution_status="resolved",
        confidence=1.0,
        source="regex",
    )


def _append_unique(
    entities: list[TokenEntity],
    seen: set[tuple[str, str, str | None]],
    entity: TokenEntity,
) -> None:
    key = (entity.entity_type, entity.normalized_value, entity.chain)
    if key in seen:
        return
    seen.add(key)
    entities.append(entity)
