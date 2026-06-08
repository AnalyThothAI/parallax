from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from parallax.domains.news_intel._constants import NEWS_MARKET_SCOPE_VERSION

NewsMarketScopeName = Literal[
    "crypto",
    "us_equity",
    "private_company",
    "macro_rates",
    "energy_geopolitics",
    "commodities",
    "fx",
    "ai_semiconductors",
    "broad_risk",
    "unknown",
]
NewsMarketScopeStatus = Literal["classified", "unknown"]


@dataclass(frozen=True, slots=True)
class NewsMarketScope:
    scope: tuple[NewsMarketScopeName, ...]
    primary: NewsMarketScopeName
    status: NewsMarketScopeStatus
    reason: str
    basis: dict[str, Any]
    version: str = NEWS_MARKET_SCOPE_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "scope": list(self.scope),
            "primary": self.primary,
            "status": self.status,
            "reason": self.reason,
            "basis": self.basis,
            "version": self.version,
        }


__all__ = ["NewsMarketScope", "NewsMarketScopeName", "NewsMarketScopeStatus"]
