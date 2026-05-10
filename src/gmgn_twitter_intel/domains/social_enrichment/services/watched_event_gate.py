from __future__ import annotations

import re
from typing import Any

HIGH_SIGNAL_TERMS = {
    "accumulated",
    "acquired",
    "airdrop",
    "binance",
    "bought",
    "burn",
    "buyback",
    "cex",
    "court",
    "delist",
    "deploy",
    "drain",
    "etf",
    "exploit",
    "funding",
    "hack",
    "launch",
    "lawsuit",
    "listing",
    "mainnet",
    "partnership",
    "raise",
    "sec",
    "sold",
    "treasury",
    "unlock",
    "upgrade",
    "whale",
}
TOPIC_TERMS = {
    "agent",
    "ai",
    "base",
    "bnb",
    "bitcoin",
    "builder",
    "ecosystem",
    "ethereum",
    "grok",
    "liquidity",
    "market",
    "pump",
    "ready",
    "rotation",
    "scaling",
    "solana",
    "throughput",
}
SERVICE_REPLY_TERMS = (
    "airdrop list",
    "already claimed",
    "api is down",
    "api returned",
    "checked your claim",
    "claim status",
    "eligibility",
    "merkle proof",
    "not eligible",
    "proof endpoint",
    "skill installed",
)


def watched_social_event_priority(
    *,
    event: Any,
    entities: list[Any],
    token_resolutions: list[Any],
) -> int | None:
    text = event_text(event)
    if not text:
        return None
    normalized = _normalize(text)
    if _is_low_information_service_reply(normalized):
        return None
    entity_types = {str(getattr(entity, "entity_type", "") or "") for entity in entities}
    has_resolved_target = any(_resolution_has_target(item) for item in token_resolutions)
    high_term_count = _term_count(normalized, HIGH_SIGNAL_TERMS)
    topic_term_count = _term_count(normalized, TOPIC_TERMS)
    if "ca" in entity_types:
        return 120
    if has_resolved_target:
        return 110 if high_term_count or topic_term_count else 100
    if high_term_count:
        return 95
    if "symbol" in entity_types and topic_term_count:
        return 90
    if topic_term_count >= 2 and len(normalized) >= 32:
        return 80
    return None


def should_enqueue_watched_social_event_text(text: str | None) -> bool:
    if not text:
        return False
    normalized = _normalize(text)
    if _is_low_information_service_reply(normalized):
        return False
    return _term_count(normalized, HIGH_SIGNAL_TERMS | TOPIC_TERMS) > 0 and len(normalized) >= 24


def event_text(event: Any) -> str:
    content = getattr(event, "content", None)
    parts = [str(getattr(content, "text", "") or "")]
    reference = getattr(event, "reference", None)
    reference_text = str(getattr(reference, "text", "") or "") if reference is not None else ""
    if reference_text:
        parts.append(reference_text)
    if not any(parts) and isinstance(event, dict):
        parts = [
            str(event.get("text_clean") or ""),
            str(event.get("search_text") or ""),
            str((event.get("content") or {}).get("text") or "") if isinstance(event.get("content"), dict) else "",
        ]
    return "\n".join(part for part in parts if part)


def _is_low_information_service_reply(normalized: str) -> bool:
    if not any(term in normalized for term in SERVICE_REPLY_TERMS):
        return False
    has_wallet_or_contract = bool(re.search(r"\b0x[a-f0-9]{8,}\b", normalized))
    return has_wallet_or_contract or "wallet" in normalized or "claim" in normalized


def _resolution_has_target(item: Any) -> bool:
    if isinstance(item, dict):
        return bool(item.get("target_id") or item.get("asset_id"))
    return bool(getattr(item, "target_id", None) or getattr(item, "asset_id", None))


def _term_count(text: str, terms: set[str]) -> int:
    return sum(1 for term in terms if re.search(rf"\b{re.escape(term)}\b", text))


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())
