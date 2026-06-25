from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, cast


class TokenIntentLookupRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def replace_lookup_keys(
        self,
        *,
        intent_id: str,
        event_id: str,
        keys: list[str],
        source_evidence_id: str | None,
        created_at_ms: int,
        commit: bool = True,
    ) -> None:
        def _write() -> None:
            delete_cursor = self.conn.execute("DELETE FROM token_intent_lookup_keys WHERE intent_id = %s", (intent_id,))
            _cursor_rowcount(delete_cursor)
            for key in sorted(set(keys)):
                cursor = self.conn.execute(
                    """
                    INSERT INTO token_intent_lookup_keys(
                      lookup_key, intent_id, event_id, source_evidence_id, created_at_ms
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT(lookup_key, intent_id) DO UPDATE SET
                      source_evidence_id = excluded.source_evidence_id,
                      created_at_ms = excluded.created_at_ms
                    """,
                    (key, intent_id, event_id, source_evidence_id, int(created_at_ms)),
                )
                _required_single_rowcount(cursor)

        _run_repository_write(self.conn, commit, _write)

    def keys_for_intent(self, intent_id: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT lookup_key
            FROM token_intent_lookup_keys
            WHERE intent_id = %s
            ORDER BY lookup_key
            """,
            (intent_id,),
        ).fetchall()
        return [str(row["lookup_key"]) for row in rows]

    def intents_for_lookup_keys(self, keys: list[str], *, limit: int) -> list[dict[str, Any]]:
        if not keys:
            return []
        placeholders = ",".join("%s" for _ in keys)
        rows = self.conn.execute(
            f"""
            SELECT DISTINCT intent_id, event_id
            FROM token_intent_lookup_keys
            WHERE lookup_key IN ({placeholders})
            ORDER BY intent_id
            LIMIT %s
            """,
            (*keys, int(limit)),
        ).fetchall()
        return [dict(row) for row in rows]

    def recent_intents_for_lookup_keys(
        self,
        keys: list[str],
        *,
        since_ms: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        parsed_limit = _required_positive_int(limit, "token_intent_lookup_limit_required")
        if not keys:
            return []
        placeholders = ",".join("%s" for _ in keys)
        rows = self.conn.execute(
            f"""
            WITH picked AS (
              SELECT DISTINCT token_intents.intent_id
              FROM token_intent_lookup_keys
              JOIN token_intents ON token_intents.intent_id = token_intent_lookup_keys.intent_id
              JOIN events ON events.event_id = token_intents.event_id
              WHERE token_intent_lookup_keys.lookup_key IN ({placeholders})
                AND events.received_at_ms >= %s
              ORDER BY token_intents.intent_id
              LIMIT %s
            )
            SELECT token_intents.*
            FROM picked
            JOIN token_intents ON token_intents.intent_id = picked.intent_id
            ORDER BY token_intents.created_at_ms DESC, token_intents.intent_id
            """,
            (*keys, int(since_ms), parsed_limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def recent_unresolved_intents_for_lookup_keys(
        self,
        keys: list[str],
        *,
        since_ms: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        parsed_limit = _required_positive_int(limit, "token_intent_lookup_limit_required")
        if not keys:
            return []
        placeholders = ",".join("%s" for _ in keys)
        rows = self.conn.execute(
            f"""
            WITH picked AS (
              SELECT DISTINCT token_intents.intent_id
              FROM token_intent_lookup_keys
              JOIN token_intents ON token_intents.intent_id = token_intent_lookup_keys.intent_id
              JOIN events ON events.event_id = token_intents.event_id
              LEFT JOIN token_intent_resolutions current_resolution
                ON current_resolution.intent_id = token_intents.intent_id
               AND current_resolution.is_current = true
              WHERE token_intent_lookup_keys.lookup_key IN ({placeholders})
                AND events.received_at_ms >= %s
                AND (
                  current_resolution.resolution_id IS NULL
                  OR current_resolution.resolution_status IN ('NIL', 'AMBIGUOUS')
                )
              ORDER BY token_intents.intent_id
              LIMIT %s
            )
            SELECT token_intents.*
            FROM picked
            JOIN token_intents ON token_intents.intent_id = picked.intent_id
            ORDER BY token_intents.created_at_ms DESC, token_intents.intent_id
            """,
            (*keys, int(since_ms), parsed_limit),
        ).fetchall()
        return [dict(row) for row in rows]


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("token_intent_lookup_repository_transaction_required") from exc
    if not callable(transaction):
        raise RuntimeError("token_intent_lookup_repository_transaction_required")
    return cast(AbstractContextManager[Any], transaction())


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("token_intent_lookup_repository_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int) or rowcount < 0:
        raise TypeError("token_intent_lookup_repository_rowcount_invalid")
    return rowcount


def _required_single_rowcount(cursor: Any) -> int:
    rowcount = _cursor_rowcount(cursor)
    if rowcount != 1:
        raise TypeError("token_intent_lookup_repository_rowcount_invalid")
    return rowcount


def _required_positive_int(value: Any, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(error_code)
    if value <= 0:
        raise ValueError(error_code)
    return int(value)


def _run_repository_write[T](conn: Any, commit: bool, write: Callable[[], T]) -> T:
    if commit:
        with _transaction(conn):
            return write()
    return write()
