from __future__ import annotations

from collections import Counter, defaultdict
from statistics import pstdev
from typing import Any

from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_FACTOR_FAMILIES

OLD_FACTOR_FAMILIES = {
    "market_quality",
    "social_attention",
    "social_quality",
    "social_semantics",
    "timing",
}


def factor_distribution_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rank_scores: list[float] = []
    family_scores: dict[str, list[float]] = {family: [] for family in TOKEN_RADAR_FACTOR_FAMILIES}
    gate_block_counts: Counter[str] = Counter()
    data_health_counts: dict[str, Counter[str]] = defaultdict(Counter)
    violations: list[dict[str, Any]] = []
    old_family_keys: set[str] = set()
    hard_gates_rows: list[int] = []

    for index, row in enumerate(rows):
        snapshot = _mapping(row.get("factor_snapshot_json"))
        composite = _mapping(snapshot.get("composite"))
        if (rank_score := _number(composite.get("rank_score"))) is not None:
            rank_scores.append(rank_score)

        families = _mapping(snapshot.get("families"))
        old_family_keys.update(OLD_FACTOR_FAMILIES & set(families))
        for family in TOKEN_RADAR_FACTOR_FAMILIES:
            block = _mapping(families.get(family))
            if (score := _number(block.get("score"))) is not None:
                family_scores[family].append(score)

        gates = _mapping(snapshot.get("gates"))
        for reason in gates.get("blocked_reasons") or []:
            if str(reason).strip():
                gate_block_counts[str(reason)] += 1

        data_health = _mapping(snapshot.get("data_health"))
        for key, value in data_health.items():
            if str(key).strip():
                data_health_counts[str(key)][str(value or "missing")] += 1

        if "hard_gates" in snapshot:
            hard_gates_rows.append(index)

    unique_count = len(set(rank_scores))
    if len(rows) > 20 and unique_count <= 3:
        violations.append(
            {
                "code": "rank_score_low_diversity",
                "row_count": len(rows),
                "rank_score_unique_count": unique_count,
            }
        )

    family_saturation = {family: _share_at_100(scores) for family, scores in family_scores.items() if len(scores) >= 20}
    for family, share in family_saturation.items():
        if share > 0.25:
            violations.append({"code": "family_score_100_saturation", "family": family, "share": share})

    if old_family_keys:
        violations.append({"code": "old_factor_family_keys", "families": sorted(old_family_keys)})
    if hard_gates_rows:
        violations.append({"code": "hard_gates_present", "rows": hard_gates_rows})

    return {
        "row_count": len(rows),
        "rank_score_unique_count": unique_count,
        "rank_score_stddev": pstdev(rank_scores) if len(rank_scores) > 1 else 0.0,
        "rank_score_saturation_100_share": _share_at_100(rank_scores),
        "family_saturation_100_share": family_saturation,
        "gate_block_counts": dict(sorted(gate_block_counts.items())),
        "data_health_counts": {key: dict(sorted(counts.items())) for key, counts in sorted(data_health_counts.items())},
        "ok": not violations,
        "violations": violations,
    }


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _share_at_100(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(1 for value in values if value >= 100.0) / len(values)


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}
