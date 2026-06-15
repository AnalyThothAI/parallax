from __future__ import annotations

from typing import Any

from parallax.domains.pulse_lab.repositories._pulse_repository_shared import (
    _json,
    _now_ms,
    _row,
    _run_repository_write,
)


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("pulse_playbooks_repository_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int) or rowcount < 0:
        raise TypeError("pulse_playbooks_repository_rowcount_invalid")
    return rowcount


def _required_returning_row(cursor: Any, row: Any) -> dict[str, Any]:
    if _cursor_rowcount(cursor) != 1 or row is None:
        raise TypeError("pulse_playbooks_repository_rowcount_invalid")
    return _row(row)


def _optional_returning_row(cursor: Any, row: Any) -> dict[str, Any] | None:
    count = _cursor_rowcount(cursor)
    if count > 1 or (count == 0 and row is not None) or (count == 1 and row is None):
        raise TypeError("pulse_playbooks_repository_rowcount_invalid")
    return _row(row) if row is not None else None


class PulsePlaybooksRepository:
    def __init__(self, conn: Any):
        self.conn = conn

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
    ) -> dict[str, Any] | None:
        def _upsert_playbook_snapshot() -> dict[str, Any] | None:
            created = int(created_at_ms if created_at_ms is not None else _now_ms())
            cursor = self.conn.execute(
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
                WHERE (
                  pulse_playbook_snapshots.target_type,
                  pulse_playbook_snapshots.target_id,
                  pulse_playbook_snapshots.playbook_status,
                  pulse_playbook_snapshots.side,
                  pulse_playbook_snapshots.setup_json,
                  pulse_playbook_snapshots.confirmation_json,
                  pulse_playbook_snapshots.invalidation_json,
                  pulse_playbook_snapshots.risk_json,
                  pulse_playbook_snapshots.entry_market_json,
                  pulse_playbook_snapshots.outcome_status
                ) IS DISTINCT FROM (
                  excluded.target_type,
                  excluded.target_id,
                  excluded.playbook_status,
                  excluded.side,
                  excluded.setup_json,
                  excluded.confirmation_json,
                  excluded.invalidation_json,
                  excluded.risk_json,
                  excluded.entry_market_json,
                  excluded.outcome_status
                )
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
            )
            row = cursor.fetchone()
            return _optional_returning_row(cursor, row)

        return _run_repository_write(self.conn, commit, _upsert_playbook_snapshot)

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
        def _upsert_playbook_outcome() -> dict[str, Any]:
            created = int(created_at_ms if created_at_ms is not None else _now_ms())
            resolved_outcome = outcome if outcome is not None else outcome_json
            cursor = self.conn.execute(
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
            )
            row = cursor.fetchone()
            return _required_returning_row(cursor, row)

        return _run_repository_write(self.conn, commit, _upsert_playbook_outcome)
