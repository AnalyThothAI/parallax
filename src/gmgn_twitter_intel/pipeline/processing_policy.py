from __future__ import annotations

from dataclasses import dataclass

from .token_extractor import TokenEntity
from .tweet_text import TextProjection


@dataclass(frozen=True, slots=True)
class ProcessingDecision:
    token_resolution_status: str
    embedding_status: str
    processing_priority: int
    quality_flags: list[str]


def decide_processing(projection: TextProjection, entities: list[TokenEntity]) -> ProcessingDecision:
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
    if projection.text_clean and len(projection.text_clean.split()) >= 4:
        return ProcessingDecision("no_token", "pending", 20, [*flags, "tokenless"])
    return ProcessingDecision("no_token", "skipped", 0, flags)


def _token_status(entities: list[TokenEntity]) -> str:
    statuses = {entity.token_resolution_status for entity in entities}
    if "resolved" in statuses:
        return "resolved"
    if "unresolved" in statuses:
        return "unresolved"
    if "invalid_candidate" in statuses:
        return "invalid_candidate"
    return "no_token"
