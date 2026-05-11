from __future__ import annotations

import math
from collections import Counter
from typing import Any, Mapping, Sequence


def source_weighted_effective_authors(rows: Sequence[Mapping[str, Any]]) -> float:
    counts = _author_counts(rows)
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    concentration = sum((count / total) ** 2 for count in counts.values())
    if concentration <= 0:
        return 0.0
    return 1.0 / concentration


def time_to_nth_independent_author_ms(rows: Sequence[Mapping[str, Any]], n: int) -> int | None:
    if n <= 0:
        return None
    ordered_rows = _ordered_rows(rows)
    if not ordered_rows:
        return None

    first_seen_ms = _int(ordered_rows[0].get("received_at_ms"))
    if first_seen_ms is None:
        return None

    seen: set[str] = set()
    for row in ordered_rows:
        handle = _handle(row)
        if handle is None or handle in seen:
            continue
        seen.add(handle)
        if len(seen) == n:
            seen_ms = _int(row.get("received_at_ms"))
            if seen_ms is None:
                return None
            return max(0, seen_ms - first_seen_ms)
    return None


def public_followup_author_count(rows: Sequence[Mapping[str, Any]]) -> int:
    ordered_rows = _ordered_rows(rows)
    seed_seen = False
    public_authors: set[str] = set()
    for row in ordered_rows:
        if not seed_seen:
            seed_seen = _is_watched(row)
            continue
        if _is_watched(row):
            continue
        handle = _handle(row)
        if handle is not None:
            public_authors.add(handle)
    return len(public_authors)


def author_entropy(rows: Sequence[Mapping[str, Any]]) -> float:
    counts = _author_counts(rows)
    total = sum(counts.values())
    if total <= 0 or len(counts) <= 1:
        return 0.0

    entropy = 0.0
    for count in counts.values():
        probability = count / total
        entropy -= probability * math.log(probability)
    return entropy / math.log(len(counts))


def _author_counts(rows: Sequence[Mapping[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        handle = _handle(row)
        if handle is not None:
            counts[handle] += 1
    return counts


def _ordered_rows(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        row
        for _, row in sorted(
            enumerate(rows),
            key=lambda item: (_sort_ms(item[1]), item[0]),
        )
    ]


def _sort_ms(row: Mapping[str, Any]) -> int:
    return _int(row.get("received_at_ms")) or 0


def _handle(row: Mapping[str, Any]) -> str | None:
    value = row.get("author_handle")
    if value is None:
        value = row.get("author")
    if value is None:
        return None
    handle = str(value).strip().lower()
    return handle or None


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_watched(row: Mapping[str, Any]) -> bool:
    return bool(row.get("is_watched"))
