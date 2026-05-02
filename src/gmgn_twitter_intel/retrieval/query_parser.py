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
    try:
        chain, ca = normalize_ca(query)
    except ValueError:
        chain = ca = None
    if ca:
        return ParsedQuery(kind="ca", text=query, ca=ca, chain=chain)
    if query.isascii() and query.isupper() and 2 <= len(query) <= 12 and query.isalnum():
        return ParsedQuery(kind="symbol", text=query, symbol=query.upper())
    return ParsedQuery(kind="text", text=query)
