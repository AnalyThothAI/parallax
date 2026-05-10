from __future__ import annotations

import json
import math
from typing import Any

from .discussion_quality_scoring import post_quality_score

CATALYST_OBSERVATION_MS = 30 * 60_000
CATALYST_BASELINE_MS = 60 * 60_000
CATALYST_K_AUTHORS = 5


class CatalystRankingService:
    def rank(
        self,
        *,
        candidates: list[dict[str, Any]],
        pool: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        scored = [self._score_candidate(candidate=dict(candidate), pool=pool) for candidate in candidates]
        scored.sort(
            key=lambda item: (
                float(item.get("catalyst_score") or 0.0),
                int(item.get("received_at_ms") or 0) * -1,
                str(item.get("event_id") or ""),
            ),
            reverse=True,
        )
        return scored[: max(0, int(limit))]

    def _score_candidate(self, *, candidate: dict[str, Any], pool: list[dict[str, Any]]) -> dict[str, Any]:
        candidate_ms = _int_or_zero(candidate.get("received_at_ms"))
        candidate_author = _handle(candidate)
        followups = [
            dict(row)
            for row in pool
            if candidate_ms < _int_or_zero(row.get("received_at_ms")) <= candidate_ms + CATALYST_OBSERVATION_MS
            and _handle(row)
            and _handle(row) != candidate_author
        ]
        baseline_count = sum(
            1
            for row in pool
            if candidate_ms - CATALYST_BASELINE_MS <= _int_or_zero(row.get("received_at_ms")) < candidate_ms
        )
        baseline_mentions_per_min = baseline_count / (CATALYST_BASELINE_MS / 60_000)
        expected_followups = baseline_mentions_per_min * (CATALYST_OBSERVATION_MS / 60_000)
        excess_followups = max(0.0, len(followups) - expected_followups)

        author_counts: dict[str, int] = {}
        for row in followups:
            author = _handle(row)
            if author:
                author_counts[author] = author_counts.get(author, 0) + 1
        independent_authors = len(author_counts)
        independence_score = (independent_authors / len(followups)) if followups else 0.0
        excess_score = _log_score(excess_followups, scale=20.0) * independence_score
        explicit_followups = _explicit_followups(candidate, followups)
        cascade_grip = len(explicit_followups) / len(followups) if followups else 0.0
        time_to_k_ms = _time_to_k_authors_ms(candidate_ms=candidate_ms, followups=followups)
        time_to_k_score = _time_to_k_score(time_to_k_ms=time_to_k_ms, independent_authors=independent_authors)
        structural_virality_score = _structural_virality_score(explicit_followups=explicit_followups)
        quality_score = _avg_followup_quality(followups)

        score = round(
            100
            * (
                0.30 * excess_score
                + 0.20 * independence_score
                + 0.20 * cascade_grip
                + 0.15 * time_to_k_score
                + 0.10 * structural_virality_score
                + 0.05 * quality_score
            )
        )
        candidate["catalyst_score"] = max(0, min(100, score))
        candidate["catalyst_components"] = {
            "observation_window_ms": CATALYST_OBSERVATION_MS,
            "baseline_window_ms": CATALYST_BASELINE_MS,
            "followup_count": len(followups),
            "independent_authors": independent_authors,
            "baseline_mentions_per_min": round(baseline_mentions_per_min, 6),
            "excess_followups": round(excess_followups, 6),
            "excess_score": round(excess_score, 6),
            "independence_score": round(independence_score, 6),
            "explicit_cascade_followups": len(explicit_followups),
            "cascade_grip": round(cascade_grip, 6),
            "time_to_k_authors": CATALYST_K_AUTHORS,
            "time_to_k_authors_ms": time_to_k_ms,
            "time_to_k_score": round(time_to_k_score, 6),
            "structural_virality_score": round(structural_virality_score, 6),
            "avg_followup_quality": round(quality_score, 6),
        }
        return candidate


def _explicit_followups(candidate: dict[str, Any], followups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tweet_id = str(candidate.get("tweet_id") or "")
    if not tweet_id:
        return []
    return [row for row in followups if (_reference(row.get("reference_json")) or {}).get("tweet_id") == tweet_id]


def _time_to_k_authors_ms(*, candidate_ms: int, followups: list[dict[str, Any]]) -> int | None:
    seen: set[str] = set()
    for row in sorted(
        followups,
        key=lambda item: (_int_or_zero(item.get("received_at_ms")), str(item.get("event_id") or "")),
    ):
        author = _handle(row)
        if not author:
            continue
        seen.add(author)
        if len(seen) >= CATALYST_K_AUTHORS:
            return max(0, _int_or_zero(row.get("received_at_ms")) - candidate_ms)
    return None


def _time_to_k_score(*, time_to_k_ms: int | None, independent_authors: int) -> float:
    if time_to_k_ms is None:
        return min(0.4, independent_authors / CATALYST_K_AUTHORS * 0.4)
    return max(0.0, 1.0 - (time_to_k_ms / CATALYST_OBSERVATION_MS))


def _structural_virality_score(*, explicit_followups: list[dict[str, Any]]) -> float:
    explicit_authors = {_handle(row) for row in explicit_followups if _handle(row)}
    if not explicit_authors:
        return 0.0
    return min(1.0, math.log1p(len(explicit_authors)) / math.log1p(8))


def _avg_followup_quality(followups: list[dict[str, Any]]) -> float:
    if not followups:
        return 0.0
    scores = [
        post_quality_score(
            {
                "text": row.get("text_clean") or row.get("search_text"),
                "mention_source": row.get("source"),
                "attribution_status": row.get("attribution_status"),
                "attribution_confidence": row.get("attribution_confidence"),
                "attribution_weight": row.get("attribution_weight"),
                "is_watched": bool(
                    row.get("event_is_watched") if row.get("event_is_watched") is not None else row.get("is_watched")
                ),
            }
        )["score"]
        / 100
        for row in followups
    ]
    return sum(scores) / len(scores)


def _reference(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _log_score(value: float, *, scale: float) -> float:
    if value <= 0:
        return 0.0
    return min(1.0, math.log1p(value) / math.log1p(scale))


def _handle(row: dict[str, Any]) -> str:
    return str(row.get("event_author_handle") or row.get("author_handle") or "").strip().lstrip("@").lower()


def _int_or_zero(value: Any) -> int:
    if value is None:
        return 0
    return int(value)
