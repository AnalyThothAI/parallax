from __future__ import annotations

import hashlib
from typing import Any

from psycopg.types.json import Jsonb


class TokenFactorEvaluationRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def historical_radar_rows(
        self,
        *,
        factor_version: str,
        window: str,
        scope: str,
        horizon_ms: int,
        generated_at_ms: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM token_radar_snapshot_audit
            WHERE factor_version = %s
              AND "window" = %s
              AND scope = %s
              AND computed_at_ms + %s <= %s
            ORDER BY computed_at_ms DESC, rank ASC, lane ASC, row_id ASC
            LIMIT %s
            """,
            (
                factor_version,
                window,
                scope,
                int(horizon_ms),
                int(generated_at_ms),
                max(0, int(limit)),
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def upsert_score_evaluation(self, summary: dict[str, Any], *, commit: bool = True) -> None:
        payload = dict(summary)
        payload.setdefault(
            "evaluation_id",
            _evaluation_id(
                horizon=str(payload["horizon"]),
                window=str(payload["window"]),
                scope=str(payload["scope"]),
                score_version=str(payload["score_version"]),
                bucket_label=str(payload["bucket_label"]),
            ),
        )
        payload.setdefault("sample_start_ms", None)
        payload.setdefault("sample_end_ms", None)
        payload.setdefault("spearman_ic", None)
        payload.setdefault("icir", None)
        payload.setdefault("score_stddev", None)
        payload["diagnostics_json"] = Jsonb(payload.get("diagnostics_json") or {})
        self.conn.execute(
            """
            INSERT INTO token_score_evaluations(
              evaluation_id, horizon, "window", scope, score_version, bucket_label, bucket_min, bucket_max,
              snapshot_count, settled_count, settlement_coverage, avg_actual_return, avg_abnormal_return,
              avg_normalized_outcome, directional_hit_rate, wilson_low, wilson_high, generated_at_ms,
              sample_start_ms, sample_end_ms, spearman_ic, icir, score_stddev, diagnostics_json
            )
            VALUES (
              %(evaluation_id)s, %(horizon)s, %(window)s, %(scope)s, %(score_version)s, %(bucket_label)s,
              %(bucket_min)s, %(bucket_max)s, %(snapshot_count)s, %(settled_count)s,
              %(settlement_coverage)s, %(avg_actual_return)s, %(avg_abnormal_return)s,
              %(avg_normalized_outcome)s, %(directional_hit_rate)s, %(wilson_low)s, %(wilson_high)s,
              %(generated_at_ms)s, %(sample_start_ms)s, %(sample_end_ms)s, %(spearman_ic)s, %(icir)s,
              %(score_stddev)s, %(diagnostics_json)s
            )
            ON CONFLICT(horizon, "window", scope, score_version, bucket_label) DO UPDATE SET
              evaluation_id = excluded.evaluation_id,
              bucket_min = excluded.bucket_min,
              bucket_max = excluded.bucket_max,
              snapshot_count = excluded.snapshot_count,
              settled_count = excluded.settled_count,
              settlement_coverage = excluded.settlement_coverage,
              avg_actual_return = excluded.avg_actual_return,
              avg_abnormal_return = excluded.avg_abnormal_return,
              avg_normalized_outcome = excluded.avg_normalized_outcome,
              directional_hit_rate = excluded.directional_hit_rate,
              wilson_low = excluded.wilson_low,
              wilson_high = excluded.wilson_high,
              generated_at_ms = excluded.generated_at_ms,
              sample_start_ms = excluded.sample_start_ms,
              sample_end_ms = excluded.sample_end_ms,
              spearman_ic = excluded.spearman_ic,
              icir = excluded.icir,
              score_stddev = excluded.score_stddev,
              diagnostics_json = excluded.diagnostics_json
            """,
            payload,
        )
        if commit:
            self.conn.commit()

    def upsert_score_evaluations(self, summaries: list[dict[str, Any]], *, commit: bool = True) -> None:
        if not commit:
            for summary in summaries:
                self.upsert_score_evaluation(summary, commit=False)
            return
        with self.conn.transaction():
            for summary in summaries:
                self.upsert_score_evaluation(summary, commit=False)

    def latest_score_evaluations(
        self,
        *,
        horizon: str,
        window: str,
        scope: str,
        score_version: str,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH ranked AS (
              SELECT
                token_score_evaluations.*,
                row_number() OVER (PARTITION BY bucket_label ORDER BY generated_at_ms DESC) AS bucket_rank
              FROM token_score_evaluations
              WHERE horizon = %s
                AND "window" = %s
                AND scope = %s
                AND score_version = %s
            )
            SELECT *
            FROM ranked
            WHERE bucket_rank = 1
            ORDER BY bucket_min ASC
            """,
            (horizon, window, scope, score_version),
        ).fetchall()
        return [dict(row) for row in rows]


def _evaluation_id(*, horizon: str, window: str, scope: str, score_version: str, bucket_label: str) -> str:
    raw = "|".join(("token-score-evaluation", horizon, window, scope, score_version, bucket_label))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
