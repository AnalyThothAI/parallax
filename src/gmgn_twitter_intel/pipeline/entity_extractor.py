from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from eth_utils import is_address, to_checksum_address
from solders.pubkey import Pubkey

from .tweet_text import CASHTAG_RE, HASHTAG_RE, MENTION_RE, URL_RE

EVM_CA_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
SOLANA_CA_RE = re.compile(r"(?<![A-Za-z0-9])[1-9A-HJ-NP-Za-km-z]{32,44}(?![A-Za-z0-9])")


@dataclass(frozen=True, slots=True)
class ExtractedEntity:
    entity_type: str
    raw_value: str
    normalized_value: str
    chain: str | None
    token_resolution_status: str
    confidence: float
    source: str


def extract_entities(text: str | None) -> list[ExtractedEntity]:
    if not text:
        return []
    entities: list[ExtractedEntity] = []
    seen: set[tuple[str, str, str | None]] = set()

    for raw in EVM_CA_RE.findall(text):
        _append_unique(entities, seen, _evm_ca_entity(raw))

    for raw in SOLANA_CA_RE.findall(text):
        if raw.startswith("0x"):
            continue
        entity = _solana_ca_entity(raw)
        if entity is not None:
            _append_unique(entities, seen, entity)

    for symbol in CASHTAG_RE.findall(text):
        _append_unique(
            entities,
            seen,
            ExtractedEntity(
                entity_type="symbol",
                raw_value=f"${symbol}",
                normalized_value=symbol.upper(),
                chain=None,
                token_resolution_status="unresolved_symbol",
                confidence=0.8,
                source="cashtag",
            ),
        )

    for hashtag in HASHTAG_RE.findall(text):
        _append_unique(
            entities,
            seen,
            ExtractedEntity("hashtag", f"#{hashtag}", hashtag.lower(), None, "non_token_entity", 1.0, "regex"),
        )

    for mention in MENTION_RE.findall(text):
        _append_unique(
            entities,
            seen,
            ExtractedEntity("mention", f"@{mention}", mention.lower(), None, "non_token_entity", 1.0, "regex"),
        )

    for raw_url in URL_RE.findall(text):
        cleaned = raw_url.rstrip(".,!?;:)]}")
        _append_unique(
            entities,
            seen,
            ExtractedEntity("url", cleaned, cleaned, None, "non_token_entity", 1.0, "url"),
        )
        domain = urlparse(cleaned).netloc.lower()
        if domain:
            _append_unique(
                entities,
                seen,
                ExtractedEntity("domain", domain, domain, None, "non_token_entity", 1.0, "url"),
            )

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


def entity_key(entity: ExtractedEntity) -> str:
    if entity.chain:
        return f"{entity.entity_type}:{entity.chain}:{entity.normalized_value}"
    return f"{entity.entity_type}:{entity.normalized_value}"


def _evm_ca_entity(raw: str) -> ExtractedEntity:
    return ExtractedEntity("ca", raw, to_checksum_address(raw), "eth", "resolved_ca", 1.0, "regex")


def _solana_ca_entity(raw: str) -> ExtractedEntity | None:
    try:
        pubkey = Pubkey.from_string(raw)
    except ValueError:
        return None
    return ExtractedEntity("ca", raw, str(pubkey), "solana", "resolved_ca", 1.0, "regex")


def _append_unique(
    entities: list[ExtractedEntity],
    seen: set[tuple[str, str, str | None]],
    entity: ExtractedEntity,
) -> None:
    key = (entity.entity_type, entity.normalized_value, entity.chain)
    if key in seen:
        return
    seen.add(key)
    entities.append(entity)
