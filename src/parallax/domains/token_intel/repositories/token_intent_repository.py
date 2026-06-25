from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any, cast

from parallax.domains.token_intel.types.token_fact_inputs import TokenIntentEvidenceLink, TokenIntentInput

TokenIntentWriteInput = TokenIntentInput | Mapping[str, Any]


class TokenIntentRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def insert_many(self, intents: Sequence[TokenIntentWriteInput], *, commit: bool = True) -> list[dict[str, Any]]:
        def _write() -> list[dict[str, Any]]:
            return [self.insert(intent, commit=False) for intent in intents]

        return _run_repository_write(self.conn, commit, _write)

    def insert(self, intent: TokenIntentWriteInput, *, commit: bool = True) -> dict[str, Any]:
        def _write() -> dict[str, Any]:
            payload = _payload(intent)
            cursor = self.conn.execute(
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
                RETURNING *
                """,
                payload,
            )
            row = cursor.fetchone()
            intent_row = _required_returning_row(cursor, row)
            for link in _evidence_links(intent):
                cursor = self.conn.execute(
                    """
                    INSERT INTO token_intent_evidence(intent_id, evidence_id, role)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (payload["intent_id"], link.evidence_id, link.role),
                )
                _optional_single_rowcount(cursor)
            return intent_row

        return _run_repository_write(self.conn, commit, _write)

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

    def intents_for_events(self, event_ids: tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
        ids = _event_ids(event_ids)
        if not ids:
            return {}
        rows = self.conn.execute(
            """
            SELECT *
            FROM token_intents
            WHERE event_id = ANY(%s)
            ORDER BY event_id, created_at_ms, intent_id
            """,
            (ids,),
        ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            item = dict(row)
            grouped.setdefault(str(item["event_id"]), []).append(item)
        return grouped

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

    def delete_by_event_id(self, event_id: str) -> None:
        cursor = self.conn.execute("DELETE FROM token_intents WHERE event_id = %s", (event_id,))
        _cursor_rowcount(cursor)

    def recent_unresolved(self, *, since_ms: int, limit: int) -> list[dict[str, Any]]:
        parsed_limit = _required_nonnegative_int(limit, "token_intent_recent_unresolved_limit_required")
        if parsed_limit == 0:
            return []
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
            (int(since_ms), parsed_limit),
        ).fetchall()
        return [dict(row) for row in rows]


def _payload(item: TokenIntentWriteInput) -> dict[str, Any]:
    if isinstance(item, TokenIntentInput):
        payload = {
            "intent_id": item.intent_id,
            "event_id": item.event_id,
            "intent_key": item.intent_key,
            "construction_policy": item.construction_policy,
            "primary_evidence_id": item.primary_evidence_id,
            "display_symbol": item.display_symbol,
            "display_name": item.display_name,
            "chain_hint": item.chain_hint,
            "address_hint": item.address_hint,
            "intent_status": item.intent_status,
            "intent_confidence": item.intent_confidence,
            "created_at_ms": item.created_at_ms,
            "updated_at_ms": item.updated_at_ms,
        }
    elif isinstance(item, Mapping):
        payload = dict(item)
    else:
        raise TypeError("token_intent_repository_input_contract_required")
    payload.pop("evidence_links", None)
    return payload


def _evidence_links(item: TokenIntentWriteInput) -> list[TokenIntentEvidenceLink]:
    if isinstance(item, TokenIntentInput):
        return list(item.evidence_links)
    if isinstance(item, Mapping):
        return []
    raise TypeError("token_intent_repository_input_contract_required")


def _event_ids(event_ids: tuple[str, ...]) -> list[str]:
    return [event_id for event_id in dict.fromkeys(str(item).strip() for item in event_ids) if event_id]


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("token_intent_repository_transaction_required") from exc
    if not callable(transaction):
        raise RuntimeError("token_intent_repository_transaction_required")
    return cast(AbstractContextManager[Any], transaction())


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("token_intent_repository_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int) or rowcount < 0:
        raise TypeError("token_intent_repository_rowcount_invalid")
    return rowcount


def _required_single_rowcount(cursor: Any) -> int:
    rowcount = _cursor_rowcount(cursor)
    if rowcount != 1:
        raise TypeError("token_intent_repository_rowcount_invalid")
    return rowcount


def _optional_single_rowcount(cursor: Any) -> int:
    rowcount = _cursor_rowcount(cursor)
    if rowcount not in (0, 1):
        raise TypeError("token_intent_repository_rowcount_invalid")
    return rowcount


def _required_nonnegative_int(value: Any, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(error_code)
    if value < 0:
        raise ValueError(error_code)
    return int(value)


def _required_returning_row(cursor: Any, row: Any | None) -> dict[str, Any]:
    _required_single_rowcount(cursor)
    if row is None:
        raise TypeError("token_intent_repository_rowcount_invalid")
    return dict(row)


def _run_repository_write[T](conn: Any, commit: bool, write: Callable[[], T]) -> T:
    if commit:
        with _transaction(conn):
            return write()
    return write()
