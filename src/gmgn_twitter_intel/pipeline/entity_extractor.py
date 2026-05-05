from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from eth_utils import is_address, to_checksum_address
from solders.pubkey import Pubkey

from .tweet_text import CASHTAG_RE, HASHTAG_RE, MENTION_RE, URL_RE

EVM_CA_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
SOLANA_CA_RE = re.compile(r"(?<![A-Za-z0-9])[1-9A-HJ-NP-Za-km-z]{32,44}(?![A-Za-z0-9])")
EVM_QUERY_CHAINS = frozenset({"evm_unknown", "evm", "eth", "base", "bsc"})
RESOLVED_EVM_CHAINS = frozenset({"eth", "base", "bsc"})
EVM_CHAIN_HINT_PATTERNS = (
    ("bsc", re.compile(r"\b(?:bsc|bnb\s+chain|binance\s+smart\s+chain|bep[-\s]?20)\b", re.IGNORECASE)),
    ("eth", re.compile(r"\b(?:eth|ethereum|erc[-\s]?20)\b", re.IGNORECASE)),
    ("base", re.compile(r"\b(?:on\s+base|base\s+(?:mainnet|chain|token|ca))\b", re.IGNORECASE)),
)
EXPLORER_HOST_CHAINS = {
    "etherscan.io": "eth",
    "bscscan.com": "bsc",
    "basescan.org": "base",
}


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

    for match in EVM_CA_RE.finditer(text):
        raw = match.group(0)
        _append_unique(
            entities,
            seen,
            _evm_ca_entity(raw, chain=_chain_for_evm_ca(text, raw=raw, start=match.start(), end=match.end())),
        )

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
    normalized_chain = _normalize_chain_hint(chain)
    if is_address(text):
        if normalized_chain is None:
            return ("evm_unknown", to_checksum_address(text))
        if normalized_chain in EVM_QUERY_CHAINS:
            return (normalized_chain, to_checksum_address(text))
    try:
        pubkey = Pubkey.from_string(text)
    except ValueError as exc:
        raise ValueError(f"invalid token CA: {value}") from exc
    return ("solana", str(pubkey))


def entity_key(entity: ExtractedEntity) -> str:
    if entity.chain:
        return f"{entity.entity_type}:{entity.chain}:{entity.normalized_value}"
    return f"{entity.entity_type}:{entity.normalized_value}"


def _evm_ca_entity(raw: str, *, chain: str | None = None) -> ExtractedEntity:
    resolved_chain = chain if chain in RESOLVED_EVM_CHAINS else "evm_unknown"
    status = "resolved_ca" if resolved_chain != "evm_unknown" else "unresolved_chain_ca"
    return ExtractedEntity("ca", raw, to_checksum_address(raw), resolved_chain, status, 1.0, "regex")


def _solana_ca_entity(raw: str) -> ExtractedEntity | None:
    try:
        pubkey = Pubkey.from_string(raw)
    except ValueError:
        return None
    return ExtractedEntity("ca", raw, str(pubkey), "solana", "resolved_ca", 1.0, "regex")


def _chain_for_evm_ca(text: str, *, raw: str, start: int, end: int) -> str | None:
    direct_url_chain = _chain_from_explorer_url_containing(text, raw.lower())
    if direct_url_chain:
        return direct_url_chain

    snippet = text[max(0, start - 180) : min(len(text), end + 180)]
    local_hint = _single_evm_chain_hint(snippet)
    if local_hint:
        return local_hint
    return _single_evm_chain_hint(text)


def _chain_from_explorer_url_containing(text: str, address: str) -> str | None:
    for raw_url in URL_RE.findall(text):
        cleaned = raw_url.rstrip(".,!?;:)]}")
        if address not in cleaned.lower():
            continue
        chain = _chain_from_url(cleaned)
        if chain:
            return chain
    return None


def _single_evm_chain_hint(text: str) -> str | None:
    hints = set()
    for raw_url in URL_RE.findall(text):
        chain = _chain_from_url(raw_url.rstrip(".,!?;:)]}"))
        if chain:
            hints.add(chain)
    for chain, pattern in EVM_CHAIN_HINT_PATTERNS:
        if pattern.search(text):
            hints.add(chain)
    return next(iter(hints)) if len(hints) == 1 else None


def _chain_from_url(raw_url: str) -> str | None:
    host = urlparse(raw_url).netloc.lower()
    for domain, chain in EXPLORER_HOST_CHAINS.items():
        if host == domain or host.endswith(f".{domain}"):
            return chain
    return None


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


def _normalize_chain_hint(chain: str | None) -> str | None:
    if chain is None:
        return None
    normalized = chain.strip().lower()
    if normalized == "ethereum":
        return "eth"
    if normalized in {"sol", "solana"}:
        return "solana"
    return normalized
