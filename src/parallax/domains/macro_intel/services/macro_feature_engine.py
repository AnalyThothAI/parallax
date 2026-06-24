from __future__ import annotations

import math
from calendar import monthrange
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from parallax.domains.macro_intel._constants import (
    MACRO_CONCEPT_METADATA,
    MACRO_HISTORY_REQUIRED_POINTS_BY_CONCEPT,
    MACRO_REQUIRED_DELTA_POINTS,
    MACRO_REQUIRED_STAT_POINTS,
)
from parallax.domains.macro_intel.observation_identity import normalize_macro_date
from parallax.domains.macro_intel.services.macro_gap_payloads import build_macro_data_gaps

DELTA_HORIZONS = (5, 20, 60)
HISTORY_POINTS = 252
STAT_LOOKBACK = 252
STALE_FRESHNESS_DAYS_BY_FREQUENCY = {
    "daily": 7,
    "weekly": 21,
    "monthly": 65,
    "quarterly": 140,
}
HISTORY_WINDOWS = {
    "20d": MACRO_REQUIRED_DELTA_POINTS["20d"],
    "60d": MACRO_REQUIRED_DELTA_POINTS["60d"],
    "252d": MACRO_REQUIRED_STAT_POINTS,
}


def build_macro_features(
    observations: Sequence[Mapping[str, Any]],
    *,
    computed_at_ms: int,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for observation in observations:
        concept_key = _required_concept_key(observation)
        grouped.setdefault(concept_key, []).append(observation)

    return {
        concept_key: _features_for_series(
            concept_key,
            series_observations,
            computed_at_ms=computed_at_ms,
        )
        for concept_key, series_observations in sorted(grouped.items())
    }


def _features_for_series(
    concept_key: str,
    observations: Sequence[Mapping[str, Any]],
    *,
    computed_at_ms: int,
) -> dict[str, Any]:
    ordered_observations = _deduped_observations(concept_key, observations)
    if not ordered_observations:
        raise ValueError(f"macro_feature_observed_at_required:{concept_key}")
    numeric_observations = [_numeric_observation(observation) for observation in ordered_observations]
    usable_observations = [observation for observation in numeric_observations if observation is not None]
    non_numeric_count = len(ordered_observations) - len(usable_observations)
    data_gaps: list[str] = []

    if not usable_observations:
        latest_observation = ordered_observations[0]
        latest_date = _date_value(latest_observation.get("observed_at")) if latest_observation else None
        frequency = _required_frequency(concept_key, latest_observation)
        freshness_days = _freshness_days(
            latest_date=latest_date,
            computed_at_ms=computed_at_ms,
            frequency=frequency,
        )
        if non_numeric_count:
            data_gaps.append(f"non_numeric_values:{non_numeric_count}")
        data_gaps.append("missing_numeric_history")
        data_quality = _series_data_quality(concept_key, ordered_observations)
        if data_quality != "ok":
            data_gaps.append(f"data_quality:{data_quality}")
        return _with_semantics(
            concept_key=concept_key,
            latest_observation=latest_observation,
            history_points=0,
            data_quality=data_quality,
            feature={
                "latest": {
                    "value": None,
                    "observed_at": _date_text(latest_observation.get("observed_at")),
                    "unit": _required_observation_text(concept_key, latest_observation, "unit"),
                },
                "freshness_days": freshness_days,
                "stale_after_days": _stale_after_days(frequency),
                "delta": {f"{horizon}d": None for horizon in DELTA_HORIZONS},
                "zscore": {"lookback": STAT_LOOKBACK, "value": None},
                "percentile": {"lookback": STAT_LOOKBACK, "value": None},
                "history": [],
                "data_gaps": build_macro_data_gaps(data_gaps),
            },
        )

    latest = usable_observations[0]
    frequency = _required_frequency(concept_key, latest["raw"])
    stale_after_days = _stale_after_days(frequency)
    freshness_days = _freshness_days(
        latest_date=latest["observed_date"],
        computed_at_ms=computed_at_ms,
        frequency=frequency,
    )
    if freshness_days is None:
        data_gaps.append("missing_latest_observed_at")
    elif freshness_days > stale_after_days:
        data_gaps.append(f"stale_latest:{freshness_days}d")

    delta: dict[str, float | None] = {}
    for horizon in DELTA_HORIZONS:
        key = f"{horizon}d"
        if len(usable_observations) <= horizon:
            delta[key] = None
            data_gaps.append(f"insufficient_history:{horizon}d")
            continue
        delta[key] = _round(latest["value"] - usable_observations[horizon]["value"])

    values = [observation["value"] for observation in usable_observations[:STAT_LOOKBACK]]
    zscore_value = _zscore(values)
    percentile_value = _percentile(values)
    if zscore_value is None:
        data_gaps.append("insufficient_history:zscore")
    if percentile_value is None:
        data_gaps.append("insufficient_history:percentile")
    if non_numeric_count:
        data_gaps.append(f"non_numeric_values:{non_numeric_count}")
    data_quality = _series_data_quality(concept_key, [observation["raw"] for observation in usable_observations])
    if data_quality != "ok":
        data_gaps.append(f"data_quality:{data_quality}")

    history_points = len(usable_observations)
    return _with_semantics(
        concept_key=concept_key,
        latest_observation=latest["raw"],
        history_points=history_points,
        data_quality=data_quality,
        feature={
            "latest": {
                "value": _round(latest["value"]),
                "observed_at": latest["observed_at"],
                "unit": _required_observation_text(concept_key, latest["raw"], "unit"),
            },
            "freshness_days": freshness_days,
            "stale_after_days": stale_after_days,
            "delta": delta,
            "zscore": {"lookback": STAT_LOOKBACK, "value": None if zscore_value is None else _round(zscore_value)},
            "percentile": {
                "lookback": STAT_LOOKBACK,
                "value": None if percentile_value is None else _round(percentile_value),
            },
            "history": _history_points(usable_observations),
            "data_gaps": build_macro_data_gaps(data_gaps),
        },
    )


def _history_points(observations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for observation in reversed(observations[:HISTORY_POINTS]):
        observed_at = str(observation.get("observed_at") or "").strip()
        value = observation.get("value")
        if not observed_at or not isinstance(value, int | float):
            continue
        points.append({"observed_at": observed_at, "value": _round(value)})
    return points


def _deduped_observations(concept_key: str, observations: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    ordered = sorted(observations, key=_sort_key, reverse=True)
    deduped: list[Mapping[str, Any]] = []
    seen_dates: set[str] = set()
    for observation in ordered:
        observed_at = _required_date_text(concept_key, observation.get("observed_at"))
        if observed_at in seen_dates:
            continue
        seen_dates.add(observed_at)
        deduped.append(observation)
    return deduped


def _sort_key(observation: Mapping[str, Any]) -> tuple[int, int, int]:
    observed_date = _date_value(observation.get("observed_at"))
    return (
        observed_date.toordinal() if observed_date is not None else 0,
        _int_value(observation.get("source_priority")),
        _int_value(observation.get("ingested_at_ms")),
    )


def _numeric_observation(observation: Mapping[str, Any]) -> dict[str, Any] | None:
    value = _numeric_value(observation)
    if value is None:
        return None
    observed_date = _date_value(observation.get("observed_at"))
    if observed_date is None:
        return None
    return {
        "value": value,
        "observed_at": _date_text(observation.get("observed_at")),
        "observed_date": observed_date,
        "raw": observation,
    }


def _numeric_value(observation: Mapping[str, Any]) -> float | None:
    return _to_float(observation.get("value_numeric"))


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal | str):
        try:
            numeric_value = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return numeric_value if math.isfinite(numeric_value) else None
    return None


def _zscore(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    latest_value = values[0]
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    standard_deviation = math.sqrt(variance)
    if standard_deviation == 0:
        return 0.0
    return (latest_value - mean) / standard_deviation


def _percentile(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    latest_value = values[0]
    less_than = sum(1 for value in values if value < latest_value)
    equal_to = sum(1 for value in values if value == latest_value)
    return (less_than + 0.5 * equal_to) / len(values)


def _freshness_days(*, latest_date: date | None, computed_at_ms: int, frequency: str) -> int | None:
    if latest_date is None:
        return None
    computed_date = datetime.fromtimestamp(int(computed_at_ms) / 1000, tz=UTC).date()
    return max(0, (computed_date - _freshness_reference_date(latest_date, frequency=frequency)).days)


def _freshness_reference_date(latest_date: date, *, frequency: str) -> date:
    if frequency == "monthly":
        return date(latest_date.year, latest_date.month, monthrange(latest_date.year, latest_date.month)[1])
    if frequency == "quarterly":
        quarter_end_month = ((latest_date.month - 1) // 3 + 1) * 3
        return date(latest_date.year, quarter_end_month, monthrange(latest_date.year, quarter_end_month)[1])
    return latest_date


def _stale_after_days(frequency: str) -> int:
    return STALE_FRESHNESS_DAYS_BY_FREQUENCY[frequency]


def _date_value(value: Any) -> date | None:
    try:
        return normalize_macro_date(value)
    except ValueError:
        return None


def _date_text(value: Any) -> str | None:
    observed_date = _date_value(value)
    if observed_date is not None:
        return observed_date.isoformat()
    return None


def _required_date_text(concept_key: str, value: Any) -> str:
    observed_at = _date_text(value)
    if observed_at is None:
        raise ValueError(f"macro_feature_observed_at_required:{concept_key}")
    return observed_at


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _round(value: float) -> float:
    return round(float(value), 10)


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _with_semantics(
    *,
    concept_key: str,
    latest_observation: Mapping[str, Any],
    history_points: int,
    data_quality: str,
    feature: dict[str, Any],
) -> dict[str, Any]:
    metadata = _required_concept_metadata(concept_key)
    required_points = MACRO_HISTORY_REQUIRED_POINTS_BY_CONCEPT.get(concept_key, MACRO_REQUIRED_STAT_POINTS)
    semantic_fields = {
        "concept_key": concept_key,
        "label": _required_metadata_text(concept_key, metadata, "label"),
        "short_label": _required_metadata_text(concept_key, metadata, "short_label"),
        "description": _required_metadata_text(concept_key, metadata, "description"),
        "unit_label": _required_metadata_text(concept_key, metadata, "unit_label"),
        "history_points": history_points,
        "history_windows": _history_windows(history_points),
        "required_history_points": required_points,
        "score_participation": history_points >= required_points,
        "data_quality": data_quality,
        "source": {
            "name": _required_observation_text(concept_key, latest_observation, "source_name"),
            "series_key": _required_observation_text(concept_key, latest_observation, "series_key"),
        },
    }
    return {**semantic_fields, **feature}


def _required_concept_key(observation: Mapping[str, Any]) -> str:
    value = observation.get("concept_key")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("macro_feature_concept_key_required")
    return value.strip()


def _required_concept_metadata(concept_key: str) -> Mapping[str, Any]:
    metadata = MACRO_CONCEPT_METADATA.get(concept_key)
    if not isinstance(metadata, Mapping):
        raise ValueError(f"macro_feature_metadata_required:{concept_key}")
    return metadata


def _required_metadata_text(concept_key: str, metadata: Mapping[str, Any], field_name: str) -> str:
    value = metadata.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"macro_feature_metadata_{field_name}_required:{concept_key}")
    return value


def _required_observation_text(concept_key: str, observation: Mapping[str, Any], field_name: str) -> str:
    value = observation.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"macro_feature_{field_name}_required:{concept_key}")
    return value


def _required_frequency(concept_key: str, observation: Mapping[str, Any]) -> str:
    value = observation.get("frequency")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"macro_feature_frequency_required:{concept_key}")
    frequency = value.strip().lower()
    if frequency not in STALE_FRESHNESS_DAYS_BY_FREQUENCY:
        raise ValueError(f"macro_feature_frequency_unknown:{concept_key}:{frequency}")
    return frequency


def _history_windows(history_points: int) -> dict[str, dict[str, Any]]:
    return {
        window: {
            "points": history_points,
            "required_points": required_points,
            "ready": history_points >= required_points,
        }
        for window, required_points in HISTORY_WINDOWS.items()
    }


def _required_data_quality(concept_key: str, observation: Mapping[str, Any]) -> str:
    value = observation.get("data_quality")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"macro_feature_data_quality_required:{concept_key}")
    return value.strip().lower()


def _series_data_quality(concept_key: str, observations: Sequence[Mapping[str, Any]]) -> str:
    for observation in observations:
        data_quality = _required_data_quality(concept_key, observation)
        if data_quality != "ok":
            return data_quality
    return "ok"


__all__ = ["build_macro_features"]
