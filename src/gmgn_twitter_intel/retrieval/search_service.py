from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..pipeline.embedding import EmbeddingBackend
from .query_parser import parse_query
from .ranking import rank_rows


@dataclass(frozen=True, slots=True)
class SearchResults:
    ok: bool
    items: list[dict[str, Any]] = field(default_factory=list)
    query: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)


class SearchService:
    def __init__(self, repo, embedding_backend: EmbeddingBackend):
        self.repo = repo
        self.embedding_backend = embedding_backend

    def search(self, query: str, *, limit: int = 20, scope: str = "all") -> SearchResults:
        matched_only = scope == "matched"
        parsed = parse_query(query)
        parsed_query = _query(parsed, scope=scope)
        if parsed.kind == "empty":
            return SearchResults(ok=False, query=parsed_query, error="empty_query")
        if parsed.kind == "ca":
            events = self.repo.recent_events(
                limit=limit,
                ca=parsed.ca,
                chain=parsed.chain,
                matched_only=matched_only,
            )
            return SearchResults(
                ok=True,
                items=[_item(event, "exact_ca", 100.0) for event in events],
                query=parsed_query,
            )
        if parsed.kind == "symbol":
            events = self.repo.recent_events(limit=limit, symbol=parsed.symbol, matched_only=matched_only)
            return SearchResults(
                ok=True,
                items=[_item(event, "exact_symbol", 90.0) for event in events],
                query=parsed_query,
            )
        if parsed.kind == "handle":
            events = self.repo.recent_events(limit=limit, handles={parsed.handle}, matched_only=matched_only)
            return SearchResults(
                ok=True,
                items=[_item(event, "handle", 80.0) for event in events],
                query=parsed_query,
            )

        query_vector = self.embedding_backend.embed(parsed.text)
        rows = self.repo.search_event_rows(matched_only=matched_only)
        ranked = rank_rows(rows, query=parsed.text, query_vector=query_vector, repo=self.repo)
        return SearchResults(ok=True, items=ranked[: max(0, int(limit))], query=parsed_query)


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
