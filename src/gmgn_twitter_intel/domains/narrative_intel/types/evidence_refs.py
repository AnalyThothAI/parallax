from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvidenceRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    ref_id: str = Field(min_length=1)
    kind: Literal["event", "semantic", "market_tick", "profile", "data_gap"]
    source_table: str = Field(min_length=1)
    event_id: str | None = None
    semantic_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    confidence: float | None = None

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return max(0.0, min(1.0, float(value)))


def ref_id_for_event(event_id: str) -> str:
    return f"event:{event_id}"


def ref_id_for_semantic(semantic_id: str) -> str:
    return f"semantic:{semantic_id}"

