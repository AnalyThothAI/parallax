from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

EVENT_TYPES = {
    "meme_phrase_seed",
    "listing_hint",
    "product_mention",
    "ecosystem_boost",
    "regulation_comment",
    "exchange_risk",
    "founder_reply",
    "market_structure_comment",
    "rumor",
}
ATTENTION_MECHANISMS = {
    "meme_phrase",
    "direct_token_mention",
    "product_or_feature",
    "reply_target",
    "exchange_or_listing",
    "risk_focus",
    "cultural_object",
}
DIRECTION_HINTS = {"attention_positive", "attention_negative", "neutral", "risk_negative"}
ANCHOR_ROLES = {"subject", "meme_phrase", "product", "asset", "person", "venue"}
SEMANTIC_RISKS = {
    "public_stream_coverage",
    "unresolved_symbol",
    "low_information",
    "ambiguous_mapping",
    "repeat_seed",
    "rumor",
}
SOURCE_ACTIONS = {"posted", "replied", "quoted", "retweeted", "profile_changed"}


@dataclass(frozen=True, slots=True)
class AnchorTerm:
    term: str
    role: str
    evidence: str


@dataclass(frozen=True, slots=True)
class SocialTokenCandidate:
    symbol: str | None
    project_name: str | None
    chain: str | None
    address: str | None
    evidence: str
    confidence: float


@dataclass(frozen=True, slots=True)
class SocialEventExtraction:
    is_signal_event: bool
    event_type: str
    source_action: str
    subject: str
    direction_hint: str
    attention_mechanism: str
    impact_hint: float
    semantic_novelty_hint: float
    confidence: float
    anchor_terms: list[AnchorTerm] = field(default_factory=list)
    token_candidates: list[SocialTokenCandidate] = field(default_factory=list)
    semantic_risks: list[str] = field(default_factory=list)
    summary_zh: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)


def build_social_event_prompt(*, event: dict[str, Any], entities: list[dict[str, Any]]) -> list[dict[str, str]]:
    event_text = _event_text(event)
    payload = {
        "event_id": event.get("event_id"),
        "author_handle": event.get("author_handle") or (event.get("author") or {}).get("handle"),
        "action": event.get("action"),
        "text": event_text,
        "deterministic_entities": [
            {
                "entity_type": item.get("entity_type"),
                "normalized_value": item.get("normalized_value"),
                "chain": item.get("chain"),
                "source": item.get("source"),
            }
            for item in entities
        ],
    }
    return [
        {
            "role": "system",
            "content": (
                "Extract one evidence-bound social-event-v2 attention event from one X/Twitter event. "
                "Return only the strict JSON object requested by the schema. The LLM must not decide trades. "
                "Every anchor term and token candidate evidence must be an exact substring of the supplied text."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]


def social_event_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "social_event_v2",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "is_signal_event",
                    "event_type",
                    "source_action",
                    "subject",
                    "direction_hint",
                    "attention_mechanism",
                    "impact_hint",
                    "semantic_novelty_hint",
                    "confidence",
                    "anchor_terms",
                    "token_candidates",
                    "semantic_risks",
                    "summary_zh",
                ],
                "properties": {
                    "is_signal_event": {"type": "boolean"},
                    "event_type": {"type": "string", "enum": sorted(EVENT_TYPES)},
                    "source_action": {"type": "string", "enum": sorted(SOURCE_ACTIONS)},
                    "subject": {"type": "string"},
                    "direction_hint": {"type": "string", "enum": sorted(DIRECTION_HINTS)},
                    "attention_mechanism": {"type": "string", "enum": sorted(ATTENTION_MECHANISMS)},
                    "impact_hint": {"type": "number"},
                    "semantic_novelty_hint": {"type": "number"},
                    "confidence": {"type": "number"},
                    "anchor_terms": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["term", "role", "evidence"],
                            "properties": {
                                "term": {"type": "string"},
                                "role": {"type": "string", "enum": sorted(ANCHOR_ROLES)},
                                "evidence": {"type": "string"},
                            },
                        },
                    },
                    "token_candidates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["symbol", "project_name", "chain", "address", "evidence", "confidence"],
                            "properties": {
                                "symbol": {"type": ["string", "null"]},
                                "project_name": {"type": ["string", "null"]},
                                "chain": {"type": ["string", "null"]},
                                "address": {"type": ["string", "null"]},
                                "evidence": {"type": "string"},
                                "confidence": {"type": "number"},
                            },
                        },
                    },
                    "semantic_risks": {"type": "array", "items": {"type": "string", "enum": sorted(SEMANTIC_RISKS)}},
                    "summary_zh": {"type": "string"},
                },
            },
        },
    }


