from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class OkxCandle:
    time_ms: int
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    volume_quote: float | None
    volume_usd: float | None
    confirmed: bool | None
    raw: dict[str, Any] | list[Any]


@dataclass(frozen=True, slots=True)
class OkxDexTokenCandidate:
    chain_index: str
    chain: str | None
    address: str
    symbol: str
    name: str | None
    price_usd: float | None
    market_cap_usd: float | None
    liquidity_usd: float | None
    holders: int | None
    community_recognized: bool | None
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class OkxDexTokenPrice:
    chain_index: str
    address: str
    observed_at_ms: int
    price_usd: float | None
    raw: dict[str, Any]
