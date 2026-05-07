from __future__ import annotations

from typing import Any


class TokenIntentRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def insert_many(self, intents: list[Any], *, commit: bool = True) -> list[dict[str, Any]]:
        rows = [self.insert(intent, commit=False) for intent in intents]
        if commit:
            self.conn.commit()
        return rows

    def insert(self, intent: Any, *, commit: bool = True) -> dict[str, Any]:
        payload = _payload(intent)
        self.conn.execute(
            """
            INSERT INTO token_intents(
              intent_id, event_id, intent_key, construction_policy, primary_evidence_id,
              display_symbol, display_name, chain_hint, address_hint, intent_status,
              intent_confidence, created_at_ms, updated_at_ms
            )
            VALUES (
              %(intent_id)s, %(event_id)s, %(intent_key)s, %(construction_policy)s, %(primary_evidence_id)s,
              %(display_symbol)s, %(display_name)s, %(chain_hint)s, %(address_hint)s, %(intent_status)s,
              %(intent_confidence)s, %(created_at_ms)s, %(updated_at_ms)s
            )
            ON CONFLICT(intent_id) DO UPDATE SET
              display_symbol = excluded.display_symbol,
              display_name = excluded.display_name,
              chain_hint = excluded.chain_hint,
              address_hint = excluded.address_hint,
              intent_status = excluded.intent_status,
              intent_confidence = excluded.intent_confidence,
              updated_at_ms = excluded.updated_at_ms
            """,
            payload,
        )
        for link in getattr(intent, "evidence_links", []):
            self.conn.execute(
                """
                INSERT INTO token_intent_evidence(intent_id, evidence_id, role)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (payload["intent_id"], link.evidence_id, link.role),
            )
        if commit:
            self.conn.commit()
        return self.get(payload["intent_id"]) or {}

    def get(self, intent_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM token_intents WHERE intent_id = %s", (intent_id,)).fetchone()
        return dict(row) if row else None

    def intents_for_event(self, event_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM token_intents
            WHERE event_id = %s
            ORDER BY created_at_ms, intent_id
            """,
            (event_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def evidence_links_for_intent(self, intent_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM token_intent_evidence
            WHERE intent_id = %s
            ORDER BY role, evidence_id
            """,
            (intent_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def recent_unresolved(self, *, since_ms: int, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT token_intents.*
            FROM token_intents
            JOIN events ON events.event_id = token_intents.event_id
            LEFT JOIN token_intent_resolutions current_resolution
              ON current_resolution.intent_id = token_intents.intent_id
             AND current_resolution.is_current = true
            WHERE events.received_at_ms >= %s
              AND (
                current_resolution.resolution_id IS NULL
                OR current_resolution.resolution_status IN ('NIL', 'AMBIGUOUS')
              )
            ORDER BY events.received_at_ms DESC, token_intents.intent_id
            LIMIT %s
            """,
            (int(since_ms), max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]


def _payload(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        payload = dict(item)
    else:
        payload = {slot: getattr(item, slot) for slot in item.__slots__ if slot != "evidence_links"}
    payload.pop("evidence_links", None)
    return payload
