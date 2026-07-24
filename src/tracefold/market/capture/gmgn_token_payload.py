from __future__ import annotations

from typing import Any

from eth_utils.address import is_address, to_checksum_address

from tracefold.market.capture.twitter_event import TokenSnapshot

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
    raw_symbol = _string(raw.get("s"))
    if not address or not chain:
        return None

    normalized_address = _normalize_address(address, chain)
    symbol = _normalize_symbol(raw_symbol, address=normalized_address)
    icon_url = _string(raw.get("i"))
    trigger_type = _string(item.get("tt"))
    return TokenSnapshot(
        address=normalized_address,
        chain=chain,
        symbol=symbol,
        icon_url=icon_url,
        trigger_type=trigger_type,
        raw=_identity_payload(
            address=normalized_address,
            chain=chain,
            symbol=symbol,
            icon_url=icon_url,
            trigger_type=trigger_type,
        ),
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


def _normalize_symbol(symbol: str | None, *, address: str) -> str | None:
    if symbol is None:
        return None
    stripped = symbol.strip().lstrip("$")
    if not stripped:
        return None
    normalized = stripped.upper() if stripped.isascii() else stripped
    if normalized.lower() == address.lower():
        return None
    if _is_address_like_symbol(normalized):
        return None
    return normalized


def _is_address_like_symbol(symbol: str) -> bool:
    value = symbol.strip().upper()
    if value.startswith("0X") and len(value) >= 22:
        return all(char in "0123456789ABCDEF" for char in value[2:])
    if len(value) < 32:
        return False
    if value.endswith("PUMP"):
        value = value[:-4]
    return all(char.isdigit() or ("A" <= char <= "Z") for char in value)


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _identity_payload(
    *,
    address: str,
    chain: str,
    symbol: str | None,
    icon_url: str | None,
    trigger_type: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"a": address, "c": chain}
    if symbol:
        payload["s"] = symbol
    if icon_url:
        payload["i"] = icon_url
    if trigger_type:
        payload["tt"] = trigger_type
    return payload
