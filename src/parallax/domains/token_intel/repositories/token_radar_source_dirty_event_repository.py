from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
from typing import Any, cast

from parallax.domains.token_intel._constants import TOKEN_RADAR_PROJECTION_VERSION
from parallax.platform.current_read_model_payload_hash import stable_dirty_target_payload_hash


def source_dirty_event_payload_hash(payload: Mapping[str, Any]) -> str:
    return stable_dirty_target_payload_hash(payload)


class TokenRadarSourceDirtyEventRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def enqueue_events(
        self,
        rows: Iterable[Mapping[str, Any]],
        *,
        reason: str,
        now_ms: int,
        due_at_ms: int | None = None,
        commit: bool = True,
    ) -> int:
        records = _source_event_records(rows, reason=reason, now_ms=int(now_ms), due_at_ms=due_at_ms)
        if not records:
            return 0

        def _enqueue_events() -> int:
            cursor = self.conn.execute(
                """
                WITH incoming AS (
                  SELECT *
                  FROM unnest(
                    %(projection_versions)s::text[],
                    %(source_event_ids)s::text[],
                    %(target_type_keys)s::text[],
                    %(identity_ids)s::text[],
                    %(payload_hashes)s::text[]
                  ) AS incoming(projection_version, source_event_id, target_type_key, identity_id, payload_hash)
                )
                INSERT INTO token_radar_source_dirty_events(
                  projection_version,
                  source_event_id,
                  target_type_key,
                  identity_id,
                  dirty_reason,
                  payload_hash,
                  due_at_ms,
                  leased_until_ms,
                  lease_owner,
                  attempt_count,
                  last_error,
                  first_dirty_at_ms,
                  updated_at_ms
                )
                SELECT
                  incoming.projection_version,
                  incoming.source_event_id,
                  incoming.target_type_key,
                  incoming.identity_id,
                  %(dirty_reason)s,
                  incoming.payload_hash,
                  %(due_at_ms)s,
                  NULL,
                  NULL,
                  0,
                  NULL,
                  %(now_ms)s,
                  %(now_ms)s
                FROM incoming
                ON CONFLICT(projection_version, source_event_id, target_type_key, identity_id) DO UPDATE SET
                  dirty_reason = CASE
                    WHEN token_radar_source_dirty_events.dirty_reason = EXCLUDED.dirty_reason
                    THEN token_radar_source_dirty_events.dirty_reason
                    ELSE 'mixed'
                  END,
                  payload_hash = EXCLUDED.payload_hash,
                  due_at_ms = LEAST(token_radar_source_dirty_events.due_at_ms, EXCLUDED.due_at_ms),
                  leased_until_ms = NULL,
                  lease_owner = NULL,
                  last_error = NULL,
                  first_dirty_at_ms = token_radar_source_dirty_events.first_dirty_at_ms,
                  updated_at_ms = EXCLUDED.updated_at_ms
                """,
                {
                    "projection_versions": [record["projection_version"] for record in records],
                    "source_event_ids": [record["source_event_id"] for record in records],
                    "target_type_keys": [record["target_type_key"] for record in records],
                    "identity_ids": [record["identity_id"] for record in records],
                    "payload_hashes": [record["payload_hash"] for record in records],
                    "dirty_reason": str(reason),
                    "due_at_ms": int(due_at_ms if due_at_ms is not None else now_ms),
                    "now_ms": int(now_ms),
                },
            )
            return _cursor_rowcount(cursor)

        return _run_repository_write(self.conn, commit, _enqueue_events)

    def claim_due(
        self,
        *,
        limit: int,
        lease_ms: int,
        now_ms: int,
        lease_owner: str,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        def _claim_due() -> list[dict[str, Any]]:
            rows = self.conn.execute(
                """
                WITH due AS (
                  SELECT projection_version, source_event_id, target_type_key, identity_id
                  FROM token_radar_source_dirty_events
                  WHERE due_at_ms <= %(now_ms)s
                    AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
                  ORDER BY due_at_ms ASC, updated_at_ms ASC, source_event_id ASC, target_type_key ASC, identity_id ASC
                  LIMIT %(limit)s
                  FOR UPDATE SKIP LOCKED
                )
                UPDATE token_radar_source_dirty_events queue
                SET leased_until_ms = %(leased_until_ms)s,
                    lease_owner = %(lease_owner)s,
                    attempt_count = queue.attempt_count + 1,
                    last_error = NULL,
                    updated_at_ms = %(now_ms)s
                FROM due
                WHERE queue.projection_version = due.projection_version
                  AND queue.source_event_id = due.source_event_id
                  AND queue.target_type_key = due.target_type_key
                  AND queue.identity_id = due.identity_id
                RETURNING queue.*
                """,
                {
                    "now_ms": int(now_ms),
                    "leased_until_ms": int(now_ms) + max(1, int(lease_ms)),
                    "lease_owner": str(lease_owner),
                    "limit": max(0, int(limit)),
                },
            ).fetchall()
            return [dict(row) for row in rows]

        return _run_repository_write(self.conn, commit, _claim_due)

    def list_recent_resolved_events(self, *, since_ms: int, now_ms: int, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            _RECENT_RESOLVED_EVENT_SQL,
            {
                "since_ms": int(since_ms),
                "now_ms": int(now_ms),
                "limit": max(0, int(limit)),
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
            },
        ).fetchall()
        return [dict(row) for row in rows]

    def count_recent_resolved_event_candidates(self, *, since_ms: int, now_ms: int, limit: int) -> int:
        row = self.conn.execute(
            f"WITH recent AS ({_RECENT_RESOLVED_EVENT_BODY_SQL}) SELECT COUNT(*) AS count FROM recent",
            {
                "since_ms": int(since_ms),
                "now_ms": int(now_ms),
                "limit": max(0, int(limit)),
            },
        ).fetchone()
        return int(row.get("count") or 0) if row else 0

    def mark_done(
        self,
        keys: Iterable[Mapping[str, Any]],
        *,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        records = _key_records(keys)
        if not records:
            return 0

        def _mark_done() -> int:
            cursor = self.conn.execute(
                """
                WITH done AS (
                  SELECT *
                  FROM unnest(
                    %(projection_versions)s::text[],
                    %(source_event_ids)s::text[],
                    %(target_type_keys)s::text[],
                    %(identity_ids)s::text[],
                    %(payload_hashes)s::text[],
                    %(lease_owners)s::text[],
                    %(attempt_counts)s::bigint[]
                  ) AS done(
                    projection_version, source_event_id, target_type_key, identity_id,
                    payload_hash, lease_owner, attempt_count
                  )
                )
                DELETE FROM token_radar_source_dirty_events queue
                USING done
                WHERE queue.projection_version = done.projection_version
                  AND queue.source_event_id = done.source_event_id
                  AND queue.target_type_key = done.target_type_key
                  AND queue.identity_id = done.identity_id
                  AND queue.payload_hash = done.payload_hash
                  AND queue.lease_owner = done.lease_owner
                  AND queue.attempt_count = done.attempt_count
                """,
                _key_params(records),
            )
            return _cursor_rowcount(cursor)

        return _run_repository_write(self.conn, commit, _mark_done)

    def mark_error(
        self,
        keys: Iterable[Mapping[str, Any]],
        *,
        error: str,
        retry_ms: int,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        records = _key_records(keys)
        if not records:
            return 0
        params = _key_params(records)
        params.update(
            {
                "due_at_ms": int(now_ms) + max(1, int(retry_ms)),
                "now_ms": int(now_ms),
                "last_error": str(error)[:2048],
            }
        )

        def _mark_error() -> int:
            cursor = self.conn.execute(
                """
                WITH failed AS (
                  SELECT *
                  FROM unnest(
                    %(projection_versions)s::text[],
                    %(source_event_ids)s::text[],
                    %(target_type_keys)s::text[],
                    %(identity_ids)s::text[],
                    %(payload_hashes)s::text[],
                    %(lease_owners)s::text[],
                    %(attempt_counts)s::bigint[]
                  ) AS failed(
                    projection_version, source_event_id, target_type_key, identity_id,
                    payload_hash, lease_owner, attempt_count
                  )
                )
                UPDATE token_radar_source_dirty_events queue
                SET due_at_ms = %(due_at_ms)s,
                    leased_until_ms = NULL,
                    lease_owner = NULL,
                    last_error = %(last_error)s,
                    updated_at_ms = %(now_ms)s
                FROM failed
                WHERE queue.projection_version = failed.projection_version
                  AND queue.source_event_id = failed.source_event_id
                  AND queue.target_type_key = failed.target_type_key
                  AND queue.identity_id = failed.identity_id
                  AND queue.payload_hash = failed.payload_hash
                  AND queue.lease_owner = failed.lease_owner
                  AND queue.attempt_count = failed.attempt_count
                """,
                params,
            )
            return _cursor_rowcount(cursor)

        return _run_repository_write(self.conn, commit, _mark_error)


def _source_event_records(
    rows: Iterable[Mapping[str, Any]],
    *,
    reason: str,
    now_ms: int,
    due_at_ms: int | None,
) -> list[dict[str, Any]]:
    records: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        source_event_id = _required_enqueue_text(row, "source_event_id")
        target_type_key = _required_enqueue_text(row, "target_type_key")
        identity_id = _required_enqueue_text(row, "identity_id")
        projection_version = str(row.get("projection_version") or TOKEN_RADAR_PROJECTION_VERSION)
        payload_hash = source_dirty_event_payload_hash(
            {
                "projection_version": projection_version,
                "source_event_id": source_event_id,
                "target_type_key": target_type_key,
                "identity_id": identity_id,
                "dirty_reason": str(reason),
                "dirty_at_ms": int(now_ms),
            }
        )
        key = (projection_version, source_event_id, target_type_key, identity_id)
        records[key] = {
            "projection_version": projection_version,
            "source_event_id": source_event_id,
            "target_type_key": target_type_key,
            "identity_id": identity_id,
            "payload_hash": payload_hash,
            "due_at_ms": int(due_at_ms if due_at_ms is not None else now_ms),
        }
    return list(records.values())


def _required_enqueue_text(row: Mapping[str, Any], field_name: str) -> str:
    try:
        value = row[field_name]
    except KeyError as exc:
        raise ValueError("token_radar_source_dirty_event_enqueue_identity_required") from exc
    if value is None:
        raise ValueError("token_radar_source_dirty_event_enqueue_identity_required")
    text = str(value).strip()
    if not text:
        raise ValueError("token_radar_source_dirty_event_enqueue_identity_required")
    return text


def _key_records(keys: Iterable[Mapping[str, Any]]) -> list[dict[str, str | int]]:
    records: list[dict[str, str | int]] = []
    for key in keys:
        projection_version, source_event_id, target_type_key, identity_id = _source_completion_key(key)
        record: dict[str, str | int] = {
            "projection_version": projection_version,
            "source_event_id": source_event_id,
            "target_type_key": target_type_key,
            "identity_id": identity_id,
        }
        payload_hash = _completion_payload_hash(key)
        lease_owner = _completion_lease_owner(key)
        attempt_count = _completion_attempt_count(key)
        record["payload_hash"] = payload_hash
        record["lease_owner"] = lease_owner
        record["attempt_count"] = attempt_count
        if not payload_hash:
            raise ValueError("token radar source dirty completion requires payload_hash from claim_due")
        if not lease_owner:
            raise ValueError("token radar source dirty completion requires lease_owner from claim_due")
        if attempt_count <= 0:
            raise ValueError("token radar source dirty completion requires attempt_count from claim_due")
        records.append(record)
    return records


def _source_completion_key(key: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        _completion_text(key, "projection_version"),
        _completion_text(key, "source_event_id"),
        _completion_text(key, "target_type_key"),
        _completion_text(key, "identity_id"),
    )


def _completion_text(key: Mapping[str, Any], field: str) -> str:
    try:
        value = key[field]
    except KeyError as exc:
        raise ValueError(f"token radar source dirty completion requires {field} from claim_due") from exc
    if value is None:
        raise ValueError(f"token radar source dirty completion requires {field} from claim_due")
    text = str(value).strip()
    if not text:
        raise ValueError(f"token radar source dirty completion requires {field} from claim_due")
    return text


def _completion_attempt_count(key: Mapping[str, Any]) -> int:
    try:
        attempt_count = int(key["attempt_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("token radar source dirty completion requires attempt_count from claim_due") from exc
    if attempt_count <= 0:
        raise ValueError("token radar source dirty completion requires attempt_count from claim_due")
    return attempt_count


def _completion_lease_owner(key: Mapping[str, Any]) -> str:
    try:
        value = key["lease_owner"]
    except KeyError as exc:
        raise ValueError("token radar source dirty completion requires lease_owner from claim_due") from exc
    if value is None:
        raise ValueError("token radar source dirty completion requires lease_owner from claim_due")
    lease_owner = str(value).strip()
    if not lease_owner:
        raise ValueError("token radar source dirty completion requires lease_owner from claim_due")
    return lease_owner


def _completion_payload_hash(key: Mapping[str, Any]) -> str:
    try:
        value = key["payload_hash"]
    except KeyError as exc:
        raise ValueError("token radar source dirty completion requires payload_hash from claim_due") from exc
    if value is None:
        raise ValueError("token radar source dirty completion requires payload_hash from claim_due")
    payload_hash = str(value).strip()
    if not payload_hash:
        raise ValueError("token radar source dirty completion requires payload_hash from claim_due")
    return payload_hash


def _key_params(records: list[dict[str, str | int]]) -> dict[str, Any]:
    return {
        "projection_versions": [str(record["projection_version"]) for record in records],
        "source_event_ids": [str(record["source_event_id"]) for record in records],
        "target_type_keys": [str(record["target_type_key"]) for record in records],
        "identity_ids": [str(record["identity_id"]) for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "lease_owners": [str(record["lease_owner"]) for record in records],
        "attempt_counts": [int(record["attempt_count"]) for record in records],
    }


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("token_radar_source_dirty_event_transaction_required") from exc
    if not callable(transaction):
        raise RuntimeError("token_radar_source_dirty_event_transaction_required")
    return cast(AbstractContextManager[Any], transaction())


def _run_repository_write[T](conn: Any, commit: bool, write: Callable[[], T]) -> T:
    if commit:
        with _transaction(conn):
            return write()
    return write()


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("token_radar_source_dirty_event_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int):
        raise TypeError("token_radar_source_dirty_event_rowcount_invalid")
    if rowcount < 0:
        raise TypeError("token_radar_source_dirty_event_rowcount_invalid")
    return rowcount


_RECENT_RESOLVED_EVENT_BODY_SQL = """
SELECT DISTINCT
  events.event_id AS source_event_id,
  token_intent_resolutions.target_type AS target_type_key,
  token_intent_resolutions.target_id AS identity_id,
  events.received_at_ms AS source_received_at_ms
FROM events
JOIN token_intents ON token_intents.event_id = events.event_id
JOIN token_intent_resolutions ON token_intent_resolutions.intent_id = token_intents.intent_id
WHERE events.received_at_ms >= %(since_ms)s
  AND events.received_at_ms <= %(now_ms)s
  AND token_intent_resolutions.is_current = true
  AND token_intent_resolutions.target_type IN ('Asset', 'CexToken')
  AND token_intent_resolutions.target_id IS NOT NULL
ORDER BY events.received_at_ms DESC,
         events.event_id ASC,
         token_intent_resolutions.target_type ASC,
         token_intent_resolutions.target_id ASC
LIMIT %(limit)s
"""

_RECENT_RESOLVED_EVENT_SQL = f"""
WITH recent AS ({_RECENT_RESOLVED_EVENT_BODY_SQL})
SELECT
  %(projection_version)s AS projection_version,
  source_event_id,
  target_type_key,
  identity_id
FROM recent
"""
