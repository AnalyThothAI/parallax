from __future__ import annotations

from typing import Any

from parallax.domains.pulse_lab.repositories._pulse_repository_shared import (
    PulseAdmissionClaim,
    _clean,
    _json,
    _optional_row,
    _row,
    _run_repository_write,
    _stable_hash,
    _stable_strings,
    _transaction,
)


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("pulse_admission_repository_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int) or rowcount < 0:
        raise TypeError("pulse_admission_repository_rowcount_invalid")
    return rowcount


def _single_returning_rowcount(cursor: Any, row: Any) -> int:
    count = _cursor_rowcount(cursor)
    if count > 1 or count != int(row is not None):
        raise TypeError("pulse_admission_repository_rowcount_invalid")
    return count


def _required_returning_row(cursor: Any, row: Any) -> dict[str, Any]:
    if _single_returning_rowcount(cursor, row) != 1:
        raise TypeError("pulse_admission_repository_rowcount_invalid")
    return _row(row)


def _optional_returning_row(cursor: Any, row: Any) -> dict[str, Any] | None:
    _single_returning_rowcount(cursor, row)
    return _row(row) if row is not None else None


def _required_positive_int(value: Any, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(error_code)
    return int(value)


class PulseAdmissionRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def edge_state_by_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM pulse_candidate_edge_state
            WHERE candidate_id = %s
            """,
            (candidate_id,),
        ).fetchone()
        return _optional_row(row)

    def record_edge_observation(
        self,
        *,
        candidate_id: str,
        current_state_json: dict[str, Any],
        edge_signature: str,
        observed_at_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        def _record_edge_observation() -> dict[str, Any]:
            observed = int(observed_at_ms)
            cursor = self.conn.execute(
                """
                INSERT INTO pulse_candidate_edge_state(
                  candidate_id, latest_observed_state_json, last_processed_state_json,
                  last_edge_events_json, last_edge_signature, observed_at_ms,
                  created_at_ms, updated_at_ms
                )
                VALUES (%s, %s, '{}'::jsonb, '[]'::jsonb, %s, %s, %s, %s)
                ON CONFLICT(candidate_id) DO UPDATE SET
                  latest_observed_state_json = excluded.latest_observed_state_json,
                  last_edge_signature = excluded.last_edge_signature,
                  observed_at_ms = excluded.observed_at_ms,
                  updated_at_ms = excluded.updated_at_ms
                RETURNING *
                """,
                (candidate_id, _json(current_state_json), edge_signature, observed, observed, observed),
            )
            row = cursor.fetchone()
            return _required_returning_row(cursor, row)

        return _run_repository_write(self.conn, commit, _record_edge_observation)

    def claim_edge_budget(
        self,
        *,
        candidate_id: str,
        hour_bucket_ms: int,
        now_ms: int,
        max_enqueues: int = 3,
        commit: bool = True,
    ) -> bool:
        enqueue_limit = _required_positive_int(max_enqueues, "pulse_edge_budget_max_enqueues_required")

        def _claim_edge_budget() -> bool:
            now = int(now_ms)
            cursor = self.conn.execute(
                """
                INSERT INTO pulse_candidate_run_budget(
                  candidate_id, hour_bucket_ms, enqueue_count, created_at_ms, updated_at_ms
                )
                VALUES (%s, %s, 1, %s, %s)
                ON CONFLICT(candidate_id, hour_bucket_ms) DO UPDATE SET
                  enqueue_count = pulse_candidate_run_budget.enqueue_count + 1,
                  updated_at_ms = excluded.updated_at_ms
                WHERE pulse_candidate_run_budget.enqueue_count < %s
                RETURNING enqueue_count
                """,
                (candidate_id, int(hour_bucket_ms), now, now, enqueue_limit),
            )
            row = cursor.fetchone()
            return _single_returning_rowcount(cursor, row) == 1

        return _run_repository_write(self.conn, commit, _claim_edge_budget)

    def mark_edge_job_enqueued(
        self,
        *,
        candidate_id: str,
        processed_state_json: dict[str, Any],
        edge_events_json: list[Any],
        job_id: str,
        processed_at_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        def _mark_edge_job_enqueued() -> dict[str, Any]:
            processed = int(processed_at_ms)
            cursor = self.conn.execute(
                """
                INSERT INTO pulse_candidate_edge_state(
                  candidate_id, latest_observed_state_json, last_processed_state_json,
                  last_edge_events_json, last_job_id, observed_at_ms,
                  created_at_ms, updated_at_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(candidate_id) DO UPDATE SET
                  last_edge_events_json = excluded.last_edge_events_json,
                  last_job_id = excluded.last_job_id,
                  last_suppressed_reason = NULL,
                  last_suppressed_at_ms = NULL,
                  pending_score_band = NULL,
                  pending_score_band_count = 0,
                  updated_at_ms = excluded.updated_at_ms
                RETURNING *
                """,
                (
                    candidate_id,
                    _json(processed_state_json),
                    _json({}),
                    _json(edge_events_json),
                    job_id,
                    processed,
                    processed,
                    processed,
                ),
            )
            row = cursor.fetchone()
            return _required_returning_row(cursor, row)

        return _run_repository_write(self.conn, commit, _mark_edge_job_enqueued)

    def mark_edge_budget_rejected(
        self,
        *,
        candidate_id: str,
        edge_events_json: list[Any],
        rejected_at_ms: int,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        def _mark_edge_budget_rejected() -> dict[str, Any] | None:
            cursor = self.conn.execute(
                """
                UPDATE pulse_candidate_edge_state
                SET last_edge_events_json = %s,
                    updated_at_ms = %s
                WHERE candidate_id = %s
                RETURNING *
                """,
                (_json(edge_events_json), int(rejected_at_ms), candidate_id),
            )
            row = cursor.fetchone()
            return _optional_returning_row(cursor, row)

        return _run_repository_write(self.conn, commit, _mark_edge_budget_rejected)

    def claim_pulse_admission(
        self,
        *,
        candidate_id: str,
        target_type: str | None,
        target_id: str | None,
        hour_bucket_ms: int,
        now_ms: int,
        target_limit: int,
        candidate_limit: int,
        edge_state: dict[str, Any],
        edge_events: list[str] | tuple[str, ...],
        admission_action: str = "enqueue_agent",
        admission_reason: str = "material_edge",
        commit: bool = True,
    ) -> PulseAdmissionClaim:
        del commit
        now = int(now_ms)
        events = _stable_strings(edge_events)
        with _transaction(self.conn):
            self.record_edge_observation(
                candidate_id=candidate_id,
                current_state_json=edge_state,
                edge_signature=_stable_hash(edge_state),
                observed_at_ms=now,
                commit=False,
            )
            if admission_action != "enqueue_agent":
                self._mark_edge_suppressed(
                    candidate_id=candidate_id,
                    reason=admission_reason,
                    edge_events_json=events,
                    current_state_json=edge_state,
                    suppressed_at_ms=now,
                )
                return PulseAdmissionClaim(False, admission_reason)
            if not target_type or not target_id or int(target_limit) <= 0:
                self._mark_edge_suppressed(
                    candidate_id=candidate_id,
                    reason="target_budget_exhausted",
                    edge_events_json=events,
                    current_state_json=edge_state,
                    suppressed_at_ms=now,
                )
                return PulseAdmissionClaim(False, "target_budget_exhausted")
            if int(candidate_limit) <= 0:
                self._mark_edge_suppressed(
                    candidate_id=candidate_id,
                    reason="candidate_budget_exhausted",
                    edge_events_json=events,
                    current_state_json=edge_state,
                    suppressed_at_ms=now,
                )
                return PulseAdmissionClaim(False, "candidate_budget_exhausted")

            target_count = self._locked_target_budget_count(
                target_type=target_type,
                target_id=target_id,
                hour_bucket_ms=hour_bucket_ms,
                now_ms=now,
            )
            candidate_count = self._locked_candidate_budget_count(
                candidate_id=candidate_id,
                hour_bucket_ms=hour_bucket_ms,
                now_ms=now,
            )
            if target_count >= int(target_limit):
                self._mark_edge_suppressed(
                    candidate_id=candidate_id,
                    reason="target_budget_exhausted",
                    edge_events_json=events,
                    current_state_json=edge_state,
                    suppressed_at_ms=now,
                )
                return PulseAdmissionClaim(False, "target_budget_exhausted")
            if candidate_count >= int(candidate_limit):
                self._mark_edge_suppressed(
                    candidate_id=candidate_id,
                    reason="candidate_budget_exhausted",
                    edge_events_json=events,
                    current_state_json=edge_state,
                    suppressed_at_ms=now,
                )
                return PulseAdmissionClaim(False, "candidate_budget_exhausted")

            self._increment_target_budget(
                target_type=target_type,
                target_id=target_id,
                hour_bucket_ms=hour_bucket_ms,
                now_ms=now,
            )
            self._increment_candidate_budget(
                candidate_id=candidate_id,
                hour_bucket_ms=hour_bucket_ms,
                now_ms=now,
            )
            return PulseAdmissionClaim(True, admission_reason)

    def _locked_target_budget_count(
        self,
        *,
        target_type: str,
        target_id: str,
        hour_bucket_ms: int,
        now_ms: int,
    ) -> int:
        self.conn.execute(
            """
            INSERT INTO pulse_target_run_budget(
              target_type, target_id, hour_bucket_ms, enqueue_count, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, 0, %s, %s)
            ON CONFLICT(target_type, target_id, hour_bucket_ms) DO NOTHING
            """,
            (target_type, target_id, int(hour_bucket_ms), int(now_ms), int(now_ms)),
        )
        row = self.conn.execute(
            """
            SELECT enqueue_count
            FROM pulse_target_run_budget
            WHERE target_type = %s AND target_id = %s AND hour_bucket_ms = %s
            FOR UPDATE
            """,
            (target_type, target_id, int(hour_bucket_ms)),
        ).fetchone()
        return int(row["enqueue_count"] if row else 0)

    def _locked_candidate_budget_count(
        self,
        *,
        candidate_id: str,
        hour_bucket_ms: int,
        now_ms: int,
    ) -> int:
        self.conn.execute(
            """
            INSERT INTO pulse_candidate_run_budget(
              candidate_id, hour_bucket_ms, enqueue_count, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, 0, %s, %s)
            ON CONFLICT(candidate_id, hour_bucket_ms) DO NOTHING
            """,
            (candidate_id, int(hour_bucket_ms), int(now_ms), int(now_ms)),
        )
        row = self.conn.execute(
            """
            SELECT enqueue_count
            FROM pulse_candidate_run_budget
            WHERE candidate_id = %s AND hour_bucket_ms = %s
            FOR UPDATE
            """,
            (candidate_id, int(hour_bucket_ms)),
        ).fetchone()
        return int(row["enqueue_count"] if row else 0)

    def _increment_target_budget(
        self,
        *,
        target_type: str,
        target_id: str,
        hour_bucket_ms: int,
        now_ms: int,
    ) -> None:
        self.conn.execute(
            """
            UPDATE pulse_target_run_budget
            SET enqueue_count = enqueue_count + 1,
                updated_at_ms = %s
            WHERE target_type = %s AND target_id = %s AND hour_bucket_ms = %s
            """,
            (int(now_ms), target_type, target_id, int(hour_bucket_ms)),
        )

    def _increment_candidate_budget(
        self,
        *,
        candidate_id: str,
        hour_bucket_ms: int,
        now_ms: int,
    ) -> None:
        self.conn.execute(
            """
            UPDATE pulse_candidate_run_budget
            SET enqueue_count = enqueue_count + 1,
                updated_at_ms = %s
            WHERE candidate_id = %s AND hour_bucket_ms = %s
            """,
            (int(now_ms), candidate_id, int(hour_bucket_ms)),
        )

    def _mark_edge_suppressed(
        self,
        *,
        candidate_id: str,
        reason: str,
        edge_events_json: list[Any],
        current_state_json: dict[str, Any],
        suppressed_at_ms: int,
    ) -> dict[str, Any] | None:
        score_band = _clean(current_state_json.get("score_band"))
        cursor = self.conn.execute(
            """
            UPDATE pulse_candidate_edge_state
            SET last_edge_events_json = %s,
                last_processed_state_json = CASE
                  WHEN %s = 'blocked_low_information' THEN %s
                  ELSE last_processed_state_json
                END,
                last_processed_at_ms = CASE
                  WHEN %s = 'blocked_low_information' THEN %s
                  ELSE last_processed_at_ms
                END,
                last_suppressed_reason = %s,
                last_suppressed_at_ms = %s,
                pending_score_band = CASE
                  WHEN %s = 'blocked_low_information' THEN NULL
                  WHEN %s = 'score_band_pending' THEN %s
                  ELSE pending_score_band
                END,
                pending_score_band_count = CASE
                  WHEN %s = 'blocked_low_information' THEN 0
                  WHEN %s = 'score_band_pending' AND pending_score_band = %s
                    THEN pending_score_band_count + 1
                  WHEN %s = 'score_band_pending'
                    THEN 1
                  ELSE pending_score_band_count
                END,
                updated_at_ms = %s
            WHERE candidate_id = %s
            RETURNING *
            """,
            (
                _json(edge_events_json),
                reason,
                _json(current_state_json),
                reason,
                int(suppressed_at_ms),
                reason,
                int(suppressed_at_ms),
                reason,
                reason,
                score_band,
                reason,
                reason,
                score_band,
                reason,
                int(suppressed_at_ms),
                candidate_id,
            ),
        )
        row = cursor.fetchone()
        return _optional_returning_row(cursor, row)

    def _mark_edge_admitted(
        self,
        *,
        candidate_id: str,
        edge_events_json: list[Any],
        job_id: str,
        admitted_at_ms: int,
    ) -> dict[str, Any] | None:
        cursor = self.conn.execute(
            """
            UPDATE pulse_candidate_edge_state
            SET last_edge_events_json = %s,
                last_job_id = %s,
                last_suppressed_reason = NULL,
                last_suppressed_at_ms = NULL,
                pending_score_band = NULL,
                pending_score_band_count = 0,
                updated_at_ms = %s
            WHERE candidate_id = %s
            RETURNING *
            """,
            (_json(edge_events_json), job_id, int(admitted_at_ms), candidate_id),
        )
        row = cursor.fetchone()
        return _optional_returning_row(cursor, row)

    def mark_edge_run_finished(
        self,
        *,
        candidate_id: str,
        agent_run_id: str,
        processed_state_json: dict[str, Any],
        edge_events_json: list[Any],
        finished_at_ms: int,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        def _mark_edge_run_finished() -> dict[str, Any] | None:
            cursor = self.conn.execute(
                """
                UPDATE pulse_candidate_edge_state
                SET last_agent_run_id = %s,
                    last_processed_state_json = %s,
                    last_edge_events_json = %s,
                    last_processed_at_ms = %s,
                    last_suppressed_reason = NULL,
                    last_suppressed_at_ms = NULL,
                    pending_score_band = NULL,
                    pending_score_band_count = 0,
                    updated_at_ms = %s
                WHERE candidate_id = %s
                RETURNING *
                """,
                (
                    agent_run_id,
                    _json(processed_state_json),
                    _json(edge_events_json),
                    int(finished_at_ms),
                    int(finished_at_ms),
                    candidate_id,
                ),
            )
            row = cursor.fetchone()
            return _optional_returning_row(cursor, row)

        return _run_repository_write(self.conn, commit, _mark_edge_run_finished)

    def recent_target_failure_count(
        self,
        *,
        target_type: str | None,
        target_id: str | None,
        since_ms: int,
        reasons: tuple[str, ...] | list[str] | set[str],
    ) -> int:
        stable_reasons = _stable_strings(reasons)
        if not target_type or not target_id or not stable_reasons:
            return 0
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS failure_count
            FROM pulse_agent_runs AS run
            JOIN pulse_agent_jobs AS job
              ON job.job_id = run.job_id
            WHERE job.target_type = %s
              AND job.target_id = %s
              AND run.status = 'failed'
              AND run.finished_at_ms >= %s
              AND run.trace_metadata_json->>'failure_reason' = ANY(%s)
            """,
            (target_type, target_id, int(since_ms), stable_reasons),
        ).fetchone()
        return int(row["failure_count"] if row else 0)
