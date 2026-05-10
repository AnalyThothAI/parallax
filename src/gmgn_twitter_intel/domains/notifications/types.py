from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class NotificationCandidate:
    dedup_key: str
    rule_id: str
    severity: str
    title: str
    body: str
    entity_type: str | None
    entity_key: str | None
    source_table: str
    source_id: str
    occurrence_at_ms: int
    payload: dict[str, Any] = field(default_factory=dict)
    channels: tuple[str, ...] = ("in_app",)
    author_handle: str | None = None
    symbol: str | None = None
    chain: str | None = None
    address: str | None = None
    event_id: str | None = None
