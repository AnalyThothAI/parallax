from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import Any, cast

from psycopg.types.json import Jsonb

from parallax.domains.token_intel.types.token_fact_inputs import DeterministicResolution

IntentResolutionWriteInput = DeterministicResolution | Mapping[str, Any]


class IntentResolutionRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def insert_resolution(self, decision: IntentResolutionWriteInput, *, commit: bool = True) -> dict[str, Any]:
        def _write() -> dict[str, Any]:
            payload = _payload(decision)
            resolution_id = token_intent_resolution_id(payload)
            decision_time_ms = int(payload["decision_time_ms"])
            self.conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (payload["intent_id"],),
            )
            current = self._active_resolution_for_intent_locked(str(payload["intent_id"]))
            if current is not None and int(current.get("decision_time_ms") or 0) > decision_time_ms:
                return current
            if current is not None and str(current.get("resolution_id") or "") != resolution_id:
                cursor = self.conn.execute(
                    """
                    UPDATE token_intent_resolutions
                    SET record_status = 'superseded',
                        is_current = false,
                        superseded_at_ms = %s
                    WHERE intent_id = %s AND is_current = true
                    """,
                    (decision_time_ms, payload["intent_id"]),
                )
                _required_single_rowcount(cursor)
            cursor = self.conn.execute(
                """
                INSERT INTO token_intent_resolutions(
                  resolution_id, intent_id, event_id, resolution_status, resolver_policy_version,
                  target_type, target_id, pricefeed_id, reason_codes_json, candidate_ids_json,
                  lookup_keys_json, record_status, is_current, decision_time_ms, created_at_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'current', true, %s, %s)
                ON CONFLICT(resolution_id) DO UPDATE SET
                  resolution_status = excluded.resolution_status,
                  resolver_policy_version = excluded.resolver_policy_version,
                  target_type = excluded.target_type,
                  target_id = excluded.target_id,
                  pricefeed_id = excluded.pricefeed_id,
                  reason_codes_json = excluded.reason_codes_json,
                  candidate_ids_json = excluded.candidate_ids_json,
                  lookup_keys_json = excluded.lookup_keys_json,
                  record_status = 'current',
                  is_current = true,
                  superseded_at_ms = NULL
                RETURNING *
                """,
                (
                    resolution_id,
                    payload["intent_id"],
                    payload["event_id"],
                    payload["resolution_status"],
                    payload["resolver_policy_version"],
                    payload.get("target_type"),
                    payload.get("target_id"),
                    payload.get("pricefeed_id"),
                    Jsonb(payload.get("reason_codes") or []),
                    Jsonb(payload.get("candidate_ids") or []),
                    Jsonb(payload.get("lookup_keys") or []),
                    decision_time_ms,
                    int(payload["created_at_ms"]),
                ),
            )
            row = cursor.fetchone()
            return _required_returning_row(cursor, row)

        return _run_repository_write(self.conn, commit, _write)

    def get(self, resolution_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM token_intent_resolutions WHERE resolution_id = %s",
            (resolution_id,),
        ).fetchone()
        return dict(row) if row else None

    def _active_resolution_for_intent_locked(self, intent_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM token_intent_resolutions
            WHERE intent_id = %s AND is_current = true
            ORDER BY decision_time_ms DESC, resolution_id DESC
            LIMIT 1
            FOR UPDATE
            """,
            (intent_id,),
        ).fetchone()
        return dict(row) if row else None

    def active_resolution_for_intent(self, intent_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM token_intent_resolutions
            WHERE intent_id = %s AND is_current = true
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
            WHERE event_id = %s AND is_current = true
            ORDER BY decision_time_ms, resolution_id
            """,
            (event_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def target_seen_before(
        self,
        *,
        target_type: str,
        target_id: str,
        author_handle: str | None,
        before_ms: int,
    ) -> tuple[bool, bool]:
        global_row = self.conn.execute(
            """
            SELECT 1 AS found
            FROM token_intent_resolutions
            WHERE target_type = %s
              AND target_id = %s
              AND decision_time_ms < %s
              AND is_current = true
            LIMIT 1
            """,
            (target_type, target_id, int(before_ms)),
        ).fetchone()
        author_seen = False
        if author_handle:
            author_row = self.conn.execute(
                """
                SELECT 1 AS found
                FROM token_intent_resolutions
                JOIN events ON events.event_id = token_intent_resolutions.event_id
                WHERE token_intent_resolutions.target_type = %s
                  AND token_intent_resolutions.target_id = %s
                  AND token_intent_resolutions.decision_time_ms < %s
                  AND token_intent_resolutions.is_current = true
                  AND events.author_handle = %s
                LIMIT 1
                """,
                (target_type, target_id, int(before_ms), author_handle),
            ).fetchone()
            author_seen = bool(author_row)
        return bool(global_row), author_seen


def _payload(item: IntentResolutionWriteInput) -> dict[str, Any]:
    if isinstance(item, DeterministicResolution):
        return {
            "intent_id": item.intent_id,
            "event_id": item.event_id,
            "resolution_status": item.resolution_status,
            "target_type": item.target_type,
            "target_id": item.target_id,
            "pricefeed_id": item.pricefeed_id,
            "resolver_policy_version": item.resolver_policy_version,
            "reason_codes": item.reason_codes,
            "candidate_ids": item.candidate_ids,
            "lookup_keys": item.lookup_keys,
            "decision_time_ms": item.decision_time_ms,
            "created_at_ms": item.created_at_ms,
        }
    if isinstance(item, Mapping):
        return dict(item)
    raise TypeError("intent_resolution_repository_input_contract_required")


def token_intent_resolution_id(item: IntentResolutionWriteInput) -> str:
    payload = _payload(item)
    return _stable_id(
        "token-intent-resolution",
        str(payload["intent_id"]),
        str(payload.get("target_type") or ""),
        str(payload.get("target_id") or ""),
        str(payload.get("pricefeed_id") or ""),
        str(payload["decision_time_ms"]),
    )


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("intent_resolution_repository_transaction_required") from exc
    if not callable(transaction):
        raise RuntimeError("intent_resolution_repository_transaction_required")
    return cast(AbstractContextManager[Any], transaction())


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("intent_resolution_repository_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int) or rowcount < 0:
        raise TypeError("intent_resolution_repository_rowcount_invalid")
    return rowcount


def _required_single_rowcount(cursor: Any) -> int:
    rowcount = _cursor_rowcount(cursor)
    if rowcount != 1:
        raise TypeError("intent_resolution_repository_rowcount_invalid")
    return rowcount


def _required_returning_row(cursor: Any, row: Any | None) -> dict[str, Any]:
    _required_single_rowcount(cursor)
    if row is None:
        raise TypeError("intent_resolution_repository_rowcount_invalid")
    return dict(row)


def _run_repository_write[T](conn: Any, commit: bool, write: Callable[[], T]) -> T:
    if commit:
        with _transaction(conn):
            return write()
    return write()
