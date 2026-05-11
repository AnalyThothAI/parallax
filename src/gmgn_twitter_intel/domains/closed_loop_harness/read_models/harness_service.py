from __future__ import annotations

from typing import Any

WINDOW_MS = {
    "5m": 300_000,
    "1h": 3_600_000,
    "4h": 4 * 3_600_000,
    "24h": 86_400_000,
}


class HarnessService:
    def __init__(self, harness: Any) -> None:
        self.harness = harness

    def social_events(
        self,
        *,
        window: str,
        limit: int,
        handles: set[str] | None = None,
        event_types: set[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "items": self.harness.list_social_events(
                window_ms=WINDOW_MS.get(window, WINDOW_MS["1h"]),
                limit=limit,
                handles=handles,
                event_types=event_types,
            )
        }

    def attention_seeds(self, *, window: str, limit: int, handles: set[str] | None = None) -> dict[str, Any]:
        return {
            "items": self.harness.list_attention_seeds(
                window_ms=WINDOW_MS.get(window, WINDOW_MS["1h"]),
                limit=limit,
                handles=handles,
            )
        }

    def snapshots(self, *, window: str, horizon: str | None, limit: int, asset: str | None = None) -> dict[str, Any]:
        return {
            "items": self.harness.list_snapshots(
                window_ms=WINDOW_MS.get(window, WINDOW_MS["1h"]),
                horizon=horizon,
                asset=asset,
                limit=limit,
            )
        }

    def outcomes(self, *, window: str, horizon: str | None, limit: int, asset: str | None = None) -> dict[str, Any]:
        return {
            "items": self.harness.list_outcomes(
                window_ms=WINDOW_MS.get(window, WINDOW_MS["1h"]),
                horizon=horizon,
                asset=asset,
                limit=limit,
            )
        }

    def credits(self, *, window: str, horizon: str | None, limit: int, asset: str | None = None) -> dict[str, Any]:
        return {
            "items": self.harness.list_credits(
                window_ms=WINDOW_MS.get(window, WINDOW_MS["1h"]),
                horizon=horizon,
                asset=asset,
                limit=limit,
            )
        }

    def weights(self, *, horizon: str | None, limit: int) -> dict[str, Any]:
        return {"items": self.harness.list_weights(horizon=horizon, limit=limit)}

    def score_buckets(self, *, horizon: str | None = None) -> dict[str, Any]:
        rows = self.harness.score_bucket_rows(horizon=horizon)
        pending_rows = self.harness.pending_score_bucket_rows(horizon=horizon)
        buckets = [_empty_bucket(label) for label in ["<= -0.8", "-0.8 to -0.4", "-0.4 to 0.4", "0.4 to 0.8", ">= 0.8"]]
        by_label = {item["bucket"]: item for item in buckets}
        for row in pending_rows:
            by_label[_bucket_label(float(row["combined_score"]))]["pending_count"] += 1
        for row in rows:
            score = float(row["combined_score"])
            outcome = float(row["normalized_outcome"])
            abnormal = float(row["abnormal_return"])
            bucket = by_label[_bucket_label(score)]
            bucket["sample_count"] += 1
            bucket["settled_count"] += 1
            bucket["pending_count"] -= 1
            bucket["_normalized_sum"] += outcome
            bucket["_abnormal_sum"] += abnormal
            bucket["_hit_count"] += int(_directional_hit(score=score, outcome=outcome))
        for bucket in buckets:
            sample_count = int(bucket["sample_count"])
            normalized_sum = float(bucket.pop("_normalized_sum"))
            abnormal_sum = float(bucket.pop("_abnormal_sum"))
            hit_count = int(bucket.pop("_hit_count"))
            bucket["avg_normalized_outcome"] = 0.0 if sample_count == 0 else round(normalized_sum / sample_count, 12)
            bucket["avg_abnormal_return"] = 0.0 if sample_count == 0 else round(abnormal_sum / sample_count, 12)
            bucket["hit_rate"] = 0.0 if sample_count == 0 else round(hit_count / sample_count, 12)
        return {"items": buckets}

    def health(
        self,
        *,
        llm_configured: bool,
        extractor_running: bool,
        pending_jobs: int,
        schema_success_rate: float | None,
    ) -> dict[str, Any]:
        health = self.harness.health()
        return {
            "llm_configured": llm_configured,
            "extractor_running": extractor_running,
            "schema_success_rate": schema_success_rate,
            "pending_jobs": pending_jobs,
            **health,
        }


def _empty_bucket(label: str) -> dict[str, Any]:
    return {
        "bucket": label,
        "sample_count": 0,
        "avg_normalized_outcome": 0.0,
        "avg_abnormal_return": 0.0,
        "hit_rate": 0.0,
        "settled_count": 0,
        "pending_count": 0,
        "_normalized_sum": 0.0,
        "_abnormal_sum": 0.0,
        "_hit_count": 0,
    }


def _bucket_label(score: float) -> str:
    if score <= -0.8:
        return "<= -0.8"
    if score < -0.4:
        return "-0.8 to -0.4"
    if score < 0.4:
        return "-0.4 to 0.4"
    if score < 0.8:
        return "0.4 to 0.8"
    return ">= 0.8"


def _directional_hit(*, score: float, outcome: float) -> bool:
    if score > 0:
        return outcome > 0
    if score < 0:
        return outcome < 0
    return abs(outcome) < 1e-12