def parse_social_event_response(
    raw_response: str | dict[str, Any],
    *,
    event_text: str,
    min_confidence: float = 0.55,
) -> SocialEventExtraction:
    payload = _json_payload(raw_response)
    normalized_text = _normalized_text(event_text)
    event_type = _enum(payload.get("event_type"), EVENT_TYPES, "rumor")
    source_action = _enum(payload.get("source_action"), SOURCE_ACTIONS, "posted")
    direction_hint = _enum(payload.get("direction_hint"), DIRECTION_HINTS, "neutral")
    attention_mechanism = _enum(payload.get("attention_mechanism"), ATTENTION_MECHANISMS, "meme_phrase")
    confidence = _clamp(payload.get("confidence"))
    anchors = _dedupe_anchors(
        anchor
        for item in _list(payload.get("anchor_terms"))
        if (anchor := _anchor_term(item, normalized_text)) is not None
    )
    candidates = _dedupe_candidates(
        candidate
        for item in _list(payload.get("token_candidates"))
        if (candidate := _token_candidate(item, normalized_text, min_confidence)) is not None
    )
    is_signal_event = bool(payload.get("is_signal_event")) and confidence >= min_confidence and bool(anchors)
    return SocialEventExtraction(
        is_signal_event=is_signal_event,
        event_type=event_type,
        source_action=source_action,
        subject=str(payload.get("subject") or "").strip(),
        direction_hint=direction_hint,
        attention_mechanism=attention_mechanism,
        impact_hint=_clamp(payload.get("impact_hint")),
        semantic_novelty_hint=_clamp(payload.get("semantic_novelty_hint")),
        confidence=confidence,
        anchor_terms=anchors,
        token_candidates=candidates,
        semantic_risks=[risk for risk in _list(payload.get("semantic_risks")) if risk in SEMANTIC_RISKS],
        summary_zh=str(payload.get("summary_zh") or "").strip(),
        raw_response=payload,
    )


def _anchor_term(item: Any, event_text: str) -> AnchorTerm | None:
    if not isinstance(item, dict):
        return None
    role = _enum(item.get("role"), ANCHOR_ROLES, "")
    term = str(item.get("term") or "").strip()
    evidence = str(item.get("evidence") or "").strip()
    if not role or not term or not _contains_evidence(event_text, evidence):
        return None
    return AnchorTerm(term=term[:120], role=role, evidence=evidence)


def _token_candidate(item: Any, event_text: str, min_confidence: float) -> SocialTokenCandidate | None:
    if not isinstance(item, dict):
        return None
    evidence = str(item.get("evidence") or "").strip()
    confidence = _clamp(item.get("confidence"))
    if confidence < min_confidence or not _contains_evidence(event_text, evidence):
        return None
    symbol = str(item.get("symbol") or "").strip().lstrip("$").upper() or None
    project_name = str(item.get("project_name") or "").strip() or None
    chain = str(item.get("chain") or "").strip().lower() or None
    address = str(item.get("address") or "").strip() or None
    if symbol and not _contains_evidence(event_text, symbol):
        symbol = None
    if project_name and not _contains_evidence(event_text, project_name):
        project_name = None
    if address and not _contains_evidence(event_text, address):
        address = None
    if not any([symbol, project_name, address]):
        return None
    return SocialTokenCandidate(
        symbol=symbol,
        project_name=project_name,
        chain=chain,
        address=address,
        evidence=evidence,
        confidence=confidence,
    )


def _dedupe_anchors(items) -> list[AnchorTerm]:
    seen: set[tuple[str, str]] = set()
    deduped: list[AnchorTerm] = []
    for item in items:
        key = (_normalized_text(item.term), item.role)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:8]


def _dedupe_candidates(items) -> list[SocialTokenCandidate]:
    seen: set[str] = set()
    deduped: list[SocialTokenCandidate] = []
    for item in items:
        key = (
            item.address.lower()
            if item.address
            else f"{item.symbol}:{item.project_name}:{_normalized_text(item.evidence)}"
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:8]


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


def _event_text(event: dict[str, Any]) -> str:
    text = event.get("search_text") or event.get("text_clean")
    if isinstance(text, str):
        return text
    content = event.get("content")
    return content.get("text", "") if isinstance(content, dict) else ""


def _contains_evidence(event_text: str, evidence: str) -> bool:
    return bool(evidence) and _normalized_text(evidence) in event_text


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _enum(value: Any, allowed: set[str], default: str) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in allowed else default


def _clamp(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(parsed, 1.0))


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
