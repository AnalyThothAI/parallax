from __future__ import annotations

import hashlib
from typing import Any

from psycopg.types.json import Jsonb


class IntentResolutionRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def insert_resolution(self, decision: Any, *, commit: bool = True) -> dict[str, Any]:
        payload = _payload(decision)
        resolution_id = _stable_id(
            "token-intent-resolution",
            str(payload["intent_id"]),
            str(payload.get("asset_id") or ""),
            str(payload.get("primary_venue_id") or ""),
            str(payload["decision_time_ms"]),
        )
        self.conn.execute(
            """
            UPDATE token_intent_resolutions
            SET resolution_status = 'superseded'
            WHERE intent_id = %s AND resolution_status <> 'superseded'
            """,
            (payload["intent_id"],),
        )
        self.conn.execute(
            """
            INSERT INTO token_intent_resolutions(
              resolution_id, intent_id, event_id, asset_id, primary_venue_id,
              resolution_status, identity_status, confidence, resolver_policy_version,
              reasons_json, risks_json, decision_time_ms, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(resolution_id) DO UPDATE SET
              resolution_status = excluded.resolution_status,
              identity_status = excluded.identity_status,
              confidence = excluded.confidence,
              reasons_json = excluded.reasons_json,
              risks_json = excluded.risks_json
            """,
            (
                resolution_id,
                payload["intent_id"],
                payload["event_id"],
                payload.get("asset_id"),
                payload.get("primary_venue_id"),
                payload["resolution_status"],
                payload["identity_status"],
                float(payload["confidence"]),
                payload["resolver_policy_version"],
                Jsonb(payload.get("reasons") or []),
                Jsonb(payload.get("risks") or []),
                int(payload["decision_time_ms"]),
                int(payload["created_at_ms"]),
            ),
        )
        if commit:
            self.conn.commit()
        return self.get(resolution_id) or {}

    def get(self, resolution_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM token_intent_resolutions WHERE resolution_id = %s",
            (resolution_id,),
        ).fetchone()
        return dict(row) if row else None

    def active_resolution_for_intent(self, intent_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM token_intent_resolutions
            WHERE intent_id = %s AND resolution_status <> 'superseded'
            ORDER BY decision_time_ms DESC
            LIMIT 1
            """,
            (intent_id,),
        ).fetchone()
        return dict(row) if row else None

    def resolutions_for_event(self, event_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM token_intent_resolutions
            WHERE event_id = %s AND resolution_status <> 'superseded'
            ORDER BY decision_time_ms, resolution_id
            """,
            (event_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def asset_seen_before(
        self,
        *,
        asset_id: str,
        author_handle: str | None,
        before_ms: int,
    ) -> tuple[bool, bool]:
        global_row = self.conn.execute(
            """
            SELECT 1 AS found
            FROM token_intent_resolutions
            WHERE asset_id = %s
              AND decision_time_ms < %s
              AND resolution_status <> 'superseded'
            LIMIT 1
            """,
            (asset_id, int(before_ms)),
        ).fetchone()
        author_seen = False
        if author_handle:
            author_row = self.conn.execute(
                """
                SELECT 1 AS found
                FROM token_intent_resolutions
                JOIN events ON events.event_id = token_intent_resolutions.event_id
                WHERE token_intent_resolutions.asset_id = %s
                  AND token_intent_resolutions.decision_time_ms < %s
                  AND token_intent_resolutions.resolution_status <> 'superseded'
                  AND events.author_handle = %s
                LIMIT 1
                """,
                (asset_id, int(before_ms), author_handle),
            ).fetchone()
            author_seen = bool(author_row)
        return bool(global_row), author_seen


def _payload(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    return {slot: getattr(item, slot) for slot in item.__slots__}


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
