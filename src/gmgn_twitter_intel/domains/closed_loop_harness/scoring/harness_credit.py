from __future__ import annotations

from typing import Any


def assign_cluster_credits(
    snapshot_clusters: list[dict[str, Any]],
    *,
    normalized_outcome: float,
) -> list[dict[str, Any]]:
    total_abs = sum(abs(float(item.get("event_score") or 0.0)) for item in snapshot_clusters)
    if total_abs <= 0:
        return []
    credits: list[dict[str, Any]] = []
    for item in snapshot_clusters:
        score = float(item.get("event_score") or 0.0)
        responsibility = abs(score) / total_abs
        sign = 1 if score >= 0 else -1
        credits.append(
            {
                "cluster_id": str(item.get("cluster_id") or ""),
                "event_type": str(item.get("event_type") or ""),
                "source": str(item.get("source") or ""),
                "event_score": score,
                "responsibility": round(responsibility, 12),
                "credit": round(responsibility * sign * normalized_outcome, 12),
            }
        )
    return credits


def update_weight_stat(
    existing: dict[str, Any],
    *,
    credit: float,
    n0: int = 50,
    lambda_: float = 0.5,
) -> dict[str, Any]:
    old_n = int(existing.get("n") or 0)
    new_n = old_n + 1
    old_mean = float(existing.get("mean_credit") or 0.0)
    mean = old_mean + (float(credit) - old_mean) / new_n
    shrunk = new_n / (new_n + n0) * mean
    weight = max(0.5, min(1 + lambda_ * shrunk, 1.5))
    return {"n": new_n, "mean_credit": round(mean, 12), "weight": round(weight, 12)}
