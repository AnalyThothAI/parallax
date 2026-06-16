from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
from typing import Any, cast

from parallax.platform.current_read_model_payload_hash import stable_dirty_target_payload_hash


class TokenProfileCurrentDirtyTargetRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def enqueue_targets(
        self,
        targets: Iterable[Mapping[str, Any] | tuple[str, str]],
        *,
        reason: str,
        now_ms: int,
        due_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, int]:
        records = _target_records(
            targets,
            reason=reason,
            default_due_at_ms=int(due_at_ms if due_at_ms is not None else now_ms),
        )
        if not records:
            return {"targets": 0}

        def _write() -> dict[str, int]:
            self.conn.execute(
                """
                WITH incoming AS (
                  SELECT *
                  FROM unnest(
                    %(target_types)s::text[],
                    %(target_ids)s::text[],
                    %(payload_hashes)s::text[],
                    %(source_watermark_ms_values)s::bigint[],
                    %(priorities)s::integer[],
                    %(due_at_ms_values)s::bigint[]
                  ) AS incoming(
                    target_type,
                    target_id,
                    payload_hash,
                    source_watermark_ms,
                    priority,
                    due_at_ms
                  )
                )
                INSERT INTO token_profile_current_dirty_targets(
                  target_type,
                  target_id,
                  dirty_reason,
                  payload_hash,
                  source_watermark_ms,
                  priority,
                  due_at_ms,
                  leased_until_ms,
                  lease_owner,
                  attempt_count,
                  last_error,
                  first_dirty_at_ms,
                  updated_at_ms
                )
                SELECT
                  incoming.target_type,
                  incoming.target_id,
                  %(dirty_reason)s,
                  incoming.payload_hash,
                  incoming.source_watermark_ms,
                  incoming.priority,
                  incoming.due_at_ms,
                  NULL,
                  NULL,
                  0,
                  NULL,
                  %(now_ms)s,
                  %(now_ms)s
                FROM incoming
                ON CONFLICT(target_type, target_id) DO UPDATE SET
                  dirty_reason = CASE
                    WHEN token_profile_current_dirty_targets.source_watermark_ms = 0
                      OR EXCLUDED.source_watermark_ms >= token_profile_current_dirty_targets.source_watermark_ms
                      THEN EXCLUDED.dirty_reason
                    ELSE token_profile_current_dirty_targets.dirty_reason
                  END,
                  payload_hash = CASE
                    WHEN token_profile_current_dirty_targets.source_watermark_ms = 0
                      OR EXCLUDED.source_watermark_ms >= token_profile_current_dirty_targets.source_watermark_ms
                      THEN EXCLUDED.payload_hash
                    ELSE token_profile_current_dirty_targets.payload_hash
                  END,
                  source_watermark_ms = GREATEST(
                    token_profile_current_dirty_targets.source_watermark_ms,
                    EXCLUDED.source_watermark_ms
                  ),
                  priority = LEAST(token_profile_current_dirty_targets.priority, EXCLUDED.priority),
                  due_at_ms = LEAST(token_profile_current_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
                  leased_until_ms = CASE
                    WHEN token_profile_current_dirty_targets.leased_until_ms IS NOT NULL
                      AND (
                        EXCLUDED.source_watermark_ms > token_profile_current_dirty_targets.source_watermark_ms
                        OR (
                          (
                            token_profile_current_dirty_targets.source_watermark_ms = 0
                            OR EXCLUDED.source_watermark_ms >= token_profile_current_dirty_targets.source_watermark_ms
                          )
                          AND (
                            token_profile_current_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                            OR token_profile_current_dirty_targets.dirty_reason IS DISTINCT FROM EXCLUDED.dirty_reason
                          )
                        )
                      )
                      THEN NULL
                    ELSE token_profile_current_dirty_targets.leased_until_ms
                  END,
                  lease_owner = CASE
                    WHEN token_profile_current_dirty_targets.leased_until_ms IS NOT NULL
                      AND (
                        EXCLUDED.source_watermark_ms > token_profile_current_dirty_targets.source_watermark_ms
                        OR (
                          (
                            token_profile_current_dirty_targets.source_watermark_ms = 0
                            OR EXCLUDED.source_watermark_ms >= token_profile_current_dirty_targets.source_watermark_ms
                          )
                          AND (
                            token_profile_current_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                            OR token_profile_current_dirty_targets.dirty_reason IS DISTINCT FROM EXCLUDED.dirty_reason
                          )
                        )
                      )
                      THEN NULL
                    ELSE token_profile_current_dirty_targets.lease_owner
                  END,
                  last_error = NULL,
                  first_dirty_at_ms = token_profile_current_dirty_targets.first_dirty_at_ms,
                  updated_at_ms = EXCLUDED.updated_at_ms
                """,
                {
                    **_target_params(records),
                    "dirty_reason": str(reason),
                    "now_ms": int(now_ms),
                },
            )
            return {"targets": len(records)}

        return _run_repository_write(self.conn, commit, _write)

    def claim_due(
        self,
        *,
        now_ms: int,
        limit: int,
        lease_owner: str,
        lease_ms: int,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        def _write() -> list[dict[str, Any]]:
            rows = self.conn.execute(
                """
                WITH due AS (
                  SELECT target_type, target_id
                  FROM token_profile_current_dirty_targets
                  WHERE due_at_ms <= %(now_ms)s
                    AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
                  ORDER BY priority ASC,
                           due_at_ms ASC,
                           updated_at_ms ASC,
                           target_type ASC,
                           target_id ASC
                  LIMIT %(limit)s
                  FOR UPDATE SKIP LOCKED
                )
                UPDATE token_profile_current_dirty_targets
                SET leased_until_ms = %(leased_until_ms)s,
                    lease_owner = %(lease_owner)s,
                    attempt_count = token_profile_current_dirty_targets.attempt_count + 1,
                    last_error = NULL,
                    updated_at_ms = %(now_ms)s
                FROM due
                WHERE token_profile_current_dirty_targets.target_type = due.target_type
                  AND token_profile_current_dirty_targets.target_id = due.target_id
                RETURNING token_profile_current_dirty_targets.*
                """,
                {
                    "now_ms": int(now_ms),
                    "leased_until_ms": int(now_ms) + max(1, int(lease_ms)),
                    "lease_owner": str(lease_owner),
                    "limit": max(0, int(limit)),
                },
            ).fetchall()
            return [dict(row) for row in rows]

        return _run_repository_write(self.conn, commit, _write)

    def mark_done(
        self,
        claims: Iterable[Mapping[str, Any]],
        *,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        records = _claim_records(claims)
        if not records:
            return 0

        def _write() -> int:
            cursor = self.conn.execute(
                """
                WITH done AS (
                  SELECT *
                  FROM unnest(
                    %(target_types)s::text[],
                    %(target_ids)s::text[],
                    %(payload_hashes)s::text[],
                    %(lease_owners)s::text[],
                    %(attempt_counts)s::bigint[]
                  ) AS done(
                    target_type,
                    target_id,
                    payload_hash,
                    lease_owner,
                    attempt_count
                  )
                )
                DELETE FROM token_profile_current_dirty_targets queue
                USING done
                WHERE queue.target_type = done.target_type
                  AND queue.target_id = done.target_id
                  AND queue.payload_hash = done.payload_hash
                  AND queue.lease_owner = done.lease_owner
                  AND queue.attempt_count = done.attempt_count
                """,
                _claim_params(records),
            )
            return _cursor_rowcount(cursor)

        return _run_repository_write(self.conn, commit, _write)

    def mark_error(
        self,
        claims: Iterable[Mapping[str, Any]],
        *,
        error: str,
        now_ms: int,
        retry_ms: int,
        commit: bool = True,
    ) -> int:
        records = _claim_records(claims)
        if not records:
            return 0
        params: dict[str, Any] = {
            **_claim_params(records),
            "due_at_ms": int(now_ms) + max(1, int(retry_ms)),
            "now_ms": int(now_ms),
            "last_error": str(error)[:2048],
        }

        def _write() -> int:
            cursor = self.conn.execute(
                """
                WITH failed AS (
                  SELECT *
                  FROM unnest(
                    %(target_types)s::text[],
                    %(target_ids)s::text[],
                    %(payload_hashes)s::text[],
                    %(lease_owners)s::text[],
                    %(attempt_counts)s::bigint[]
                  ) AS failed(
                    target_type,
                    target_id,
                    payload_hash,
                    lease_owner,
                    attempt_count
                  )
                )
                UPDATE token_profile_current_dirty_targets queue
                SET due_at_ms = %(due_at_ms)s,
                    leased_until_ms = NULL,
                    lease_owner = NULL,
                    last_error = %(last_error)s,
                    updated_at_ms = %(now_ms)s
                FROM failed
                WHERE queue.target_type = failed.target_type
                  AND queue.target_id = failed.target_id
                  AND queue.payload_hash = failed.payload_hash
                  AND queue.lease_owner = failed.lease_owner
                  AND queue.attempt_count = failed.attempt_count
                """,
                params,
            )
            return _cursor_rowcount(cursor)

        return _run_repository_write(self.conn, commit, _write)

    def queue_depth(self, *, now_ms: int) -> int:
        row = self.conn.execute(
            """
            SELECT count(*) AS count
            FROM token_profile_current_dirty_targets
            WHERE due_at_ms <= %(now_ms)s
              AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
            """,
            {"now_ms": int(now_ms)},
        ).fetchone()
        return int(row["count"] if row else 0)


def _target_records(
    targets: Iterable[Mapping[str, Any] | tuple[str, str]],
    *,
    reason: str,
    default_due_at_ms: int,
) -> list[dict[str, Any]]:
    records: dict[tuple[str, str], dict[str, Any]] = {}
    for target in targets:
        target_type, target_id = _target_key(target)
        if not target_type or not target_id:
            continue
        source_watermark_ms = _source_watermark_ms(target)
        priority = _priority_value(target)
        due_at_ms = (
            int(target.get("due_at_ms") or default_due_at_ms) if isinstance(target, Mapping) else default_due_at_ms
        )
        record = {
            "target_type": target_type,
            "target_id": target_id,
            "source_watermark_ms": source_watermark_ms,
            "priority": priority,
            "due_at_ms": due_at_ms,
        }
        payload_source = dict(target) if isinstance(target, Mapping) else {}
        record["payload_hash"] = str(
            payload_source.get("payload_hash") or _payload_hash({**record, **payload_source, "dirty_reason": reason})
        )
        key = (target_type, target_id)
        existing = records.get(key)
        if existing is None:
            records[key] = record
            continue
        if source_watermark_ms >= int(existing["source_watermark_ms"]):
            record["priority"] = min(int(existing["priority"]), priority)
            record["due_at_ms"] = min(int(existing["due_at_ms"]), due_at_ms)
            records[key] = record
        else:
            existing["priority"] = min(int(existing["priority"]), priority)
            existing["due_at_ms"] = min(int(existing["due_at_ms"]), due_at_ms)
    return list(records.values())


def _target_key(target: Mapping[str, Any] | tuple[str, str]) -> tuple[str, str]:
    if isinstance(target, tuple):
        target_type, target_id = target
        return str(target_type).strip(), str(target_id).strip()
    return str(target.get("target_type") or "").strip(), str(target.get("target_id") or "").strip()


def _target_params(records: list[dict[str, Any]]) -> dict[str, list[Any]]:
    return {
        "target_types": [str(record["target_type"]) for record in records],
        "target_ids": [str(record["target_id"]) for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "source_watermark_ms_values": [int(record["source_watermark_ms"]) for record in records],
        "priorities": [int(record["priority"]) for record in records],
        "due_at_ms_values": [int(record["due_at_ms"]) for record in records],
    }


def _claim_records(claims: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for claim in claims:
        target_type, target_id = _target_key(claim)
        if not target_type or not target_id:
            raise ValueError("token profile current dirty target completion requires full target key from claim_due")
        payload_hash = _completion_payload_hash(claim)
        if not payload_hash:
            raise ValueError("token profile current dirty target completion requires payload_hash from claim_due")
        lease_owner = _completion_lease_owner(claim)
        attempt_count = _completion_attempt_count(claim)
        if not lease_owner:
            raise ValueError("token profile current dirty target completion requires lease_owner from claim_due")
        if attempt_count <= 0:
            raise ValueError("token profile current dirty target completion requires attempt_count from claim_due")
        records.append(
            {
                "target_type": target_type,
                "target_id": target_id,
                "payload_hash": payload_hash,
                "lease_owner": lease_owner,
                "attempt_count": attempt_count,
            }
        )
    return records


def _completion_attempt_count(claim: Mapping[str, Any]) -> int:
    try:
        attempt_count = int(claim["attempt_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("token profile current dirty target completion requires attempt_count from claim_due") from exc
    if attempt_count <= 0:
        raise ValueError("token profile current dirty target completion requires attempt_count from claim_due")
    return attempt_count


def _completion_lease_owner(claim: Mapping[str, Any]) -> str:
    try:
        value = claim["lease_owner"]
    except KeyError as exc:
        raise ValueError("token profile current dirty target completion requires lease_owner from claim_due") from exc
    if value is None:
        raise ValueError("token profile current dirty target completion requires lease_owner from claim_due")
    lease_owner = str(value).strip()
    if not lease_owner:
        raise ValueError("token profile current dirty target completion requires lease_owner from claim_due")
    return lease_owner


def _completion_payload_hash(claim: Mapping[str, Any]) -> str:
    try:
        value = claim["payload_hash"]
    except KeyError as exc:
        raise ValueError("token profile current dirty target completion requires payload_hash from claim_due") from exc
    if value is None:
        raise ValueError("token profile current dirty target completion requires payload_hash from claim_due")
    payload_hash = str(value).strip()
    if not payload_hash:
        raise ValueError("token profile current dirty target completion requires payload_hash from claim_due")
    return payload_hash


def _claim_params(records: list[dict[str, Any]]) -> dict[str, list[Any]]:
    return {
        "target_types": [str(record["target_type"]) for record in records],
        "target_ids": [str(record["target_id"]) for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "lease_owners": [str(record["lease_owner"]) for record in records],
        "attempt_counts": [int(record["attempt_count"]) for record in records],
    }


def _source_watermark_ms(target: Mapping[str, Any] | tuple[str, str]) -> int:
    if not isinstance(target, Mapping):
        raise ValueError("token_profile_current_dirty_target_source_watermark_required")
    try:
        value = target["source_watermark_ms"]
    except KeyError as exc:
        raise ValueError("token_profile_current_dirty_target_source_watermark_required") from exc
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("token_profile_current_dirty_target_source_watermark_required")
    if value <= 0:
        raise ValueError("token_profile_current_dirty_target_source_watermark_required")
    return int(value)


def _priority_value(target: Mapping[str, Any] | tuple[str, str]) -> int:
    if not isinstance(target, Mapping):
        return 100
    raw_priority = target.get("priority")
    if raw_priority in (None, ""):
        return 100
    return int(str(raw_priority))


def _payload_hash(payload: Mapping[str, Any]) -> str:
    return stable_dirty_target_payload_hash(payload)


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("token_profile_current_dirty_target_transaction_required") from exc
    if not callable(transaction):
        raise RuntimeError("token_profile_current_dirty_target_transaction_required")
    return cast(AbstractContextManager[Any], transaction())


def _run_repository_write[T](conn: Any, commit: bool, write: Callable[[], T]) -> T:
    if commit:
        with _transaction(conn):
            return write()
    return write()


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("token_profile_current_dirty_target_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int):
        raise TypeError("token_profile_current_dirty_target_rowcount_invalid")
    if rowcount < 0:
        raise TypeError("token_profile_current_dirty_target_rowcount_invalid")
    return int(rowcount)
