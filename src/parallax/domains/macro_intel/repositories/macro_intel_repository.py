from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from datetime import date
from typing import Any, NotRequired, TypedDict, cast

from psycopg.types.json import Jsonb

from parallax.domains.macro_intel._constants import MACRO_VIEW_PROJECTION_VERSION
from parallax.domains.macro_intel.observation_identity import (
    macro_observation_fact_payload_hash,
    macro_observation_id,
    macro_series_current_row_payload_hash,
    normalize_macro_date,
)
from parallax.platform.db.json_safety import postgres_safe_json


class MacroSeriesRefreshResult(TypedDict):
    status: str
    rows_written: int
    source_rows: int
    source_signature: str
    latest_attempt_error: NotRequired[str | None]


class MacroObservationUpsertOutcome(TypedDict):
    observation_id: str
    status: str
    concept_key: str
    observed_at: date
    fact_payload_hash: str


_POSTGRES_MAX_BIND_PARAMS = 65_535
_MACRO_SERIES_INSERT_PARAM_COUNT = 16
_MACRO_SERIES_INSERT_CHUNK_SIZE = min(4_000, _POSTGRES_MAX_BIND_PARAMS // _MACRO_SERIES_INSERT_PARAM_COUNT)


class MacroIntelRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_observation(self, observation: Mapping[str, Any]) -> MacroObservationUpsertOutcome:
        observed_at = normalize_macro_date(observation.get("observed_at"))
        observation_id = str(observation.get("observation_id") or macro_observation_id(observation))
        raw_payload = dict(observation.get("raw_payload") or observation.get("raw_payload_json") or {})
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
                "data_quality": str(observation.get("data_quality") or "ok"),
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

    def record_import_run(self, import_run: Mapping[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO macro_import_runs(
              run_id, source_name, bundle_name, asof_date, status, observations_count,
              seen_observation_count, inserted_observation_count, changed_observation_count, noop_observation_count,
              coverage_json, missing_series_json, series_errors_json, reason_codes_json,
              started_at_ms, completed_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(run_id) DO UPDATE SET
              source_name = excluded.source_name,
              bundle_name = excluded.bundle_name,
              asof_date = excluded.asof_date,
              status = excluded.status,
              observations_count = excluded.observations_count,
              seen_observation_count = excluded.seen_observation_count,
              inserted_observation_count = excluded.inserted_observation_count,
              changed_observation_count = excluded.changed_observation_count,
              noop_observation_count = excluded.noop_observation_count,
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
                int(import_run.get("seen_observation_count") or 0),
                int(import_run.get("inserted_observation_count") or 0),
                int(import_run.get("changed_observation_count") or 0),
                int(import_run.get("noop_observation_count") or 0),
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
              %s, %s, %s, %s, %s, %s, %s
            )
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
                run.get("import_run_id"),
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
            """,
            (
                str(source_name),
                str(bundle_name),
                normalize_macro_date(max_observed_at),
                int(now_ms),
            ),
        )
        return int(getattr(cursor, "rowcount", 0) or 0)

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
                """,
                (str(source_name), str(bundle_name)),
            )
            return {"max_observed_at": None, "rows_written": int(getattr(cursor, "rowcount", 0) or 0)}

        normalized_max_observed_at = normalize_macro_date(max_observed_at)
        cursor = self.conn.execute(
            """
            INSERT INTO macro_sync_state(source_name, bundle_name, max_observed_at, updated_at_ms)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(source_name, bundle_name) DO UPDATE SET
              max_observed_at = EXCLUDED.max_observed_at,
              updated_at_ms = EXCLUDED.updated_at_ms
            WHERE macro_sync_state.max_observed_at IS DISTINCT FROM EXCLUDED.max_observed_at
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
            "rows_written": int(getattr(cursor, "rowcount", 0) or 0),
        }

    def enqueue_macro_projection_dirty_target(
        self,
        *,
        projection_name: str,
        projection_version: str,
        now_ms: int,
        due_at_ms: int | None = None,
        reason: str,
        commit: bool = True,
    ) -> int:
        payload_hash = _macro_projection_dirty_payload_hash(
            projection_name=projection_name,
            projection_version=projection_version,
            target_kind="current",
            target_id="current",
            reason=reason,
            source_watermark_ms=int(now_ms),
        )
        cursor = self.conn.execute(
            """
            INSERT INTO macro_projection_dirty_targets(
              projection_name,
              projection_version,
              target_kind,
              target_id,
              payload_hash,
              dirty_reason,
              source_watermark_ms,
              priority,
              due_at_ms,
              leased_until_ms,
              lease_owner,
              attempt_count,
              last_error,
              created_at_ms,
              updated_at_ms
            )
            VALUES (
              %(projection_name)s,
              %(projection_version)s,
              %(target_kind)s,
              %(target_id)s,
              %(payload_hash)s,
              %(dirty_reason)s,
              %(source_watermark_ms)s,
              0,
              %(due_at_ms)s,
              NULL,
              NULL,
              0,
              NULL,
              %(now_ms)s,
              %(now_ms)s
            )
            ON CONFLICT (projection_name, projection_version, target_kind, target_id) DO UPDATE SET
              payload_hash = EXCLUDED.payload_hash,
              dirty_reason = EXCLUDED.dirty_reason,
              source_watermark_ms = GREATEST(
                macro_projection_dirty_targets.source_watermark_ms,
                EXCLUDED.source_watermark_ms
              ),
              priority = LEAST(macro_projection_dirty_targets.priority, EXCLUDED.priority),
              due_at_ms = LEAST(macro_projection_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
              leased_until_ms = NULL,
              lease_owner = NULL,
              last_error = NULL,
              updated_at_ms = EXCLUDED.updated_at_ms
            RETURNING 1 AS inserted
            """,
            {
                "projection_name": str(projection_name),
                "projection_version": str(projection_version),
                "target_kind": "current",
                "target_id": "current",
                "payload_hash": payload_hash,
                "dirty_reason": str(reason),
                "source_watermark_ms": int(now_ms),
                "due_at_ms": int(due_at_ms if due_at_ms is not None else now_ms),
                "now_ms": int(now_ms),
            },
        )
        rowcount = getattr(cursor, "rowcount", None)
        if rowcount is None or int(rowcount) < 0:
            return 1
        return int(rowcount)

    def enqueue_macro_projection_dirty_targets_for_changes(
        self,
        *,
        changed_observations: Sequence[Mapping[str, Any]],
        projection_name: str,
        projection_version: str,
        now_ms: int,
        due_at_ms: int | None = None,
        reason: str,
        commit: bool = True,
    ) -> int:
        targets = _macro_projection_dirty_change_targets(
            changed_observations,
            projection_name=projection_name,
            projection_version=projection_version,
            reason=reason,
        )
        if not targets:
            return 0
        params: dict[str, Any] = {
            "projection_names": [target["projection_name"] for target in targets],
            "projection_versions": [target["projection_version"] for target in targets],
            "target_kinds": [target["target_kind"] for target in targets],
            "target_ids": [target["target_id"] for target in targets],
            "concept_keys": [target["concept_key"] for target in targets],
            "min_observed_ats": [target["min_observed_at"] for target in targets],
            "max_observed_ats": [target["max_observed_at"] for target in targets],
            "source_watermark_dates": [target["source_watermark_date"] for target in targets],
            "payload_hashes": [target["payload_hash"] for target in targets],
            "dirty_reasons": [reason for _target in targets],
            "source_watermark_ms": int(now_ms),
            "due_at_ms": int(due_at_ms if due_at_ms is not None else now_ms),
            "now_ms": int(now_ms),
        }
        cursor = self.conn.execute(
            """
            INSERT INTO macro_projection_dirty_targets(
              projection_name,
              projection_version,
              target_kind,
              target_id,
              concept_key,
              min_observed_at,
              max_observed_at,
              source_watermark_date,
              payload_hash,
              dirty_reason,
              source_watermark_ms,
              priority,
              due_at_ms,
              leased_until_ms,
              lease_owner,
              attempt_count,
              last_error,
              created_at_ms,
              updated_at_ms
            )
            SELECT
              projection_name,
              projection_version,
              target_kind,
              target_id,
              concept_key,
              min_observed_at,
              max_observed_at,
              source_watermark_date,
              payload_hash,
              dirty_reason,
              %(source_watermark_ms)s,
              0,
              %(due_at_ms)s,
              NULL,
              NULL,
              0,
              NULL,
              %(now_ms)s,
              %(now_ms)s
            FROM unnest(
              %(projection_names)s::text[],
              %(projection_versions)s::text[],
              %(target_kinds)s::text[],
              %(target_ids)s::text[],
              %(concept_keys)s::text[],
              %(min_observed_ats)s::date[],
              %(max_observed_ats)s::date[],
              %(source_watermark_dates)s::date[],
              %(payload_hashes)s::text[],
              %(dirty_reasons)s::text[]
            ) AS target(
              projection_name,
              projection_version,
              target_kind,
              target_id,
              concept_key,
              min_observed_at,
              max_observed_at,
              source_watermark_date,
              payload_hash,
              dirty_reason
            )
            ON CONFLICT (projection_name, projection_version, target_kind, target_id) DO UPDATE SET
              concept_key = EXCLUDED.concept_key,
              min_observed_at = LEAST(
                COALESCE(macro_projection_dirty_targets.min_observed_at, EXCLUDED.min_observed_at),
                EXCLUDED.min_observed_at
              ),
              max_observed_at = GREATEST(
                COALESCE(macro_projection_dirty_targets.max_observed_at, EXCLUDED.max_observed_at),
                EXCLUDED.max_observed_at
              ),
              source_watermark_date = GREATEST(
                COALESCE(macro_projection_dirty_targets.source_watermark_date, EXCLUDED.source_watermark_date),
                EXCLUDED.source_watermark_date
              ),
              payload_hash = EXCLUDED.payload_hash,
              dirty_reason = EXCLUDED.dirty_reason,
              source_watermark_ms = GREATEST(
                macro_projection_dirty_targets.source_watermark_ms,
                EXCLUDED.source_watermark_ms
              ),
              priority = LEAST(macro_projection_dirty_targets.priority, EXCLUDED.priority),
              due_at_ms = LEAST(macro_projection_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
              leased_until_ms = NULL,
              lease_owner = NULL,
              last_error = NULL,
              updated_at_ms = EXCLUDED.updated_at_ms
            RETURNING 1 AS inserted
            """,
            params,
        )
        rowcount = getattr(cursor, "rowcount", None)
        if rowcount is None or int(rowcount) < 0:
            return len(targets)
        return int(rowcount)

    def claim_macro_projection_dirty_targets(
        self,
        *,
        projection_name: str,
        projection_version: str,
        limit: int,
        lease_ms: int,
        lease_owner: str,
        now_ms: int,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH due AS (
              SELECT projection_name, projection_version, target_kind, target_id
              FROM macro_projection_dirty_targets
              WHERE projection_name = %(projection_name)s
                AND projection_version = %(projection_version)s
                AND due_at_ms <= %(now_ms)s
                AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
              ORDER BY priority ASC, due_at_ms ASC, updated_at_ms ASC, target_kind ASC, target_id ASC
              LIMIT %(limit)s
              FOR UPDATE SKIP LOCKED
            )
            UPDATE macro_projection_dirty_targets
            SET leased_until_ms = %(leased_until_ms)s,
                lease_owner = %(lease_owner)s,
                attempt_count = macro_projection_dirty_targets.attempt_count + 1,
                last_error = NULL,
                updated_at_ms = %(now_ms)s
            FROM due
            WHERE macro_projection_dirty_targets.projection_name = due.projection_name
              AND macro_projection_dirty_targets.projection_version = due.projection_version
              AND macro_projection_dirty_targets.target_kind = due.target_kind
              AND macro_projection_dirty_targets.target_id = due.target_id
            RETURNING macro_projection_dirty_targets.*
            """,
            {
                "projection_name": str(projection_name),
                "projection_version": str(projection_version),
                "now_ms": int(now_ms),
                "leased_until_ms": int(now_ms) + max(1, int(lease_ms)),
                "lease_owner": str(lease_owner),
                "limit": max(0, int(limit)),
            },
        ).fetchall()
        if commit:
            self.conn.commit()
        return [dict(row) for row in rows]

    def mark_macro_projection_dirty_targets_done(
        self,
        claimed: Sequence[Mapping[str, Any]],
        *,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        records = _macro_projection_dirty_claims(claimed)
        if not records:
            return 0
        cursor = self.conn.execute(
            """
            DELETE FROM macro_projection_dirty_targets queue
            USING (
              SELECT *
              FROM unnest(
                %(projection_names)s::text[],
                %(projection_versions)s::text[],
                %(target_kinds)s::text[],
                %(target_ids)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::int[]
              ) AS done(
                projection_name,
                projection_version,
                target_kind,
                target_id,
                payload_hash,
                lease_owner,
                attempt_count
              )
            ) AS done
            WHERE queue.projection_name = done.projection_name
              AND queue.projection_version = done.projection_version
              AND queue.target_kind = done.target_kind
              AND queue.target_id = done.target_id
              AND queue.payload_hash = done.payload_hash
              AND queue.lease_owner = done.lease_owner
              AND queue.attempt_count = done.attempt_count
            """,
            _macro_projection_dirty_claim_params(records),
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def mark_macro_projection_dirty_targets_error(
        self,
        claimed: Sequence[Mapping[str, Any]],
        *,
        error: str,
        retry_ms: int,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        records = _macro_projection_dirty_claims(claimed)
        if not records:
            return 0
        params = _macro_projection_dirty_claim_params(records)
        params.update(
            {
                "due_at_ms": int(now_ms) + max(1, int(retry_ms)),
                "now_ms": int(now_ms),
                "last_error": str(error)[:2048],
            }
        )
        cursor = self.conn.execute(
            """
            UPDATE macro_projection_dirty_targets queue
            SET due_at_ms = %(due_at_ms)s,
                leased_until_ms = NULL,
                lease_owner = NULL,
                last_error = %(last_error)s,
                updated_at_ms = %(now_ms)s
            FROM (
              SELECT *
              FROM unnest(
                %(projection_names)s::text[],
                %(projection_versions)s::text[],
                %(target_kinds)s::text[],
                %(target_ids)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::int[]
              ) AS failed(
                projection_name,
                projection_version,
                target_kind,
                target_id,
                payload_hash,
                lease_owner,
                attempt_count
              )
            ) AS failed
            WHERE queue.projection_name = failed.projection_name
              AND queue.projection_version = failed.projection_version
              AND queue.target_kind = failed.target_kind
              AND queue.target_id = failed.target_id
              AND queue.payload_hash = failed.payload_hash
              AND queue.lease_owner = failed.lease_owner
              AND queue.attempt_count = failed.attempt_count
            """,
            params,
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

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

    def refresh_observation_series_rows_for_concepts(
        self,
        *,
        projection_version: str,
        now_ms: int,
        lookback_days: int,
        limit_per_series: int,
        claimed_targets: Sequence[Mapping[str, Any]] = (),
        concept_keys: Sequence[str] = (),
    ) -> MacroSeriesRefreshResult:
        bounded_lookback_days = max(1, int(lookback_days))
        bounded_limit_per_series = max(1, int(limit_per_series))
        target_concept_keys = _refresh_target_concept_keys(claimed_targets=claimed_targets, concept_keys=concept_keys)
        if not target_concept_keys:
            source_signature = _series_source_signature(
                projection_version=projection_version,
                lookback_days=bounded_lookback_days,
                limit_per_series=bounded_limit_per_series,
                rows=[],
            )
            return {
                "status": "unchanged",
                "rows_written": 0,
                "source_rows": 0,
                "source_signature": source_signature,
            }

        selected_rows = self._select_observation_series_rows(
            projection_version=projection_version,
            lookback_days=bounded_lookback_days,
            limit_per_series=bounded_limit_per_series,
            projected_at_ms=int(now_ms),
            concept_keys=target_concept_keys,
        )
        source_signature = _series_source_signature(
            projection_version=projection_version,
            lookback_days=bounded_lookback_days,
            limit_per_series=bounded_limit_per_series,
            rows=selected_rows,
        )
        existing_rows = self._current_observation_series_payload_rows(
            projection_version=projection_version,
            concept_keys=target_concept_keys,
        )
        empty_current_concept_keys = _empty_current_refresh_concept_keys(
            concept_keys=target_concept_keys,
            selected_rows=selected_rows,
            existing_rows=existing_rows,
        )
        if empty_current_concept_keys:
            latest_attempt_error = (
                "macro_observation_series_empty: empty current refresh preserved existing current rows "
                f"for {','.join(empty_current_concept_keys)}"
            )
            self._upsert_macro_series_publication_state(
                projection_version=projection_version,
                status="failed",
                source_signature=source_signature,
                row_count=len(existing_rows),
                started_at_ms=int(now_ms),
                finished_at_ms=int(now_ms),
                latest_attempt_error=latest_attempt_error,
                preserve_current=True,
            )
            return {
                "status": "failed",
                "rows_written": 0,
                "source_rows": len(selected_rows),
                "source_signature": source_signature,
                "latest_attempt_error": latest_attempt_error,
            }
        changed_concept_keys = _changed_series_concept_keys(
            concept_keys=target_concept_keys,
            selected_rows=selected_rows,
            existing_rows=existing_rows,
        )
        if not changed_concept_keys:
            self._upsert_macro_series_publication_state(
                projection_version=projection_version,
                status="unchanged",
                source_signature=source_signature,
                row_count=len(selected_rows),
                started_at_ms=int(now_ms),
                finished_at_ms=int(now_ms),
                latest_attempt_error=None,
                preserve_current=False,
            )
            return {
                "status": "unchanged",
                "rows_written": 0,
                "source_rows": len(selected_rows),
                "source_signature": source_signature,
            }

        rows_to_insert = [
            row for row in selected_rows if str(row.get("concept_key") or "") in set(changed_concept_keys)
        ]
        with _transaction_context(self.conn):
            self.conn.execute(
                """
                DELETE FROM macro_observation_series_rows
                WHERE projection_version = %s
                  AND concept_key = ANY(%s)
                """,
                (projection_version, list(changed_concept_keys)),
            )
            rows_written = self._insert_observation_series_rows(rows_to_insert)
            self._upsert_macro_series_publication_state(
                projection_version=projection_version,
                status="published",
                source_signature=source_signature,
                row_count=len(selected_rows),
                started_at_ms=int(now_ms),
                finished_at_ms=int(now_ms),
                latest_attempt_error=None,
                preserve_current=False,
            )
        return {
            "status": "published",
            "rows_written": rows_written,
            "source_rows": len(selected_rows),
            "source_signature": source_signature,
        }

    def macro_series_publication_state(self, projection_version: str) -> dict[str, Any] | None:
        return self._macro_series_publication_state(projection_version)

    def _select_observation_series_rows(
        self,
        *,
        projection_version: str,
        lookback_days: int,
        limit_per_series: int,
        projected_at_ms: int,
        concept_keys: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        bounded_concept_keys = _normalize_concept_keys(concept_keys or ())
        if not bounded_concept_keys:
            raise RuntimeError("macro_observation_series_refresh_requires_concepts")
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
              WHERE concept_key = ANY(%s)
                AND observed_at >= CURRENT_DATE - %s::int
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
            (
                list(bounded_concept_keys),
                int(lookback_days),
                projection_version,
                int(projected_at_ms),
                int(limit_per_series),
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def _current_observation_series_payload_rows(
        self,
        *,
        projection_version: str,
        concept_keys: Sequence[str],
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              rows.concept_key,
              rows.observed_at,
              rows.series_rank,
              rows.payload_hash
            FROM macro_observation_series_rows AS rows
            WHERE rows.projection_version = %s
              AND rows.concept_key = ANY(%s)
            ORDER BY rows.concept_key ASC, rows.observed_at DESC, rows.series_rank ASC
            """,
            (projection_version, list(concept_keys)),
        ).fetchall()
        return [dict(row) for row in rows]

    def _insert_observation_series_rows(self, rows: Sequence[Mapping[str, Any]]) -> int:
        if not rows:
            return 0
        rows_written = 0
        for start in range(0, len(rows), _MACRO_SERIES_INSERT_CHUNK_SIZE):
            rows_written += self._insert_observation_series_rows_chunk(
                rows[start : start + _MACRO_SERIES_INSERT_CHUNK_SIZE]
            )
        return rows_written

    def _insert_observation_series_rows_chunk(self, rows: Sequence[Mapping[str, Any]]) -> int:
        values_sql = ",".join(["(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(rows))
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
                    macro_series_current_row_payload_hash(row),
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
              projected_at_ms,
              payload_hash
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
        preserve_current: bool = False,
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
              source_signature = CASE
                WHEN %s THEN macro_observation_series_publication_state.source_signature
                ELSE excluded.source_signature
              END,
              row_count = CASE
                WHEN %s THEN macro_observation_series_publication_state.row_count
                ELSE excluded.row_count
              END,
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
                preserve_current,
                preserve_current,
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

    def insert_snapshot(self, snapshot: Mapping[str, Any]) -> bool:
        payload_hash = _macro_snapshot_payload_hash(snapshot)
        row = self.conn.execute(
            """
            INSERT INTO macro_view_snapshots(
              snapshot_id, projection_version, asof_date, status, regime, overall_score, panels_json,
              indicators_json, triggers_json, data_gaps_json, source_coverage_json, features_json,
              chain_json, scenario_json, scorecard_json, computed_at_ms, payload_hash
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(snapshot_id) DO UPDATE SET
              projection_version = excluded.projection_version,
              asof_date = excluded.asof_date,
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
              computed_at_ms = excluded.computed_at_ms,
              payload_hash = excluded.payload_hash
            WHERE macro_view_snapshots.payload_hash IS DISTINCT FROM excluded.payload_hash
            RETURNING true AS changed
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
                payload_hash,
            ),
        ).fetchone()
        self.conn.commit()
        return bool(dict(row or {}).get("changed", False))

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


def _refresh_target_concept_keys(
    *,
    claimed_targets: Sequence[Mapping[str, Any]],
    concept_keys: Sequence[str],
) -> tuple[str, ...]:
    keys: list[str] = list(concept_keys)
    for target in claimed_targets:
        concept_key = str(target.get("concept_key") or "").strip()
        if concept_key:
            keys.append(concept_key)
            continue
        if str(target.get("target_kind") or "") == "concept":
            keys.append(str(target.get("target_id") or "").strip())
    return _normalize_concept_keys(keys)


def _normalize_concept_keys(concept_keys: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(key for key in (str(value).strip() for value in concept_keys) if key))


def _changed_series_concept_keys(
    *,
    concept_keys: Sequence[str],
    selected_rows: Sequence[Mapping[str, Any]],
    existing_rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    selected_by_concept = _series_payload_hashes_by_concept(selected_rows, compute_hash=True)
    existing_by_concept = _series_payload_hashes_by_concept(existing_rows, compute_hash=False)
    return [
        concept_key
        for concept_key in concept_keys
        if selected_by_concept.get(concept_key, []) != existing_by_concept.get(concept_key, [])
    ]


def _empty_current_refresh_concept_keys(
    *,
    concept_keys: Sequence[str],
    selected_rows: Sequence[Mapping[str, Any]],
    existing_rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    selected_by_concept = _series_payload_hashes_by_concept(selected_rows, compute_hash=True)
    existing_by_concept = _series_payload_hashes_by_concept(existing_rows, compute_hash=False)
    return [
        concept_key
        for concept_key in concept_keys
        if not selected_by_concept.get(concept_key) and existing_by_concept.get(concept_key)
    ]


def _series_payload_hashes_by_concept(
    rows: Sequence[Mapping[str, Any]],
    *,
    compute_hash: bool,
) -> dict[str, list[tuple[str, int, str]]]:
    grouped: dict[str, list[tuple[str, int, str]]] = {}
    for row in rows:
        concept_key = str(row.get("concept_key") or "").strip()
        if not concept_key:
            continue
        payload_hash = (
            macro_series_current_row_payload_hash(row) if compute_hash else str(row.get("payload_hash") or "")
        )
        grouped.setdefault(concept_key, []).append(
            (
                str(row.get("observed_at") or ""),
                int(row.get("series_rank") or 0),
                payload_hash,
            )
        )
    for hashes in grouped.values():
        hashes.sort()
    return grouped


def _macro_snapshot_payload_hash(snapshot: Mapping[str, Any]) -> str:
    payload = {
        "projection_version": snapshot["projection_version"],
        "asof_date": snapshot["asof_date"],
        "status": snapshot["status"],
        "regime": snapshot["regime"],
        "overall_score": snapshot.get("overall_score"),
        "panels_json": snapshot.get("panels_json") or {},
        "indicators_json": snapshot.get("indicators_json") or {},
        "triggers_json": snapshot.get("triggers_json") or [],
        "data_gaps_json": snapshot.get("data_gaps_json") or [],
        "source_coverage_json": snapshot.get("source_coverage_json") or {},
        "features_json": snapshot.get("features_json") or {},
        "chain_json": snapshot.get("chain_json") or {},
        "scenario_json": snapshot.get("scenario_json") or {},
        "scorecard_json": snapshot.get("scorecard_json") or {},
    }
    encoded = json.dumps(postgres_safe_json(payload), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _macro_projection_dirty_payload_hash(
    *,
    projection_name: str,
    projection_version: str,
    target_kind: str,
    target_id: str,
    reason: str,
    source_watermark_ms: int,
) -> str:
    payload = {
        "projection_name": projection_name,
        "projection_version": projection_version,
        "target_kind": target_kind,
        "target_id": target_id,
        "reason": reason,
        "source_watermark_ms": int(source_watermark_ms),
    }
    encoded = json.dumps(postgres_safe_json(payload), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _macro_projection_dirty_change_targets(
    changed_observations: Sequence[Mapping[str, Any]],
    *,
    projection_name: str,
    projection_version: str,
    reason: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[date]] = {}
    for observation in changed_observations:
        concept_key = str(observation.get("concept_key") or "").strip()
        if not concept_key:
            continue
        grouped.setdefault(concept_key, []).append(normalize_macro_date(observation.get("observed_at")))

    targets: list[dict[str, Any]] = []
    for concept_key in sorted(grouped):
        observed_dates = grouped[concept_key]
        min_observed_at = min(observed_dates)
        max_observed_at = max(observed_dates)
        source_watermark_date = max_observed_at
        target = {
            "projection_name": str(projection_name),
            "projection_version": str(projection_version),
            "target_kind": "concept",
            "target_id": concept_key,
            "concept_key": concept_key,
            "min_observed_at": min_observed_at,
            "max_observed_at": max_observed_at,
            "source_watermark_date": source_watermark_date,
        }
        target["payload_hash"] = _macro_projection_dirty_change_payload_hash(
            projection_name=str(projection_name),
            projection_version=str(projection_version),
            concept_key=concept_key,
            min_observed_at=min_observed_at,
            max_observed_at=max_observed_at,
            source_watermark_date=source_watermark_date,
            reason=reason,
        )
        targets.append(target)
    return targets


def _macro_projection_dirty_change_payload_hash(
    *,
    projection_name: str,
    projection_version: str,
    concept_key: str,
    min_observed_at: date,
    max_observed_at: date,
    source_watermark_date: date,
    reason: str,
) -> str:
    payload = {
        "projection_name": projection_name,
        "projection_version": projection_version,
        "target_kind": "concept",
        "target_id": concept_key,
        "concept_key": concept_key,
        "min_observed_at": min_observed_at,
        "max_observed_at": max_observed_at,
        "source_watermark_date": source_watermark_date,
        "reason": reason,
    }
    encoded = json.dumps(postgres_safe_json(payload), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _macro_projection_dirty_claims(claimed: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "projection_name": str(claim["projection_name"]),
            "projection_version": str(claim["projection_version"]),
            "target_kind": str(claim["target_kind"]),
            "target_id": str(claim["target_id"]),
            "payload_hash": str(claim["payload_hash"]),
            "lease_owner": str(claim["lease_owner"]),
            "attempt_count": int(claim["attempt_count"]),
        }
        for claim in claimed
    ]


def _macro_projection_dirty_claim_params(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "projection_names": [record["projection_name"] for record in records],
        "projection_versions": [record["projection_version"] for record in records],
        "target_kinds": [record["target_kind"] for record in records],
        "target_ids": [record["target_id"] for record in records],
        "payload_hashes": [record["payload_hash"] for record in records],
        "lease_owners": [record["lease_owner"] for record in records],
        "attempt_counts": [int(record["attempt_count"]) for record in records],
    }


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


def _transaction_context(conn: Any) -> AbstractContextManager[Any]:
    transaction = getattr(conn, "transaction", None)
    if transaction is None:
        return nullcontext()
    return cast(Callable[[], AbstractContextManager[Any]], transaction)()


def _count(row: Any) -> int:
    if row is None:
        return 0
    return int(dict(row).get("count") or 0)


__all__ = ["MacroIntelRepository", "MacroSeriesRefreshResult"]
