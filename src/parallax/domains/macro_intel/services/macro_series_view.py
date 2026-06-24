from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.macro_intel._constants import (
    MACRO_CONCEPT_METADATA,
    MACRO_CORE_CONCEPTS,
    MACRO_MIN_CHART_POINTS,
)


class UnsupportedMacroConceptError(ValueError):
    def __init__(self, concept_key: str) -> None:
        super().__init__(f"Unsupported macro concept: {concept_key}")
        self.code = "unsupported_macro_concept"
        self.concept_key = concept_key


class UnsupportedMacroSeriesWindowError(ValueError):
    def __init__(self, window: str) -> None:
        super().__init__(f"Unsupported macro series window: {window}")
        self.code = "unsupported_macro_series_window"
        self.window = window


MACRO_SERIES_WINDOWS = ("20d", "60d", "120d", "1y", "3y")

_SERIES_QUERY_BOUNDS = {
    "20d": {"lookback_days": 35, "limit_per_series": 35},
    "60d": {"lookback_days": 90, "limit_per_series": 90},
    "120d": {"lookback_days": 180, "limit_per_series": 180},
    "1y": {"lookback_days": 390, "limit_per_series": 390},
    "3y": {"lookback_days": 1095, "limit_per_series": 800},
}


def macro_series_query_bounds(window: str) -> dict[str, int]:
    validate_macro_series_window(window)
    return dict(_SERIES_QUERY_BOUNDS[window])


def validate_macro_series_window(window: str) -> str:
    if window not in MACRO_SERIES_WINDOWS:
        raise UnsupportedMacroSeriesWindowError(window)
    return window


def validate_macro_series_concepts(concept_keys: Sequence[str]) -> tuple[str, ...]:
    supported = set(MACRO_CORE_CONCEPTS)
    normalized = tuple(
        dict.fromkeys(str(concept_key).strip() for concept_key in concept_keys if str(concept_key).strip())
    )
    for concept_key in normalized:
        if concept_key not in supported:
            raise UnsupportedMacroConceptError(concept_key)
    return normalized


def build_macro_series_view(
    *,
    concept_keys: Sequence[str],
    observations: Sequence[Mapping[str, Any]],
    window: str,
) -> dict[str, Any]:
    validate_macro_series_window(window)
    normalized_keys = validate_macro_series_concepts(concept_keys)
    observations_by_concept = _group_observations(observations)
    series = {
        concept_key: _series_payload(concept_key, observations_by_concept.get(concept_key, []))
        for concept_key in normalized_keys
    }
    data_gaps = [gap for payload in series.values() for gap in payload["data_gaps"] if isinstance(gap, Mapping)]
    return {"window": window, "series": series, "data_gaps": data_gaps}


def _group_observations(observations: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for observation in observations:
        concept_key = str(observation.get("concept_key") or "").strip()
        if not concept_key:
            continue
        grouped.setdefault(concept_key, []).append(observation)
    return grouped


def _series_payload(concept_key: str, observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    sorted_observations = sorted(observations, key=lambda observation: str(observation.get("observed_at") or ""))
    points = [_point(observation) for observation in sorted_observations]
    data_gaps: list[dict[str, Any]] = []
    status = "ok"
    if not points:
        status = "missing"
        data_gaps.append(_series_gap("series_missing", concept_key))
    elif len(points) < MACRO_MIN_CHART_POINTS:
        status = "insufficient_history"
        data_gaps.append(_series_gap(f"insufficient_history_{MACRO_MIN_CHART_POINTS}_points", concept_key))
    return {
        "concept_key": concept_key,
        "status": status,
        "unit": _first_present(sorted_observations, "unit"),
        "sources": _sources(sorted_observations),
        "latest_observed_at": points[-1]["observed_at"] if points else None,
        "data_quality": _quality(sorted_observations),
        "points": points,
        "data_gaps": data_gaps,
    }


def _series_gap(code: str, concept_key: str) -> dict[str, Any]:
    if code == "series_missing":
        label = f"缺少序列数据：{_concept_label(concept_key)}"
        severity = "error"
    else:
        label = f"历史样本不足：至少需要 {MACRO_MIN_CHART_POINTS} 个点才能绘图"
        severity = "warning"
    return {
        "code": code,
        "label": label,
        "severity": severity,
        "score_participation": False,
        "concept_key": concept_key,
    }


def _concept_label(concept_key: str) -> str:
    metadata = MACRO_CONCEPT_METADATA.get(concept_key, {})
    label = _metadata_label(metadata)
    if label:
        return label
    raise ValueError(f"Missing macro concept label metadata: {concept_key}")


def _metadata_label(metadata: Mapping[str, Any]) -> str | None:
    label = metadata.get("short_label") or metadata.get("label")
    if isinstance(label, str) and label.strip():
        return label
    return None


def _point(observation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "observed_at": observation.get("observed_at"),
        "value": observation.get("value_numeric"),
        "source_name": observation.get("source_name"),
        "data_quality": _required_observation_quality(observation),
    }


def _first_present(observations: Sequence[Mapping[str, Any]], key: str) -> object:
    for observation in observations:
        value = observation.get(key)
        if value is not None:
            return value
    return None


def _sources(observations: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted(
        {
            str(observation.get("source_name") or "").strip()
            for observation in observations
            if observation.get("source_name")
        }
    )


def _quality(observations: Sequence[Mapping[str, Any]]) -> str:
    qualities = {_required_observation_quality(observation) for observation in observations}
    if not qualities:
        return "missing"
    if qualities == {"ok"}:
        return "ok"
    if len(qualities) == 1:
        return next(iter(qualities))
    return "mixed"


def _required_observation_quality(observation: Mapping[str, Any]) -> str:
    concept_key = str(observation.get("concept_key") or "").strip() or "<missing>"
    if "data_quality" not in observation or observation.get("data_quality") is None:
        raise ValueError(f"macro_series_observation_quality_required:{concept_key}")
    quality = str(observation.get("data_quality")).strip()
    if not quality:
        raise ValueError(f"macro_series_observation_quality_required:{concept_key}")
    return quality


__all__ = [
    "MACRO_SERIES_WINDOWS",
    "UnsupportedMacroConceptError",
    "UnsupportedMacroSeriesWindowError",
    "build_macro_series_view",
    "macro_series_query_bounds",
    "validate_macro_series_concepts",
    "validate_macro_series_window",
]
