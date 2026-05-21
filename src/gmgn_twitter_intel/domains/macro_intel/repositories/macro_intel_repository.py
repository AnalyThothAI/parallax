from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.macro_intel._constants import MACRO_VIEW_PROJECTION_VERSION


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

    def latest_observations(
        self,
        *,
        limit: int = 250,
        concept_keys: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        bounded_limit = max(1, int(limit))
        if concept_keys:
            rows = self.conn.execute(
                """
                WITH ranked AS (
                  SELECT *,
                         row_number() OVER (
                           PARTITION BY concept_key
                           ORDER BY observed_at DESC, source_priority DESC, ingested_at_ms DESC
                         ) AS rn
                  FROM macro_observations
                  WHERE concept_key = ANY(%s)
                )
                SELECT *
                FROM ranked
                WHERE rn = 1
                ORDER BY concept_key ASC
                LIMIT %s
                """,
                (list(concept_keys), bounded_limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                WITH ranked AS (
                  SELECT *,
                         row_number() OVER (
                           PARTITION BY concept_key
                           ORDER BY observed_at DESC, source_priority DESC, ingested_at_ms DESC
                         ) AS rn
                  FROM macro_observations
                )
                SELECT *
                FROM ranked
                WHERE rn = 1
                ORDER BY concept_key ASC
                LIMIT %s
                """,
                (bounded_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def observations_for_concepts(
        self,
        *,
        concept_keys: Sequence[str],
        lookback_days: int,
        limit_per_series: int,
    ) -> list[dict[str, Any]]:
        bounded_lookback_days = max(1, int(lookback_days))
        bounded_limit_per_series = max(1, int(limit_per_series))
        rows = self.conn.execute(
            """
            WITH deduped AS (
              SELECT *,
                     row_number() OVER (
                       PARTITION BY concept_key, observed_at
                       ORDER BY source_priority DESC, ingested_at_ms DESC
                     ) AS dedupe_rn
              FROM macro_observations
              WHERE concept_key = ANY(%s)
                AND observed_at >= CURRENT_DATE - %s::int
            ),
            ranked AS (
              SELECT *,
                     row_number() OVER (
                       PARTITION BY concept_key
                       ORDER BY observed_at DESC, source_priority DESC, ingested_at_ms DESC
                     ) AS series_rn
              FROM deduped
              WHERE dedupe_rn = 1
            )
            SELECT *
            FROM ranked
            WHERE series_rn <= %s
            ORDER BY concept_key ASC, observed_at DESC, source_priority DESC, ingested_at_ms DESC
            """,
            (list(concept_keys), bounded_lookback_days, bounded_limit_per_series),
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


def _count(row: Any) -> int:
    if row is None:
        return 0
    return int(dict(row).get("count") or 0)


__all__ = ["MacroIntelRepository"]
