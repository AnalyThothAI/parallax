from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from typing import Any


class TokenSignalRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_snapshot(self, *, commit: bool = True, **data: Any) -> dict[str, Any]:
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO token_signal_snapshots(
              snapshot_id, token_id, identity_key, chain, address, symbol, window, scope,
              decision_time_ms, rank, decision, opportunity_score, score_versions_json,
              component_payload_json, identity_json, market_json, flow_json, timeline_json,
              source_event_ids_json, market_snapshot_ids_json, data_health_json, risks_json,
              created_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(token_id, window, scope, decision_time_ms) DO UPDATE SET
              snapshot_id = excluded.snapshot_id,
              identity_key = excluded.identity_key,
              chain = excluded.chain,
              address = excluded.address,
              symbol = excluded.symbol,
              rank = excluded.rank,
              decision = excluded.decision,
              opportunity_score = excluded.opportunity_score,
              score_versions_json = excluded.score_versions_json,
              component_payload_json = excluded.component_payload_json,
              identity_json = excluded.identity_json,
              market_json = excluded.market_json,
              flow_json = excluded.flow_json,
              timeline_json = excluded.timeline_json,
              source_event_ids_json = excluded.source_event_ids_json,
              market_snapshot_ids_json = excluded.market_snapshot_ids_json,
              data_health_json = excluded.data_health_json,
              risks_json = excluded.risks_json,
              created_at_ms = excluded.created_at_ms
            """,
            (
                data["snapshot_id"],
                data["token_id"],
                data["identity_key"],
                data["chain"],
                data["address"],
                data["symbol"],
                data["window"],
                data["scope"],
                int(data["decision_time_ms"]),
                int(data["rank"]),
                data["decision"],
                int(data["opportunity_score"]),
                _json(data.get("score_versions") or {}),
                _json(data.get("component_payload") or {}),
                _json(data.get("identity") or {}),
                _json(data.get("market") or {}),
                _json(data.get("flow") or {}),
                _json(data.get("timeline") or {}),
                _json(data.get("source_event_ids") or []),
                _json(data.get("market_snapshot_ids") or []),
                _json(data.get("data_health") or {}),
                _json(data.get("risks") or []),
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()
        snapshot = self.snapshot_by_id(str(data["snapshot_id"]))
        return snapshot or {}

    def snapshot_by_id(self, snapshot_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM token_signal_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        return _decode_snapshot(dict(row)) if row else None

    def list_snapshots(
        self,
        *,
        window: str | None = None,
        scope: str | None = None,
        token_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if window:
            clauses.append("window = ?")
            params.append(window)
        if scope:
            clauses.append("scope = ?")
            params.append(scope)
        if token_id:
            clauses.append("token_id = ?")
            params.append(token_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT * FROM token_signal_snapshots
            {where}
            ORDER BY decision_time_ms DESC, rank ASC
            LIMIT ?
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [_decode_snapshot(dict(row)) for row in rows]

    def pending_settlement_snapshots(self, *, horizon: str, now_ms: int, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT s.*
            FROM token_signal_snapshots s
            WHERE NOT EXISTS (
              SELECT 1 FROM token_signal_outcomes o
              WHERE o.snapshot_id = s.snapshot_id
                AND o.horizon = ?
            )
              AND s.decision_time_ms <= ?
            ORDER BY s.decision_time_ms ASC
            LIMIT ?
            """,
            (horizon, int(now_ms), max(0, int(limit))),
        ).fetchall()
        return [_decode_snapshot(dict(row)) for row in rows]

    def record_outcome(self, *, commit: bool = True, **data: Any) -> dict[str, Any]:
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO token_signal_outcomes(
              outcome_id, snapshot_id, horizon, status, entry_snapshot_id, exit_snapshot_id,
              benchmark_snapshot_ids_json, entry_price, exit_price, benchmark_return,
              actual_return, abnormal_return, realized_vol, normalized_outcome,
              market_coverage_status, settled_at_ms, created_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(snapshot_id, horizon) DO UPDATE SET
              outcome_id = excluded.outcome_id,
              status = excluded.status,
              entry_snapshot_id = excluded.entry_snapshot_id,
              exit_snapshot_id = excluded.exit_snapshot_id,
              benchmark_snapshot_ids_json = excluded.benchmark_snapshot_ids_json,
              entry_price = excluded.entry_price,
              exit_price = excluded.exit_price,
              benchmark_return = excluded.benchmark_return,
              actual_return = excluded.actual_return,
              abnormal_return = excluded.abnormal_return,
              realized_vol = excluded.realized_vol,
              normalized_outcome = excluded.normalized_outcome,
              market_coverage_status = excluded.market_coverage_status,
              settled_at_ms = excluded.settled_at_ms,
              created_at_ms = excluded.created_at_ms
            """,
            (
                data["outcome_id"],
                data["snapshot_id"],
                data["horizon"],
                data["status"],
                data.get("entry_snapshot_id"),
                data.get("exit_snapshot_id"),
                _json(data.get("benchmark_snapshot_ids") or []),
                data.get("entry_price"),
                data.get("exit_price"),
                data.get("benchmark_return"),
                data.get("actual_return"),
                data.get("abnormal_return"),
                data.get("realized_vol"),
                data.get("normalized_outcome"),
                data["market_coverage_status"],
                int(data["settled_at_ms"]),
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()
        return self.outcome_by_id(str(data["outcome_id"])) or {}

    def outcome_by_id(self, outcome_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM token_signal_outcomes WHERE outcome_id = ?",
            (outcome_id,),
        ).fetchone()
        return _decode_outcome(dict(row)) if row else None

    def list_outcomes(
        self,
        *,
        horizon: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if horizon:
            clauses.append("horizon = ?")
            params.append(horizon)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT * FROM token_signal_outcomes
            {where}
            ORDER BY settled_at_ms DESC
            LIMIT ?
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [_decode_outcome(dict(row)) for row in rows]

    def upsert_evaluation(self, *, commit: bool = True, **data: Any) -> dict[str, Any]:
        self.conn.execute(
            """
            INSERT INTO token_score_evaluations(
              evaluation_id, horizon, window, scope, score_version, bucket_label, bucket_min,
              bucket_max, snapshot_count, settled_count, settlement_coverage,
              avg_actual_return, avg_abnormal_return, avg_normalized_outcome,
              directional_hit_rate, wilson_low, wilson_high, generated_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(horizon, window, scope, score_version, bucket_label) DO UPDATE SET
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
              generated_at_ms = excluded.generated_at_ms
            """,
            (
                data["evaluation_id"],
                data["horizon"],
                data["window"],
                data["scope"],
                data["score_version"],
                data["bucket_label"],
                int(data["bucket_min"]),
                int(data["bucket_max"]),
                int(data["snapshot_count"]),
                int(data["settled_count"]),
                float(data["settlement_coverage"]),
                float(data["avg_actual_return"]),
                float(data["avg_abnormal_return"]),
                float(data["avg_normalized_outcome"]),
                float(data["directional_hit_rate"]),
                float(data["wilson_low"]),
                float(data["wilson_high"]),
                int(data["generated_at_ms"]),
            ),
        )
        if commit:
            self.conn.commit()
        return self.evaluation_by_id(str(data["evaluation_id"])) or {}

    def evaluation_by_id(self, evaluation_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM token_score_evaluations WHERE evaluation_id = ?",
            (evaluation_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_evaluations(
        self,
        *,
        horizon: str | None = None,
        window: str | None = None,
        scope: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if horizon:
            clauses.append("horizon = ?")
            params.append(horizon)
        if window:
            clauses.append("window = ?")
            params.append(window)
        if scope:
            clauses.append("scope = ?")
            params.append(scope)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT * FROM token_score_evaluations
            {where}
            ORDER BY generated_at_ms DESC, bucket_min ASC
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def _decode_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    for source, target in [
        ("score_versions_json", "score_versions"),
        ("component_payload_json", "component_payload"),
        ("identity_json", "identity"),
        ("market_json", "market"),
        ("flow_json", "flow"),
        ("timeline_json", "timeline"),
        ("source_event_ids_json", "source_event_ids"),
        ("market_snapshot_ids_json", "market_snapshot_ids"),
        ("data_health_json", "data_health"),
        ("risks_json", "risks"),
    ]:
        row[target] = _loads(row.pop(source))
    return row


def _decode_outcome(row: dict[str, Any]) -> dict[str, Any]:
    row["benchmark_snapshot_ids"] = _loads(row.pop("benchmark_snapshot_ids_json"))
    return row


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _loads(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return json.loads(value)


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)
