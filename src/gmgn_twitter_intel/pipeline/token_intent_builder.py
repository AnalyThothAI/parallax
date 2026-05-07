from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .token_evidence_builder import TokenEvidenceInput

CONSTRUCTION_POLICY = "token_intent_builder_v1"


@dataclass(frozen=True, slots=True)
class TokenIntentEvidenceLink:
    evidence_id: str
    role: str


@dataclass(frozen=True, slots=True)
class TokenIntentInput:
    intent_id: str
    event_id: str
    intent_key: str
    construction_policy: str
    primary_evidence_id: str | None
    display_symbol: str | None
    display_name: str | None
    chain_hint: str | None
    address_hint: str | None
    intent_status: str
    intent_confidence: float
    created_at_ms: int
    updated_at_ms: int
    evidence_links: list[TokenIntentEvidenceLink] = field(default_factory=list)


def build_token_intents(
    *,
    event_id: str,
    evidence: list[TokenEvidenceInput],
    created_at_ms: int,
) -> list[TokenIntentInput]:
    strong_identity = [item for item in evidence if item.address_hint]
    cashtags = [item for item in evidence if item.evidence_type == "cashtag" and item.normalized_symbol]
    intents: list[TokenIntentInput] = []
    consumed_cashtags: set[str] = set()

    for identity in strong_identity:
        local_cashtags = _display_cashtags_for_identity(identity, cashtags=cashtags, identities=strong_identity)
        display = _single_display_symbol(local_cashtags)
        if display:
            consumed_cashtags.update(item.evidence_id for item in local_cashtags if item.normalized_symbol == display)
        intents.append(
            _intent(
                event_id=event_id,
                primary=identity,
                display_symbol=display,
                links=[
                    TokenIntentEvidenceLink(identity.evidence_id, "primary_identity"),
                    *[
                        TokenIntentEvidenceLink(item.evidence_id, "display_alias")
                        for item in local_cashtags
                        if item.normalized_symbol == display
                    ],
                ],
                created_at_ms=created_at_ms,
            )
        )

    for cashtag in cashtags:
        if cashtag.evidence_id in consumed_cashtags:
            continue
        intents.append(
            _intent(
                event_id=event_id,
                primary=cashtag,
                display_symbol=cashtag.normalized_symbol,
                links=[TokenIntentEvidenceLink(cashtag.evidence_id, "primary_identity")],
                created_at_ms=created_at_ms,
            )
        )

    return _unique_intents(intents)


def _intent(
    *,
    event_id: str,
    primary: TokenEvidenceInput,
    display_symbol: str | None,
    links: list[TokenIntentEvidenceLink],
    created_at_ms: int,
) -> TokenIntentInput:
    intent_key = _intent_key(event_id, primary)
    return TokenIntentInput(
        intent_id=_stable_id("token-intent", event_id, intent_key),
        event_id=event_id,
        intent_key=intent_key,
        construction_policy=CONSTRUCTION_POLICY,
        primary_evidence_id=primary.evidence_id,
        display_symbol=display_symbol or primary.normalized_symbol,
        display_name=None,
        chain_hint=primary.chain_hint,
        address_hint=primary.address_hint,
        intent_status="pending",
        intent_confidence=max(0.0, min(1.0, float(primary.confidence))),
        created_at_ms=created_at_ms,
        updated_at_ms=created_at_ms,
        evidence_links=links,
    )


def _intent_key(event_id: str, primary: TokenEvidenceInput) -> str:
    if primary.address_hint:
        return f"ca:{(primary.chain_hint or 'unknown')}:{primary.address_hint.lower()}"
    if primary.normalized_symbol:
        return f"symbol:{primary.normalized_symbol}"
    return _stable_id("intent-key", event_id, primary.evidence_id)


def _single_display_symbol(items: list[TokenEvidenceInput]) -> str | None:
    symbols = {str(item.normalized_symbol) for item in items if item.normalized_symbol}
    return next(iter(symbols)) if len(symbols) == 1 else None


def _display_cashtags_for_identity(
    identity: TokenEvidenceInput,
    *,
    cashtags: list[TokenEvidenceInput],
    identities: list[TokenEvidenceInput],
) -> list[TokenEvidenceInput]:
    local = [
        item
        for item in cashtags
        if item.local_group_key == identity.local_group_key and item.text_surface == identity.text_surface
    ]
    if local:
        return local

    same_surface_cashtags = [item for item in cashtags if item.text_surface == identity.text_surface]
    same_surface_identities = [item for item in identities if item.text_surface == identity.text_surface]
    if len(same_surface_cashtags) != 1 or len(same_surface_identities) != 1:
        if len(cashtags) == 1 and len(identities) == 1:
            return [cashtags[0]]
        return []

    cashtag = same_surface_cashtags[0]
    return [cashtag] if _span_distance(identity, cashtag) <= 180 else []


def _span_distance(left: TokenEvidenceInput, right: TokenEvidenceInput) -> int:
    if left.span_end < right.span_start:
        return int(right.span_start - left.span_end)
    if right.span_end < left.span_start:
        return int(left.span_start - right.span_end)
    return 0


def _unique_intents(items: list[TokenIntentInput]) -> list[TokenIntentInput]:
    out: list[TokenIntentInput] = []
    seen: set[str] = set()
    for item in items:
        if item.intent_id in seen:
            continue
        seen.add(item.intent_id)
        out.append(item)
    return out


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
