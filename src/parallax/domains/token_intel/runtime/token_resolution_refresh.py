from __future__ import annotations

from typing import Any

from parallax.domains.token_intel._constants import WINDOW_MS
from parallax.domains.token_intel.services.token_intent_resolver import TokenIntentResolver

DEFAULT_REPROCESS_LIMIT = 500
DEFAULT_REPROCESS_WINDOW = "24h"


def refresh_recent_token_state(
    *,
    repos: Any,
    lookup_keys: list[str],
    now_ms: int,
    window: str = DEFAULT_REPROCESS_WINDOW,
    reprocess_limit: int = DEFAULT_REPROCESS_LIMIT,
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
    window: str = DEFAULT_REPROCESS_WINDOW,
    limit: int = DEFAULT_REPROCESS_LIMIT,
    lookup_keys: list[str] | None = None,
) -> dict[str, Any]:
    since_ms = int(now_ms) - WINDOW_MS.get(window, WINDOW_MS[DEFAULT_REPROCESS_WINDOW])
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
    for intent in intents:
        evidence = repos.token_evidence.evidence_for_intent(str(intent["intent_id"]))
        decision = resolver.resolve(
            intent,
            evidence,
            decision_time_ms=now_ms,
            persist=True,
            commit=False,
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
    dirty_repo = getattr(repos, "token_radar_source_dirty_events", None)
    if dirty_targets and dirty_repo is not None:
        dirty_repo.enqueue_events(
            dirty_targets,
            reason="resolution_refresh",
            now_ms=now_ms,
            commit=False,
        )
    repos.conn.commit()
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


def _source_dirty_event_for_decision(decision: Any) -> dict[str, Any] | None:
    target_type = getattr(decision, "target_type", None)
    target_id = getattr(decision, "target_id", None)
    event_id = str(getattr(decision, "event_id", "") or "")
    if event_id and target_type in {"Asset", "CexToken"} and target_id:
        return {
            "source_event_id": event_id,
            "target_type_key": str(target_type),
            "identity_id": str(target_id),
        }
    return None
