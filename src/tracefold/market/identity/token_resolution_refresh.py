from __future__ import annotations

from typing import Any

from tracefold.market.identity.token_intent_resolver import (
    TokenIntentResolutionDecision,
    TokenIntentResolver,
)
from tracefold.market.radar.constants import WINDOW_MS

TOKEN_REPROCESS_WINDOW = "24h"


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
        )
        reprocessed += 1
        if decision.target_type and decision.target_id:
            resolved += 1
        else:
            discovery_lookup_keys.update(
                key for key in decision.lookup_keys if str(key).startswith(("symbol:", "address:"))
            )
        dirty_target = _dirty_target_for_decision(decision)
        if dirty_target is not None:
            dirty_targets.append(dirty_target)
    if discovery_lookup_keys:
        repos.discovery.enqueue_lookup_keys(
            sorted(discovery_lookup_keys),
            reason="resolution_refresh_unresolved",
            now_ms=now_ms,
        )
    if dirty_targets:
        repos.token_radar_dirty_targets.enqueue_targets(
            dirty_targets,
            reason="resolution_refresh",
            now_ms=now_ms,
        )
    return {
        "window": window,
        "lookup_keys": lookup_keys or [],
        "reprocessed_intents": reprocessed,
        "resolved_intents": resolved,
        "dirty_targets": len(dirty_targets),
        "since_ms": since_ms,
    }


def _dirty_target_for_decision(decision: TokenIntentResolutionDecision) -> dict[str, Any] | None:
    if not isinstance(decision, TokenIntentResolutionDecision):
        raise RuntimeError("token_resolution_refresh_decision_contract_required")
    target_type = decision.target_type
    target_id = decision.target_id
    if target_type in {"Asset", "CexToken"} and target_id:
        return {
            "target_type_key": str(target_type),
            "identity_id": str(target_id),
        }
    return None
