from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class CexTicker:
    inst_id: str
    inst_type: str
    last_price: float | None
    volume_24h: float | None
    open_interest: float | None
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DexTokenCandidate:
    chain_id: str
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
class DexTokenPrice:
    chain_id: str
    address: str
    observed_at_ms: int
    price_usd: float | None
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DexTokenPriceRequest:
    chain_id: str
    address: str


@dataclass(frozen=True, slots=True)
class DexMarketStreamTarget:
    chain_id: str
    address: str
    subject_type: str
    subject_id: str
    pricefeed_id: str | None = None


@dataclass(frozen=True, slots=True)
class DexMarketFactUpdate:
    chain_id: str
    address: str
    observed_at_ms: int
    price_usd: float | None = None
    market_cap_usd: float | None = None
    liquidity_usd: float | None = None
    volume_24h_usd: float | None = None
    open_interest_usd: float | None = None
    holders: int | None = None
    raw: dict[str, Any] | None = None


class CexMarketProvider(Protocol):
    def tickers(self, *, inst_type: str) -> list[CexTicker]: ...

    def ticker(self, *, inst_id: str) -> CexTicker | None: ...


class DexMarketProvider(Protocol):
    def search_tokens(self, *, query: str, chain_ids: tuple[str, ...]) -> list[DexTokenCandidate]: ...

    def token_prices(self, tokens: list[DexTokenPriceRequest]) -> list[DexTokenPrice]: ...


class DexMarketStreamProvider(Protocol):
    def stream_price_info(self, targets: list[DexMarketStreamTarget]) -> AsyncIterator[DexMarketFactUpdate]: ...


__all__ = [
    "CexMarketProvider",
    "CexTicker",
    "DexMarketFactUpdate",
    "DexMarketProvider",
    "DexMarketStreamProvider",
    "DexMarketStreamTarget",
    "DexTokenCandidate",
    "DexTokenPrice",
    "DexTokenPriceRequest",
]
