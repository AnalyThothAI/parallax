from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from parallax.domains.news_intel.types.text_normalization import title_fingerprint

_SOURCE_PREFIX_RE = re.compile(
    r"^([A-Z][A-Z0-9&.+/-]*(?:[ -][A-Z][A-Z0-9&.+/-]*){0,2})[:：]\s+",
    re.IGNORECASE,
)
_SOURCE_PREFIX_ALIASES = frozenset(
    {
        "AFP",
        "BLOOMBERG",
        "BUSINESS INSIDER",
        "CNBC",
        "COINDESK",
        "COIN DESK",
        "FINANCEFEEDS",
        "FINANCE FEEDS",
        "FORBES",
        "JP-BLOOMBERG",
        "TASS",
        "TASS RU",
        "ZEROHEDGE",
    }
)
_MIN_MATERIAL_TOKENS = 6


def material_title_fingerprint(title: object) -> str:
    text = str(title or "").strip()
    match = _SOURCE_PREFIX_RE.match(text)
    if match and match.group(1).strip().upper() in _SOURCE_PREFIX_ALIASES:
        text = text[match.end() :]
    return title_fingerprint(text)


def material_title_is_eligible(fingerprint: str) -> bool:
    return len(str(fingerprint or "").split()) >= _MIN_MATERIAL_TOKENS


def provider_symbol_set(provider_token_impacts: object) -> set[str]:
    symbols: set[str] = set()
    for item in _coerce_provider_token_impacts(provider_token_impacts):
        if not isinstance(item, Mapping):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        if symbol:
            symbols.add(symbol)
    return symbols


def symbol_sets_compatible(incoming: Iterable[str], existing: Iterable[str]) -> bool:
    incoming_set = {str(symbol).strip().upper() for symbol in incoming if str(symbol).strip()}
    existing_set = {str(symbol).strip().upper() for symbol in existing if str(symbol).strip()}
    return not incoming_set or not existing_set or bool(incoming_set & existing_set)


def _coerce_provider_token_impacts(provider_token_impacts: object) -> Sequence[Any]:
    if isinstance(provider_token_impacts, str):
        try:
            provider_token_impacts = json.loads(provider_token_impacts or "[]")
        except json.JSONDecodeError:
            return ()
    if isinstance(provider_token_impacts, Mapping):
        if "symbol" in provider_token_impacts:
            return (provider_token_impacts,)
        return tuple(provider_token_impacts.values())
    if isinstance(provider_token_impacts, Sequence):
        return provider_token_impacts
    return ()
