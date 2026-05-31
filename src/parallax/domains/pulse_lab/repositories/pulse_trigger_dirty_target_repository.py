from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from parallax.platform.db.json_safety import postgres_safe_json


class PulseTriggerDirtyTargetRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def enqueue_targets(
        self,
        targets: Iterable[Mapping[str, Any]],
        *,
        reason: str,
        now_ms: int,
        due_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, int]:
        records = _target_records(
            targets,
            reason=reason,
            now_ms=int(now_ms),
            default_due_at_ms=int(due_at_ms if due_at_ms is not None else now_ms),
        )
        if not records:
            return {"targets": 0}
        self.conn.execute(
            """
            WITH incoming AS (
              SELECT *
              FROM unnest(
                %(target_types)s::text[],
                %(target_ids)s::text[],
                %(windows)s::text[],
                %(scopes)s::text[],
                %(payload_hashes)s::text[],
                %(source_watermark_ms_values)s::bigint[],
                %(priorities)s::integer[],
                %(due_at_ms_values)s::bigint[]
              ) AS incoming(
                target_type,
                target_id,
                "window",
                scope,
                payload_hash,
                source_watermark_ms,
                priority,
                due_at_ms
              )
            )
            INSERT INTO pulse_trigger_dirty_targets(
              target_type,
              target_id,
              "window",
              scope,
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
              incoming."window",
              incoming.scope,
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
            ON CONFLICT(target_type, target_id, "window", scope) DO UPDATE SET
              dirty_reason = CASE
                WHEN pulse_trigger_dirty_targets.source_watermark_ms = 0
                  OR EXCLUDED.source_watermark_ms >= pulse_trigger_dirty_targets.source_watermark_ms
                  THEN EXCLUDED.dirty_reason
                ELSE pulse_trigger_dirty_targets.dirty_reason
              END,
              payload_hash = CASE
                WHEN pulse_trigger_dirty_targets.source_watermark_ms = 0
                  OR EXCLUDED.source_watermark_ms >= pulse_trigger_dirty_targets.source_watermark_ms
                  THEN EXCLUDED.payload_hash
                ELSE pulse_trigger_dirty_targets.payload_hash
              END,
              source_watermark_ms = GREATEST(
                pulse_trigger_dirty_targets.source_watermark_ms,
                EXCLUDED.source_watermark_ms
              ),
              priority = LEAST(pulse_trigger_dirty_targets.priority, EXCLUDED.priority),
              due_at_ms = LEAST(pulse_trigger_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
              leased_until_ms = CASE
                WHEN pulse_trigger_dirty_targets.leased_until_ms IS NOT NULL
                  AND (
                    EXCLUDED.source_watermark_ms > pulse_trigger_dirty_targets.source_watermark_ms
                    OR (
                      (
                        pulse_trigger_dirty_targets.source_watermark_ms = 0
                        OR EXCLUDED.source_watermark_ms >= pulse_trigger_dirty_targets.source_watermark_ms
                      )
                      AND (
                        pulse_trigger_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                        OR pulse_trigger_dirty_targets.dirty_reason IS DISTINCT FROM EXCLUDED.dirty_reason
                      )
                    )
                  )
                  THEN NULL
                ELSE pulse_trigger_dirty_targets.leased_until_ms
              END,
              lease_owner = CASE
                WHEN pulse_trigger_dirty_targets.leased_until_ms IS NOT NULL
                  AND (
                    EXCLUDED.source_watermark_ms > pulse_trigger_dirty_targets.source_watermark_ms
                    OR (
                      (
                        pulse_trigger_dirty_targets.source_watermark_ms = 0
                        OR EXCLUDED.source_watermark_ms >= pulse_trigger_dirty_targets.source_watermark_ms
                      )
                      AND (
                        pulse_trigger_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                        OR pulse_trigger_dirty_targets.dirty_reason IS DISTINCT FROM EXCLUDED.dirty_reason
                      )
                    )
                  )
                  THEN NULL
                ELSE pulse_trigger_dirty_targets.lease_owner
              END,
              last_error = NULL,
              first_dirty_at_ms = pulse_trigger_dirty_targets.first_dirty_at_ms,
              updated_at_ms = EXCLUDED.updated_at_ms
            """,
            {
                **_target_params(records),
                "dirty_reason": str(reason),
                "now_ms": int(now_ms),
            },
        )
        if commit:
            self.conn.commit()
        return {"targets": len(records)}

    def claim_due(
        self,
        *,
        now_ms: int,
        limit: int,
        lease_owner: str,
        lease_ms: int,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH due AS (
              SELECT target_type, target_id, "window", scope
              FROM pulse_trigger_dirty_targets
              WHERE due_at_ms <= %(now_ms)s
                AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
              ORDER BY priority ASC,
                       due_at_ms ASC,
                       updated_at_ms ASC,
                       target_type ASC,
                       target_id ASC,
                       "window" ASC,
                       scope ASC
              LIMIT %(limit)s
              FOR UPDATE SKIP LOCKED
            )
            UPDATE pulse_trigger_dirty_targets
            SET leased_until_ms = %(leased_until_ms)s,
                lease_owner = %(lease_owner)s,
                attempt_count = pulse_trigger_dirty_targets.attempt_count + 1,
                last_error = NULL,
                updated_at_ms = %(now_ms)s
            FROM due
            WHERE pulse_trigger_dirty_targets.target_type = due.target_type
              AND pulse_trigger_dirty_targets.target_id = due.target_id
              AND pulse_trigger_dirty_targets."window" = due."window"
              AND pulse_trigger_dirty_targets.scope = due.scope
            RETURNING pulse_trigger_dirty_targets.*
            """,
            {
                "now_ms": int(now_ms),
                "leased_until_ms": int(now_ms) + max(1, int(lease_ms)),
                "lease_owner": str(lease_owner),
                "limit": max(0, int(limit)),
            },
        ).fetchall()
        if commit:
            self.conn.commit()
        return [dict(row) for row in rows]

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
        cursor = self.conn.execute(
            """
            WITH done AS (
              SELECT *
              FROM unnest(
                %(target_types)s::text[],
                %(target_ids)s::text[],
                %(windows)s::text[],
                %(scopes)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS done(
                target_type,
                target_id,
                "window",
                scope,
                payload_hash,
                lease_owner,
                attempt_count
              )
            )
            DELETE FROM pulse_trigger_dirty_targets queue
            USING done
            WHERE queue.target_type = done.target_type
              AND queue.target_id = done.target_id
              AND queue."window" = done."window"
              AND queue.scope = done.scope
              AND queue.payload_hash = done.payload_hash
              AND queue.lease_owner = done.lease_owner
              AND queue.attempt_count = done.attempt_count
            """,
            _claim_params(records),
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

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
        cursor = self.conn.execute(
            """
            WITH failed AS (
              SELECT *
              FROM unnest(
                %(target_types)s::text[],
                %(target_ids)s::text[],
                %(windows)s::text[],
                %(scopes)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS failed(
                target_type,
                target_id,
                "window",
                scope,
                payload_hash,
                lease_owner,
                attempt_count
              )
            )
            UPDATE pulse_trigger_dirty_targets queue
            SET due_at_ms = %(due_at_ms)s,
                leased_until_ms = NULL,
                lease_owner = NULL,
                last_error = %(last_error)s,
                updated_at_ms = %(now_ms)s
            FROM failed
            WHERE queue.target_type = failed.target_type
              AND queue.target_id = failed.target_id
              AND queue."window" = failed."window"
              AND queue.scope = failed.scope
              AND queue.payload_hash = failed.payload_hash
              AND queue.lease_owner = failed.lease_owner
              AND queue.attempt_count = failed.attempt_count
            """,
            params,
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def reschedule(
        self,
        claims: Iterable[Mapping[str, Any]],
        *,
        due_at_ms: int,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        records = _claim_records(claims)
        if not records:
            return 0
        params: dict[str, Any] = {
            **_claim_params(records),
            "due_at_ms": int(due_at_ms),
            "now_ms": int(now_ms),
        }
        cursor = self.conn.execute(
            """
            WITH rescheduled AS (
              SELECT *
              FROM unnest(
                %(target_types)s::text[],
                %(target_ids)s::text[],
                %(windows)s::text[],
                %(scopes)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS rescheduled(
                target_type,
                target_id,
                "window",
                scope,
                payload_hash,
                lease_owner,
                attempt_count
              )
            )
            UPDATE pulse_trigger_dirty_targets queue
            SET due_at_ms = %(due_at_ms)s,
                leased_until_ms = NULL,
                lease_owner = NULL,
                updated_at_ms = %(now_ms)s
            FROM rescheduled
            WHERE queue.target_type = rescheduled.target_type
              AND queue.target_id = rescheduled.target_id
              AND queue."window" = rescheduled."window"
              AND queue.scope = rescheduled.scope
              AND queue.payload_hash = rescheduled.payload_hash
              AND queue.lease_owner = rescheduled.lease_owner
              AND queue.attempt_count = rescheduled.attempt_count
            """,
            params,
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def queue_depth(self, *, now_ms: int) -> int:
        row = self.conn.execute(
            """
            SELECT count(*) AS count
            FROM pulse_trigger_dirty_targets
            WHERE due_at_ms <= %(now_ms)s
              AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
            """,
            {"now_ms": int(now_ms)},
        ).fetchone()
        return int(row["count"] if row else 0)


def _target_records(
    targets: Iterable[Mapping[str, Any]],
    *,
    reason: str,
    now_ms: int,
    default_due_at_ms: int,
) -> list[dict[str, Any]]:
    records: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for target in targets:
        target_type = str(target.get("target_type") or "").strip()
        target_id = str(target.get("target_id") or "").strip()
        window = str(target.get("window") or "").strip()
        scope = str(target.get("scope") or "").strip()
        if not target_type or not target_id or not window or not scope:
            continue
        source_watermark_ms = int(target.get("source_watermark_ms") or 0)
        priority = _priority_value(target)
        due_at_ms = int(target.get("due_at_ms") or default_due_at_ms)
        record = {
            "target_type": target_type,
            "target_id": target_id,
            "window": window,
            "scope": scope,
            "source_watermark_ms": source_watermark_ms,
            "priority": priority,
            "due_at_ms": due_at_ms,
        }
        record["payload_hash"] = str(target.get("payload_hash") or _payload_hash({**record, "dirty_reason": reason}))
        key = (target_type, target_id, window, scope)
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


def _target_params(records: list[dict[str, Any]]) -> dict[str, list[Any]]:
    return {
        "target_types": [str(record["target_type"]) for record in records],
        "target_ids": [str(record["target_id"]) for record in records],
        "windows": [str(record["window"]) for record in records],
        "scopes": [str(record["scope"]) for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "source_watermark_ms_values": [int(record["source_watermark_ms"]) for record in records],
        "priorities": [int(record["priority"]) for record in records],
        "due_at_ms_values": [int(record["due_at_ms"]) for record in records],
    }


def _claim_records(claims: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for claim in claims:
        target_type = str(claim.get("target_type") or "").strip()
        target_id = str(claim.get("target_id") or "").strip()
        window = str(claim.get("window") or "").strip()
        scope = str(claim.get("scope") or "").strip()
        payload_hash = str(claim.get("payload_hash") or "")
        lease_owner = str(claim.get("lease_owner") or "")
        attempt_count = int(claim.get("attempt_count") or 0)
        if not target_type or not target_id or not window or not scope:
            raise ValueError("pulse trigger dirty target completion requires full target key from claim_due")
        if not payload_hash:
            raise ValueError("pulse trigger dirty target completion requires payload_hash from claim_due")
        if not lease_owner:
            raise ValueError("pulse trigger dirty target completion requires lease_owner from claim_due")
        if attempt_count <= 0:
            raise ValueError("pulse trigger dirty target completion requires attempt_count from claim_due")
        records.append(
            {
                "target_type": target_type,
                "target_id": target_id,
                "window": window,
                "scope": scope,
                "payload_hash": payload_hash,
                "lease_owner": lease_owner,
                "attempt_count": attempt_count,
            }
        )
    return records


def _claim_params(records: list[dict[str, Any]]) -> dict[str, list[Any]]:
    return {
        "target_types": [str(record["target_type"]) for record in records],
        "target_ids": [str(record["target_id"]) for record in records],
        "windows": [str(record["window"]) for record in records],
        "scopes": [str(record["scope"]) for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "lease_owners": [str(record["lease_owner"]) for record in records],
        "attempt_counts": [int(record["attempt_count"]) for record in records],
    }


def _priority_value(row: Mapping[str, Any]) -> int:
    raw_priority = row.get("priority")
    if raw_priority in (None, ""):
        return 100
    return int(str(raw_priority))


def _payload_hash(payload: Mapping[str, Any]) -> str:
    safe_payload = postgres_safe_json(dict(payload))
    encoded = json.dumps(safe_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
