from __future__ import annotations

import hashlib
import math
import time
from typing import Any

from ..storage.token_signal_repository import TokenSignalRepository

BUCKETS = (
    ("0-39", 0, 39),
    ("40-54", 40, 54),
    ("55-69", 55, 69),
    ("70-84", 70, 84),
    ("85-100", 85, 100),
)


class TokenSignalEvaluationService:
    def __init__(self, *, repository: TokenSignalRepository):
        self.repository = repository

    def evaluate(
        self,
        *,
        horizon: str,
        window: str,
        scope: str,
        score_version: str = "social_opportunity_v2",
    ) -> dict[str, Any]:
        rows = self.repository.conn.execute(
            """
            SELECT
              s.snapshot_id,
              s.opportunity_score,
              s.window,
              s.scope,
              o.status AS outcome_status,
              o.actual_return,
              o.abnormal_return,
              o.normalized_outcome
            FROM token_signal_snapshots s
            LEFT JOIN token_signal_outcomes o
              ON o.snapshot_id = s.snapshot_id
             AND o.horizon = ?
            WHERE s.window = ?
              AND s.scope = ?
            """,
            (horizon, window, scope),
        ).fetchall()
        now_ms = _now_ms()
        buckets = []
        for label, bucket_min, bucket_max in BUCKETS:
            bucket_rows = [
                dict(row)
                for row in rows
                if bucket_min <= int(row["opportunity_score"] or 0) <= bucket_max
            ]
            settled_rows = [row for row in bucket_rows if row.get("outcome_status") == "settled"]
            hit_count = sum(1 for row in settled_rows if _directional_hit(row))
            settled_count = len(settled_rows)
            snapshot_count = len(bucket_rows)
            directional_hit_rate = hit_count / settled_count if settled_count else 0.0
            wilson_low, wilson_high = _wilson(hit_count, settled_count)
            payload = {
                "evaluation_id": _evaluation_id(horizon, window, scope, score_version, label),
                "horizon": horizon,
                "window": window,
                "scope": scope,
                "score_version": score_version,
                "bucket_label": label,
                "bucket_min": bucket_min,
                "bucket_max": bucket_max,
                "snapshot_count": snapshot_count,
                "settled_count": settled_count,
                "settlement_coverage": settled_count / snapshot_count if snapshot_count else 0.0,
                "avg_actual_return": _avg(row.get("actual_return") for row in settled_rows),
                "avg_abnormal_return": _avg(row.get("abnormal_return") for row in settled_rows),
                "avg_normalized_outcome": _avg(row.get("normalized_outcome") for row in settled_rows),
                "directional_hit_rate": directional_hit_rate,
                "wilson_low": wilson_low,
                "wilson_high": wilson_high,
                "generated_at_ms": now_ms,
            }
            self.repository.upsert_evaluation(**payload)
            buckets.append(payload)
        return {
            "horizon": horizon,
            "window": window,
            "scope": scope,
            "score_version": score_version,
            "buckets": buckets,
        }


def _directional_hit(row: dict[str, Any]) -> bool:
    score = int(row.get("opportunity_score") or 0)
    outcome = float(row.get("normalized_outcome") or 0.0)
    return outcome > 0 if score >= 50 else outcome < 0


def _avg(values: Any) -> float:
    numbers = [float(value) for value in values if value is not None]
    return 0.0 if not numbers else sum(numbers) / len(numbers)


def _wilson(hit_count: int, sample_count: int, *, z: float = 1.96) -> tuple[float, float]:
    if sample_count <= 0:
        return 0.0, 0.0
    phat = hit_count / sample_count
    denom = 1 + z**2 / sample_count
    centre = phat + z**2 / (2 * sample_count)
    margin = z * math.sqrt((phat * (1 - phat) + z**2 / (4 * sample_count)) / sample_count)
    return max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom)


def _evaluation_id(horizon: str, window: str, scope: str, score_version: str, bucket_label: str) -> str:
    return hashlib.sha256(
        f"token_score_evaluation|{horizon}|{window}|{scope}|{score_version}|{bucket_label}".encode()
    ).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)
