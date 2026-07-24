from __future__ import annotations

import re
from collections.abc import Iterable

from tracefold.news.ingest.content_classification import NewsContentClassification

NEWS_CONTENT_CLASSIFICATION_POLICY_VERSION = "news_content_classification_v1"

_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("security_hack", "text:security_hack", re.compile(r"\b(?:hack|hacked|exploit|exploited|drain|drained)\b", re.I)),
    ("regulation", "text:regulation", re.compile(r"\b(?:sec|cftc|regulator|lawsuit|settlement|court)\b", re.I)),
    (
        "etf_fund_flow",
        "text:etf_fund_flow",
        re.compile(r"\b(?:ETF|exchange-traded fund|inflow|outflow|net flow)\b", re.I),
    ),
    ("exchange_listing", "text:exchange_listing", re.compile(r"\b(?:lists?|listing|delists?|trading starts)\b", re.I)),
    (
        "analyst_rating",
        "text:analyst_rating",
        re.compile(r"\b(?:price target|upgrade|downgrade|initiates? coverage|rating)\b", re.I),
    ),
    (
        "rates_fed",
        "text:rates_fed",
        re.compile(r"\b(?:fed|fomc|rate cut|rate hike|treasury yields?|dot plot)\b", re.I),
    ),
    (
        "macro_policy",
        "text:macro_policy",
        re.compile(r"\b(?:cpi|pce|inflation|payrolls?|jobs report|gdp|central bank)\b", re.I),
    ),
    (
        "protocol_development",
        "text:protocol_development",
        re.compile(r"\b(?:mainnet|upgrade|hard fork|proposal|governance|developer)\b", re.I),
    ),
    (
        "ai_semiconductors",
        "text:ai_semiconductors",
        re.compile(r"\b(?:nvidia|semiconductor|chip|gpu|ai server|accelerator)\b", re.I),
    ),
    (
        "energy_geopolitics",
        "text:energy_geopolitics",
        re.compile(r"\b(?:oil|opec|crude|sanctions|geopolitical|middle east)\b", re.I),
    ),
    (
        "consumer_macro",
        "text:consumer_macro",
        re.compile(r"\b(?:consumer confidence|retail sales|consumer spending|household income)\b", re.I),
    ),
    (
        "market_structure",
        "text:market_structure",
        re.compile(r"\b(?:liquidation|open interest|funding rate|volatility|options?|market maker)\b", re.I),
    ),
    (
        "crypto_market",
        "text:crypto_market",
        re.compile(
            r"\b(?:bitcoin|btc|ethereum|eth|crypto|token|altcoin|solana|zec|zcash|orchard|cex|dex|binance)\b",
            re.I,
        ),
    ),
)

_FACT_EVENT_CLASS_BY_TYPE = {
    "security_incident": "security_hack",
    "security_hack": "security_hack",
    "regulatory": "regulation",
    "regulatory_action": "regulation",
    "etf_fund_flow": "etf_fund_flow",
    "exchange_listing": "exchange_listing",
    "exchange_delisting": "exchange_listing",
    "protocol_upgrade": "protocol_development",
    "governance_tokenomics": "protocol_development",
}


def classify_news_item_content(
    *,
    headline: str,
    summary: str,
    source_domain: str,
    fact_event_types: Iterable[str],
) -> NewsContentClassification:
    text = " ".join(part.strip() for part in (headline, summary) if part and part.strip())
    tags: list[str] = []

    event_types = [str(event_type).strip() for event_type in fact_event_types if str(event_type).strip()]
    event_class, event_rule = _first_fact_event_match(event_types)
    if event_class is not None and event_rule is not None:
        tags.extend(_tags_for_event_types(event_types))
        tags.extend(_context_tags(text=text, summary=summary, source_domain=source_domain))
        return _classification(event_class, tags, [event_rule])

    matched_class, matched_rule = _first_text_match(text)
    if matched_class is not None and matched_rule is not None:
        tags.append(matched_class)
        tags.extend(_context_tags(text=text, summary=summary, source_domain=source_domain))
        return _classification(matched_class, tags, [matched_rule])

    tags.extend(_context_tags(text=text, summary=summary, source_domain=source_domain))
    return _classification("low_signal", tags, ["default:low_signal"])


def _first_fact_event_match(event_types: list[str]) -> tuple[str | None, str | None]:
    normalized = {event_type.lower() for event_type in event_types}
    for event_type, content_class in _FACT_EVENT_CLASS_BY_TYPE.items():
        if event_type in normalized:
            return content_class, f"fact_event_type:{event_type}"
    return None, None


def _first_text_match(text: str) -> tuple[str | None, str | None]:
    for content_class, rule_name, pattern in _RULES:
        if pattern.search(text):
            return content_class, rule_name
    return None, None


def _tags_for_event_types(event_types: list[str]) -> list[str]:
    tags: list[str] = []
    for event_type in event_types:
        normalized = event_type.lower()
        if normalized in _FACT_EVENT_CLASS_BY_TYPE:
            tags.append(normalized)
    return tags


def _context_tags(*, text: str, summary: str, source_domain: str) -> list[str]:
    tags: list[str] = []
    if re.search(r"\btokeni[sz]ed stocks?\b", text, re.I):
        tags.append("tokenized_stocks")
    if not summary.strip():
        tags.append("low_context")
    if source_domain.strip().lower() in {"finance.yahoo.com", "finance.yahoo.co.jp"}:
        tags.append("yahoo_finance")
    return tags


def _classification(
    content_class: str,
    tags: list[str],
    matched_rules: list[str],
) -> NewsContentClassification:
    return NewsContentClassification(
        content_class=content_class,  # type: ignore[arg-type]
        content_tags=_dedupe(tags),
        classification_payload={
            "policy_version": NEWS_CONTENT_CLASSIFICATION_POLICY_VERSION,
            "matched_rules": matched_rules,
        },
    )


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
