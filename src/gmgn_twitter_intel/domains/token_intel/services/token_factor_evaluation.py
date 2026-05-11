from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean, pstdev
from typing import Any

from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_FACTOR_SNAPSHOT_VERSION

HORIZON_MS = {
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "6h": 6 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
}

BUCKETS = (
    ("0-19", 0, 19),
    ("20-39", 20, 39),
    ("40-59", 40, 59),
    ("60-79", 60, 79),
    ("80-100", 80, 100),
)

FACTOR_FAMILIES = ("social_heat", "social_propagation", "semantic_catalyst", "timing_risk")


def settle_token_factor_scores(
    *,
    repos: Any,
    horizon: str,
    window: str,
    scope: str,
    generated_at_ms: int,
    limit: int,
) -> dict[str, Any]:
    if horizon not in HORIZON_MS:
        raise ValueError(f"unsupported token factor evaluation horizon: {horizon}")
    horizon_ms = HORIZON_MS[horizon]
    rows = repos.token_factor_evaluations.historical_radar_rows(
        factor_version=TOKEN_FACTOR_SNAPSHOT_VERSION,
        window=window,
        scope=scope,
        horizon_ms=horizon_ms,
        generated_at_ms=int(generated_at_ms),
        limit=max(0, int(limit)),
    )
    settlements = [
        _settle_row(row, repos=repos, horizon_ms=horizon_ms, generated_at_ms=int(generated_at_ms)) for row in rows
    ]
    settled = [item for item in settlements if item["status"] == "settled"]
    spearman_ic = _spearman(
        [float(item["rank_score"]) for item in settled],
        [float(item["actual_return"]) for item in settled],
    )
    daily_ics = _daily_ics(settled)
    icir_daily = _icir(daily_ics)
    global_diagnostics = {
        "spearman_ic": spearman_ic,
        "icir": icir_daily,
        "daily_ics": daily_ics,
        "eligible_count": len(settlements),
        "settled_count": len(settled),
        "unsettled_count": len(settlements) - len(settled),
        "unsettled_reasons": _reason_counts(settlements),
        "family_rank_ic": _family_rank_ics(settled),
        "family_coverage": _family_coverage(settlements),
    }
    summaries = [
        _bucket_summary(
            bucket_label=label,
            bucket_min=bucket_min,
            bucket_max=bucket_max,
            settlements=settlements,
            horizon=horizon,
            window=window,
            scope=scope,
            score_version=TOKEN_FACTOR_SNAPSHOT_VERSION,
            generated_at_ms=int(generated_at_ms),
            diagnostics=global_diagnostics,
        )
        for label, bucket_min, bucket_max in BUCKETS
    ]
    repos.token_factor_evaluations.upsert_score_evaluations(summaries)
    return {
        "horizon": horizon,
        "horizon_ms": horizon_ms,
        "window": window,
        "scope": scope,
        "score_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "generated_at_ms": int(generated_at_ms),
        "eligible_count": len(settlements),
        "settled_count": len(settled),
        "unsettled_count": len(settlements) - len(settled),
        "spearman_ic": spearman_ic,
        "daily_ics": daily_ics,
        "icir_daily": icir_daily,
        "buckets": summaries,
    }


def _settle_row(row: dict[str, Any], *, repos: Any, horizon_ms: int, generated_at_ms: int) -> dict[str, Any]:
    snapshot = _mapping(row.get("factor_snapshot_json"))
    subject = _mapping(snapshot.get("subject"))
    subject_type = str(subject.get("target_type") or row.get("target_type") or "").strip()
    subject_id = str(subject.get("target_id") or row.get("target_id") or "").strip()
    computed_at_ms = int(row.get("computed_at_ms") or 0)
    rank_score = _rank_score(snapshot)
    family_scores = _family_scores(snapshot)
    base = {
        "row_id": row.get("row_id"),
        "subject_type": subject_type,
        "subject_id": subject_id,
        "computed_at_ms": computed_at_ms,
        "rank_score": rank_score,
        "family_scores": family_scores,
        "bucket_label": _bucket_label(rank_score),
        "status": "unsettled",
        "actual_return": None,
    }
    if not subject_type or not subject_id:
        return {**base, "reason": "missing_subject"}
    entry = repos.price_observations.latest_price_for_subject_at_or_before(
        subject_type=subject_type,
        subject_id=subject_id,
        at_or_before_ms=computed_at_ms,
    )
    entry_price = _positive_price(entry)
    if entry_price is None:
        return {**base, "reason": "missing_entry_price"}
    exit_row = repos.price_observations.first_price_for_subject_between(
        subject_type=subject_type,
        subject_id=subject_id,
        at_or_after_ms=computed_at_ms + int(horizon_ms),
        at_or_before_ms=int(generated_at_ms),
    )
    exit_price = _price(exit_row)
    if exit_price is None:
        return {**base, "reason": "missing_exit_price", "entry_price": entry_price}
    actual_return = (exit_price - entry_price) / entry_price
    return {
        **base,
        "status": "settled",
        "entry_price": entry_price,
        "exit_price": exit_price,
        "actual_return": actual_return,
        "directional_hit": actual_return > 0,
    }


