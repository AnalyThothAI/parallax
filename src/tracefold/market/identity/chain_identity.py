from __future__ import annotations

from typing import Any

_CHAIN_ALIASES = {
    "eth": "eip155:1",
    "ethereum": "eip155:1",
    "base": "eip155:8453",
    "bsc": "eip155:56",
    "bnb": "eip155:56",
    "bnb_chain": "eip155:56",
    "sol": "solana",
    "solana": "solana",
    "toncoin": "ton",
    "the open network": "ton",
}


def canonical_chain_id(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return _CHAIN_ALIASES.get(normalized, normalized)


def canonical_chain_address(chain_id: Any, address: Any) -> str:
    chain = canonical_chain_id(chain_id)
    value = str(address or "").strip()
    return value.lower() if chain.startswith("eip155:") or value.startswith(("0x", "0X")) else value


def chain_address_key(chain_id: Any, address: Any) -> tuple[str, str]:
    chain = canonical_chain_id(chain_id)
    return (chain, canonical_chain_address(chain, address))


__all__ = ["canonical_chain_address", "canonical_chain_id", "chain_address_key"]
