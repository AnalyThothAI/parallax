from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int = 0
    failed: int = 0
    dead: int = 0
    skipped: int = 0
    notes: dict[str, Any] = field(default_factory=dict)
