from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from gmgn_twitter_intel.domains.token_intel.services.query_parser import SearchIntent

TOKEN_QUERY_ALIASES: Mapping[str, Sequence[str]] = {
    "BTC": ("btc", "bitcoin", "bitcoins", "比特币", "xbt"),
    "ETH": ("eth", "ethereum", "ether", "以太坊"),
    "SOL": ("sol", "solana"),
    "DOGE": ("doge", "dogecoin", "狗狗币"),
}

_EXPLICIT_WEBSEARCH_OPERATOR_RE = re.compile(r"\b(?:OR|NOT)\b|\"", re.IGNORECASE)
_ALIAS_TO_SYMBOL = {alias.lower(): symbol for symbol, aliases in TOKEN_QUERY_ALIASES.items() for alias in aliases}


def canonical_symbol_for_query(value: str) -> str | None:
    return _ALIAS_TO_SYMBOL.get(value.strip().lower())


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
