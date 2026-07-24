from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, TypedDict

from psycopg.types.json import Jsonb

from tracefold.macro.observations.identity import (
    macro_observation_fact_payload_hash,
    macro_observation_id,
    normalize_macro_date,
    require_macro_observation_raw_payload,
)


class MacroObservationUpsertOutcome(TypedDict):
    observation_id: str
    status: str
    concept_key: str
    observed_at: date
    fact_payload_hash: str


class MacroIntelRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_observation(self, observation: Mapping[str, Any]) -> MacroObservationUpsertOutcome:
        observed_at = normalize_macro_date(observation.get("observed_at"))
        observation_id = str(observation.get("observation_id") or macro_observation_id(observation))
        raw_payload = require_macro_observation_raw_payload(observation)
        fact_payload_hash = macro_observation_fact_payload_hash(observation)
        row = self.conn.execute(
            """
            WITH upserted AS (
            INSERT INTO macro_observations(
              observation_id, source_name, concept_key, series_key, source_priority, observed_at, value_numeric, unit,
              frequency, data_quality, source_ts, raw_payload_json, ingested_at_ms, fact_payload_hash
            )
            VALUES (
              %(observation_id)s,
              %(source_name)s,
              %(concept_key)s,
              %(series_key)s,
              %(source_priority)s,
              %(observed_at)s,
              %(value_numeric)s,
              %(unit)s,
              %(frequency)s,
              %(data_quality)s,
              %(source_ts)s,
              %(raw_payload_json)s,
              %(ingested_at_ms)s,
              %(fact_payload_hash)s
            )
            ON CONFLICT(concept_key, observed_at, source_name, series_key) DO UPDATE SET
              source_priority = excluded.source_priority,
              value_numeric = excluded.value_numeric,
              unit = excluded.unit,
              frequency = excluded.frequency,
              data_quality = excluded.data_quality,
              source_ts = excluded.source_ts,
              raw_payload_json = excluded.raw_payload_json,
              ingested_at_ms = excluded.ingested_at_ms,
              fact_payload_hash = excluded.fact_payload_hash
            WHERE macro_observations.fact_payload_hash IS DISTINCT FROM excluded.fact_payload_hash
            RETURNING
              observation_id,
              concept_key,
              observed_at,
              fact_payload_hash,
              (xmax = 0) AS inserted
            ),
            existing AS (
              SELECT
                observation_id,
                concept_key,
                observed_at,
                fact_payload_hash
              FROM macro_observations
              WHERE concept_key = %(concept_key)s
                AND observed_at = %(observed_at)s
                AND source_name = %(source_name)s
                AND series_key = %(series_key)s
                AND NOT EXISTS (SELECT 1 FROM upserted)
            )
            SELECT
              observation_id,
              CASE WHEN inserted THEN 'inserted' ELSE 'changed' END AS status,
              concept_key,
              observed_at,
              fact_payload_hash
            FROM upserted
            UNION ALL
            SELECT
              observation_id,
              'noop' AS status,
              concept_key,
              observed_at,
              fact_payload_hash
            FROM existing
            LIMIT 1
            """,
            {
                "observation_id": observation_id,
                "source_name": str(observation["source_name"]),
                "concept_key": str(observation["concept_key"]),
                "series_key": str(observation["series_key"]),
                "source_priority": int(observation["source_priority"]),
                "observed_at": observed_at,
                "value_numeric": observation.get("value_numeric"),
                "unit": observation.get("unit"),
                "frequency": observation.get("frequency"),
                "data_quality": _required_observation_text(observation, "data_quality"),
                "source_ts": observation.get("source_ts"),
                "raw_payload_json": Jsonb(raw_payload),
                "ingested_at_ms": int(observation["ingested_at_ms"]),
                "fact_payload_hash": fact_payload_hash,
            },
        ).fetchone()
        if row is None:
            raise RuntimeError("macro_observation_upsert_returned_no_outcome")
        outcome = dict(row)
        return {
            "observation_id": str(outcome["observation_id"]),
            "status": str(outcome["status"]),
            "concept_key": str(outcome["concept_key"]),
            "observed_at": normalize_macro_date(outcome["observed_at"]),
            "fact_payload_hash": str(outcome["fact_payload_hash"]),
        }

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
        cursor = self.conn.execute(
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
                  status = CASE
                    WHEN macro_sync_windows.status IN ('done', 'failed')
                      AND excluded.trigger_reason IN ('steady_overlap', 'operator_sync')
                    THEN 'pending'
                    ELSE macro_sync_windows.status
                  END,
                  leased_until_ms = CASE
                    WHEN macro_sync_windows.status IN ('done', 'failed')
                      AND excluded.trigger_reason IN ('steady_overlap', 'operator_sync')
                    THEN NULL
                    ELSE macro_sync_windows.leased_until_ms
                  END,
                  lease_owner = CASE
                    WHEN macro_sync_windows.status IN ('done', 'failed')
                      AND excluded.trigger_reason IN ('steady_overlap', 'operator_sync')
                    THEN NULL
                    ELSE macro_sync_windows.lease_owner
                  END,
                  attempt_count = CASE
                    WHEN macro_sync_windows.status IN ('done', 'failed')
                      AND excluded.trigger_reason IN ('steady_overlap', 'operator_sync')
                    THEN 0
                    ELSE macro_sync_windows.attempt_count
                  END,
                  last_error_code = CASE
                    WHEN macro_sync_windows.status IN ('done', 'failed')
                      AND excluded.trigger_reason IN ('steady_overlap', 'operator_sync')
                    THEN NULL
                    ELSE macro_sync_windows.last_error_code
                  END,
                  last_error_message = CASE
                    WHEN macro_sync_windows.status IN ('done', 'failed')
                      AND excluded.trigger_reason IN ('steady_overlap', 'operator_sync')
                    THEN NULL
                    ELSE macro_sync_windows.last_error_message
                  END,
                  last_run_id = CASE
                    WHEN macro_sync_windows.status IN ('done', 'failed')
                      AND excluded.trigger_reason IN ('steady_overlap', 'operator_sync')
                    THEN NULL
                    ELSE macro_sync_windows.last_run_id
                  END,
                  completed_at_ms = CASE
                    WHEN macro_sync_windows.status IN ('done', 'failed')
                      AND excluded.trigger_reason IN ('steady_overlap', 'operator_sync')
                    THEN NULL
                    ELSE macro_sync_windows.completed_at_ms
                  END,
                  updated_at_ms = CASE
                    WHEN macro_sync_windows.status IN ('pending', 'retryable')
                      OR (
                        macro_sync_windows.status IN ('done', 'failed')
                        AND excluded.trigger_reason IN ('steady_overlap', 'operator_sync')
                      )
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
        )
        row = cursor.fetchone()
        return str(row["sync_window_id"])

    def claim_macro_sync_window(
        self,
        *,
        lease_owner: str,
        lease_ms: int,
        now_ms: int,
    ) -> dict[str, Any] | None:
        cursor = self.conn.execute(
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
              ORDER BY priority ASC, window_end DESC, due_at_ms ASC, updated_at_ms ASC, sync_window_id ASC
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
        )
        row = cursor.fetchone()
        return dict(row) if row is not None else None

    def claim_macro_sync_window_by_id(
        self,
        *,
        sync_window_id: str,
        lease_owner: str,
        lease_ms: int,
        now_ms: int,
    ) -> dict[str, Any] | None:
        cursor = self.conn.execute(
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
        )
        row = cursor.fetchone()
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
              asof_date,
              max_observed_at,
              observations_count,
              imported_observation_count,
              seen_observation_count,
              inserted_observation_count,
              changed_observation_count,
              noop_observation_count,
              max_seen_observed_at,
              min_changed_observed_at,
              max_changed_observed_at,
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
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT(sync_run_id) DO UPDATE SET
              sync_window_id = excluded.sync_window_id,
              source_name = excluded.source_name,
              bundle_name = excluded.bundle_name,
              requested_start = excluded.requested_start,
              requested_end = excluded.requested_end,
              status = excluded.status,
              asof_date = excluded.asof_date,
              max_observed_at = excluded.max_observed_at,
              observations_count = excluded.observations_count,
              imported_observation_count = excluded.imported_observation_count,
              seen_observation_count = excluded.seen_observation_count,
              inserted_observation_count = excluded.inserted_observation_count,
              changed_observation_count = excluded.changed_observation_count,
              noop_observation_count = excluded.noop_observation_count,
              max_seen_observed_at = excluded.max_seen_observed_at,
              min_changed_observed_at = excluded.min_changed_observed_at,
              max_changed_observed_at = excluded.max_changed_observed_at,
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
                run.get("asof_date"),
                run.get("max_observed_at"),
                int(run.get("observations_count") or 0),
                int(run.get("imported_observation_count") or 0),
                int(run.get("seen_observation_count") or 0),
                int(run.get("inserted_observation_count") or 0),
                int(run.get("changed_observation_count") or 0),
                int(run.get("noop_observation_count") or 0),
                run.get("max_seen_observed_at"),
                run.get("min_changed_observed_at"),
                run.get("max_changed_observed_at"),
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
            RETURNING 1 AS changed
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
        return cursor.fetchone() is not None

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
            RETURNING 1 AS changed
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
        return cursor.fetchone() is not None

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
            RETURNING 1 AS changed
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
        return cursor.fetchone() is not None

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

    def macro_sync_state_max_observed_at(self, *, source_name: str, bundle_name: str) -> date | None:
        row = self.conn.execute(
            """
            SELECT max_observed_at
            FROM macro_sync_state
            WHERE source_name = %s
              AND bundle_name = %s
            """,
            (str(source_name), str(bundle_name)),
        ).fetchone()
        max_observed_at = dict(row or {}).get("max_observed_at")
        return normalize_macro_date(max_observed_at) if max_observed_at is not None else None

    def update_macro_sync_state(
        self,
        *,
        source_name: str,
        bundle_name: str,
        max_observed_at: date | None,
        now_ms: int,
    ) -> int:
        if max_observed_at is None:
            return 0
        cursor = self.conn.execute(
            """
            INSERT INTO macro_sync_state(source_name, bundle_name, max_observed_at, updated_at_ms)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(source_name, bundle_name) DO UPDATE SET
              max_observed_at = EXCLUDED.max_observed_at,
              updated_at_ms = EXCLUDED.updated_at_ms
            WHERE macro_sync_state.max_observed_at IS NULL
               OR EXCLUDED.max_observed_at > macro_sync_state.max_observed_at
            RETURNING 1 AS changed
            """,
            (
                str(source_name),
                str(bundle_name),
                normalize_macro_date(max_observed_at),
                int(now_ms),
            ),
        )
        return 1 if cursor.fetchone() is not None else 0

    def rebuild_macro_sync_state(self, *, source_name: str, bundle_name: str, now_ms: int) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT MAX(COALESCE(max_seen_observed_at, max_observed_at, requested_end)) AS max_observed_at
            FROM macro_sync_runs
            WHERE source_name = %s
              AND bundle_name = %s
              AND status IN ('ok', 'partial')
            """,
            (str(source_name), str(bundle_name)),
        ).fetchone()
        max_observed_at = dict(row or {}).get("max_observed_at")
        if max_observed_at is None and str(source_name) == "macrodata-cli" and str(bundle_name) == "macro-core":
            row = self.conn.execute(
                """
                SELECT observed_at AS max_observed_at
                FROM macro_observations
                ORDER BY observed_at DESC
                LIMIT 1
                """
            ).fetchone()
            max_observed_at = dict(row or {}).get("max_observed_at")
        if max_observed_at is None:
            cursor = self.conn.execute(
                """
                DELETE FROM macro_sync_state
                WHERE source_name = %s
                  AND bundle_name = %s
                RETURNING 1 AS deleted
                """,
                (str(source_name), str(bundle_name)),
            )
            return {"max_observed_at": None, "rows_written": len(cursor.fetchall())}

        normalized_max_observed_at = normalize_macro_date(max_observed_at)
        cursor = self.conn.execute(
            """
            INSERT INTO macro_sync_state(source_name, bundle_name, max_observed_at, updated_at_ms)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(source_name, bundle_name) DO UPDATE SET
              max_observed_at = EXCLUDED.max_observed_at,
              updated_at_ms = EXCLUDED.updated_at_ms
            WHERE macro_sync_state.max_observed_at IS DISTINCT FROM EXCLUDED.max_observed_at
            RETURNING 1 AS changed
            """,
            (
                str(source_name),
                str(bundle_name),
                normalized_max_observed_at,
                int(now_ms),
            ),
        )
        return {
            "max_observed_at": normalized_max_observed_at,
            "rows_written": 1 if cursor.fetchone() is not None else 0,
        }

    def live_observations(
        self,
        *,
        concept_keys: tuple[str, ...],
        start_date: date,
        max_rows_per_series: int,
    ) -> list[dict[str, Any]]:
        bounded_concept_keys = _normalize_concept_keys(concept_keys)
        if not bounded_concept_keys:
            return []
        rows = self.conn.execute(
            """
            WITH ranked AS (
              SELECT
                observation_id,
                concept_key,
                source_name,
                series_key,
                source_priority,
                observed_at,
                value_numeric,
                unit,
                frequency,
                data_quality,
                source_ts,
                raw_payload_json,
                ingested_at_ms,
                ROW_NUMBER() OVER (
                  PARTITION BY concept_key, source_name, series_key
                  ORDER BY observed_at DESC, source_ts DESC NULLS LAST,
                           ingested_at_ms DESC, observation_id ASC
                ) AS series_rank
              FROM macro_observations
              WHERE concept_key = ANY(%s::text[])
                AND observed_at >= %s
            )
            SELECT
              observation_id,
              concept_key,
              source_name,
              series_key,
              source_priority,
              observed_at,
              value_numeric,
              unit,
              frequency,
              data_quality,
              source_ts,
              raw_payload_json,
              ingested_at_ms
            FROM ranked
            WHERE series_rank <= %s
            ORDER BY concept_key ASC, source_priority DESC, source_name ASC,
                     series_key ASC, observed_at ASC, ingested_at_ms ASC
            """,
            (list(bounded_concept_keys), start_date, int(max_rows_per_series)),
        ).fetchall()
        return [dict(row) for row in rows]

    def latest_uncatalogued_observations(
        self,
        *,
        catalog_concept_keys: tuple[str, ...],
        limit: int,
    ) -> list[dict[str, Any]]:
        bounded_concept_keys = _normalize_concept_keys(catalog_concept_keys)
        if not bounded_concept_keys:
            raise RuntimeError("macro_live_catalog_concepts_required")
        rows = self.conn.execute(
            """
            WITH ranked AS (
              SELECT
                observation_id,
                concept_key,
                source_name,
                series_key,
                source_priority,
                observed_at,
                value_numeric,
                unit,
                frequency,
                data_quality,
                source_ts,
                raw_payload_json,
                ingested_at_ms,
                ROW_NUMBER() OVER (
                  PARTITION BY concept_key, source_name, series_key
                  ORDER BY observed_at DESC, source_ts DESC NULLS LAST,
                           ingested_at_ms DESC, observation_id ASC
                ) AS series_rank
              FROM macro_observations
              WHERE concept_key <> ALL(%s::text[])
            )
            SELECT
              observation_id,
              concept_key,
              source_name,
              series_key,
              source_priority,
              observed_at,
              value_numeric,
              unit,
              frequency,
              data_quality,
              source_ts,
              raw_payload_json,
              ingested_at_ms
            FROM ranked
            WHERE series_rank = 1
            ORDER BY ingested_at_ms DESC, concept_key ASC, source_priority DESC,
                     source_name ASC, series_key ASC
            LIMIT %s
            """,
            (list(bounded_concept_keys), int(limit)),
        ).fetchall()
        return [dict(row) for row in rows]

    def material_fact_max_observed_at(
        self,
        *,
        concept_keys: Sequence[str],
        through_date: date,
    ) -> date | None:
        bounded_concept_keys = _normalize_concept_keys(concept_keys)
        if not bounded_concept_keys:
            return None
        row = self.conn.execute(
            """
            SELECT MAX(observed_at) AS max_observed_at
            FROM macro_observations
            WHERE concept_key = ANY(%s::text[])
              AND observed_at <= %s
            """,
            (list(bounded_concept_keys), through_date),
        ).fetchone()
        if row is None:
            return None
        value = dict(row).get("max_observed_at")
        return value if isinstance(value, date) else normalize_macro_date(value) if value is not None else None

    def material_fact_state(self, *, through_date: date) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT
              MAX(observed_at) AS max_observed_at,
              COUNT(*)::int AS observations_count,
              COUNT(DISTINCT concept_key)::int AS concept_count
            FROM macro_observations
            WHERE observed_at <= %s
            """,
            (through_date,),
        ).fetchone()
        payload = dict(row or {})
        max_observed_at = payload.get("max_observed_at")
        return {
            "max_observed_at": (
                max_observed_at
                if isinstance(max_observed_at, date)
                else normalize_macro_date(max_observed_at)
                if max_observed_at is not None
                else None
            ),
            "observations_count": int(payload.get("observations_count") or 0),
            "concept_count": int(payload.get("concept_count") or 0),
        }

    def observations_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS count FROM macro_observations").fetchone()
        return _count(row)

    def concept_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(DISTINCT concept_key) AS count FROM macro_observations").fetchone()
        return _count(row)


def _normalize_concept_keys(concept_keys: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in concept_keys if str(value).strip()}))


def _required_observation_text(observation: Mapping[str, Any], field_name: str) -> str:
    value = observation.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"macro_observation_{field_name}_required")
    return value.strip()


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


def _count(row: Any) -> int:
    if row is None:
        return 0
    return int(dict(row).get("count") or 0)


__all__ = ["MacroIntelRepository"]
