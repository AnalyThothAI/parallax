from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from datetime import date
from typing import Any, TypedDict

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.macro_intel._constants import MACRO_VIEW_PROJECTION_VERSION


class MacroSeriesRefreshResult(TypedDict):
    status: str
    rows_written: int
    source_rows: int
    source_signature: str


class MacroIntelRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_observation(self, observation: Mapping[str, Any]) -> str:
        observation_id = str(observation.get("observation_id") or _observation_id(observation))
        self.conn.execute(
            """
            INSERT INTO macro_observations(
              observation_id, source_name, concept_key, series_key, source_priority, observed_at, value_numeric, unit,
              frequency, data_quality, source_ts, raw_payload_json, ingested_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(concept_key, observed_at, source_name, series_key) DO UPDATE SET
              source_priority = excluded.source_priority,
              value_numeric = excluded.value_numeric,
              unit = excluded.unit,
              frequency = excluded.frequency,
              data_quality = excluded.data_quality,
              source_ts = excluded.source_ts,
              raw_payload_json = excluded.raw_payload_json,
              ingested_at_ms = excluded.ingested_at_ms
            """,
            (
                observation_id,
                str(observation["source_name"]),
                str(observation["concept_key"]),
                str(observation["series_key"]),
                int(observation["source_priority"]),
                observation["observed_at"],
                observation.get("value_numeric"),
                observation.get("unit"),
                observation.get("frequency"),
                str(observation.get("data_quality") or "ok"),
                observation.get("source_ts"),
                Jsonb(dict(observation.get("raw_payload") or observation.get("raw_payload_json") or {})),
                int(observation["ingested_at_ms"]),
            ),
        )
        return observation_id

    def record_import_run(self, import_run: Mapping[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO macro_import_runs(
              run_id, source_name, bundle_name, asof_date, status, observations_count,
              coverage_json, missing_series_json, series_errors_json, reason_codes_json,
              started_at_ms, completed_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(run_id) DO UPDATE SET
              source_name = excluded.source_name,
              bundle_name = excluded.bundle_name,
              asof_date = excluded.asof_date,
              status = excluded.status,
              observations_count = excluded.observations_count,
              coverage_json = excluded.coverage_json,
              missing_series_json = excluded.missing_series_json,
              series_errors_json = excluded.series_errors_json,
              reason_codes_json = excluded.reason_codes_json,
              started_at_ms = excluded.started_at_ms,
              completed_at_ms = excluded.completed_at_ms
            """,
            (
                str(import_run["run_id"]),
                str(import_run["source_name"]),
                str(import_run["bundle_name"]),
                import_run.get("asof_date"),
                str(import_run["status"]),
                int(import_run.get("observations_count") or 0),
                Jsonb(dict(import_run.get("coverage_json") or {})),
                Jsonb(list(import_run.get("missing_series_json") or [])),
                Jsonb(list(import_run.get("series_errors_json") or [])),
                Jsonb(list(import_run.get("reason_codes_json") or [])),
                int(import_run["started_at_ms"]),
                int(import_run["completed_at_ms"]),
            ),
        )

    def enqueue_macro_sync_window(
        self,
        *,
        source_name: str,
        bundle_name: str,
        window_start: date,
        window_end: date,
        trigger_reason: str,
        priority: int,
        due_at_ms: int,
        max_attempts: int,
        now_ms: int,
    ) -> str:
        sync_window_id = _sync_window_id(
            source_name=source_name,
            bundle_name=bundle_name,
            window_start=window_start,
            window_end=window_end,
            trigger_reason=trigger_reason,
        )
        payload_hash = _payload_hash(
            source_name=source_name,
            bundle_name=bundle_name,
            window_start=window_start,
            window_end=window_end,
            trigger_reason=trigger_reason,
        )
        row = self.conn.execute(
            """
            INSERT INTO macro_sync_windows(
              sync_window_id,
              source_name,
              bundle_name,
              window_start,
              window_end,
              trigger_reason,
              status,
              payload_hash,
              priority,
              due_at_ms,
              attempt_count,
              max_attempts,
              created_at_ms,
              updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s, 0, %s, %s, %s)
            ON CONFLICT(source_name, bundle_name, window_start, window_end, trigger_reason) DO UPDATE
              SET priority = LEAST(macro_sync_windows.priority, excluded.priority),
                  due_at_ms = LEAST(macro_sync_windows.due_at_ms, excluded.due_at_ms),
                  max_attempts = GREATEST(macro_sync_windows.max_attempts, excluded.max_attempts),
                  payload_hash = excluded.payload_hash,
                  updated_at_ms = CASE
                    WHEN macro_sync_windows.status IN ('pending', 'retryable')
                    THEN excluded.updated_at_ms
                    ELSE macro_sync_windows.updated_at_ms
                  END
            RETURNING sync_window_id
            """,
            (
                sync_window_id,
                str(source_name),
                str(bundle_name),
                window_start,
                window_end,
                str(trigger_reason),
                payload_hash,
                int(priority),
                int(due_at_ms),
                int(max_attempts),
                int(now_ms),
                int(now_ms),
            ),
        ).fetchone()
        return str(dict(row or {})["sync_window_id"])

    def claim_macro_sync_window(
        self,
        *,
        lease_owner: str,
        lease_ms: int,
        now_ms: int,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            WITH expired_terminal AS (
              UPDATE macro_sync_windows
                 SET status = 'failed',
                     leased_until_ms = NULL,
                     lease_owner = NULL,
                     last_error_code = 'macro_sync_lease_expired_attempt_budget_exhausted',
                     last_error_message = 'macro sync window lease expired after max attempts',
                     completed_at_ms = %s,
                     updated_at_ms = %s
               WHERE status = 'running'
                 AND leased_until_ms IS NOT NULL
                 AND leased_until_ms <= %s
                 AND attempt_count >= max_attempts
              RETURNING sync_window_id
            ),
            candidate AS (
              SELECT sync_window_id
              FROM macro_sync_windows
              WHERE (
                  (
                    status IN ('pending', 'retryable')
                    AND due_at_ms <= %s
                    AND (leased_until_ms IS NULL OR leased_until_ms <= %s)
                  )
                  OR (status = 'running' AND leased_until_ms IS NOT NULL AND leased_until_ms <= %s)
                )
                AND attempt_count < max_attempts
              ORDER BY priority ASC, due_at_ms ASC, updated_at_ms ASC, sync_window_id ASC
              FOR UPDATE SKIP LOCKED
              LIMIT 1
            )
            UPDATE macro_sync_windows AS sync_window
            SET status = 'running',
                lease_owner = %s,
                leased_until_ms = %s,
                attempt_count = sync_window.attempt_count + 1,
                updated_at_ms = %s
            FROM candidate
            WHERE sync_window.sync_window_id = candidate.sync_window_id
            RETURNING sync_window.*
            """,
            (
                int(now_ms),
                int(now_ms),
                int(now_ms),
                int(now_ms),
                int(now_ms),
                int(now_ms),
                str(lease_owner),
                int(now_ms) + int(lease_ms),
                int(now_ms),
            ),
        ).fetchone()
        return dict(row) if row is not None else None

    def claim_macro_sync_window_by_id(
        self,
        *,
        sync_window_id: str,
        lease_owner: str,
        lease_ms: int,
        now_ms: int,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            WITH candidate AS (
              SELECT sync_window_id
              FROM macro_sync_windows
              WHERE sync_window_id = %s
                AND (
                  (
                    status IN ('pending', 'retryable')
                    AND due_at_ms <= %s
                    AND (leased_until_ms IS NULL OR leased_until_ms <= %s)
                  )
                  OR (status = 'running' AND leased_until_ms IS NOT NULL AND leased_until_ms <= %s)
                )
                AND attempt_count < max_attempts
              FOR UPDATE SKIP LOCKED
              LIMIT 1
            )
            UPDATE macro_sync_windows AS sync_window
            SET status = 'running',
                lease_owner = %s,
                leased_until_ms = %s,
                attempt_count = sync_window.attempt_count + 1,
                updated_at_ms = %s
            FROM candidate
            WHERE sync_window.sync_window_id = candidate.sync_window_id
            RETURNING sync_window.*
            """,
            (
                str(sync_window_id),
                int(now_ms),
                int(now_ms),
                int(now_ms),
                str(lease_owner),
                int(now_ms) + int(lease_ms),
                int(now_ms),
            ),
        ).fetchone()
        return dict(row) if row is not None else None

    def record_macro_sync_run(self, run: Mapping[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO macro_sync_runs(
              sync_run_id,
              sync_window_id,
              source_name,
              bundle_name,
              requested_start,
              requested_end,
              status,
              import_run_id,
              asof_date,
              max_observed_at,
              observations_count,
              imported_observation_count,
              coverage_json,
              missing_series_json,
              series_errors_json,
              reason_codes_json,
              diagnostics_json,
              fred_api_key_env,
              fred_api_key_configured,
              error_code,
              error_message,
              started_at_ms,
              completed_at_ms,
              duration_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(sync_run_id) DO UPDATE SET
              sync_window_id = excluded.sync_window_id,
              source_name = excluded.source_name,
              bundle_name = excluded.bundle_name,
              requested_start = excluded.requested_start,
              requested_end = excluded.requested_end,
              status = excluded.status,
              import_run_id = excluded.import_run_id,
              asof_date = excluded.asof_date,
              max_observed_at = excluded.max_observed_at,
              observations_count = excluded.observations_count,
              imported_observation_count = excluded.imported_observation_count,
              coverage_json = excluded.coverage_json,
              missing_series_json = excluded.missing_series_json,
              series_errors_json = excluded.series_errors_json,
              reason_codes_json = excluded.reason_codes_json,
              diagnostics_json = excluded.diagnostics_json,
              fred_api_key_env = excluded.fred_api_key_env,
              fred_api_key_configured = excluded.fred_api_key_configured,
              error_code = excluded.error_code,
              error_message = excluded.error_message,
              started_at_ms = excluded.started_at_ms,
              completed_at_ms = excluded.completed_at_ms,
              duration_ms = excluded.duration_ms
            """,
            (
                str(run["sync_run_id"]),
                run.get("sync_window_id"),
                str(run["source_name"]),
                str(run["bundle_name"]),
                run["requested_start"],
                run["requested_end"],
                str(run["status"]),
                run.get("import_run_id"),
                run.get("asof_date"),
                run.get("max_observed_at"),
                int(run.get("observations_count") or 0),
                int(run.get("imported_observation_count") or 0),
                Jsonb(dict(run.get("coverage_json") or {})),
                Jsonb(list(run.get("missing_series_json") or [])),
                Jsonb(list(run.get("series_errors_json") or [])),
                Jsonb(list(run.get("reason_codes_json") or [])),
                Jsonb(dict(run.get("diagnostics_json") or {})),
                run.get("fred_api_key_env"),
                bool(run.get("fred_api_key_configured") or False),
                run.get("error_code"),
                run.get("error_message"),
                int(run["started_at_ms"]),
                int(run["completed_at_ms"]),
                int(run["duration_ms"]),
            ),
        )

    def complete_macro_sync_window(
        self,
        *,
        sync_window_id: str,
        lease_owner: str,
        attempt_count: int,
        sync_run_id: str,
        completed_at_ms: int,
    ) -> bool:
        cursor = self.conn.execute(
            """
            UPDATE macro_sync_windows
               SET status = 'done',
                   leased_until_ms = NULL,
                   lease_owner = NULL,
                   last_error_code = NULL,
                   last_error_message = NULL,
                   last_run_id = %s,
                   completed_at_ms = %s,
                   updated_at_ms = %s
             WHERE sync_window_id = %s
               AND lease_owner = %s
               AND attempt_count = %s
            """,
            (
                str(sync_run_id),
                int(completed_at_ms),
                int(completed_at_ms),
                str(sync_window_id),
                str(lease_owner),
                int(attempt_count),
            ),
        )
        return int(getattr(cursor, "rowcount", 0) or 0) > 0

    def retry_macro_sync_window(
        self,
        *,
        sync_window_id: str,
        lease_owner: str,
        attempt_count: int,
        sync_run_id: str | None,
        error_code: str,
        error_message: str,
        retry_delay_ms: int,
        now_ms: int,
    ) -> bool:
        cursor = self.conn.execute(
            """
            UPDATE macro_sync_windows
               SET status = CASE WHEN attempt_count >= max_attempts THEN 'failed' ELSE 'retryable' END,
                   leased_until_ms = NULL,
                   lease_owner = NULL,
                   last_error_code = %s,
                   last_error_message = %s,
                   last_run_id = %s,
                   due_at_ms = CASE WHEN attempt_count >= max_attempts THEN due_at_ms ELSE %s END,
                   completed_at_ms = CASE WHEN attempt_count >= max_attempts THEN %s ELSE completed_at_ms END,
                   updated_at_ms = %s
             WHERE sync_window_id = %s
               AND lease_owner = %s
               AND attempt_count = %s
            """,
            (
                str(error_code),
                str(error_message),
                sync_run_id,
                int(now_ms) + int(retry_delay_ms),
                int(now_ms),
                int(now_ms),
                str(sync_window_id),
                str(lease_owner),
                int(attempt_count),
            ),
        )
        return int(getattr(cursor, "rowcount", 0) or 0) > 0

    def fail_macro_sync_window(
        self,
        *,
        sync_window_id: str,
        lease_owner: str,
        attempt_count: int,
        sync_run_id: str | None,
        error_code: str,
        error_message: str,
        now_ms: int,
    ) -> bool:
        cursor = self.conn.execute(
            """
            UPDATE macro_sync_windows
               SET status = 'failed',
                   leased_until_ms = NULL,
                   lease_owner = NULL,
                   last_error_code = %s,
                   last_error_message = %s,
                   last_run_id = %s,
                   completed_at_ms = %s,
                   updated_at_ms = %s
             WHERE sync_window_id = %s
               AND lease_owner = %s
               AND attempt_count = %s
            """,
            (
                str(error_code),
                str(error_message),
                sync_run_id,
                int(now_ms),
                int(now_ms),
                str(sync_window_id),
                str(lease_owner),
                int(attempt_count),
            ),
        )
        return int(getattr(cursor, "rowcount", 0) or 0) > 0

    def latest_macro_sync_run(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM macro_sync_runs
            ORDER BY completed_at_ms DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row is not None else None

    def macro_sync_queue_summary(self, *, now_ms: int) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT
              COUNT(*) FILTER (
                WHERE status IN ('pending', 'retryable')
                  AND attempt_count < max_attempts
              )::int AS open_count,
              COUNT(*) FILTER (
                WHERE status IN ('pending', 'retryable')
                  AND due_at_ms <= %s
                  AND attempt_count < max_attempts
              )::int AS due_count,
              COUNT(*) FILTER (WHERE status = 'running')::int AS running_count,
              COUNT(*) FILTER (
                WHERE status = 'running'
                  AND leased_until_ms IS NOT NULL
                  AND leased_until_ms <= %s
                  AND attempt_count < max_attempts
              )::int AS expired_running_count,
              COUNT(*) FILTER (
                WHERE status = 'running'
                  AND leased_until_ms IS NOT NULL
                  AND leased_until_ms <= %s
                  AND attempt_count >= max_attempts
              )::int AS expired_running_exhausted_count,
              COUNT(*) FILTER (
                WHERE status IN ('pending', 'retryable')
                  AND attempt_count >= max_attempts
              )::int AS exhausted_count,
              COUNT(*) FILTER (WHERE status = 'failed')::int AS failed_count
            FROM macro_sync_windows
            """,
            (int(now_ms), int(now_ms), int(now_ms)),
        ).fetchone()
        return dict(row or {})

    def macro_observations_max_observed_at(self) -> date | None:
        row = self.conn.execute(
            """
            SELECT MAX(observed_at) AS max_observed_at
            FROM macro_observations
            """
        ).fetchone()
        return dict(row or {}).get("max_observed_at")

    def latest_observations(
        self,
        *,
        limit: int = 250,
        concept_keys: Sequence[str] | None = None,
        projection_version: str = MACRO_VIEW_PROJECTION_VERSION,
    ) -> list[dict[str, Any]]:
        bounded_limit = max(1, int(limit))
        if concept_keys:
            rows = self.conn.execute(
                """
                SELECT rows.*
                FROM macro_observation_series_rows AS rows
                WHERE rows.projection_version = %s
                  AND rows.concept_key = ANY(%s)
                  AND rows.series_rank = 1
                ORDER BY rows.concept_key ASC
                LIMIT %s
                """,
                (projection_version, list(concept_keys), bounded_limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT rows.*
                FROM macro_observation_series_rows AS rows
                WHERE rows.projection_version = %s
                  AND rows.series_rank = 1
                ORDER BY rows.concept_key ASC
                LIMIT %s
                """,
                (projection_version, bounded_limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def refresh_observation_series_rows(
        self,
        *,
        projection_version: str,
        now_ms: int,
        lookback_days: int,
        limit_per_series: int,
    ) -> MacroSeriesRefreshResult:
        bounded_lookback_days = max(1, int(lookback_days))
        bounded_limit_per_series = max(1, int(limit_per_series))
        selected_rows = self._select_observation_series_rows(
            projection_version=projection_version,
            lookback_days=bounded_lookback_days,
            limit_per_series=bounded_limit_per_series,
            projected_at_ms=int(now_ms),
        )
        source_signature = _series_source_signature(
            projection_version=projection_version,
            lookback_days=bounded_lookback_days,
            limit_per_series=bounded_limit_per_series,
            rows=selected_rows,
        )
        if not selected_rows:
            self._upsert_macro_series_publication_state(
                projection_version=projection_version,
                status="failed",
                source_signature=source_signature,
                row_count=0,
                started_at_ms=int(now_ms),
                finished_at_ms=int(now_ms),
                latest_attempt_error="macro_observation_series_empty",
            )
            raise RuntimeError("macro_observation_series_empty")

        current_state = self._macro_series_publication_state(projection_version)
        if current_state and current_state.get("source_signature") == source_signature:
            self._upsert_macro_series_publication_state(
                projection_version=projection_version,
                status="unchanged",
                source_signature=source_signature,
                row_count=len(selected_rows),
                started_at_ms=int(now_ms),
                finished_at_ms=int(now_ms),
                latest_attempt_error=None,
            )
            return {
                "status": "unchanged",
                "rows_written": 0,
                "source_rows": len(selected_rows),
                "source_signature": source_signature,
            }

        with _transaction_context(self.conn):
            self.conn.execute(
                """
                DELETE FROM macro_observation_series_rows
                WHERE projection_version = %s
                """,
                (projection_version,),
            )
            rows_written = self._insert_observation_series_rows(selected_rows)
            self._upsert_macro_series_publication_state(
                projection_version=projection_version,
                status="published",
                source_signature=source_signature,
                row_count=len(selected_rows),
                started_at_ms=int(now_ms),
                finished_at_ms=int(now_ms),
                latest_attempt_error=None,
            )
        return {
            "status": "published",
            "rows_written": rows_written,
            "source_rows": len(selected_rows),
            "source_signature": source_signature,
        }

    def _select_observation_series_rows(
        self,
        *,
        projection_version: str,
        lookback_days: int,
        limit_per_series: int,
        projected_at_ms: int,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH source_ranked AS (
              SELECT
                concept_key,
                observed_at,
                value_numeric,
                source_name,
                series_key,
                source_priority,
                unit,
                frequency,
                data_quality,
                source_ts,
                raw_payload_json,
                ingested_at_ms,
                row_number() OVER (
                  PARTITION BY concept_key, observed_at
                  ORDER BY source_priority DESC, source_ts DESC NULLS LAST, ingested_at_ms DESC
                ) AS dedupe_rank
              FROM macro_observations
              WHERE observed_at >= CURRENT_DATE - %s::int
                AND value_numeric IS NOT NULL
            ),
            series_ranked AS (
              SELECT
                *,
                row_number() OVER (
                  PARTITION BY concept_key
                  ORDER BY observed_at DESC
                ) AS series_rank
              FROM source_ranked
              WHERE dedupe_rank = 1
            )
            SELECT
              %s AS projection_version,
              concept_key,
              observed_at,
              series_rank,
              value_numeric,
              source_name,
              series_key,
              source_priority,
              unit,
              frequency,
              data_quality,
              source_ts,
              COALESCE(raw_payload_json, '{}'::jsonb) AS raw_payload_json,
              ingested_at_ms,
              %s AS projected_at_ms
            FROM series_ranked
            WHERE series_rank <= %s
            ORDER BY concept_key ASC, observed_at DESC
            """,
            (int(lookback_days), projection_version, int(projected_at_ms), int(limit_per_series)),
        ).fetchall()
        return [dict(row) for row in rows]

    def _insert_observation_series_rows(self, rows: Sequence[Mapping[str, Any]]) -> int:
        if not rows:
            return 0
        values_sql = ",".join(["(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(rows))
        params: list[Any] = []
        for row in rows:
            params.extend(
                [
                    row["projection_version"],
                    row["concept_key"],
                    row["observed_at"],
                    int(row["series_rank"]),
                    row["value_numeric"],
                    row["source_name"],
                    row["series_key"],
                    int(row["source_priority"]),
                    row.get("unit"),
                    row.get("frequency"),
                    row.get("data_quality"),
                    row.get("source_ts"),
                    Jsonb(dict(row.get("raw_payload_json") or {})),
                    int(row["ingested_at_ms"]),
                    int(row["projected_at_ms"]),
                ]
            )
        cursor = self.conn.execute(
            f"""
            INSERT INTO macro_observation_series_rows(
              projection_version,
              concept_key,
              observed_at,
              series_rank,
              value_numeric,
              source_name,
              series_key,
              source_priority,
              unit,
              frequency,
              data_quality,
              source_ts,
              raw_payload_json,
              ingested_at_ms,
              projected_at_ms
            )
            VALUES {values_sql}
            """,
            tuple(params),
        )
        rowcount = getattr(cursor, "rowcount", None)
        if rowcount is None or int(rowcount) < 0:
            return len(rows)
        return int(rowcount)

    def _macro_series_publication_state(self, projection_version: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM macro_observation_series_publication_state
            WHERE projection_version = %s
            """,
            (projection_version,),
        ).fetchone()
        return dict(row) if row is not None else None

    def _upsert_macro_series_publication_state(
        self,
        *,
        projection_version: str,
        status: str,
        source_signature: str,
        row_count: int,
        started_at_ms: int,
        finished_at_ms: int,
        latest_attempt_error: str | None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO macro_observation_series_publication_state(
              projection_version,
              source_signature,
              row_count,
              latest_attempt_status,
              latest_attempt_started_at_ms,
              latest_attempt_finished_at_ms,
              latest_attempt_error,
              updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (projection_version) DO UPDATE SET
              source_signature = excluded.source_signature,
              row_count = excluded.row_count,
              latest_attempt_status = excluded.latest_attempt_status,
              latest_attempt_started_at_ms = excluded.latest_attempt_started_at_ms,
              latest_attempt_finished_at_ms = excluded.latest_attempt_finished_at_ms,
              latest_attempt_error = excluded.latest_attempt_error,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                projection_version,
                source_signature,
                int(row_count),
                status,
                int(started_at_ms),
                int(finished_at_ms),
                latest_attempt_error,
                int(finished_at_ms),
            ),
        )

    def observations_for_concepts(
        self,
        *,
        concept_keys: Sequence[str],
        lookback_days: int,
        limit_per_series: int,
        projection_version: str = MACRO_VIEW_PROJECTION_VERSION,
    ) -> list[dict[str, Any]]:
        bounded_lookback_days = max(1, int(lookback_days))
        bounded_limit_per_series = max(1, int(limit_per_series))
        rows = self.conn.execute(
            """
            SELECT rows.*
            FROM macro_observation_series_rows AS rows
            WHERE rows.projection_version = %s
              AND rows.concept_key = ANY(%s)
              AND rows.observed_at >= CURRENT_DATE - %s::int
              AND rows.series_rank <= %s
            ORDER BY rows.concept_key ASC, rows.observed_at DESC, rows.series_rank ASC
            """,
            (projection_version, list(concept_keys), bounded_lookback_days, bounded_limit_per_series),
        ).fetchall()
        return [dict(row) for row in rows]

    def concept_history_counts(
        self,
        concept_keys: Sequence[str],
        lookback_days: int,
        projection_version: str = MACRO_VIEW_PROJECTION_VERSION,
    ) -> list[dict[str, Any]]:
        bounded_lookback_days = max(1, int(lookback_days))
        rows = self.conn.execute(
            """
            WITH requested AS (
              SELECT unnest(%s::text[]) AS concept_key
            ),
            aggregated AS (
              SELECT rows.concept_key,
                     COUNT(*)::int AS points,
                     MAX(rows.observed_at) AS latest_observed_at,
                     MIN(rows.observed_at) AS oldest_observed_at,
                     array_remove(array_agg(DISTINCT rows.source_name ORDER BY rows.source_name), NULL) AS sources
              FROM macro_observation_series_rows AS rows
              JOIN requested ON requested.concept_key = rows.concept_key
              WHERE rows.projection_version = %s
                AND rows.observed_at >= CURRENT_DATE - %s::int
              GROUP BY rows.concept_key
            )
            SELECT requested.concept_key,
                   COALESCE(aggregated.points, 0) AS points,
                   aggregated.latest_observed_at,
                   aggregated.oldest_observed_at,
                   COALESCE(aggregated.sources, ARRAY[]::text[]) AS sources
            FROM requested
            LEFT JOIN aggregated ON aggregated.concept_key = requested.concept_key
            ORDER BY requested.concept_key ASC
            """,
            (list(concept_keys), projection_version, bounded_lookback_days),
        ).fetchall()
        return [dict(row) for row in rows]

    def insert_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO macro_view_snapshots(
              snapshot_id, projection_version, asof_date, status, regime, overall_score, panels_json,
              indicators_json, triggers_json, data_gaps_json, source_coverage_json, features_json,
              chain_json, scenario_json, scorecard_json, computed_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(snapshot_id) DO UPDATE SET
              status = excluded.status,
              regime = excluded.regime,
              overall_score = excluded.overall_score,
              panels_json = excluded.panels_json,
              indicators_json = excluded.indicators_json,
              triggers_json = excluded.triggers_json,
              data_gaps_json = excluded.data_gaps_json,
              source_coverage_json = excluded.source_coverage_json,
              features_json = excluded.features_json,
              chain_json = excluded.chain_json,
              scenario_json = excluded.scenario_json,
              scorecard_json = excluded.scorecard_json,
              computed_at_ms = excluded.computed_at_ms
            """,
            (
                snapshot["snapshot_id"],
                snapshot["projection_version"],
                snapshot["asof_date"],
                snapshot["status"],
                snapshot["regime"],
                snapshot.get("overall_score"),
                Jsonb(snapshot.get("panels_json") or {}),
                Jsonb(snapshot.get("indicators_json") or {}),
                Jsonb(snapshot.get("triggers_json") or []),
                Jsonb(snapshot.get("data_gaps_json") or []),
                Jsonb(snapshot.get("source_coverage_json") or {}),
                Jsonb(snapshot.get("features_json") or {}),
                Jsonb(snapshot.get("chain_json") or {}),
                Jsonb(snapshot.get("scenario_json") or {}),
                Jsonb(snapshot.get("scorecard_json") or {}),
                int(snapshot["computed_at_ms"]),
            ),
        )
        self.conn.commit()

    def latest_snapshot(
        self,
        *,
        projection_version: str | None = MACRO_VIEW_PROJECTION_VERSION,
    ) -> dict[str, Any] | None:
        if projection_version is None:
            row = self.conn.execute(
                """
                SELECT *
                FROM macro_view_snapshots
                ORDER BY computed_at_ms DESC
                LIMIT 1
                """
            ).fetchone()
        else:
            row = self.conn.execute(
                """
                SELECT *
                FROM macro_view_snapshots
                WHERE projection_version = %s
                ORDER BY computed_at_ms DESC
                LIMIT 1
                """,
                (projection_version,),
            ).fetchone()
        return dict(row) if row is not None else None

    def observations_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS count FROM macro_observations").fetchone()
        return _count(row)

    def concept_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(DISTINCT concept_key) AS count FROM macro_observations").fetchone()
        return _count(row)

    def latest_import_run(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM macro_import_runs
            ORDER BY completed_at_ms DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row is not None else None


def _series_source_signature(
    *,
    projection_version: str,
    lookback_days: int,
    limit_per_series: int,
    rows: Sequence[Mapping[str, Any]],
) -> str:
    stable_rows = [
        {
            "concept_key": str(row.get("concept_key") or ""),
            "observed_at": str(row.get("observed_at") or ""),
            "value_numeric": str(row.get("value_numeric") or ""),
            "source_name": str(row.get("source_name") or ""),
            "series_key": str(row.get("series_key") or ""),
            "source_priority": int(row.get("source_priority") or 0),
            "unit": row.get("unit"),
            "frequency": row.get("frequency"),
            "data_quality": str(row.get("data_quality") or ""),
            "source_ts": str(row.get("source_ts") or ""),
        }
        for row in rows
    ]
    stable_rows.sort(
        key=lambda item: (item["concept_key"], item["observed_at"], item["source_name"], item["series_key"])
    )
    payload = {
        "projection_version": str(projection_version),
        "lookback_days": int(lookback_days),
        "limit_per_series": int(limit_per_series),
        "rows": stable_rows,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _observation_id(observation: Mapping[str, Any]) -> str:
    identity = "|".join(
        [
            str(observation.get("source_name") or ""),
            str(observation.get("concept_key") or ""),
            str(observation.get("observed_at") or ""),
            str(observation.get("series_key") or ""),
        ]
    )
    digest = hashlib.sha256(identity.encode()).hexdigest()[:32]
    return f"macro-observation:{digest}"


def _sync_window_id(
    *,
    source_name: str,
    bundle_name: str,
    window_start: date,
    window_end: date,
    trigger_reason: str,
) -> str:
    digest = _payload_hash(
        source_name=source_name,
        bundle_name=bundle_name,
        window_start=window_start,
        window_end=window_end,
        trigger_reason=trigger_reason,
    )[:32]
    return f"macro-sync-window:{digest}"


def _payload_hash(
    *,
    source_name: str,
    bundle_name: str,
    window_start: date,
    window_end: date,
    trigger_reason: str,
) -> str:
    identity = "|".join(
        [
            str(source_name),
            str(bundle_name),
            str(window_start),
            str(window_end),
            str(trigger_reason),
        ]
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def _transaction_context(conn: Any):
    transaction = getattr(conn, "transaction", None)
    if transaction is None:
        return nullcontext()
    return transaction()


def _count(row: Any) -> int:
    if row is None:
        return 0
    return int(dict(row).get("count") or 0)


__all__ = ["MacroIntelRepository", "MacroSeriesRefreshResult"]
