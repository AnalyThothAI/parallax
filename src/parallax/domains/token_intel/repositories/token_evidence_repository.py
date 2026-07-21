from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any, cast

from parallax.domains.token_intel.types.token_fact_inputs import TokenEvidenceInput

TokenEvidenceWriteInput = TokenEvidenceInput | Mapping[str, Any]


class TokenEvidenceRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def insert_many(self, evidence: Sequence[TokenEvidenceWriteInput], *, commit: bool = True) -> list[dict[str, Any]]:
        def _write() -> list[dict[str, Any]]:
            return [self.insert(item, commit=False) for item in evidence]

        return _run_repository_write(self.conn, commit, _write)

    def insert(self, evidence: TokenEvidenceWriteInput, *, commit: bool = True) -> dict[str, Any]:
        def _write() -> dict[str, Any]:
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

        return _run_repository_write(self.conn, commit, _write)

    def get(self, evidence_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM token_evidence WHERE evidence_id = %s", (evidence_id,)).fetchone()
        return dict(row) if row else None

    def delete_by_event_id(self, event_id: str) -> None:
        cursor = self.conn.execute("DELETE FROM token_evidence WHERE event_id = %s", (event_id,))
        _cursor_rowcount(cursor)

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


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("token_evidence_repository_transaction_required") from exc
    if not callable(transaction):
        raise RuntimeError("token_evidence_repository_transaction_required")
    return cast(AbstractContextManager[Any], transaction())


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("token_evidence_repository_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int) or rowcount < 0:
        raise TypeError("token_evidence_repository_rowcount_invalid")
    return rowcount


def _required_single_rowcount(cursor: Any) -> int:
    rowcount = _cursor_rowcount(cursor)
    if rowcount != 1:
        raise TypeError("token_evidence_repository_rowcount_invalid")
    return rowcount


def _required_returning_row(cursor: Any, row: Any | None) -> dict[str, Any]:
    _required_single_rowcount(cursor)
    if row is None:
        raise TypeError("token_evidence_repository_rowcount_invalid")
    return dict(row)


def _run_repository_write[T](conn: Any, commit: bool, write: Callable[[], T]) -> T:
    if commit:
        with _transaction(conn):
            return write()
    return write()
