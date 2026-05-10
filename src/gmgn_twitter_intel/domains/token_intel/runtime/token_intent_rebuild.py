from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.evidence.interfaces import TextSurface, TokenSnapshot, extract_entities_from_surfaces
from gmgn_twitter_intel.domains.token_intel.queries.event_rebuild_query import EventRebuildQuery
from gmgn_twitter_intel.domains.token_intel.runtime.token_resolution_refresh import (
    DEFAULT_REPROCESS_WINDOW,
    rebuild_token_radar_windows,
)
from gmgn_twitter_intel.domains.token_intel.services.token_evidence_builder import build_token_evidence
from gmgn_twitter_intel.domains.token_intel.services.token_intent_builder import build_token_intents
from gmgn_twitter_intel.domains.token_intel.services.token_intent_resolver import TokenIntentResolver
from gmgn_twitter_intel.domains.token_intel.services.token_radar_projection import WINDOW_MS


def rebuild_recent_token_intents(
    *,
    repos: Any,
    now_ms: int,
    window: str = DEFAULT_REPROCESS_WINDOW,
    limit: int = 500,
    projection_limit: int = 100,
) -> dict[str, Any]:
    since_ms = int(now_ms) - WINDOW_MS.get(window, WINDOW_MS[DEFAULT_REPROCESS_WINDOW])
    rows = EventRebuildQuery(repos.conn).recent_events(since_ms=since_ms, limit=limit)

    rebuilt_events = 0
    intents_written = 0
    resolved_intents = 0
    for row in rows:
        result = rebuild_event_token_intents(repos=repos, event_row=row, commit=False)
        rebuilt_events += 1
        intents_written += result["intents_written"]
        resolved_intents += result["resolved_intents"]
    repos.conn.commit()
    projection = rebuild_token_radar_windows(repos=repos, now_ms=now_ms, limit=projection_limit)
    return {
        "window": window,
        "since_ms": since_ms,
        "events_selected": len(rows),
        "events_rebuilt": rebuilt_events,
        "intents_written": intents_written,
        "resolved_intents": resolved_intents,
        "projection": projection,
    }


def rebuild_event_token_intents(*, repos: Any, event_row: dict[str, Any], commit: bool = True) -> dict[str, int]:
    event_id = str(event_row["event_id"])
    received_at_ms = int(event_row["received_at_ms"])
    repos.token_intents.delete_by_event_id(event_id)
    repos.token_evidence.delete_by_event_id(event_id)

    evidence_inputs = build_token_evidence(
        event_id=event_id,
        entities=extract_entities_from_surfaces(_surfaces(event_row)),
        token_snapshot=_token_snapshot(event_row.get("event_json")),
        created_at_ms=received_at_ms,
    )
    repos.token_evidence.insert_many(evidence_inputs, commit=False)
    intent_inputs = build_token_intents(
        event_id=event_id,
        evidence=evidence_inputs,
        created_at_ms=received_at_ms,
    )
    repos.token_intents.insert_many(intent_inputs, commit=False)
    _upsert_chain_intent_registry(repos=repos, intents=intent_inputs, observed_at_ms=received_at_ms)

    resolver = TokenIntentResolver(registry=repos.registry, resolutions=repos.intent_resolutions)
    resolved = 0
    for intent in intent_inputs:
        decision = resolver.resolve(
            intent,
            evidence_inputs,
            decision_time_ms=received_at_ms,
            persist=True,
            commit=False,
        )
        repos.token_intent_lookup.replace_lookup_keys(
            intent_id=decision.intent_id,
            event_id=decision.event_id,
            keys=decision.lookup_keys,
            source_evidence_id=intent.primary_evidence_id,
            created_at_ms=received_at_ms,
            commit=False,
        )
        if decision.target_type and decision.target_id:
            resolved += 1
    if commit:
        repos.conn.commit()
    return {"intents_written": len(intent_inputs), "resolved_intents": resolved}


def _surfaces(event_row: dict[str, Any]) -> list[TextSurface]:
    surfaces: list[TextSurface] = []
    text = event_row.get("text")
    if text:
        surfaces.append(TextSurface("primary", str(text)))
    reference_text = _reference_text(event_row.get("reference_json"))
    if reference_text:
        surfaces.append(TextSurface("reference", reference_text))
    return surfaces


def _reference_text(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("text")
    return str(value) if value else None


def _token_snapshot(event_json: Any) -> TokenSnapshot | None:
    if not isinstance(event_json, dict):
        return None
    payload = event_json.get("token_snapshot")
    if not isinstance(payload, dict):
        return None
    address = str(payload.get("address") or "")
    chain = str(payload.get("chain") or "")
    if not address or not chain:
        return None
    return TokenSnapshot(
        address=address,
        chain=chain,
        symbol=payload.get("symbol"),
        market_cap=_float_or_none(payload.get("market_cap")),
        price=_float_or_none(payload.get("price")),
        previous_price=_float_or_none(payload.get("previous_price")),
        icon_url=payload.get("icon_url"),
        trigger_type=payload.get("trigger_type"),
        raw=payload.get("raw") if isinstance(payload.get("raw"), dict) else payload,
    )


def _upsert_chain_intent_registry(*, repos: Any, intents: list[Any], observed_at_ms: int) -> None:
    for intent in intents:
        if not intent.chain_hint or not intent.address_hint:
            continue
        repos.registry.upsert_chain_asset(
            chain_id=str(intent.chain_hint),
            address=str(intent.address_hint),
            symbol=intent.display_symbol,
            name=None,
            decimals=None,
            source="tweet_ca",
            observed_at_ms=observed_at_ms,
            commit=False,
        )


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
