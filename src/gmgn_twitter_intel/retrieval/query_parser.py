from __future__ import annotations

from dataclasses import dataclass

from ..pipeline.entity_extractor import normalize_ca


@dataclass(frozen=True, slots=True)
class ParsedQuery:
    kind: str
    text: str
    ca: str | None = None
    chain: str | None = None
    symbol: str | None = None
    handle: str | None = None


def parse_query(text: str) -> ParsedQuery:
    query = text.strip()
    if not query:
        return ParsedQuery(kind="empty", text="")
    if query.startswith("@") and len(query) > 1:
        return ParsedQuery(kind="handle", text=query, handle=query.lstrip("@").lower())
    if query.startswith("$") and len(query) > 1:
        return ParsedQuery(kind="symbol", text=query, symbol=query.lstrip("$").upper())
    chain_prefixed_ca = _parse_chain_prefixed_ca(query)
    if chain_prefixed_ca is not None:
        chain, ca = chain_prefixed_ca
        return ParsedQuery(kind="ca", text=query, ca=ca, chain=chain)
    try:
        chain, ca = normalize_ca(query)
    except ValueError:
        chain = ca = None
    if ca:
        return ParsedQuery(kind="ca", text=query, ca=ca, chain=chain)
    return ParsedQuery(kind="text", text=query)


def _parse_chain_prefixed_ca(query: str) -> tuple[str, str] | None:
    chain_hint, separator, value = query.partition(":")
    if not separator or not chain_hint.strip() or not value.strip():
        return None
    try:
        return normalize_ca(value, chain=chain_hint)
    except ValueError:
        return None
