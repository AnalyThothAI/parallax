from __future__ import annotations

from typing import Any

from parallax.domains.pulse_lab.repositories._pulse_repository_shared import (
    _json,
    _now_ms,
    _row,
)


class PulsePlaybooksRepository:
    def __init__(self, conn: Any, *, running_timeout_ms: int = 300_000):
        self.conn = conn
        self.running_timeout_ms = int(running_timeout_ms)

    def upsert_playbook_snapshot(
        self,
        *,
        playbook_id: str,
        candidate_id: str,
        horizon: str,
        decision_time_ms: int,
        playbook_status: str,
        side: str,
        setup: dict[str, Any],
        confirmation: dict[str, Any],
        invalidation: dict[str, Any],
        risk: dict[str, Any],
        playbook_version: str,
        target_type: str | None = None,
        target_id: str | None = None,
        entry_market: dict[str, Any] | None = None,
        outcome_status: str = "pending",
        created_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        created = int(created_at_ms if created_at_ms is not None else _now_ms())
        row = self.conn.execute(
            """
            INSERT INTO pulse_playbook_snapshots(
              playbook_id, candidate_id, target_type, target_id, horizon, decision_time_ms,
              playbook_status, side, setup_json, confirmation_json, invalidation_json,
              risk_json, entry_market_json, playbook_version, outcome_status, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(candidate_id, horizon, playbook_version) DO UPDATE SET
              target_type = excluded.target_type,
              target_id = excluded.target_id,
              decision_time_ms = excluded.decision_time_ms,
              playbook_status = excluded.playbook_status,
              side = excluded.side,
              setup_json = excluded.setup_json,
              confirmation_json = excluded.confirmation_json,
              invalidation_json = excluded.invalidation_json,
              risk_json = excluded.risk_json,
              entry_market_json = excluded.entry_market_json,
              outcome_status = excluded.outcome_status,
              created_at_ms = excluded.created_at_ms
            RETURNING *
            """,
            (
                playbook_id,
                candidate_id,
                target_type,
                target_id,
                horizon,
                int(decision_time_ms),
                playbook_status,
                side,
                _json(setup),
                _json(confirmation),
                _json(invalidation),
                _json(risk),
                _json(entry_market or {}),
                playbook_version,
                outcome_status,
                created,
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return _row(row)

    def upsert_playbook_outcome(
        self,
        *,
        playbook_id: str,
        settled_at_ms: int,
        actual_return: float | None = None,
        benchmark_return: float | None = None,
        abnormal_return: float | None = None,
        max_favorable_excursion: float | None = None,
        max_adverse_excursion: float | None = None,
        confirmation_hit: bool = False,
        invalidation_hit: bool = False,
        outcome: dict[str, Any] | None = None,
        outcome_json: dict[str, Any] | None = None,
        created_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        created = int(created_at_ms if created_at_ms is not None else _now_ms())
        resolved_outcome = outcome if outcome is not None else outcome_json
        row = self.conn.execute(
            """
            INSERT INTO pulse_playbook_outcomes(
              playbook_id, settled_at_ms, actual_return, benchmark_return, abnormal_return,
              max_favorable_excursion, max_adverse_excursion, confirmation_hit,
              invalidation_hit, outcome_json, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(playbook_id) DO UPDATE SET
              settled_at_ms = excluded.settled_at_ms,
              actual_return = excluded.actual_return,
              benchmark_return = excluded.benchmark_return,
              abnormal_return = excluded.abnormal_return,
              max_favorable_excursion = excluded.max_favorable_excursion,
              max_adverse_excursion = excluded.max_adverse_excursion,
              confirmation_hit = excluded.confirmation_hit,
              invalidation_hit = excluded.invalidation_hit,
              outcome_json = excluded.outcome_json,
              created_at_ms = excluded.created_at_ms
            RETURNING *
            """,
            (
                playbook_id,
                int(settled_at_ms),
                actual_return,
                benchmark_return,
                abnormal_return,
                max_favorable_excursion,
                max_adverse_excursion,
                bool(confirmation_hit),
                bool(invalidation_hit),
                _json(resolved_outcome or {}),
                created,
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return _row(row)
