from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .query_parser import parse_query


@dataclass(frozen=True, slots=True)
class SearchResults:
    ok: bool
    items: list[dict[str, Any]] = field(default_factory=list)
    query: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)


class SearchService:
    def __init__(self, *, evidence, entities, signals):
        self.evidence = evidence
        self.entities = entities
        self.signals = signals

    def search(self, query: str, *, limit: int = 20, scope: str = "all") -> SearchResults:
        watched_only = scope == "matched"
        parsed = parse_query(query)
        parsed_query = _query(parsed, scope=scope)
        if parsed.kind == "empty":
            return SearchResults(ok=False, query=parsed_query, error="empty_query")
        if parsed.kind == "ca":
            entity_rows = self.entities.find_by_ca(
                parsed.ca,
                chain=parsed.chain,
                limit=limit,
                watched_only=watched_only,
            )
            mention_rows = self.signals.token_mentions_by_ca(
                chain=parsed.chain,
                address=parsed.ca,
                limit=limit,
                watched_only=watched_only,
            )
            events = _events_for_rows(self.evidence, [*entity_rows, *mention_rows])
            return SearchResults(
                ok=True,
                items=[_item(event, "exact_ca", 100.0) for event in events],
                query=parsed_query,
            )
        if parsed.kind == "symbol":
            entity_rows = self.entities.find_by_symbol(parsed.symbol, limit=limit, watched_only=watched_only)
            mention_rows = self.signals.token_mentions_by_symbol(
                symbol=parsed.symbol,
                limit=limit,
                watched_only=watched_only,
            )
            events = _events_for_rows(self.evidence, [*entity_rows, *mention_rows])
            return SearchResults(
                ok=True,
                items=[_item(event, "exact_symbol", 90.0) for event in events],
                query=parsed_query,
            )
        if parsed.kind == "handle":
            events = self.evidence.recent_events(limit=limit, handles={parsed.handle}, watched_only=watched_only)
            return SearchResults(
                ok=True,
                items=[_item(event, "handle", 80.0) for event in events],
                query=parsed_query,
            )

        events = self.evidence.search_fts(parsed.text, limit=limit, watched_only=watched_only)
        return SearchResults(
            ok=True,
            items=[_item(event, "fts", float(event.get("score") or 0.0)) for event in events],
            query=parsed_query,
        )


def _item(event: dict[str, Any], match_type: str, score: float) -> dict[str, Any]:
    return {"event": event, "match_type": match_type, "score": score}


def _events_for_rows(evidence, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    event_ids = []
    seen: set[str] = set()
    for row in rows:
        event_id = str(row.get("event_id") or "")
        if not event_id or event_id in seen:
            continue
        seen.add(event_id)
        event_ids.append(event_id)
    by_id = evidence.events_by_ids(event_ids)
    events = [by_id[event_id] for event_id in event_ids if event_id in by_id]
    events.sort(key=lambda event: int(event.get("received_at_ms") or 0), reverse=True)
    return events


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
