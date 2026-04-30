from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import httpx

from .token_extractor import normalize_ca


@dataclass(frozen=True, slots=True)
class TokenRegistryEntry:
    chain: str
    ca: str
    symbol: str | None
    name: str | None
    aliases: list[str] = field(default_factory=list)
    source: str = "provider"


class TokenProvider(Protocol):
    def search(self, query: str) -> list[TokenRegistryEntry]: ...


class DexScreenerProvider:
    def __init__(self, *, timeout: float = 5.0):
        self.timeout = timeout

    def search(self, query: str) -> list[TokenRegistryEntry]:
        response = httpx.get(
            "https://api.dexscreener.com/latest/dex/search",
            params={"q": query},
            timeout=self.timeout,
        )
        response.raise_for_status()
        pairs = response.json().get("pairs") or []
        entries: dict[tuple[str, str], TokenRegistryEntry] = {}
        for pair in pairs:
            base = pair.get("baseToken") if isinstance(pair, dict) else None
            if not isinstance(base, dict):
                continue
            chain = _normalize_chain(str(pair.get("chainId") or ""))
            ca = str(base.get("address") or "")
            if not chain or not ca:
                continue
            symbol = str(base.get("symbol") or "").upper() or None
            entry = TokenRegistryEntry(
                chain=chain,
                ca=ca,
                symbol=symbol,
                name=base.get("name"),
                aliases=[value for value in [symbol, base.get("name")] if value],
                source="dexscreener",
            )
            entries[(entry.chain, entry.ca)] = entry
        return list(entries.values())


class TokenResolver:
    def __init__(self, repo, provider: TokenProvider):
        self.repo = repo
        self.provider = provider

    def resolve_symbol(self, symbol: str) -> dict:
        candidates = self.provider.search(symbol)
        for candidate in candidates:
            self.repo.upsert_token(candidate)
        matches = [
            candidate
            for candidate in candidates
            if candidate.symbol and candidate.symbol.upper() == symbol.strip().lstrip("$").upper()
        ]
        if len(matches) == 1:
            return {"status": "resolved", "token": _entry_dict(matches[0]), "candidates": []}
        return {
            "status": "ambiguous" if matches else "unresolved",
            "candidates": [_entry_dict(item) for item in matches],
        }

    def resolve_ca(self, ca: str, *, chain: str | None = None) -> dict:
        normalized_chain, normalized_ca = normalize_ca(ca, chain=chain)
        candidates = self.provider.search(normalized_ca)
        for candidate in candidates:
            self.repo.upsert_token(candidate)
        for candidate in candidates:
            if candidate.chain == normalized_chain and candidate.ca.lower() == normalized_ca.lower():
                return {"status": "resolved", "token": _entry_dict(candidate), "candidates": []}
        entry = TokenRegistryEntry(
            chain=normalized_chain,
            ca=normalized_ca,
            symbol=None,
            name=None,
            aliases=[],
            source="local_ca",
        )
        self.repo.upsert_token(entry)
        return {"status": "resolved", "token": _entry_dict(entry), "candidates": []}


def _entry_dict(entry: TokenRegistryEntry) -> dict:
    return {
        "chain": entry.chain,
        "ca": entry.ca,
        "symbol": entry.symbol,
        "name": entry.name,
        "aliases": entry.aliases,
        "source": entry.source,
    }


def _normalize_chain(chain: str) -> str:
    normalized = chain.strip().lower()
    return {"ethereum": "eth", "solana": "solana"}.get(normalized, normalized)
