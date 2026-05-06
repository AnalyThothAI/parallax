from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .query_parser import parse_query


@dataclass(frozen=True, slots=True)
class AssetSearchResults:
    ok: bool
    items: list[dict[str, Any]] = field(default_factory=list)
    query: dict[str, Any] = field(default_factory=dict)
    resolution: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    total_count: int = 0
    returned_count: int = 0
    has_more: bool = False


class AssetSearchService:
    def __init__(self, *, evidence, assets):
        self.evidence = evidence
        self.assets = assets

    def search(self, query: str, *, limit: int = 20, scope: str = "all") -> AssetSearchResults:
        watched_only = scope == "matched"
        parsed = parse_query(query)
        parsed_query = _query(parsed, scope=scope)
        if parsed.kind == "empty":
            return AssetSearchResults(ok=False, query=parsed_query, error="empty_query")
        requested_limit = max(0, int(limit))
        if parsed.kind == "symbol":
            return self._search_symbol(
                parsed.symbol or "",
                limit=requested_limit,
                watched_only=watched_only,
                query=parsed_query,
            )
        if parsed.kind == "handle":
            events = self.evidence.recent_events(
                limit=requested_limit,
                handles={parsed.handle},
                watched_only=watched_only,
            )
            return AssetSearchResults(
                ok=True,
                items=[_item(event, "handle", 80.0) for event in events],
                query=parsed_query,
                resolution={"status": "not_applicable", "candidates": []},
                total_count=len(events),
                returned_count=len(events),
                has_more=False,
            )
        events = self.evidence.search_fts(parsed.text, limit=requested_limit, watched_only=watched_only)
        total_count = self.evidence.count_fts(parsed.text, watched_only=watched_only)
        return AssetSearchResults(
            ok=True,
            items=[_item(event, "fts", float(event.get("score") or 0.0)) for event in events],
            query=parsed_query,
            resolution={"status": "not_applicable", "candidates": []},
            total_count=total_count,
            returned_count=len(events),
            has_more=total_count > len(events),
        )

    def _search_symbol(
        self,
        symbol: str,
        *,
        limit: int,
        watched_only: bool,
        query: dict[str, Any],
    ) -> AssetSearchResults:
        candidates = self.assets.candidates_for_symbol(symbol)
        events = self.assets.events_for_symbol_mentions(symbol, limit=limit, watched_only=watched_only)
        status = _resolution_status(candidates)
        return AssetSearchResults(
            ok=True,
            items=[_item(event, "asset_mention", 100.0) for event in events],
            query=query,
            resolution={"status": status, "candidates": candidates},
            candidates=candidates,
            total_count=len(events),
            returned_count=len(events),
            has_more=False,
        )


def _resolution_status(candidates: list[dict[str, Any]]) -> str:
    asset_ids = {str(candidate.get("asset_id")) for candidate in candidates if candidate.get("asset_id")}
    if not candidates:
        return "unresolved"
    if any(str(candidate.get("identity_status") or "") == "unresolved" for candidate in candidates):
        return "unresolved"
    if any(str(candidate.get("identity_status") or "") == "ambiguous" for candidate in candidates):
        return "ambiguous"
    if len(asset_ids) == 1:
        return "resolved"
    return "ambiguous"


def _item(event: dict[str, Any], match_type: str, score: float) -> dict[str, Any]:
    return {"event": event, "match_type": match_type, "score": score}


def _query(parsed, *, scope: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"kind": parsed.kind, "text": parsed.text, "scope": scope}
    if parsed.ca:
        payload["ca"] = parsed.ca
    if parsed.chain:
        payload["chain"] = parsed.chain
    if parsed.symbol:
        payload["symbol"] = parsed.symbol
    if parsed.handle:
        payload["handle"] = parsed.handle
    return payload
