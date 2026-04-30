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
    error: str | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)


class SearchService:
    def __init__(self, repo, embedding_backend: EmbeddingBackend):
        self.repo = repo
        self.embedding_backend = embedding_backend

    def search(self, query: str, *, limit: int = 20) -> SearchResults:
        parsed = parse_query(query)
        if parsed.kind == "empty":
            return SearchResults(ok=False, error="empty_query")
        if parsed.kind == "ca":
            events = self.repo.recent_events(limit=limit, ca=parsed.ca, chain=parsed.chain)
            return SearchResults(ok=True, items=[_item(event, "exact_ca", 100.0) for event in events])
        if parsed.kind == "symbol":
            events = self.repo.recent_events(limit=limit, symbol=parsed.symbol)
            return SearchResults(ok=True, items=[_item(event, "exact_symbol", 90.0) for event in events])
        if parsed.kind == "handle":
            events = self.repo.recent_events(limit=limit, handles={parsed.handle})
            return SearchResults(ok=True, items=[_item(event, "handle", 80.0) for event in events])

        query_vector = self.embedding_backend.embed(parsed.text)
        rows = self.repo.matched_event_rows()
        ranked = rank_rows(rows, query=parsed.text, query_vector=query_vector, repo=self.repo)
        return SearchResults(ok=True, items=ranked[: max(0, int(limit))])


def _item(event: dict[str, Any], match_type: str, score: float) -> dict[str, Any]:
    return {"event": event, "match_type": match_type, "score": score}
