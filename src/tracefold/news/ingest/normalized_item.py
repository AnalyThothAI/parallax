from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NormalizedNewsItem:
    source_item_key: str
    canonical_url: str
    title: str
    summary: str
    body_text: str
    language: str
    published_at_ms: int
    raw_payload: dict[str, Any]


__all__ = ["NormalizedNewsItem"]
