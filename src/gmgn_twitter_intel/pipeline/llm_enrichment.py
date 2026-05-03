from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

VALID_STANCES = {"bullish", "bearish", "neutral", "question", "informational"}
VALID_INTENTS = {
    "trade_signal",
    "technical_commentary",
    "macro_commentary",
    "meme",
    "social_reply",
    "informational",
}
MIN_CONFIDENCE = 0.55


@dataclass(frozen=True, slots=True)
class TokenCandidate:
    symbol: str | None
    project_name: str | None
    chain: str | None
    address: str | None
    evidence: str
    confidence: float


@dataclass(frozen=True, slots=True)
class NarrativeItem:
    label: str
    description: str
    evidence: str
    confidence: float


@dataclass(frozen=True, slots=True)
class EnrichmentResult:
    summary: str
    token_candidates: list[TokenCandidate] = field(default_factory=list)
    narratives: list[NarrativeItem] = field(default_factory=list)
    stance: str = "neutral"
    intent: str = "informational"
    confidence: float = 0.0
    raw_response: dict[str, Any] = field(default_factory=dict)


def build_enrichment_prompt(*, event: dict[str, Any], entities: list[dict[str, Any]]) -> list[dict[str, str]]:
    event_text = _event_text(event)
    entity_payload = [
        {
            "entity_type": item.get("entity_type"),
            "normalized_value": item.get("normalized_value"),
            "chain": item.get("chain"),
            "source": item.get("source"),
        }
        for item in entities
    ]
    user_payload = {
        "event_id": event.get("event_id"),
        "author_handle": _event_author_handle(event),
        "action": event.get("action"),
        "text": event_text,
        "deterministic_entities": entity_payload,
    }
    return [
        {
            "role": "system",
            "content": (
                "You extract trading-relevant intelligence from one X/Twitter event. "
                "Return only JSON. Every token candidate and narrative must include an evidence "
                "substring copied exactly from the provided text. Do not infer hidden tickers."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=False, sort_keys=True),
        },
    ]


def parse_enrichment_response(
    raw_response: str | dict[str, Any],
    *,
    event_text: str,
    min_confidence: float = MIN_CONFIDENCE,
) -> EnrichmentResult:
    payload = _json_payload(raw_response)
    text = _normalized_text(event_text)
    token_candidates = _dedupe_token_candidates([
        candidate
        for item in _list(payload.get("token_candidates"))
        if (candidate := _token_candidate(item, text, min_confidence)) is not None
    ])
    narratives = _dedupe_narratives([
        narrative
        for item in _list(payload.get("narratives"))
        if (narrative := _narrative(item, text, min_confidence)) is not None
    ])
    stance = str(payload.get("stance") or "neutral").strip().lower()
    intent = str(payload.get("intent") or "informational").strip().lower()
    return EnrichmentResult(
        summary=str(payload.get("summary") or "").strip(),
        token_candidates=token_candidates,
        narratives=narratives,
        stance=stance if stance in VALID_STANCES else "neutral",
        intent=intent if intent in VALID_INTENTS else "informational",
        confidence=_confidence(payload.get("confidence")),
        raw_response=payload,
    )


def _token_candidate(item: Any, event_text: str, min_confidence: float) -> TokenCandidate | None:
    if not isinstance(item, dict):
        return None
    evidence = str(item.get("evidence") or "").strip()
    confidence = _confidence(item.get("confidence"))
    if confidence < min_confidence or not _contains_evidence(event_text, evidence):
        return None
    symbol = str(item.get("symbol") or "").strip().lstrip("$").upper() or None
    project_name = str(item.get("project_name") or "").strip() or None
    chain = str(item.get("chain") or "").strip().lower() or None
    address = str(item.get("address") or "").strip() or None
    if not any([symbol, project_name, address]):
        return None
    return TokenCandidate(
        symbol=symbol,
        project_name=project_name,
        chain=chain,
        address=address,
        evidence=evidence,
        confidence=confidence,
    )


def _narrative(item: Any, event_text: str, min_confidence: float) -> NarrativeItem | None:
    if not isinstance(item, dict):
        return None
    evidence = str(item.get("evidence") or "").strip()
    confidence = _confidence(item.get("confidence"))
    label = _label(str(item.get("label") or ""))
    description = str(item.get("description") or "").strip()
    if confidence < min_confidence or not label or not description:
        return None
    if not _contains_evidence(event_text, evidence):
        return None
    return NarrativeItem(label=label, description=description, evidence=evidence, confidence=confidence)


def _json_payload(raw_response: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_response, dict):
        return raw_response
    text = raw_response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _contains_evidence(event_text: str, evidence: str) -> bool:
    if not evidence:
        return False
    return _normalized_text(evidence) in event_text


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _confidence(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(parsed, 1.0))


def _label(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    normalized = re.sub(r"_+", "_", normalized)
    return normalized[:80]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _event_text(event: dict[str, Any]) -> str:
    text = event.get("search_text") or event.get("text_clean")
    if isinstance(text, str):
        return text
    content = event.get("content")
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"]
    return ""


def _dedupe_token_candidates(candidates: list[TokenCandidate]) -> list[TokenCandidate]:
    deduped: list[TokenCandidate] = []
    seen: set[tuple[str | None, str | None, str | None, str | None, str]] = set()
    for candidate in candidates:
        key = (
            candidate.symbol,
            candidate.project_name,
            candidate.chain,
            candidate.address,
            _normalized_text(candidate.evidence),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _dedupe_narratives(narratives: list[NarrativeItem]) -> list[NarrativeItem]:
    deduped: list[NarrativeItem] = []
    seen: set[str] = set()
    for narrative in narratives:
        if narrative.label in seen:
            continue
        seen.add(narrative.label)
        deduped.append(narrative)
    return deduped


def _event_author_handle(event: dict[str, Any]) -> str | None:
    if event.get("author_handle"):
        return str(event["author_handle"]).lower()
    author = event.get("author")
    if isinstance(author, dict) and author.get("handle"):
        return str(author["handle"]).lower()
    return None
