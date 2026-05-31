from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from parallax.domains.evidence.interfaces import TwitterEvent


def normalize_handles(handles: Iterable[str] | None) -> set[str]:
    if not handles:
        return set()
    return {handle.lstrip("@").strip().lower() for handle in handles if handle and handle.lstrip("@").strip()}


def event_matches_handles(event: TwitterEvent | dict[str, Any], handles: set[str]) -> bool:
    if not handles:
        return True

    if isinstance(event, TwitterEvent):
        author_handle = event.author.handle
        matched_handles = event.matched_handles
    else:
        author_handle = (event.get("author") or {}).get("handle")
        matched_handles = event.get("matched_handles") or []

    candidates = normalize_handles([author_handle] if author_handle else [])
    candidates.update(normalize_handles(matched_handles))
    return bool(candidates & handles)
