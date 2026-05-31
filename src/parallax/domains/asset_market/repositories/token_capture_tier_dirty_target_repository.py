from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


class TokenCaptureTierDirtyTargetRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def enqueue_global(self, *, reason: str, now_ms: int, commit: bool = True) -> dict[str, int]:
        self.conn.execute(
            """
            INSERT INTO token_capture_tier_dirty_targets(
              work_name,
              partition_key,
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
            VALUES (
              'active_live_market_rank_set',
              'global',
              %(reason)s,
              %(payload_hash)s,
              %(now_ms)s,
              50,
              %(now_ms)s,
              NULL,
              NULL,
              0,
              NULL,
              %(now_ms)s,
              %(now_ms)s
            )
            ON CONFLICT(work_name, partition_key) DO UPDATE SET
              dirty_reason = EXCLUDED.dirty_reason,
              payload_hash = EXCLUDED.payload_hash,
              source_watermark_ms = GREATEST(
                token_capture_tier_dirty_targets.source_watermark_ms,
                EXCLUDED.source_watermark_ms
              ),
              priority = LEAST(token_capture_tier_dirty_targets.priority, EXCLUDED.priority),
              due_at_ms = LEAST(token_capture_tier_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
              leased_until_ms = NULL,
              lease_owner = NULL,
              last_error = NULL,
              first_dirty_at_ms = token_capture_tier_dirty_targets.first_dirty_at_ms,
              updated_at_ms = EXCLUDED.updated_at_ms
            """,
            {
                "reason": str(reason),
                "payload_hash": f"capture-tier:{reason}:{int(now_ms)}",
                "now_ms": int(now_ms),
            },
        )
        if commit:
            self.conn.commit()
        return {"targets": 1}

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
              SELECT work_name, partition_key
              FROM token_capture_tier_dirty_targets
              WHERE due_at_ms <= %(now_ms)s
                AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
              ORDER BY priority ASC, due_at_ms ASC, updated_at_ms ASC, work_name ASC, partition_key ASC
              LIMIT %(limit)s
              FOR UPDATE SKIP LOCKED
            )
            UPDATE token_capture_tier_dirty_targets
            SET leased_until_ms = %(leased_until_ms)s,
                lease_owner = %(lease_owner)s,
                attempt_count = token_capture_tier_dirty_targets.attempt_count + 1,
                last_error = NULL,
                updated_at_ms = %(now_ms)s
            FROM due
            WHERE token_capture_tier_dirty_targets.work_name = due.work_name
              AND token_capture_tier_dirty_targets.partition_key = due.partition_key
            RETURNING token_capture_tier_dirty_targets.*
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

    def mark_done(self, claims: Iterable[Mapping[str, Any]], *, now_ms: int, commit: bool = True) -> int:
        records = list(claims)
        if not records:
            return 0
        cursor = self.conn.execute(
            """
            WITH done AS (
              SELECT *
              FROM unnest(
                %(work_names)s::text[],
                %(partition_keys)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS done(work_name, partition_key, payload_hash, lease_owner, attempt_count)
            )
            DELETE FROM token_capture_tier_dirty_targets queue
            USING done
            WHERE queue.work_name = done.work_name
              AND queue.partition_key = done.partition_key
              AND queue.payload_hash = done.payload_hash
              AND queue.lease_owner = done.lease_owner
              AND queue.attempt_count = done.attempt_count
            """,
            _claim_params(records),
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def queue_depth(self, *, now_ms: int) -> int:
        row = self.conn.execute(
            """
            SELECT count(*) AS count
            FROM token_capture_tier_dirty_targets
            WHERE due_at_ms <= %(now_ms)s
              AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
            """,
            {"now_ms": int(now_ms)},
        ).fetchone()
        return int(row["count"] if row else 0)


def _claim_params(records: list[Mapping[str, Any]]) -> dict[str, list[Any]]:
    return {
        "work_names": [str(record["work_name"]) for record in records],
        "partition_keys": [str(record["partition_key"]) for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "lease_owners": [str(record["lease_owner"]) for record in records],
        "attempt_counts": [int(record["attempt_count"]) for record in records],
    }
