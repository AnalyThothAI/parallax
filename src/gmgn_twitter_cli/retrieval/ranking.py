from __future__ import annotations

import re
from typing import Any

from ..pipeline.embedding import cosine_similarity

TOKEN_RE = re.compile(r"[A-Za-z0-9_$#@]+")


def rank_rows(rows: list[dict[str, Any]], *, query: str, query_vector: list[float], repo) -> list[dict[str, Any]]:
    query_terms = _terms(query)
    ranked = []
    for row in rows:
        event = repo.decode_event_row(row)
        text = " ".join(
            str(value or "")
            for value in [row.get("embedding_text"), row.get("text_clean"), row.get("text"), row.get("author_handle")]
        )
        lexical = _lexical_score(query_terms, _terms(text))
        semantic = cosine_similarity(query_vector, [float(value) for value in row.get("embedding") or []])
        recency = int(row.get("received_at_ms") or 0) / 1_000_000_000_000
        score = lexical * 5.0 + semantic + recency
        if score <= 0:
            continue
        ranked.append({"event": event, "score": round(score, 6), "match_type": "hybrid"})
    ranked.sort(
        key=lambda item: (
            -item["score"],
            -int(item["event"].get("received_at_ms") or 0),
            item["event"]["event_id"],
        )
    )
    return ranked


def _terms(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text)}


def _lexical_score(query_terms: set[str], text_terms: set[str]) -> float:
    if not query_terms or not text_terms:
        return 0.0
    return len(query_terms.intersection(text_terms)) / len(query_terms)
