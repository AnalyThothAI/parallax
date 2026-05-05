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
    total_count: int = 0
    returned_count: int = 0
    has_more: bool = False


class SearchService:
    def __init__(self, *, evidence, signals, tokens):
        self.evidence = evidence
        self.signals = signals
        self.tokens = tokens

    def search(self, query: str, *, limit: int = 20, scope: str = "all") -> SearchResults:
        watched_only = scope == "matched"
        parsed = parse_query(query)
        parsed_query = _query(parsed, scope=scope)
        if parsed.kind == "empty":
            return SearchResults(ok=False, query=parsed_query, error="empty_query")
        requested_limit = max(0, int(limit))
        if parsed.kind == "ca":
            rows = self.signals.token_attributions_by_ca(
                chain=parsed.chain,
                address=parsed.ca,
                limit=requested_limit,
                watched_only=watched_only,
            )
            events = _events_for_rows(self.evidence, rows)[:requested_limit]
            total_count = self.signals.token_attribution_count_by_ca(
                chain=parsed.chain,
                address=parsed.ca,
                watched_only=watched_only,
            )
            return SearchResults(
                ok=True,
                items=[_item(event, "token_attribution", 100.0) for event in events],
                query=parsed_query,
                total_count=total_count,
                returned_count=len(events),
                has_more=total_count > len(events),
            )
        if parsed.kind == "symbol":
            candidates = self.tokens.tokens_for_symbol(parsed.symbol)
            if not candidates:
                return SearchResults(
                    ok=False,
                    query=parsed_query,
                    error="unresolved_token_symbol",
                    candidates=[],
                )
            if len(candidates) > 1:
                return SearchResults(
                    ok=False,
                    query=parsed_query,
                    error="ambiguous_token_symbol",
                    candidates=candidates,
                )
            token_id = str(candidates[0]["token_id"])
            rows = self.signals.token_attributions_by_token_id(
                token_id=token_id,
                limit=requested_limit,
                watched_only=watched_only,
            )
            events = _events_for_rows(self.evidence, rows)[:requested_limit]
            total_count = self.signals.token_attribution_count_by_token_id(
                token_id=token_id,
                watched_only=watched_only,
            )
            return SearchResults(
                ok=True,
                items=[_item(event, "token_attribution", 100.0) for event in events],
                query=parsed_query,
                candidates=candidates,
                total_count=total_count,
                returned_count=len(events),
                has_more=total_count > len(events),
            )
        if parsed.kind == "handle":
            events = self.evidence.recent_events(
                limit=requested_limit,
                handles={parsed.handle},
                watched_only=watched_only,
            )
            total_count = _handle_count(self.evidence.conn, handle=parsed.handle, watched_only=watched_only)
            return SearchResults(
                ok=True,
                items=[_item(event, "handle", 80.0) for event in events],
                query=parsed_query,
                total_count=total_count,
                returned_count=len(events),
                has_more=total_count > len(events),
            )

        events = self.evidence.search_fts(parsed.text, limit=requested_limit, watched_only=watched_only)
        total_count = self.evidence.count_fts(parsed.text, watched_only=watched_only)
        return SearchResults(
            ok=True,
            items=[_item(event, "fts", float(event.get("score") or 0.0)) for event in events],
            query=parsed_query,
            total_count=total_count,
            returned_count=len(events),
            has_more=total_count > len(events),
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


def _handle_count(conn, *, handle: str, watched_only: bool) -> int:
    clauses = ["author_handle = ?"]
    params: list[Any] = [handle]
    if watched_only:
        clauses.append("is_watched = 1")
    row = conn.execute(
        f"SELECT COUNT(*) AS count FROM events WHERE {' AND '.join(clauses)}",
        params,
    ).fetchone()
    return int(row["count"] or 0) if row else 0
