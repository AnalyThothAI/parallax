from __future__ import annotations

from typing import Any

from parallax.domains.token_intel._constants import WINDOW_MS
from parallax.domains.token_intel.services.token_intent_resolver import (
    TokenIntentResolutionDecision,
    TokenIntentResolver,
)

TOKEN_REPROCESS_WINDOW = "24h"


def refresh_recent_token_state(
    *,
    repos: Any,
    lookup_keys: list[str],
    now_ms: int,
    window: str,
    reprocess_limit: int,
) -> dict[str, Any]:
    keys = sorted({key for key in lookup_keys if key})
    result = {
        "lookup_keys": keys,
        "reprocess": None,
        "reprocessed_intents": 0,
        "projection": deferred_token_radar_projection(),
    }
    if not keys:
        return result
    reprocess = reprocess_recent_token_intents(
        repos=repos,
        lookup_keys=keys,
        now_ms=now_ms,
        window=window,
        limit=reprocess_limit,
    )
    result["reprocess"] = reprocess
    result["reprocessed_intents"] = reprocess["reprocessed_intents"]
    return result


def reprocess_recent_token_intents(
    *,
    repos: Any,
    now_ms: int,
    window: str,
    limit: int,
    lookup_keys: list[str] | None = None,
) -> dict[str, Any]:
    with repos.transaction():
        return _reprocess_recent_token_intents(
            repos=repos,
            now_ms=now_ms,
            window=window,
            limit=limit,
            lookup_keys=lookup_keys,
        )


def _reprocess_recent_token_intents(
    *,
    repos: Any,
    now_ms: int,
    window: str,
    limit: int,
    lookup_keys: list[str] | None,
) -> dict[str, Any]:
    repos.require_transaction(operation="token_resolution_refresh")
    since_ms = int(now_ms) - WINDOW_MS[window]
    if lookup_keys:
        intents = repos.token_intent_lookup.recent_intents_for_lookup_keys(
            lookup_keys,
            since_ms=since_ms,
            limit=limit,
        )
    else:
        intents = repos.token_intents.recent_unresolved(since_ms=since_ms, limit=limit)
    resolver = TokenIntentResolver(
        registry=repos.registry,
        resolutions=repos.intent_resolutions,
    )
    reprocessed = 0
    resolved = 0
    dirty_targets: list[dict[str, Any]] = []
    discovery_lookup_keys: set[str] = set()
    evidence_by_intent = repos.token_evidence.evidence_for_intents([str(intent["intent_id"]) for intent in intents])
    for intent in intents:
        evidence = evidence_by_intent.get(str(intent["intent_id"]), [])
        decision = resolver.resolve(
            intent,
            evidence,
            decision_time_ms=now_ms,
            persist=True,
        )
        repos.token_intent_lookup.replace_lookup_keys(
            intent_id=decision.intent_id,
            event_id=decision.event_id,
            keys=decision.lookup_keys,
            source_evidence_id=intent.get("primary_evidence_id"),
            created_at_ms=now_ms,
            commit=False,
        )
        reprocessed += 1
        if decision.target_type and decision.target_id:
            resolved += 1
        else:
            discovery_lookup_keys.update(
                key for key in decision.lookup_keys if str(key).startswith(("symbol:", "address:"))
            )
        dirty_event = _source_dirty_event_for_decision(decision)
        if dirty_event is not None:
            dirty_targets.append(dirty_event)
    if discovery_lookup_keys:
        repos.discovery.enqueue_lookup_keys(
            sorted(discovery_lookup_keys),
            reason="resolution_refresh_unresolved",
            now_ms=now_ms,
            commit=False,
        )
    if dirty_targets:
        repos.token_radar_source_dirty_events.enqueue_events(
            dirty_targets,
            reason="resolution_refresh",
            now_ms=now_ms,
            commit=False,
        )
    return {
        "window": window,
        "lookup_keys": lookup_keys or [],
        "reprocessed_intents": reprocessed,
        "resolved_intents": resolved,
        "dirty_targets": len(dirty_targets),
        "since_ms": since_ms,
    }


def deferred_token_radar_projection() -> dict[str, Any]:
    return {
        "status": "deferred_to_worker",
        "rows_written": 0,
        "source_rows": 0,
        "windows": {},
    }


def _source_dirty_event_for_decision(decision: TokenIntentResolutionDecision) -> dict[str, Any] | None:
    if not isinstance(decision, TokenIntentResolutionDecision):
        raise RuntimeError("token_resolution_refresh_decision_contract_required")
    target_type = decision.target_type
    target_id = decision.target_id
    event_id = decision.event_id
    if event_id and target_type in {"Asset", "CexToken"} and target_id:
        return {
            "source_event_id": event_id,
            "target_type_key": str(target_type),
            "identity_id": str(target_id),
        }
    return None
