from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, NotRequired, TypedDict

from psycopg.types.json import Jsonb

from parallax.domains.macro_intel._constants import (
    MACRO_EVENT_CONCEPTS,
    MACRO_MODULE_IDS,
    MACRO_VIEW_PROJECTION_VERSION,
)
from parallax.domains.macro_intel.observation_identity import (
    macro_observation_fact_payload_hash,
    macro_observation_id,
    normalize_macro_date,
)
from parallax.platform.current_read_model_payload_hash import (
    stable_current_payload_hash,
    stable_dirty_target_payload_hash,
)
from parallax.platform.db.queue_terminal import terminalize_source_row


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
_MACRO_SERIES_INSERT_PARAM_COUNT = 10
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

    def enqueue_macro_projection_dirty_target(
        self,
        *,
        projection_name: str,
        projection_version: str,
        now_ms: int,
        due_at_ms: int | None = None,
        reason: str,
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
              attempt_count = CASE
                WHEN macro_projection_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                THEN 0
                ELSE macro_projection_dirty_targets.attempt_count
              END,
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
        return 1 if cursor.fetchone() is not None else 0

    def enqueue_macro_projection_dirty_targets_for_changes(
        self,
        *,
        changed_observations: Sequence[Mapping[str, Any]],
        projection_name: str,
        projection_version: str,
        now_ms: int,
        due_at_ms: int | None = None,
        reason: str,
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
              attempt_count = CASE
                WHEN macro_projection_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                THEN 0
                ELSE macro_projection_dirty_targets.attempt_count
              END,
              last_error = NULL,
              updated_at_ms = EXCLUDED.updated_at_ms
            RETURNING 1 AS inserted
            """,
            params,
        )
        return len(cursor.fetchall())

    def claim_macro_projection_dirty_targets(
        self,
        *,
        projection_name: str,
        projection_version: str,
        limit: int,
        lease_ms: int,
        lease_owner: str,
        now_ms: int,
    ) -> list[dict[str, Any]]:
        cursor = self.conn.execute(
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
                "leased_until_ms": int(now_ms) + int(lease_ms),
                "lease_owner": str(lease_owner),
                "limit": int(limit),
            },
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def mark_macro_projection_dirty_targets_done(
        self,
        claimed: Sequence[Mapping[str, Any]],
        *,
        now_ms: int,
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
            RETURNING 1 AS deleted
            """,
            _macro_projection_dirty_claim_params(records),
        )
        return len(cursor.fetchall())

    def mark_macro_projection_dirty_targets_error(
        self,
        claimed: Sequence[Mapping[str, Any]],
        *,
        error: str,
        retry_ms: int,
        max_attempts: int,
        worker_name: str,
        now_ms: int,
    ) -> int:
        records = _macro_projection_dirty_claims(claimed)
        if not records:
            return 0
        retry_records = [record for record in records if int(record["attempt_count"]) < int(max_attempts)]
        exhausted_records = [record for record in records if int(record["attempt_count"]) >= int(max_attempts)]
        retry_params = _macro_projection_dirty_claim_params(retry_records)
        retry_params.update(
            {
                "due_at_ms": int(now_ms) + int(retry_ms),
                "now_ms": int(now_ms),
                "last_error": str(error)[:2048],
            }
        )
        changed = 0
        if retry_records:
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
                RETURNING 1 AS changed
                """,
                retry_params,
            )
            changed += len(cursor.fetchall())
        if exhausted_records:
            deleted_rows, deleted_count = self._delete_macro_projection_dirty_claims_returning(exhausted_records)
            changed += deleted_count
            for row in deleted_rows:
                terminalize_source_row(
                    self.conn,
                    worker_name=worker_name,
                    source_table="macro_projection_dirty_targets",
                    target_key=_macro_projection_dirty_target_key(row),
                    source_row=row,
                    final_status="terminal",
                    final_reason=_macro_projection_retry_budget_exhausted_reason(error),
                    now_ms=now_ms,
                    attempt_count=int(row["attempt_count"]),
                    last_attempted_at_ms=now_ms,
                )
        return changed

    def _delete_macro_projection_dirty_claims_returning(
        self,
        records: Sequence[Mapping[str, Any]],
    ) -> tuple[list[dict[str, Any]], int]:
        cursor = self.conn.execute(
            """
            WITH exhausted AS (
              SELECT *
              FROM unnest(
                %(projection_names)s::text[],
                %(projection_versions)s::text[],
                %(target_kinds)s::text[],
                %(target_ids)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::int[]
              ) AS exhausted(
                projection_name,
                projection_version,
                target_kind,
                target_id,
                payload_hash,
                lease_owner,
                attempt_count
              )
            )
            DELETE FROM macro_projection_dirty_targets queue
            USING exhausted
            WHERE queue.projection_name = exhausted.projection_name
              AND queue.projection_version = exhausted.projection_version
              AND queue.target_kind = exhausted.target_kind
              AND queue.target_id = exhausted.target_id
              AND queue.payload_hash = exhausted.payload_hash
              AND queue.lease_owner = exhausted.lease_owner
              AND queue.attempt_count = exhausted.attempt_count
            RETURNING queue.*
            """,
            _macro_projection_dirty_claim_params(records),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows], len(rows)

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
        target_concept_keys = _refresh_target_concept_keys(claimed_targets=claimed_targets, concept_keys=concept_keys)
        if not target_concept_keys:
            source_signature = _series_source_signature(
                projection_version=projection_version,
                lookback_days=lookback_days,
                limit_per_series=limit_per_series,
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
            lookback_days=lookback_days,
            limit_per_series=limit_per_series,
            concept_keys=target_concept_keys,
        )
        source_signature = _series_source_signature(
            projection_version=projection_version,
            lookback_days=lookback_days,
            limit_per_series=limit_per_series,
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
        rows_written = self._delete_exited_observation_series_rows(
            projection_version=projection_version,
            concept_keys=changed_concept_keys,
            current_rows=rows_to_insert,
        )
        rows_written += self._insert_observation_series_rows(rows_to_insert)
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
        concept_keys: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        bounded_concept_keys = _normalize_concept_keys(concept_keys or ())
        if not bounded_concept_keys:
            raise RuntimeError("macro_observation_series_refresh_requires_concepts")
        rows = self.conn.execute(
            """
            WITH requested AS (
              SELECT unnest(%s::text[]) AS concept_key
            )
            SELECT
              %s AS projection_version,
              selected.concept_key,
              selected.observed_at,
              selected.value_numeric,
              selected.source_name,
              selected.series_key,
              selected.unit,
              selected.frequency,
              selected.data_quality,
              COALESCE(selected.raw_payload_json, '{}'::jsonb) AS raw_payload_json
            FROM requested
            CROSS JOIN LATERAL (
              SELECT DISTINCT ON (observed_at)
                concept_key,
                observed_at,
                value_numeric,
                source_name,
                series_key,
                unit,
                frequency,
                data_quality,
                raw_payload_json
              FROM macro_observations
              WHERE concept_key = requested.concept_key
                AND observed_at >= CURRENT_DATE - %s::int
                AND (value_numeric IS NOT NULL OR concept_key = ANY(%s))
              ORDER BY
                observed_at DESC,
                source_priority DESC,
                source_ts DESC NULLS LAST,
                ingested_at_ms DESC
              LIMIT %s
            ) AS selected
            ORDER BY selected.concept_key ASC, selected.observed_at DESC
            """,
            (
                list(bounded_concept_keys),
                projection_version,
                int(lookback_days),
                list(MACRO_EVENT_CONCEPTS),
                int(limit_per_series),
            ),
        ).fetchall()
        return [_compact_series_row(row) for row in rows]

    def _current_observation_series_payload_rows(
        self,
        *,
        projection_version: str,
        concept_keys: Sequence[str],
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              rows.projection_version,
              rows.concept_key,
              rows.observed_at,
              rows.value_numeric,
              rows.source_name,
              rows.series_key,
              rows.unit,
              rows.frequency,
              rows.data_quality,
              rows.event_metadata_json
            FROM macro_observation_series_rows AS rows
            WHERE rows.projection_version = %s
              AND rows.concept_key = ANY(%s)
            ORDER BY rows.concept_key ASC, rows.observed_at DESC
            """,
            (projection_version, list(concept_keys)),
        ).fetchall()
        return [dict(row) for row in rows]

    def _delete_exited_observation_series_rows(
        self,
        *,
        projection_version: str,
        concept_keys: Sequence[str],
        current_rows: Sequence[Mapping[str, Any]],
    ) -> int:
        concept_key_values = [str(row["concept_key"]) for row in current_rows]
        observed_at_values = [row["observed_at"] for row in current_rows]
        if concept_key_values:
            cursor = self.conn.execute(
                """
                WITH current_keys(concept_key, observed_at) AS (
                  SELECT *
                  FROM unnest(%s::text[], %s::date[])
                )
                DELETE FROM macro_observation_series_rows AS rows
                WHERE rows.projection_version = %s
                  AND rows.concept_key = ANY(%s)
                  AND NOT EXISTS (
                    SELECT 1
                    FROM current_keys
                    WHERE current_keys.concept_key = rows.concept_key
                      AND current_keys.observed_at = rows.observed_at
                  )
                RETURNING 1 AS deleted
                """,
                (
                    concept_key_values,
                    observed_at_values,
                    projection_version,
                    list(concept_keys),
                ),
            )
        else:
            cursor = self.conn.execute(
                """
                DELETE FROM macro_observation_series_rows
                WHERE projection_version = %s
                  AND concept_key = ANY(%s)
                RETURNING 1 AS deleted
                """,
                (projection_version, list(concept_keys)),
            )
        return len(cursor.fetchall())

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
        values_sql = ",".join(["(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(rows))
        params: list[Any] = []
        for row in rows:
            params.extend(
                [
                    row["projection_version"],
                    row["concept_key"],
                    row["observed_at"],
                    row["value_numeric"],
                    row["source_name"],
                    row["series_key"],
                    row.get("unit"),
                    row.get("frequency"),
                    row.get("data_quality"),
                    Jsonb(dict(row.get("event_metadata_json") or {})),
                ]
            )
        cursor = self.conn.execute(
            f"""
            INSERT INTO macro_observation_series_rows(
              projection_version,
              concept_key,
              observed_at,
              value_numeric,
              source_name,
              series_key,
              unit,
              frequency,
              data_quality,
              event_metadata_json
            )
            VALUES {values_sql}
            ON CONFLICT (projection_version, concept_key, observed_at) DO UPDATE SET
              value_numeric = excluded.value_numeric,
              source_name = excluded.source_name,
              series_key = excluded.series_key,
              unit = excluded.unit,
              frequency = excluded.frequency,
              data_quality = excluded.data_quality,
              event_metadata_json = excluded.event_metadata_json
            WHERE (
              macro_observation_series_rows.value_numeric,
              macro_observation_series_rows.source_name,
              macro_observation_series_rows.series_key,
              macro_observation_series_rows.unit,
              macro_observation_series_rows.frequency,
              macro_observation_series_rows.data_quality,
              macro_observation_series_rows.event_metadata_json
            ) IS DISTINCT FROM (
              excluded.value_numeric,
              excluded.source_name,
              excluded.series_key,
              excluded.unit,
              excluded.frequency,
              excluded.data_quality,
              excluded.event_metadata_json
            )
            RETURNING 1 AS changed
            """,
            tuple(params),
        )
        return len(cursor.fetchall())

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
        bounded_concept_keys = _normalize_concept_keys(concept_keys)
        if not bounded_concept_keys:
            return []
        rows = self.conn.execute(
            """
            WITH requested AS (
              SELECT unnest(%s::text[]) AS concept_key
            )
            SELECT rows.*
            FROM requested
            CROSS JOIN LATERAL (
              SELECT series.*
              FROM macro_observation_series_rows AS series
              WHERE series.projection_version = %s
                AND series.concept_key = requested.concept_key
                AND series.observed_at >= CURRENT_DATE - %s::int
              ORDER BY series.observed_at DESC
              LIMIT %s
            ) AS rows
            ORDER BY rows.concept_key ASC, rows.observed_at DESC
            """,
            (
                list(bounded_concept_keys),
                projection_version,
                int(lookback_days),
                int(limit_per_series),
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def concept_history_counts(
        self,
        concept_keys: Sequence[str],
        lookback_days: int,
        projection_version: str = MACRO_VIEW_PROJECTION_VERSION,
    ) -> list[dict[str, Any]]:
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
                     array_remove(
                       array_agg(DISTINCT rows.source_name ORDER BY rows.source_name),
                       NULL
                     ) AS sources
              FROM macro_observation_series_rows AS rows
              JOIN requested ON requested.concept_key = rows.concept_key
              WHERE rows.projection_version = %s
                AND rows.observed_at >= CURRENT_DATE - %s::int
                AND rows.value_numeric IS NOT NULL
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
            (list(concept_keys), projection_version, int(lookback_days)),
        ).fetchall()
        return [dict(row) for row in rows]

    def insert_snapshot(self, snapshot: Mapping[str, Any]) -> bool:
        payload = _macro_snapshot_payload(snapshot)
        payload_hash = stable_current_payload_hash(_macro_snapshot_hash_payload(payload))
        cursor = self.conn.execute(
            """
            INSERT INTO macro_view_snapshots(
              projection_version, asof_date, status, regime, overall_score, panels_json,
              indicators_json, triggers_json, data_gaps_json, source_coverage_json, features_json,
              chain_json, scenario_json, scorecard_json, assets_brief_json, module_views_json,
              computed_at_ms, payload_hash
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(projection_version) DO UPDATE SET
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
              assets_brief_json = excluded.assets_brief_json,
              module_views_json = excluded.module_views_json,
              computed_at_ms = excluded.computed_at_ms,
              payload_hash = excluded.payload_hash
            WHERE macro_view_snapshots.payload_hash IS DISTINCT FROM excluded.payload_hash
            RETURNING true AS changed
            """,
            (
                snapshot["projection_version"],
                snapshot["asof_date"],
                snapshot["status"],
                snapshot["regime"],
                payload["overall_score"],
                Jsonb(payload["panels_json"]),
                Jsonb(payload["indicators_json"]),
                Jsonb(payload["triggers_json"]),
                Jsonb(payload["data_gaps_json"]),
                Jsonb(payload["source_coverage_json"]),
                Jsonb(payload["features_json"]),
                Jsonb(payload["chain_json"]),
                Jsonb(payload["scenario_json"]),
                Jsonb(payload["scorecard_json"]),
                Jsonb(payload["assets_brief_json"]),
                Jsonb(payload["module_views_json"]),
                int(snapshot["computed_at_ms"]),
                payload_hash,
            ),
        )
        row = cursor.fetchone()
        return row is not None

    def latest_snapshot(
        self,
        *,
        projection_version: str | None = MACRO_VIEW_PROJECTION_VERSION,
    ) -> dict[str, Any] | None:
        if projection_version is None:
            raise ValueError("projection_version is required")
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

    def module_view(
        self,
        *,
        module_id: str,
        projection_version: str = MACRO_VIEW_PROJECTION_VERSION,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT module_views_json -> %s AS module_view
            FROM macro_view_snapshots
            WHERE projection_version = %s
            LIMIT 1
            """,
            (module_id, projection_version),
        ).fetchone()
        if row is None:
            return None
        module_view = dict(row).get("module_view")
        if module_view is None:
            return None
        if not isinstance(module_view, Mapping):
            raise RuntimeError(f"macro_module_view_payload_invalid:{module_id}")
        return dict(module_view)

    def observations_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS count FROM macro_observations").fetchone()
        return _count(row)

    def concept_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(DISTINCT concept_key) AS count FROM macro_observations").fetchone()
        return _count(row)


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
            "value_numeric": None if row.get("value_numeric") is None else str(row.get("value_numeric")),
            "source_name": str(row.get("source_name") or ""),
            "series_key": str(row.get("series_key") or ""),
            "unit": row.get("unit"),
            "frequency": row.get("frequency"),
            "data_quality": str(row.get("data_quality") or ""),
            "event_metadata_json": dict(row.get("event_metadata_json") or {}),
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
    selected_by_concept = _series_payload_signatures_by_concept(selected_rows)
    existing_by_concept = _series_payload_signatures_by_concept(existing_rows)
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
    selected_by_concept = _series_payload_signatures_by_concept(selected_rows)
    existing_by_concept = _series_payload_signatures_by_concept(existing_rows)
    return [
        concept_key
        for concept_key in concept_keys
        if not selected_by_concept.get(concept_key) and existing_by_concept.get(concept_key)
    ]


def _series_payload_signatures_by_concept(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, list[tuple[str, str]]]:
    grouped: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        concept_key = str(row.get("concept_key") or "").strip()
        if not concept_key:
            continue
        payload_hash = stable_current_payload_hash(_compact_series_payload(row))
        grouped.setdefault(concept_key, []).append(
            (
                str(row.get("observed_at") or ""),
                payload_hash,
            )
        )
    for hashes in grouped.values():
        hashes.sort()
    return grouped


def _compact_series_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "projection_version": row.get("projection_version"),
        "concept_key": row.get("concept_key"),
        "observed_at": normalize_macro_date(row.get("observed_at")),
        "value_numeric": row.get("value_numeric"),
        "source_name": row.get("source_name"),
        "series_key": row.get("series_key"),
        "unit": row.get("unit"),
        "frequency": row.get("frequency"),
        "data_quality": row.get("data_quality"),
        "event_metadata_json": dict(row.get("event_metadata_json") or {}),
    }


def _compact_series_row(row: Mapping[str, Any]) -> dict[str, Any]:
    compact = dict(row)
    raw_payload = compact.pop("raw_payload_json", None)
    compact["event_metadata_json"] = _event_metadata_json(
        concept_key=str(compact.get("concept_key") or ""),
        raw_payload=raw_payload,
    )
    return compact


def _event_metadata_json(*, concept_key: str, raw_payload: object) -> dict[str, Any]:
    if concept_key not in MACRO_EVENT_CONCEPTS or not isinstance(raw_payload, Mapping):
        return {}
    provenance = raw_payload.get("provenance")
    first_provenance = (
        provenance[0]
        if isinstance(provenance, Sequence)
        and not isinstance(provenance, str | bytes | bytearray)
        and provenance
        and isinstance(provenance[0], Mapping)
        else {}
    )
    metadata: dict[str, Any] = {}
    raw_value = raw_payload.get("value")
    text_value = _first_non_empty_text(
        raw_value if isinstance(raw_value, str) else None,
        first_provenance.get("document_title"),
    )
    source_url = _first_non_empty_text(
        first_provenance.get("source_url"),
        raw_payload.get("source_url"),
        raw_payload.get("url"),
    )
    event_code = _first_non_empty_text(raw_payload.get("series_key"))
    if text_value is not None:
        metadata["text_value"] = text_value
    if source_url is not None:
        metadata["source_url"] = source_url
    if event_code is not None:
        metadata["event_code"] = event_code
    for field_name in (
        "document_type",
        "speaker",
        "event_time",
        "event_time_et",
        "reference_period",
        "cusip",
        "announcement_date",
        "settlement_date",
    ):
        value = _first_non_empty_text(first_provenance.get(field_name), raw_payload.get(field_name))
        if value is not None:
            metadata[field_name] = value
    if bool(first_provenance.get("reopening") or raw_payload.get("reopening")):
        metadata["reopening"] = True
    return metadata


def _first_non_empty_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _macro_snapshot_payload(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "projection_version": snapshot["projection_version"],
        "asof_date": snapshot["asof_date"],
        "status": snapshot["status"],
        "regime": snapshot["regime"],
        "overall_score": snapshot.get("overall_score"),
        "panels_json": _required_snapshot_mapping(snapshot, "panels_json"),
        "indicators_json": _required_snapshot_mapping(snapshot, "indicators_json"),
        "triggers_json": _required_snapshot_list(snapshot, "triggers_json"),
        "data_gaps_json": _required_snapshot_list(snapshot, "data_gaps_json"),
        "source_coverage_json": _required_snapshot_mapping(snapshot, "source_coverage_json"),
        "features_json": _required_snapshot_mapping(snapshot, "features_json"),
        "chain_json": _required_snapshot_mapping(snapshot, "chain_json"),
        "scenario_json": _required_snapshot_mapping(snapshot, "scenario_json"),
        "scorecard_json": _required_snapshot_mapping(snapshot, "scorecard_json"),
        "assets_brief_json": _required_snapshot_mapping(snapshot, "assets_brief_json"),
        "module_views_json": _required_module_views(snapshot),
    }
    return payload


def _macro_snapshot_hash_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return _without_lifecycle_clocks(payload)


def _required_module_views(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    module_views = _required_snapshot_mapping(snapshot, "module_views_json")
    expected = set(MACRO_MODULE_IDS)
    actual = set(module_views)
    if actual != expected:
        missing = ",".join(sorted(expected - actual))
        extra = ",".join(sorted(actual - expected))
        raise RuntimeError(f"macro_module_views_catalog_mismatch:missing={missing}:extra={extra}")
    for module_id, module_view in module_views.items():
        if not isinstance(module_view, Mapping):
            raise RuntimeError(f"macro_module_view_payload_invalid:{module_id}")
        header = module_view.get("snapshot")
        if not isinstance(header, Mapping) or str(header.get("module_id") or "") != module_id:
            raise RuntimeError(f"macro_module_view_snapshot_invalid:{module_id}")
    return module_views


def _without_lifecycle_clocks(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _without_lifecycle_clocks(item)
            for key, item in value.items()
            if str(key) not in {"computed_at_ms", "computed_at_label"}
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_without_lifecycle_clocks(item) for item in value]
    return value


def _required_snapshot_mapping(snapshot: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    try:
        value = snapshot[field_name]
    except KeyError as exc:
        raise RuntimeError(f"macro_view_snapshot_payload_required:{field_name}") from exc
    if value is None:
        raise RuntimeError(f"macro_view_snapshot_payload_required:{field_name}")
    if not isinstance(value, Mapping):
        raise RuntimeError(f"macro_view_snapshot_payload_invalid:{field_name}")
    return dict(value)


def _required_snapshot_list(snapshot: Mapping[str, Any], field_name: str) -> list[Any]:
    try:
        value = snapshot[field_name]
    except KeyError as exc:
        raise RuntimeError(f"macro_view_snapshot_payload_required:{field_name}") from exc
    if value is None:
        raise RuntimeError(f"macro_view_snapshot_payload_required:{field_name}")
    if isinstance(value, Mapping | str | bytes | bytearray):
        raise RuntimeError(f"macro_view_snapshot_payload_invalid:{field_name}")
    if not isinstance(value, Sequence):
        raise RuntimeError(f"macro_view_snapshot_payload_invalid:{field_name}")
    return list(value)


def _required_observation_text(observation: Mapping[str, Any], field_name: str) -> str:
    value = observation.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"macro_observation_{field_name}_required")
    return value.strip()


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
    return stable_dirty_target_payload_hash(payload)


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
    return stable_dirty_target_payload_hash(payload)


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


def _macro_projection_dirty_target_key(row: Mapping[str, Any]) -> str:
    return ":".join(
        str(row[field_name]) for field_name in ("projection_name", "projection_version", "target_kind", "target_id")
    )


def _macro_projection_retry_budget_exhausted_reason(error: str) -> str:
    message = str(error or "").strip()
    return f"macro_view_projection_retry_budget_exhausted: {message}"[:2048]


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


__all__ = ["MacroIntelRepository", "MacroSeriesRefreshResult"]
