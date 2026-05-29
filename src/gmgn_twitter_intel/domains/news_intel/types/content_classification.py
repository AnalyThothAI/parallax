from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

NewsContentClass = Literal[
    "crypto_market",
    "macro_policy",
    "rates_fed",
    "regulation",
    "etf_fund_flow",
    "exchange_listing",
    "security_hack",
    "protocol_development",
    "analyst_rating",
    "ai_semiconductors",
    "energy_geopolitics",
    "consumer_macro",
    "market_structure",
    "low_signal",
]

NEWS_CONTENT_CLASSES: tuple[str, ...] = (
    "crypto_market",
    "macro_policy",
    "rates_fed",
    "regulation",
    "etf_fund_flow",
    "exchange_listing",
    "security_hack",
    "protocol_development",
    "analyst_rating",
    "ai_semiconductors",
    "energy_geopolitics",
    "consumer_macro",
    "market_structure",
    "low_signal",
)


@dataclass(frozen=True, slots=True)
class NewsContentClassification:
    content_class: NewsContentClass
    content_tags: list[str]
    classification_payload: dict[str, Any]
