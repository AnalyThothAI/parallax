from __future__ import annotations

from typing import Any


class TokenEvidenceRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def insert_many(self, evidence: list[Any], *, commit: bool = True) -> list[dict[str, Any]]:
        rows = [self.insert(item, commit=False) for item in evidence]
        if commit:
            self.conn.commit()
        return rows

    def insert(self, evidence: Any, *, commit: bool = True) -> dict[str, Any]:
        payload = _payload(evidence)
        self.conn.execute(
            """
            INSERT INTO token_evidence(
              evidence_id, event_id, source_kind, source_id, evidence_type, raw_value,
              normalized_symbol, chain_hint, address_hint, provider, provider_ref,
              text_surface, span_start, span_end, sentence_id, local_group_key,
              strength, confidence, created_at_ms
            )
            VALUES (
              %(evidence_id)s, %(event_id)s, %(source_kind)s, %(source_id)s, %(evidence_type)s, %(raw_value)s,
              %(normalized_symbol)s, %(chain_hint)s, %(address_hint)s, %(provider)s, %(provider_ref)s,
              %(text_surface)s, %(span_start)s, %(span_end)s, %(sentence_id)s, %(local_group_key)s,
              %(strength)s, %(confidence)s, %(created_at_ms)s
            )
            ON CONFLICT(evidence_id) DO UPDATE SET
              normalized_symbol = excluded.normalized_symbol,
              chain_hint = excluded.chain_hint,
              address_hint = excluded.address_hint,
              strength = excluded.strength,
              confidence = excluded.confidence
            """,
            payload,
        )
        if commit:
            self.conn.commit()
        return self.get(payload["evidence_id"]) or {}

    def get(self, evidence_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM token_evidence WHERE evidence_id = %s", (evidence_id,)).fetchone()
        return dict(row) if row else None

    def delete_by_event_id(self, event_id: str) -> None:
        self.conn.execute("DELETE FROM token_evidence WHERE event_id = %s", (event_id,))

    def evidence_for_event(self, event_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM token_evidence
            WHERE event_id = %s
            ORDER BY text_surface, span_start, evidence_id
            """,
            (event_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def evidence_for_intent(self, intent_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT token_evidence.*
            FROM token_intent_evidence
            JOIN token_evidence ON token_evidence.evidence_id = token_intent_evidence.evidence_id
            WHERE token_intent_evidence.intent_id = %s
            ORDER BY token_intent_evidence.role, token_evidence.text_surface, token_evidence.span_start,
              token_evidence.evidence_id
            """,
            (intent_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def _payload(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    return {slot: getattr(item, slot) for slot in item.__slots__}
