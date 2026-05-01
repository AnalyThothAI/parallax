from __future__ import annotations

import re
from dataclasses import dataclass

from .token_extractor import TokenEntity
from .tweet_text import TextProjection

CRYPTO_SIGNAL_RE = re.compile(
    r"\b("
    r"airdrop|base|btc|bitcoin|bnb|bsc|ca|cex|chain|coin|coins|contract|defi|dex|eth|ethereum|"
    r"futures|gmgn|hyperliquid|launch|launchpad|leverage|liquidity|listing|lp|marketcap|mcap|"
    r"meme|memecoin|memes|onchain|perp|pump|pumpfun|rug|smart money|sol|solana|token|tokens|"
    r"trading|trx|wallet|whale"
    r")\b",
    re.IGNORECASE,
)
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_']*")


@dataclass(frozen=True, slots=True)
class ProcessingDecision:
    token_resolution_status: str
    embedding_status: str
    processing_priority: int
    quality_flags: list[str]


def decide_processing(
    projection: TextProjection,
    entities: list[TokenEntity],
    *,
    matched: bool = False,
) -> ProcessingDecision:
    flags: list[str] = []
    if not projection.text_clean:
        flags.append("no_text")
    if projection.urls:
        flags.append("has_url")
    if projection.cashtags:
        flags.append("has_cashtag")

    token_status = _token_status(entities)
    if token_status == "resolved":
        return ProcessingDecision(token_status, "pending", 100, flags)
    if token_status == "unresolved":
        return ProcessingDecision(token_status, "pending", 60, flags)
    if token_status == "invalid_candidate":
        return ProcessingDecision(token_status, "skipped", 10, [*flags, "invalid_candidate"])

    if _is_low_information(projection):
        return ProcessingDecision("no_token", "skipped", 0, [*flags, "low_information"])
    if matched:
        return ProcessingDecision("no_token", "pending", 40, [*flags, "tokenless", "matched_handle"])
    if _has_crypto_signal(projection):
        return ProcessingDecision("no_token", "pending", 20, [*flags, "tokenless"])
    return ProcessingDecision("no_token", "skipped", 0, [*flags, "tokenless", "off_topic"])


def _token_status(entities: list[TokenEntity]) -> str:
    statuses = {entity.token_resolution_status for entity in entities}
    if "resolved" in statuses:
        return "resolved"
    if "unresolved" in statuses:
        return "unresolved"
    if "invalid_candidate" in statuses:
        return "invalid_candidate"
    return "no_token"


def _has_crypto_signal(projection: TextProjection) -> bool:
    text = projection.embedding_text or projection.text_clean or ""
    return bool(CRYPTO_SIGNAL_RE.search(text))


def _is_low_information(projection: TextProjection) -> bool:
    text = projection.text_clean or ""
    if not text:
        return True
    return len(WORD_RE.findall(text)) < 4
