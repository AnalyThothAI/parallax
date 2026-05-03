from __future__ import annotations

from typing import Any

from eth_utils import is_address, to_checksum_address

from ..models import TokenSnapshot

EVM_CHAINS = {"eth", "ethereum", "base", "bsc", "bnb", "arbitrum", "optimism", "polygon", "avalanche"}
CHAIN_ALIASES = {
    "ethereum": "eth",
    "bnb": "bsc",
    "sol": "solana",
}


def parse_gmgn_token_payload(item: dict[str, Any]) -> TokenSnapshot | None:
    raw = item.get("t")
    if not isinstance(raw, dict):
        return None

    address = _string(raw.get("a"))
    chain = _normalize_chain(_string(raw.get("c")))
    symbol = _string(raw.get("s"))
    if not address or not chain or not symbol:
        return None

    return TokenSnapshot(
        address=_normalize_address(address, chain),
        chain=chain,
        symbol=symbol.strip().lstrip("$").upper() if symbol.isascii() else symbol.strip().lstrip("$"),
        market_cap=_float_or_none(raw.get("mc")),
        price=_float_or_none(raw.get("p")),
        previous_price=_float_or_none(raw.get("p1")),
        icon_url=_string(raw.get("i")),
        trigger_type=_string(item.get("tt")),
        raw=dict(raw),
    )


def _normalize_chain(value: str | None) -> str | None:
    if not value:
        return None
    chain = value.strip().lower()
    return CHAIN_ALIASES.get(chain, chain)


def _normalize_address(address: str, chain: str) -> str:
    text = address.strip()
    if chain in EVM_CHAINS and is_address(text):
        return to_checksum_address(text)
    return text


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
