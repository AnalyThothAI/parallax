from __future__ import annotations

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
    ) -> None:
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
                  lane, rank, intent_id, event_id, asset_id, primary_venue_id, intent_json,
                  asset_json, primary_venue_json, attention_json, resolution_json, market_json,
                  score_json, decision, data_health_json, source_event_ids_json, created_at_ms
                )
                VALUES (
                  %(row_id)s, %(projection_version)s, %(window)s, %(scope)s, %(computed_at_ms)s,
                  %(source_max_received_at_ms)s, %(lane)s, %(rank)s, %(intent_id)s, %(event_id)s,
                  %(asset_id)s, %(primary_venue_id)s, %(intent_json)s, %(asset_json)s,
                  %(primary_venue_json)s, %(attention_json)s, %(resolution_json)s, %(market_json)s,
                  %(score_json)s, %(decision)s, %(data_health_json)s, %(source_event_ids_json)s,
                  %(created_at_ms)s
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

    def latest_rows(
        self,
        *,
        window: str,
        scope: str,
        limit: int,
        projection_version: str = "token-radar-v3",
    ) -> list[dict[str, Any]]:
        latest = self.conn.execute(
            """
            SELECT MAX(computed_at_ms) AS computed_at_ms
            FROM token_radar_rows
            WHERE projection_version = %s AND "window" = %s AND scope = %s
            """,
            (projection_version, window, scope),
        ).fetchone()
        computed_at_ms = latest["computed_at_ms"] if latest else None
        if computed_at_ms is None:
            return []
        rows = self.conn.execute(
            """
            SELECT *
            FROM token_radar_rows
            WHERE projection_version = %s AND "window" = %s AND scope = %s AND computed_at_ms = %s
            ORDER BY lane DESC, rank ASC
            LIMIT %s
            """,
            (projection_version, window, scope, computed_at_ms, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]


def _json_payload(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in (
        "intent_json",
        "asset_json",
        "primary_venue_json",
        "attention_json",
        "resolution_json",
        "market_json",
        "score_json",
        "data_health_json",
        "source_event_ids_json",
    ):
        out[key] = Jsonb(out.get(key) if out.get(key) is not None else ([] if key.endswith("_ids_json") else {}))
    return out
