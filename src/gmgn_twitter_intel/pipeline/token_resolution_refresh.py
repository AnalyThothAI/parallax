from __future__ import annotations

from typing import Any

from .token_intent_resolver import TokenIntentResolver
from .token_radar_projection import WINDOW_MS, TokenRadarProjection
from .token_radar_projection_worker import DEFAULT_SCOPES, DEFAULT_WINDOWS

DEFAULT_REPROCESS_LIMIT = 500
DEFAULT_REPROCESS_WINDOW = "24h"


def refresh_recent_token_state(
    *,
    repos: Any,
    lookup_keys: list[str],
    now_ms: int,
    window: str = DEFAULT_REPROCESS_WINDOW,
    reprocess_limit: int = DEFAULT_REPROCESS_LIMIT,
    projection_limit: int = 100,
    windows: tuple[str, ...] = DEFAULT_WINDOWS,
    scopes: tuple[str, ...] = DEFAULT_SCOPES,
) -> dict[str, Any]:
    keys = sorted({key for key in lookup_keys if key})
    result = {
        "lookup_keys": keys,
        "reprocess": None,
        "reprocessed_intents": 0,
        "projection": {"rows_written": 0, "source_rows": 0, "windows": {}},
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
    if result["reprocessed_intents"]:
        result["projection"] = rebuild_token_radar_windows(
            repos=repos,
            now_ms=now_ms,
            windows=windows,
            scopes=scopes,
            limit=projection_limit,
        )
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
    repos.conn.commit()
    return {
        "window": window,
        "lookup_keys": lookup_keys or [],
        "reprocessed_intents": reprocessed,
        "resolved_intents": resolved,
        "since_ms": since_ms,
    }


def rebuild_token_radar_windows(
    *,
    repos: Any,
    now_ms: int,
    windows: tuple[str, ...] = DEFAULT_WINDOWS,
    scopes: tuple[str, ...] = DEFAULT_SCOPES,
    limit: int = 100,
) -> dict[str, Any]:
    projection = TokenRadarProjection(repos=repos)
    result: dict[str, Any] = {"rows_written": 0, "source_rows": 0, "windows": {}}
    for window in windows:
        for scope in scopes:
            key = f"{window}:{scope}"
            window_result = projection.rebuild(window=window, scope=scope, now_ms=now_ms, limit=limit)
            result["windows"][key] = window_result
            result["rows_written"] += int(window_result.get("rows_written") or 0)
            result["source_rows"] += int(window_result.get("source_rows") or 0)
    return result
