from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from parallax.domains.evidence.interfaces import TwitterEvent


@dataclass(frozen=True, slots=True)
class IngestedEvent:
    event: TwitterEvent
    entities: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    inserted: bool
    token_intents: list[dict[str, Any]] = field(default_factory=list)
    token_resolutions: list[dict[str, Any]] = field(default_factory=list)
