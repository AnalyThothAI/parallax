from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class CexOiTicker24h:
    symbol: str
    quote_volume_24h: float | None
    price_change_pct_24h: float | None
    last_price: float | None = None


@dataclass(frozen=True, slots=True)
class CexFundingPremium:
    symbol: str
    mark_price: float | None
    last_funding_rate: float | None


@dataclass(frozen=True, slots=True)
class CexOpenInterestPoint:
    symbol: str
    open_interest_value: float | None
    observed_at_ms: int | None


class CexOiMarketProvider(Protocol):
    def list_24h_tickers(self, symbol: str | None = None) -> Sequence[CexOiTicker24h]: ...

    def list_funding_premium(self, symbol: str | None = None) -> Sequence[CexFundingPremium]: ...

    def list_open_interest_history(
        self,
        symbol: str,
        period: str,
        limit: int,
    ) -> Sequence[CexOpenInterestPoint]: ...

    def close(self) -> None: ...


class CoinglassDerivativesProvider(Protocol):
    def fetch_oi_history(self, *, symbol: str, time_type: str, lookback: str) -> dict[str, Any]: ...

    def fetch_cvd_history(self, *, symbol: str, time_type: str, lookback: str) -> dict[str, Any]: ...

    def fetch_long_short_ratio_history(self, *, symbol: str, time_type: str, lookback: str) -> dict[str, Any]: ...

    def fetch_top_trader_position_history(self, *, symbol: str, time_type: str, lookback: str) -> dict[str, Any]: ...

    def fetch_liquidation_levels(self, *, symbol: str, range: str) -> dict[str, Any]: ...


__all__ = [
    "CexFundingPremium",
    "CexOiMarketProvider",
    "CexOiTicker24h",
    "CexOpenInterestPoint",
    "CoinglassDerivativesProvider",
]
