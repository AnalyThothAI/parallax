from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from parallax.domains.macro_intel.services.macro_concept_manifest import MACRO_CONCEPT_MANIFEST

COMPUTED_DATE = date(2026, 7, 23)
COMPUTED_AT_MS = int(datetime(2026, 7, 23, 22, tzinfo=UTC).timestamp() * 1000)


def observation(
    concept_key: str,
    value: float,
    *,
    observed_at: date = COMPUTED_DATE,
    source_name: str = "fixture",
    series_key: str | None = None,
    unit: str | None = None,
    frequency: str | None = None,
    data_quality: str = "ok",
    event_metadata_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec = MACRO_CONCEPT_MANIFEST[concept_key]
    return {
        "concept_key": concept_key,
        "observed_at": observed_at,
        "value_numeric": value,
        "source_name": source_name,
        "series_key": series_key or f"fixture:{concept_key}",
        "unit": spec.source_unit if unit is None else unit,
        "frequency": spec.frequency if frequency is None else frequency,
        "data_quality": data_quality,
        "event_metadata_json": dict(event_metadata_json or {}),
    }


def series(
    concept_key: str,
    values: Sequence[float],
    *,
    end: date = COMPUTED_DATE,
    step_days: int = 1,
) -> list[dict[str, Any]]:
    start = end - timedelta(days=step_days * (len(values) - 1))
    return [
        observation(concept_key, value, observed_at=start + timedelta(days=step_days * index))
        for index, value in enumerate(values)
    ]


def flatten(groups: Iterable[Sequence[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [item for group in groups for item in group]
