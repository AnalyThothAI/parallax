from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

from .diffusion_health import text_fingerprint

BUCKET_WIDTH_MS = {
    "5m": 30_000,
    "1h": 5 * 60_000,
    "4h": 15 * 60_000,
    "24h": 60 * 60_000,
}


def bucket_width_ms(window: str) -> int:
    return BUCKET_WIDTH_MS[window]


def build_timeline_features(
    events: list[dict[str, Any]],
    *,
    window: str,
    window_start_ms: int,
    window_end_ms: int,
) -> dict[str, Any]:
    bucket_ms = bucket_width_ms(window)
    bucket_starts = list(range(window_start_ms, window_end_ms, bucket_ms))
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    sorted_events = sorted(
        (
            event
            for event in events
            if event.get("received_at_ms") is not None
            and window_start_ms <= int(event["received_at_ms"]) < window_end_ms
        ),
        key=lambda item: (int(item["received_at_ms"]), str(item.get("event_id") or "")),
    )
    first_bucket_by_author: dict[str, int] = {}
    for event in sorted_events:
        received_at_ms = int(event["received_at_ms"])
        bucket_start = window_start_ms + ((received_at_ms - window_start_ms) // bucket_ms) * bucket_ms
        grouped[bucket_start].append(event)
        handle = _handle(event)
        if handle and handle not in first_bucket_by_author:
            first_bucket_by_author[handle] = bucket_start

    buckets: list[dict[str, Any]] = []
    for start_ms in bucket_starts:
        bucket_events = grouped[start_ms]
        author_counts = Counter(_handle(event) for event in bucket_events if _handle(event))
        authors = set(author_counts)
        top_author_share = max(author_counts.values(), default=0) / len(bucket_events) if bucket_events else 0.0
        buckets.append(
            {
                "bucket_start_ms": start_ms,
                "bucket_end_ms": start_ms + bucket_ms,
                "start_ms": start_ms,
                "end_ms": start_ms + bucket_ms,
                "mentions": len(bucket_events),
                "posts": len(bucket_events),
                "authors": len(authors),
                "new_authors": sum(
                    1 for handle, first_bucket in first_bucket_by_author.items() if first_bucket == start_ms
                ),
                "watched_authors": len({_handle(event) for event in bucket_events if _is_watched(event)}),
                "watched_posts": sum(1 for event in bucket_events if _is_watched(event)),
                "top_author_share": round(top_author_share, 4),
                "duplicate_text_share": _duplicate_text_share(bucket_events),
                "effective_authors": _effective_authors(author_counts),
                "reproduction_rate_to_next": 0.0,
            }
        )
    for index, bucket in enumerate(buckets[:-1]):
        bucket["reproduction_rate_to_next"] = round(
            int(buckets[index + 1]["new_authors"]) / max(int(bucket["authors"]), 1),
            4,
        )

    author_counts = Counter(_handle(event) for event in sorted_events if _handle(event))
    mentions = len(sorted_events)
    top_author_share = max(author_counts.values(), default=0) / mentions if mentions else 0.0
    duplicate_text_share = _duplicate_text_share(sorted_events)
    effective_authors = _effective_authors(author_counts)
    peak_reproduction_rate = max((float(bucket["reproduction_rate_to_next"]) for bucket in buckets), default=0.0)
    non_empty_indexes = [index for index, bucket in enumerate(buckets) if int(bucket["mentions"]) > 0]
    latest_non_empty_bucket_index = non_empty_indexes[-1] if non_empty_indexes else None
    phase_inputs = {
        "independent_authors": len(author_counts),
        "effective_authors": effective_authors,
        "new_authors_total": len(first_bucket_by_author),
        "peak_reproduction_rate": peak_reproduction_rate,
        "latest_non_empty_bucket_index": latest_non_empty_bucket_index,
        "last_bucket_index": len(buckets) - 1,
        "top_author_share": top_author_share,
        "duplicate_text_share": duplicate_text_share,
    }
    summary = {
        "mentions": mentions,
        "posts": mentions,
        "independent_authors": len(author_counts),
        "authors": len(author_counts),
        "effective_authors": effective_authors,
        "new_authors_total": len(first_bucket_by_author),
        "watched_author_count": len({_handle(event) for event in sorted_events if _is_watched(event)}),
        "first_seen_ms": int(sorted_events[0]["received_at_ms"]) if sorted_events else None,
        "latest_seen_ms": int(sorted_events[-1]["received_at_ms"]) if sorted_events else None,
        "peak_reproduction_rate": peak_reproduction_rate,
        "latest_non_empty_bucket_index": latest_non_empty_bucket_index,
        "top_author_share": top_author_share,
        "duplicate_text_share": duplicate_text_share,
        "phase": _phase(mentions=mentions, phase_inputs=phase_inputs),
        "phase_inputs": phase_inputs,
    }
    return {
        "window": window,
        "bucket_ms": bucket_ms,
        "window_start_ms": window_start_ms,
        "window_end_ms": window_end_ms,
        "event_ids": [str(event.get("event_id")) for event in sorted_events if event.get("event_id")],
        "summary": summary,
        "buckets": buckets,
    }


def _phase(*, mentions: int, phase_inputs: dict[str, Any]) -> str:
    authors = int(phase_inputs["independent_authors"])
    effective_authors = float(phase_inputs["effective_authors"])
    top_author_share = float(phase_inputs["top_author_share"])
    duplicate_text_share = float(phase_inputs["duplicate_text_share"])
    peak_reproduction_rate = float(phase_inputs["peak_reproduction_rate"])
    latest_index = phase_inputs["latest_non_empty_bucket_index"]
    last_index = int(phase_inputs["last_bucket_index"])
    if mentions <= 1 or authors <= 1:
        return "seed"
    if top_author_share >= 0.65 or duplicate_text_share >= 0.45:
        return "concentration"
    if latest_index is not None and latest_index < last_index - 1 and peak_reproduction_rate < 0.40:
        return "fade"
    if authors >= 5 and effective_authors >= 3.5 and peak_reproduction_rate >= 0.60 and top_author_share < 0.50:
        return "expansion"
    return "ignition"


def _duplicate_text_share(events: list[dict[str, Any]]) -> float:
    if len(events) < 3:
        return 0.0
    fingerprints = [text_fingerprint(event.get("text_clean") or event.get("search_text")) for event in events]
    counts = Counter(item for item in fingerprints if item)
    return round(max(counts.values(), default=0) / len(events), 4)


def _effective_authors(author_counts: Counter[str]) -> float:
    total = sum(author_counts.values())
    if not total:
        return 0.0
    entropy = -sum((count / total) * math.log(count / total) for count in author_counts.values())
    return round(math.exp(entropy), 4)


def _handle(event: dict[str, Any]) -> str:
    return str(event.get("event_author_handle") or event.get("author_handle") or "").strip().lstrip("@").lower()


def _is_watched(event: dict[str, Any]) -> bool:
    value = event.get("event_is_watched") if event.get("event_is_watched") is not None else event.get("is_watched")
    return bool(value)
