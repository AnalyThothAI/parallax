from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

_FORMULA_ID = (
    "fetch25|process15|resolved15|brief15|dedupe10|freshness10|useful_fact_or_context10"
)
_FORMULA_HASH = hashlib.sha256(_FORMULA_ID.encode()).hexdigest()[:12]
SOURCE_QUALITY_PROJECTION_VERSION = f"news_source_quality_projection:v1:{_FORMULA_HASH}"

_COUNT_KEYS = (
    "fetch_run_count",
    "fetch_success_count",
    "items_fetched",
    "items_inserted",
    "items_duplicate",
    "item_count",
    "processed_item_count",
    "mention_count",
    "resolved_mention_count",
    "attention_fact_count",
    "accepted_fact_count",
    "fact_count",
    "ready_brief_count",
    "context_item_count",
    "useful_item_count",
    "median_lag_ms",
)


def quality_score(metrics: Mapping[str, float | int | None]) -> float:
    score = (
        25 * _metric(metrics, "fetch_success_rate")
        + 15 * _metric(metrics, "process_success_rate")
        + 15 * _metric(metrics, "resolved_token_rate")
        + 15 * _metric(metrics, "brief_ready_rate")
        + 10 * (1 - _metric(metrics, "duplicate_rate", default=1.0))
        + 10 * _metric(metrics, "normalized_freshness")
        + 10 * _metric(metrics, "useful_fact_or_context_rate")
    )
    return round(max(0.0, min(100.0, score)), 2)


def quality_status(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 75:
        return "healthy"
    if score >= 50:
        return "watch"
    if score >= 25:
        return "degraded"
    return "poor"


def build_source_quality_row(
    *,
    source_id: str,
    window: str,
    computed_at_ms: int,
    metrics: Mapping[str, float | int | None],
    counts: Mapping[str, int | None] | None = None,
    window_ms: int | None = None,
) -> dict[str, Any]:
    normalized_metrics = _normalized_metrics(metrics)
    normalized_counts = _normalized_counts(counts or {})
    score = quality_score(normalized_metrics) if _has_score_input(normalized_metrics) else None
    diagnostics: dict[str, Any] = {
        "counts": normalized_counts,
        "metrics": normalized_metrics,
        "status": quality_status(score),
    }
    if window_ms is not None:
        diagnostics["window_ms"] = int(window_ms)
    return {
        "row_id": f"news-source-quality:{source_id}:{window}",
        "source_id": str(source_id),
        "window": str(window),
        "computed_at_ms": int(computed_at_ms),
        "fetch_success_rate": normalized_metrics.get("fetch_success_rate"),
        "items_fetched": _count(counts or {}, "items_fetched"),
        "items_inserted": _count(counts or {}, "items_inserted"),
        "duplicate_rate": normalized_metrics.get("duplicate_rate"),
        "process_success_rate": normalized_metrics.get("process_success_rate"),
        "resolved_token_rate": normalized_metrics.get("resolved_token_rate"),
        "attention_rate": normalized_metrics.get("attention_rate"),
        "accepted_fact_rate": normalized_metrics.get("accepted_fact_rate"),
        "brief_ready_rate": normalized_metrics.get("brief_ready_rate"),
        "median_lag_ms": _optional_int((counts or {}).get("median_lag_ms")),
        "quality_score": score,
        "diagnostics_json": diagnostics,
        "projection_version": SOURCE_QUALITY_PROJECTION_VERSION,
    }


def build_source_quality_rows(
    *,
    aggregate_inputs: Sequence[Mapping[str, Any]],
    window: str,
    window_ms: int,
    computed_at_ms: int,
) -> list[dict[str, Any]]:
    return [
        build_source_quality_row(
            source_id=str(row["source_id"]),
            window=window,
            computed_at_ms=computed_at_ms,
            metrics=_metrics_from_input(row, window_ms=window_ms, computed_at_ms=computed_at_ms),
            counts=_counts_from_input(row),
            window_ms=window_ms,
        )
        for row in aggregate_inputs
    ]


def _metrics_from_input(
    row: Mapping[str, Any],
    *,
    window_ms: int,
    computed_at_ms: int,
) -> dict[str, float]:
    item_count = _count(row, "item_count")
    fact_count = _count(row, "fact_count")
    useful_item_count = min(item_count, _count(row, "useful_item_count"))
    latest_item_published_at_ms = _optional_int(row.get("latest_item_published_at_ms"))
    return _normalized_metrics(
        {
            "fetch_success_rate": _rate(_count(row, "fetch_success_count"), _count(row, "fetch_run_count")),
            "duplicate_rate": _rate(_count(row, "items_duplicate"), _count(row, "items_fetched")),
            "process_success_rate": _rate(_count(row, "processed_item_count"), item_count),
            "resolved_token_rate": _rate(_count(row, "resolved_mention_count"), _count(row, "mention_count")),
            "attention_rate": _rate(_count(row, "attention_fact_count"), fact_count),
            "accepted_fact_rate": _rate(_count(row, "accepted_fact_count"), fact_count),
            "brief_ready_rate": _rate(_count(row, "ready_brief_count"), item_count),
            "normalized_freshness": _normalized_freshness(
                latest_item_published_at_ms=latest_item_published_at_ms,
                computed_at_ms=computed_at_ms,
                window_ms=window_ms,
            ),
            "useful_fact_or_context_rate": _rate(useful_item_count, item_count),
        }
    )


def _counts_from_input(row: Mapping[str, Any]) -> dict[str, int]:
    return {key: _count(row, key) for key in _COUNT_KEYS}


def _normalized_metrics(metrics: Mapping[str, float | int | None]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for key, value in metrics.items():
        if value is None:
            continue
        normalized[str(key)] = round(max(0.0, min(1.0, float(value))), 4)
    return normalized


def _normalized_counts(counts: Mapping[str, int | None]) -> dict[str, int]:
    return {str(key): _count(counts, str(key)) for key in counts if counts.get(key) is not None}


def _has_score_input(metrics: Mapping[str, float]) -> bool:
    return any(
        key in metrics
        for key in (
            "fetch_success_rate",
            "process_success_rate",
            "resolved_token_rate",
            "brief_ready_rate",
            "duplicate_rate",
            "normalized_freshness",
            "useful_fact_or_context_rate",
        )
    )


def _metric(metrics: Mapping[str, float | int | None], key: str, *, default: float = 0.0) -> float:
    value = metrics.get(key)
    if value is None:
        return default
    return max(0.0, min(1.0, float(value)))


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(max(0.0, min(1.0, numerator / denominator)), 4)


def _normalized_freshness(
    *,
    latest_item_published_at_ms: int | None,
    computed_at_ms: int,
    window_ms: int,
) -> float | None:
    if latest_item_published_at_ms is None or window_ms <= 0:
        return None
    age_ms = max(0, int(computed_at_ms) - int(latest_item_published_at_ms))
    return round(max(0.0, min(1.0, 1 - age_ms / int(window_ms))), 4)


def _count(row: Mapping[str, Any], key: str) -> int:
    value = row.get(key)
    if value is None:
        return 0
    return max(0, int(value))


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
