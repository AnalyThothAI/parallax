from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from psycopg.types.json import Jsonb


class MacroIntelRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_observation(self, observation: Mapping[str, Any]) -> str:
        observation_id = str(observation.get("observation_id") or _observation_id(observation))
        self.conn.execute(
            """
            INSERT INTO macro_observations(
              observation_id, source_name, series_key, observed_at, value_numeric, unit, frequency,
              data_quality, source_ts, raw_payload_json, ingested_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(source_name, series_key, observed_at) DO UPDATE SET
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
                str(observation["series_key"]),
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

    def latest_observations(
        self,
        *,
        limit: int = 250,
        series_keys: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        bounded_limit = max(1, int(limit))
        if series_keys:
            rows = self.conn.execute(
                """
                WITH ranked AS (
                  SELECT *,
                         row_number() OVER (
                           PARTITION BY series_key
                           ORDER BY observed_at DESC, ingested_at_ms DESC
                         ) AS rn
                  FROM macro_observations
                  WHERE series_key = ANY(%s)
                )
                SELECT *
                FROM ranked
                WHERE rn = 1
                ORDER BY series_key ASC
                LIMIT %s
                """,
                (list(series_keys), bounded_limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                WITH ranked AS (
                  SELECT *,
                         row_number() OVER (
                           PARTITION BY series_key
                           ORDER BY observed_at DESC, ingested_at_ms DESC
                         ) AS rn
                  FROM macro_observations
                )
                SELECT *
                FROM ranked
                WHERE rn = 1
                ORDER BY series_key ASC
                LIMIT %s
                """,
                (bounded_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO macro_view_snapshots(
              snapshot_id, projection_version, asof_date, status, regime, overall_score, panels_json,
              indicators_json, triggers_json, data_gaps_json, source_coverage_json, computed_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(snapshot_id) DO UPDATE SET
              status = excluded.status,
              regime = excluded.regime,
              overall_score = excluded.overall_score,
              panels_json = excluded.panels_json,
              indicators_json = excluded.indicators_json,
              triggers_json = excluded.triggers_json,
              data_gaps_json = excluded.data_gaps_json,
              source_coverage_json = excluded.source_coverage_json,
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
                int(snapshot["computed_at_ms"]),
            ),
        )
        self.conn.commit()

    def latest_snapshot(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM macro_view_snapshots
            ORDER BY computed_at_ms DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row is not None else None


def _observation_id(observation: Mapping[str, Any]) -> str:
    identity = "|".join(
        [
            str(observation.get("source_name") or ""),
            str(observation.get("series_key") or ""),
            str(observation.get("observed_at") or ""),
        ]
    )
    digest = hashlib.sha256(identity.encode()).hexdigest()[:32]
    return f"macro-observation:{digest}"


__all__ = ["MacroIntelRepository"]
