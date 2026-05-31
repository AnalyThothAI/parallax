from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .token_evidence_builder import TokenEvidenceInput

CONSTRUCTION_POLICY = "token_intent_builder_v1"
MAX_LOCAL_ALIAS_DISTANCE = 180
MAX_SINGLE_PRECEDING_ALIAS_DISTANCE = 360


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
    alias_by_identity = _display_aliases_by_identity(identities=strong_identity, cashtags=cashtags)
    intents: list[TokenIntentInput] = []
    consumed_cashtags: set[str] = set()

    for identity in strong_identity:
        local_cashtags = alias_by_identity.get(identity.evidence_id, [])
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


def _display_aliases_by_identity(
    *,
    identities: list[TokenEvidenceInput],
    cashtags: list[TokenEvidenceInput],
) -> dict[str, list[TokenEvidenceInput]]:
    out: dict[str, list[TokenEvidenceInput]] = {}
    assigned_identities: set[str] = set()
    assigned_cashtags: set[str] = set()

    local_pairs = [
        (_span_distance(identity, cashtag), identity.evidence_id, cashtag.evidence_id, identity, cashtag)
        for identity in identities
        for cashtag in cashtags
        if _is_local_alias_candidate(identity=identity, cashtag=cashtag)
    ]
    for _distance, identity_id, cashtag_id, identity, cashtag in sorted(local_pairs, key=_alias_sort_key):
        if identity_id in assigned_identities or cashtag_id in assigned_cashtags:
            continue
        out[identity.evidence_id] = [cashtag]
        assigned_identities.add(identity_id)
        assigned_cashtags.add(cashtag_id)

    remaining_cashtags = [item for item in cashtags if item.evidence_id not in assigned_cashtags]
    preceding_pairs = [
        (_span_distance(identity, cashtag), identity.evidence_id, cashtag.evidence_id, identity, cashtag)
        for identity in identities
        if identity.evidence_id not in assigned_identities
        for cashtag in remaining_cashtags
        if _is_single_preceding_alias_candidate(identity=identity, cashtag=cashtag, cashtags=remaining_cashtags)
    ]
    for _distance, identity_id, cashtag_id, identity, cashtag in sorted(preceding_pairs, key=_alias_sort_key):
        if identity_id in assigned_identities or cashtag_id in assigned_cashtags:
            continue
        out[identity.evidence_id] = [cashtag]
        assigned_identities.add(identity_id)
        assigned_cashtags.add(cashtag_id)
    return out


def _is_local_alias_candidate(*, identity: TokenEvidenceInput, cashtag: TokenEvidenceInput) -> bool:
    return (
        identity.text_surface == cashtag.text_surface
        and identity.local_group_key == cashtag.local_group_key
        and _span_distance(identity, cashtag) <= MAX_LOCAL_ALIAS_DISTANCE
    )


def _is_single_preceding_alias_candidate(
    *,
    identity: TokenEvidenceInput,
    cashtag: TokenEvidenceInput,
    cashtags: list[TokenEvidenceInput],
) -> bool:
    if identity.text_surface != cashtag.text_surface:
        return False
    if cashtag.span_end > identity.span_start:
        return False
    if _span_distance(identity, cashtag) > MAX_SINGLE_PRECEDING_ALIAS_DISTANCE:
        return False
    preceding = [
        item
        for item in cashtags
        if item.text_surface == identity.text_surface
        and item.span_end <= identity.span_start
        and _span_distance(identity, item) <= MAX_SINGLE_PRECEDING_ALIAS_DISTANCE
    ]
    return len(preceding) == 1 and preceding[0].evidence_id == cashtag.evidence_id


def _alias_sort_key(
    item: tuple[int, str, str, TokenEvidenceInput, TokenEvidenceInput],
) -> tuple[int, str, str]:
    distance, identity_id, cashtag_id, _identity, _cashtag = item
    return int(distance), str(identity_id), str(cashtag_id)


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
