from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tracefold.market.identity.token_fact_inputs import TokenEvidenceInput
from tracefold.platform.postgres.postgres_client import require_transaction
from tracefold.platform.postgres.write_contract import expect_mutation_count, mutation_count

TokenEvidenceWriteInput = TokenEvidenceInput | Mapping[str, Any]


class TokenEvidenceRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def insert_many(self, evidence: Sequence[TokenEvidenceWriteInput]) -> list[dict[str, Any]]:
        require_transaction(self.conn, operation="insert_token_evidence_batch")
        return [self.insert(item) for item in evidence]

    def insert(self, evidence: TokenEvidenceWriteInput) -> dict[str, Any]:
        require_transaction(self.conn, operation="insert_token_evidence")
        payload = _payload(evidence)
        cursor = self.conn.execute(
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
            RETURNING *
            """,
            payload,
        )
        row = cursor.fetchone()
        return _required_returning_row(cursor, row)

    def get(self, evidence_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM token_evidence WHERE evidence_id = %s", (evidence_id,)).fetchone()
        return dict(row) if row else None

    def delete_by_event_id(self, event_id: str) -> None:
        require_transaction(self.conn, operation="delete_token_evidence_by_event")
        cursor = self.conn.execute("DELETE FROM token_evidence WHERE event_id = %s", (event_id,))
        mutation_count(cursor, error_code="token_evidence_repository_rowcount_invalid")

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

    def evidence_for_intents(self, intent_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        normalized = _unique_ids(intent_ids)
        if not normalized:
            return {}
        rows = self.conn.execute(
            """
            WITH input_intents AS (
              SELECT intent_id, ordinality
              FROM unnest(%s::text[]) WITH ORDINALITY AS input(intent_id, ordinality)
            ),
            distinct_intents AS (
              SELECT intent_id, MIN(ordinality) AS ordinality
              FROM input_intents
              GROUP BY intent_id
            )
            SELECT
              token_intent_evidence.intent_id,
              token_evidence.*
            FROM distinct_intents
            JOIN token_intent_evidence
              ON token_intent_evidence.intent_id = distinct_intents.intent_id
            JOIN token_evidence
              ON token_evidence.evidence_id = token_intent_evidence.evidence_id
            ORDER BY distinct_intents.ordinality ASC,
              token_intent_evidence.role ASC,
              token_evidence.text_surface ASC,
              token_evidence.span_start ASC,
              token_evidence.evidence_id ASC
            """,
            (normalized,),
        ).fetchall()
        evidence_by_intent: dict[str, list[dict[str, Any]]] = {intent_id: [] for intent_id in normalized}
        for row in rows:
            evidence = dict(row)
            intent_id = str(evidence.pop("intent_id"))
            if intent_id in evidence_by_intent:
                evidence_by_intent[intent_id].append(evidence)
        return evidence_by_intent


def _payload(item: TokenEvidenceWriteInput) -> dict[str, Any]:
    if isinstance(item, TokenEvidenceInput):
        return {
            "evidence_id": item.evidence_id,
            "event_id": item.event_id,
            "source_kind": item.source_kind,
            "source_id": item.source_id,
            "evidence_type": item.evidence_type,
            "raw_value": item.raw_value,
            "normalized_symbol": item.normalized_symbol,
            "chain_hint": item.chain_hint,
            "address_hint": item.address_hint,
            "provider": item.provider,
            "provider_ref": item.provider_ref,
            "text_surface": item.text_surface,
            "span_start": item.span_start,
            "span_end": item.span_end,
            "sentence_id": item.sentence_id,
            "local_group_key": item.local_group_key,
            "strength": item.strength,
            "confidence": item.confidence,
            "created_at_ms": item.created_at_ms,
        }
    if isinstance(item, Mapping):
        return dict(item)
    raise TypeError("token_evidence_repository_input_contract_required")


def _unique_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        parsed = str(value).strip()
        if not parsed or parsed in seen:
            continue
        seen.add(parsed)
        unique.append(parsed)
    return unique


def _required_returning_row(cursor: Any, row: Any | None) -> dict[str, Any]:
    expect_mutation_count(cursor, expected=1, error_code="token_evidence_repository_rowcount_invalid")
    if row is None:
        raise TypeError("token_evidence_repository_rowcount_invalid")
    return dict(row)
