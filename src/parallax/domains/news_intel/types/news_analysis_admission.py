from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

NewsAnalysisAdmissionStatus = Literal["admitted", "page_only", "research_context", "suppressed", "needs_review"]


@dataclass(frozen=True, slots=True)
class NewsAnalysisAdmission:
    status: NewsAnalysisAdmissionStatus
    reason: str
    basis: dict[str, Any]
    version: str


__all__ = ["NewsAnalysisAdmission", "NewsAnalysisAdmissionStatus"]
