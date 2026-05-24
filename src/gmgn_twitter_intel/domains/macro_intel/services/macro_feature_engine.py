from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from gmgn_twitter_intel.domains.macro_intel._constants import (
    MACRO_CONCEPT_METADATA,
    MACRO_REQUIRED_DELTA_POINTS,
    MACRO_REQUIRED_STAT_POINTS,
)
from gmgn_twitter_intel.domains.macro_intel.services.macro_gap_payloads import build_macro_data_gaps

DELTA_HORIZONS = (5, 20, 60)
HISTORY_POINTS = 252
STAT_LOOKBACK = 252
STALE_FRESHNESS_DAYS = 7
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
        concept_key = str(observation.get("concept_key") or "").strip()
        if not concept_key:
            continue
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
    ordered_observations = _deduped_observations(observations)
    numeric_observations = [_numeric_observation(observation) for observation in ordered_observations]
    usable_observations = [observation for observation in numeric_observations if observation is not None]
    non_numeric_count = len(ordered_observations) - len(usable_observations)
    data_gaps: list[str] = []

    if not usable_observations:
        latest_observation = ordered_observations[0] if ordered_observations else {}
        latest_date = _date_value(latest_observation.get("observed_at")) if latest_observation else None
        if non_numeric_count:
            data_gaps.append(f"non_numeric_values:{non_numeric_count}")
        data_gaps.append("missing_numeric_history")
        data_quality = _series_data_quality(ordered_observations)
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
                    "observed_at": _date_text(latest_observation.get("observed_at")) if latest_observation else None,
                    "unit": latest_observation.get("unit") if latest_observation else None,
                },
                "freshness_days": _freshness_days(latest_date=latest_date, computed_at_ms=computed_at_ms),
                "delta": {f"{horizon}d": None for horizon in DELTA_HORIZONS},
                "zscore": {"lookback": STAT_LOOKBACK, "value": None},
                "percentile": {"lookback": STAT_LOOKBACK, "value": None},
                "history": [],
                "data_gaps": build_macro_data_gaps(data_gaps),
            },
        )

    latest = usable_observations[0]
    freshness_days = _freshness_days(latest_date=latest["observed_date"], computed_at_ms=computed_at_ms)
    if freshness_days is None:
        data_gaps.append("missing_latest_observed_at")
    elif freshness_days > STALE_FRESHNESS_DAYS:
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
    data_quality = _series_data_quality([observation["raw"] for observation in usable_observations])
    if data_quality != "ok":
        data_gaps.append(f"data_quality:{data_quality}")

    history_points = len(usable_observations)
    return _with_semantics(
        concept_key=concept_key,
        latest_observation=latest["raw"],
        history_points=history_points,
        data_quality=data_quality,
        feature={
            "latest": {"value": _round(latest["value"]), "observed_at": latest["observed_at"], "unit": latest["unit"]},
            "freshness_days": freshness_days,
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


def _deduped_observations(observations: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    ordered = sorted(observations, key=_sort_key, reverse=True)
    deduped: list[Mapping[str, Any]] = []
    seen_dates: set[str] = set()
    for observation in ordered:
        observed_at = _date_text(observation.get("observed_at"))
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
    return {
        "value": value,
        "observed_at": _date_text(observation.get("observed_at")),
        "observed_date": observed_date,
        "unit": observation.get("unit"),
        "raw": observation,
    }


def _numeric_value(observation: Mapping[str, Any]) -> float | None:
    for field_name in ("value_numeric", "value"):
        value = observation.get(field_name)
        if value is None:
            continue
        numeric_value = _to_float(value)
        if numeric_value is not None:
            return numeric_value
    return None


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


def _freshness_days(*, latest_date: date | None, computed_at_ms: int) -> int | None:
    if latest_date is None:
        return None
    computed_date = datetime.fromtimestamp(int(computed_at_ms) / 1000, tz=UTC).date()
    return max(0, (computed_date - latest_date).days)


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _date_text(value: Any) -> str:
    observed_date = _date_value(value)
    if observed_date is not None:
        return observed_date.isoformat()
    return str(value or "")


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
    metadata = MACRO_CONCEPT_METADATA.get(concept_key, {})
    unit = str(feature.get("latest", {}).get("unit") or "")
    semantic_fields = {
        "concept_key": concept_key,
        "label": str(metadata.get("label") or concept_key),
        "short_label": str(metadata.get("short_label") or metadata.get("label") or concept_key),
        "description": str(metadata.get("description") or ""),
        "unit_label": str(metadata.get("unit_label") or unit),
        "history_points": history_points,
        "history_windows": _history_windows(history_points),
        "score_participation": history_points >= MACRO_REQUIRED_STAT_POINTS,
        "data_quality": data_quality,
        "source": {
            "name": str(latest_observation.get("source_name") or ""),
            "series_key": str(latest_observation.get("series_key") or ""),
        },
    }
    return {**semantic_fields, **feature}


def _history_windows(history_points: int) -> dict[str, dict[str, Any]]:
    return {
        window: {
            "points": history_points,
            "required_points": required_points,
            "ready": history_points >= required_points,
        }
        for window, required_points in HISTORY_WINDOWS.items()
    }


def _series_data_quality(observations: Sequence[Mapping[str, Any]]) -> str:
    for observation in observations:
        data_quality = str(observation.get("data_quality") or "").strip().lower()
        if data_quality and data_quality != "ok":
            return data_quality
    return "ok"


__all__ = ["build_macro_features"]
