from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from tracefold.market.views.query_parser import SearchIntent

TOKEN_QUERY_ALIASES: Mapping[str, Sequence[str]] = {
    "BTC": ("btc", "bitcoin", "bitcoins", "比特币", "xbt"),
    "ETH": ("eth", "ethereum", "ether", "以太坊"),
    "SOL": ("sol", "solana"),
    "DOGE": ("doge", "dogecoin", "狗狗币"),
}

_EXPLICIT_WEBSEARCH_OPERATOR_RE = re.compile(r"\b(?:OR|NOT)\b|\"", re.IGNORECASE)
_OR_SEPARATOR_RE = re.compile(r"\s+OR\s+", re.IGNORECASE)
_SYMBOL_TOKEN_RE = re.compile(r"^\$?[A-Za-z][A-Za-z0-9_]{1,20}$")
_ALIAS_TO_SYMBOL = {alias.lower(): symbol for symbol, aliases in TOKEN_QUERY_ALIASES.items() for alias in aliases}


def canonical_symbol_for_query(value: str) -> str | None:
    return _ALIAS_TO_SYMBOL.get(value.strip().lower())


def fuzzy_canonical_symbol_for_query(value: str) -> str | None:
    exact = canonical_symbol_for_query(value)
    if exact:
        return exact
    normalized = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{5,20}", normalized):
        return None
    best_symbol: str | None = None
    best_distance = 2
    for alias, symbol in _ALIAS_TO_SYMBOL.items():
        if len(alias) < 5 or not re.fullmatch(r"[a-z0-9_]+", alias):
            continue
        distance = _edit_distance_at_most_one(normalized, alias)
        if distance is not None and distance < best_distance:
            best_symbol = symbol
            best_distance = distance
    return best_symbol


def target_symbols_for_or_query(value: str) -> list[str]:
    normalized = value.strip()
    if not normalized or '"' in normalized or re.search(r"\bNOT\b", normalized, re.IGNORECASE):
        return []
    parts = [part.strip() for part in _OR_SEPARATOR_RE.split(normalized)]
    if len(parts) < 2 or any(not part for part in parts):
        return []
    symbols: list[str] = []
    for part in parts:
        if not _SYMBOL_TOKEN_RE.fullmatch(part):
            return []
        token = part.lstrip("$")
        symbols.append(canonical_symbol_for_query(token) or fuzzy_canonical_symbol_for_query(token) or token.upper())
    return list(dict.fromkeys(symbols))


def expanded_lexical_query(intent: SearchIntent, target_candidates: list[dict[str, object]]) -> str:
    lexical_query = (intent.lexical_query or intent.normalized_text or intent.text).strip()
    if not lexical_query:
        return ""
    if _EXPLICIT_WEBSEARCH_OPERATOR_RE.search(lexical_query):
        return lexical_query
    symbol = intent.symbol or canonical_symbol_for_query(lexical_query)
    if symbol and symbol in TOKEN_QUERY_ALIASES:
        return " OR ".join(TOKEN_QUERY_ALIASES[symbol])
    if len(lexical_query.split()) == 1:
        alias_symbol = canonical_symbol_for_query(lexical_query)
        if alias_symbol and alias_symbol in TOKEN_QUERY_ALIASES:
            return " OR ".join(TOKEN_QUERY_ALIASES[alias_symbol])
    if target_candidates:
        symbols = [str(candidate.get("symbol") or "").strip() for candidate in target_candidates]
        aliases = [alias for symbol in symbols for alias in TOKEN_QUERY_ALIASES.get(symbol.upper(), ())]
        if aliases:
            return " OR ".join(dict.fromkeys([lexical_query, *aliases]))
    return lexical_query


def _edit_distance_at_most_one(left: str, right: str) -> int | None:
    if left == right:
        return 0
    if abs(len(left) - len(right)) > 1:
        return None
    if len(left) == len(right):
        mismatches = sum(1 for left_char, right_char in zip(left, right, strict=True) if left_char != right_char)
        return mismatches if mismatches <= 1 else None
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    i = j = edits = 0
    while i < len(shorter) and j < len(longer):
        if shorter[i] == longer[j]:
            i += 1
            j += 1
            continue
        edits += 1
        if edits > 1:
            return None
        j += 1
    return 1