def _bucket_summary(
    *,
    bucket_label: str,
    bucket_min: int,
    bucket_max: int,
    settlements: list[dict[str, Any]],
    horizon: str,
    window: str,
    scope: str,
    score_version: str,
    generated_at_ms: int,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    bucket_rows = [item for item in settlements if item["bucket_label"] == bucket_label]
    settled = [item for item in bucket_rows if item["status"] == "settled"]
    returns = [float(item["actual_return"]) for item in settled]
    hits = [1.0 if item.get("directional_hit") else 0.0 for item in settled]
    hit_rate = mean(hits) if hits else 0.0
    wilson_low, wilson_high = _wilson_interval(sum(hits), len(hits))
    avg_return = mean(returns) if returns else 0.0
    sample_times = [int(item["computed_at_ms"]) for item in bucket_rows if item.get("computed_at_ms") is not None]
    rank_scores = [float(item["rank_score"]) for item in bucket_rows if item.get("rank_score") is not None]
    return {
        "horizon": horizon,
        "window": window,
        "scope": scope,
        "score_version": score_version,
        "bucket_label": bucket_label,
        "bucket_min": bucket_min,
        "bucket_max": bucket_max,
        "snapshot_count": len(bucket_rows),
        "settled_count": len(settled),
        "settlement_coverage": (len(settled) / len(bucket_rows)) if bucket_rows else 0.0,
        "avg_actual_return": avg_return,
        "avg_abnormal_return": avg_return,
        "avg_normalized_outcome": avg_return,
        "directional_hit_rate": hit_rate,
        "wilson_low": wilson_low,
        "wilson_high": wilson_high,
        "generated_at_ms": generated_at_ms,
        "sample_start_ms": min(sample_times) if sample_times else None,
        "sample_end_ms": max(sample_times) if sample_times else None,
        "spearman_ic": diagnostics["spearman_ic"],
        "icir": diagnostics["icir"],
        "score_stddev": pstdev(rank_scores) if len(rank_scores) > 1 else (0.0 if rank_scores else None),
        "diagnostics_json": {
            **diagnostics,
            "bucket_unsettled_reasons": _reason_counts(bucket_rows),
        },
    }


def _rank_score(snapshot: dict[str, Any]) -> float:
    composite = _mapping(snapshot.get("composite"))
    try:
        return max(0.0, min(100.0, float(composite.get("rank_score") or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _family_scores(snapshot: dict[str, Any]) -> dict[str, float | None]:
    composite = _mapping(snapshot.get("composite"))
    raw_scores = _mapping(composite.get("family_scores"))
    return {family: _factor_score(raw_scores.get(family)) for family in FACTOR_FAMILIES}


def _factor_score(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return None


def _bucket_label(rank_score: float) -> str:
    for label, bucket_min, bucket_max in BUCKETS:
        if bucket_min <= rank_score <= bucket_max:
            return label
    return "80-100" if rank_score > 100 else "0-19"


def _price(row: dict[str, Any] | None) -> float | None:
    if not row or row.get("price_usd") is None:
        return None
    try:
        return float(row["price_usd"])
    except (TypeError, ValueError):
        return None


def _positive_price(row: dict[str, Any] | None) -> float | None:
    price = _price(row)
    if price is None or price <= 0:
        return None
    return price


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    return _pearson(_ranks(xs), _ranks(ys))


def _daily_ics(settled: list[dict[str, Any]]) -> list[float]:
    by_day: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in settled:
        by_day[int(item["computed_at_ms"]) // (24 * 60 * 60 * 1000)].append(item)
    values: list[float] = []
    for day in sorted(by_day):
        rows = by_day[day]
        ic = _spearman(
            [float(item["rank_score"]) for item in rows],
            [float(item["actual_return"]) for item in rows],
        )
        if ic is not None:
            values.append(ic)
    return values


def _family_rank_ics(settled: list[dict[str, Any]]) -> dict[str, float | None]:
    values: dict[str, float | None] = {}
    for family in FACTOR_FAMILIES:
        paired = [
            (float(family_score), float(item["actual_return"]))
            for item in settled
            if (family_score := _mapping(item.get("family_scores")).get(family)) is not None
        ]
        values[family] = _spearman([score for score, _ in paired], [actual_return for _, actual_return in paired])
    return values


def _family_coverage(settlements: list[dict[str, Any]]) -> dict[str, float]:
    if not settlements:
        return {family: 0.0 for family in FACTOR_FAMILIES}
    return {
        family: sum(
            1 for item in settlements if _mapping(item.get("family_scores")).get(family) is not None
        )
        / len(settlements)
        for family in FACTOR_FAMILIES
    }


def _icir(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    stddev = pstdev(values)
    if stddev <= 0:
        return None
    return mean(values) / stddev


def _reason_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in rows:
        if item.get("status") == "settled":
            continue
        reason = str(item.get("reason") or "unknown")
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(indexed):
        end = index + 1
        while end < len(indexed) and indexed[end][1] == indexed[index][1]:
            end += 1
        rank = (index + 1 + end) / 2.0
        for original_index, _ in indexed[index:end]:
            ranks[original_index] = rank
        index = end
    return ranks


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    mean_x = mean(xs)
    mean_y = mean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    denominator = denom_x * denom_y
    if denominator <= 0:
        return None
    return numerator / denominator


def _wilson_interval(successes: float, total: int) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 0.0)
    z = 1.96
    p = successes / total
    denominator = 1 + z * z / total
    center = p + z * z / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return ((center - margin) / denominator, (center + margin) / denominator)
