from __future__ import annotations

from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb


class TokenRadarRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def replace_rows(
        self,
        *,
        projection_version: str,
        window: str,
        scope: str,
        computed_at_ms: int,
        rows: list[dict[str, Any]],
        commit: bool = True,
    ) -> bool:
        self.conn.execute(
            """
            SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))
            """,
            (projection_version, f"{window}:{scope}"),
        )
        latest = self.conn.execute(
            """
            SELECT MAX(computed_at_ms) AS computed_at_ms
            FROM token_radar_rows
            WHERE projection_version = %s AND "window" = %s AND scope = %s
            """,
            (projection_version, window, scope),
        ).fetchone()
        latest_computed_at_ms = (
            int(latest["computed_at_ms"])
            if latest and latest["computed_at_ms"] is not None
            else None
        )
        if latest_computed_at_ms is not None and latest_computed_at_ms > int(computed_at_ms):
            if commit:
                self.conn.commit()
            return False
        self.conn.execute(
            """
            DELETE FROM token_radar_rows
            WHERE projection_version = %s AND "window" = %s AND scope = %s
            """,
            (projection_version, window, scope),
        )
        for row in rows:
            self.conn.execute(
                """
                INSERT INTO token_radar_rows(
                  row_id, projection_version, "window", scope, computed_at_ms, source_max_received_at_ms,
                  lane, rank, intent_id, event_id, target_type, target_id, pricefeed_id, intent_json,
                  asset_json, primary_venue_json, target_json, attention_json, resolution_json, market_json,
                  price_json, score_json, decision, data_health_json,
                  source_event_ids_json, created_at_ms
                )
                VALUES (
                  %(row_id)s, %(projection_version)s, %(window)s, %(scope)s, %(computed_at_ms)s,
                  %(source_max_received_at_ms)s, %(lane)s, %(rank)s, %(intent_id)s, %(event_id)s,
                  %(target_type)s, %(target_id)s, %(pricefeed_id)s, %(intent_json)s, %(asset_json)s,
                  %(primary_venue_json)s, %(target_json)s, %(attention_json)s, %(resolution_json)s,
                  %(market_json)s, %(price_json)s, %(score_json)s, %(decision)s, %(data_health_json)s,
                  %(source_event_ids_json)s, %(created_at_ms)s
                )
                """,
                _json_payload(
                    {
                        **row,
                        "projection_version": projection_version,
                        "window": window,
                        "scope": scope,
                        "computed_at_ms": computed_at_ms,
                    }
                ),
            )
        if commit:
            self.conn.commit()
        return True

    def latest_rows(
        self,
        *,
        window: str,
        scope: str,
        limit: int,
        projection_version: str,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH latest AS (
              SELECT MAX(computed_at_ms) AS computed_at_ms
              FROM token_radar_rows
              WHERE projection_version = %s AND "window" = %s AND scope = %s
            ),
            ranked AS (
              SELECT
                token_radar_rows.*,
                row_number() OVER (PARTITION BY lane ORDER BY rank ASC) AS lane_rank
              FROM token_radar_rows
              JOIN latest
                ON token_radar_rows.computed_at_ms = latest.computed_at_ms
              WHERE token_radar_rows.projection_version = %s
                AND token_radar_rows."window" = %s
                AND token_radar_rows.scope = %s
            )
            SELECT *
            FROM ranked
            WHERE lane_rank <= %s
            ORDER BY lane DESC, rank ASC
            LIMIT %s
            """,
            (
                projection_version,
                window,
                scope,
                projection_version,
                window,
                scope,
                max(0, int(limit)),
                max(0, int(limit)) * 2,
            ),
        ).fetchall()
        return [dict(row) for row in rows]


def _json_payload(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in (
        "intent_json",
        "asset_json",
        "primary_venue_json",
        "target_json",
        "attention_json",
        "resolution_json",
        "market_json",
        "price_json",
        "score_json",
        "data_health_json",
        "source_event_ids_json",
    ):
        payload = out.get(key) if out.get(key) is not None else ([] if key.endswith("_ids_json") else {})
        out[key] = Jsonb(_json_ready(payload))
    return out


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    return value
