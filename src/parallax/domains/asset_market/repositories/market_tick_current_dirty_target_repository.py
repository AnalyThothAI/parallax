from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from parallax.platform.current_read_model_payload_hash import stable_dirty_target_payload_hash
from parallax.platform.db.queue_terminal import terminalize_source_row
from parallax.platform.db.write_contract import expect_mutation_count, mutation_count
from parallax.platform.validation import require_nonnegative_int, require_positive_int


class MarketTickCurrentDirtyTargetRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def enqueue_targets(
        self,
        targets: Iterable[Mapping[str, Any] | tuple[str, str]],
        *,
        reason: str,
        now_ms: int,
    ) -> int:
        records = _target_records(targets, reason=reason)
        if not records:
            return 0

        cursor = self.conn.execute(
            """
            WITH incoming(target_type, target_id, payload_hash) AS (
              SELECT *
              FROM unnest(
                %(target_types)s::text[],
                %(target_ids)s::text[],
                %(payload_hashes)s::text[]
              )
            )
            INSERT INTO market_tick_current_dirty_targets(
              target_type,
              target_id,
              dirty_reason,
              payload_hash,
              due_at_ms,
              source_watermark_ms,
              priority,
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
              %(now_ms)s,
              %(now_ms)s,
              0,
              NULL,
              NULL,
              0,
              NULL,
              %(now_ms)s,
              %(now_ms)s
            FROM incoming
            ON CONFLICT(target_type, target_id) DO UPDATE SET
              dirty_reason = EXCLUDED.dirty_reason,
              payload_hash = EXCLUDED.payload_hash,
              due_at_ms = LEAST(market_tick_current_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
              source_watermark_ms = GREATEST(
                market_tick_current_dirty_targets.source_watermark_ms,
                EXCLUDED.source_watermark_ms
              ),
              priority = GREATEST(market_tick_current_dirty_targets.priority, EXCLUDED.priority),
              leased_until_ms = NULL,
              lease_owner = NULL,
              attempt_count = CASE
                WHEN market_tick_current_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                THEN 0
                ELSE market_tick_current_dirty_targets.attempt_count
              END,
              last_error = NULL,
              first_dirty_at_ms = market_tick_current_dirty_targets.first_dirty_at_ms,
              updated_at_ms = EXCLUDED.updated_at_ms
            WHERE market_tick_current_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
               OR market_tick_current_dirty_targets.dirty_reason IS DISTINCT FROM EXCLUDED.dirty_reason
               OR market_tick_current_dirty_targets.due_at_ms > EXCLUDED.due_at_ms
               OR market_tick_current_dirty_targets.source_watermark_ms < EXCLUDED.source_watermark_ms
               OR market_tick_current_dirty_targets.priority < EXCLUDED.priority
               OR market_tick_current_dirty_targets.leased_until_ms IS NOT NULL
               OR market_tick_current_dirty_targets.last_error IS NOT NULL
            """,
            {
                "target_types": [record["target_type"] for record in records],
                "target_ids": [record["target_id"] for record in records],
                "payload_hashes": [record["payload_hash"] for record in records],
                "dirty_reason": str(reason),
                "now_ms": int(now_ms),
            },
        )
        return mutation_count(cursor, error_code="market_tick_current_dirty_target_rowcount_invalid")

    def claim_due(
        self,
        *,
        limit: int,
        now_ms: int,
        lease_ms: int,
        lease_owner: str,
    ) -> list[dict[str, Any]]:
        parsed_limit = require_nonnegative_int(
            limit,
            error_code="market_tick_current_dirty_target_claim_limit_required",
        )
        parsed_lease_ms = require_positive_int(
            lease_ms,
            error_code="market_tick_current_dirty_target_claim_lease_ms_required",
        )

        cursor = self.conn.execute(
            """
            WITH due AS (
              SELECT target_type, target_id
              FROM market_tick_current_dirty_targets
              WHERE due_at_ms <= %(now_ms)s
                AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
              ORDER BY priority DESC, due_at_ms ASC, updated_at_ms ASC, target_type ASC, target_id ASC
              LIMIT %(limit)s
              FOR UPDATE SKIP LOCKED
            )
            UPDATE market_tick_current_dirty_targets
            SET leased_until_ms = %(leased_until_ms)s,
                lease_owner = %(lease_owner)s,
                attempt_count = market_tick_current_dirty_targets.attempt_count + 1,
                last_error = NULL,
                updated_at_ms = %(now_ms)s
            FROM due
            WHERE market_tick_current_dirty_targets.target_type = due.target_type
              AND market_tick_current_dirty_targets.target_id = due.target_id
            RETURNING market_tick_current_dirty_targets.*
            """,
            {
                "now_ms": int(now_ms),
                "leased_until_ms": int(now_ms) + parsed_lease_ms,
                "lease_owner": str(lease_owner),
                "limit": parsed_limit,
            },
        )
        rows = cursor.fetchall()
        expect_mutation_count(
            cursor,
            expected=len(rows),
            error_code="market_tick_current_dirty_target_rowcount_invalid",
        )
        return [dict(row) for row in rows]

    def mark_done(
        self,
        claims: Iterable[Mapping[str, Any]],
        *,
        now_ms: int,
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
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS done(target_type, target_id, payload_hash, lease_owner, attempt_count)
            )
            DELETE FROM market_tick_current_dirty_targets queue
            USING done
            WHERE queue.target_type = done.target_type
              AND queue.target_id = done.target_id
              AND queue.payload_hash = done.payload_hash
              AND queue.lease_owner = done.lease_owner
              AND queue.attempt_count = done.attempt_count
            """,
            _claim_params(records),
        )
        return mutation_count(cursor, error_code="market_tick_current_dirty_target_rowcount_invalid")

    def mark_error(
        self,
        claims: Iterable[Mapping[str, Any]],
        *,
        error: str,
        retry_ms: int,
        max_attempts: int,
        worker_name: str,
        now_ms: int,
    ) -> int:
        records = _claim_records(claims)
        if not records:
            return 0
        parsed_max_attempts = _required_max_attempts(max_attempts)
        parsed_retry_ms = require_positive_int(
            retry_ms,
            error_code="market_tick_current_dirty_target_retry_ms_required",
        )
        parsed_worker_name = _required_text(worker_name, "worker_name")
        retry_records = [record for record in records if int(record["attempt_count"]) < parsed_max_attempts]
        exhausted_records = [record for record in records if int(record["attempt_count"]) >= parsed_max_attempts]
        params = {
            **_claim_params(retry_records),
            "due_at_ms": int(now_ms) + parsed_retry_ms,
            "now_ms": int(now_ms),
            "last_error": str(error)[:2048],
        }

        changed = 0
        if retry_records:
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
                  ) AS failed(target_type, target_id, payload_hash, lease_owner, attempt_count)
                )
                UPDATE market_tick_current_dirty_targets queue
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
            changed += mutation_count(cursor, error_code="market_tick_current_dirty_target_rowcount_invalid")
        if exhausted_records:
            deleted_rows, deleted_count = self._delete_claims_returning(exhausted_records)
            changed += deleted_count
            for row in deleted_rows:
                terminalize_source_row(
                    self.conn,
                    worker_name=parsed_worker_name,
                    source_table="market_tick_current_dirty_targets",
                    target_key=_terminal_target_key(row),
                    source_row=row,
                    final_status="terminal",
                    final_reason=_retry_budget_exhausted_reason(error),
                    now_ms=int(now_ms),
                    attempt_count=int(row["attempt_count"]),
                    payload_hash=_completion_payload_hash(row),
                    first_seen_at_ms=_optional_int(row.get("first_dirty_at_ms")),
                    last_attempted_at_ms=int(now_ms),
                )
        return changed

    def _delete_claims_returning(self, records: list[dict[str, str | int]]) -> tuple[list[dict[str, Any]], int]:
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
              ) AS done(target_type, target_id, payload_hash, lease_owner, attempt_count)
            )
            DELETE FROM market_tick_current_dirty_targets queue
            USING done
            WHERE queue.target_type = done.target_type
              AND queue.target_id = done.target_id
              AND queue.payload_hash = done.payload_hash
              AND queue.lease_owner = done.lease_owner
              AND queue.attempt_count = done.attempt_count
            RETURNING queue.*
            """,
            _claim_params(records),
        )
        rows = cursor.fetchall()
        deleted_count = expect_mutation_count(
            cursor,
            expected=len(rows),
            error_code="market_tick_current_dirty_target_rowcount_invalid",
        )
        return [dict(row) for row in rows], deleted_count

    def queue_depth(self, *, now_ms: int) -> int:
        row = self.conn.execute(
            """
            SELECT count(*) AS count
            FROM market_tick_current_dirty_targets
            WHERE due_at_ms <= %(now_ms)s
              AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
            """,
            {"now_ms": int(now_ms)},
        ).fetchone()
        if row is None:
            return 0
        return int(row["count"])

    def get(self, target_type: str, target_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM market_tick_current_dirty_targets
            WHERE target_type = %(target_type)s
              AND target_id = %(target_id)s
            """,
            {"target_type": str(target_type), "target_id": str(target_id)},
        ).fetchone()
        return dict(row) if row is not None else None


def _target_records(
    targets: Iterable[Mapping[str, Any] | tuple[str, str]],
    *,
    reason: str,
) -> list[dict[str, str]]:
    records: dict[tuple[str, str], dict[str, str]] = {}
    for target in targets:
        target_type, target_id = _target_key(target)
        if not target_type or not target_id:
            continue
        records[(target_type, target_id)] = {
            "target_type": target_type,
            "target_id": target_id,
            "payload_hash": _payload_hash(
                {
                    "target_type": target_type,
                    "target_id": target_id,
                    "dirty_reason": str(reason),
                }
            ),
        }
    return list(records.values())


def _target_key(target: Mapping[str, Any] | tuple[str, str]) -> tuple[str, str]:
    if isinstance(target, tuple):
        target_type, target_id = target
        return str(target_type).strip(), str(target_id).strip()
    return str(target.get("target_type") or "").strip(), str(target.get("target_id") or "").strip()


def _payload_hash(payload: Mapping[str, Any]) -> str:
    return stable_dirty_target_payload_hash(payload)


def _claim_records(claims: Iterable[Mapping[str, Any]]) -> list[dict[str, str | int]]:
    records: list[dict[str, str | int]] = []
    for claim in claims:
        target_type, target_id = _target_key(claim)
        if not target_type or not target_id:
            continue
        payload_hash = _completion_payload_hash(claim)
        lease_owner = _completion_lease_owner(claim)
        attempt_count = _completion_attempt_count(claim)
        if not payload_hash:
            raise ValueError("market tick current dirty target completion requires payload_hash from claim_due")
        if not lease_owner:
            raise ValueError("market tick current dirty target completion requires lease_owner from claim_due")
        if attempt_count <= 0:
            raise ValueError("market tick current dirty target completion requires attempt_count from claim_due")
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
        value = claim["attempt_count"]
    except KeyError as exc:
        raise ValueError("market tick current dirty target completion requires attempt_count from claim_due") from exc
    return require_positive_int(
        value,
        error_code="market tick current dirty target completion requires attempt_count from claim_due",
    )


def _completion_lease_owner(claim: Mapping[str, Any]) -> str:
    try:
        value = claim["lease_owner"]
    except KeyError as exc:
        raise ValueError("market tick current dirty target completion requires lease_owner from claim_due") from exc
    if value is None:
        raise ValueError("market tick current dirty target completion requires lease_owner from claim_due")
    lease_owner = str(value).strip()
    if not lease_owner:
        raise ValueError("market tick current dirty target completion requires lease_owner from claim_due")
    return lease_owner


def _completion_payload_hash(claim: Mapping[str, Any]) -> str:
    try:
        value = claim["payload_hash"]
    except KeyError as exc:
        raise ValueError("market tick current dirty target completion requires payload_hash from claim_due") from exc
    if value is None:
        raise ValueError("market tick current dirty target completion requires payload_hash from claim_due")
    payload_hash = str(value).strip()
    if not payload_hash:
        raise ValueError("market tick current dirty target completion requires payload_hash from claim_due")
    return payload_hash


def _claim_params(records: list[dict[str, str | int]]) -> dict[str, Any]:
    return {
        "target_types": [str(record["target_type"]) for record in records],
        "target_ids": [str(record["target_id"]) for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "lease_owners": [str(record["lease_owner"]) for record in records],
        "attempt_counts": [int(record["attempt_count"]) for record in records],
    }


def _required_max_attempts(value: Any) -> int:
    return require_positive_int(value, error_code="market_tick_current_dirty_target_max_attempts_required")


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"market_tick_current_dirty_target_{field_name}_required")
    return text


def _terminal_target_key(row: Mapping[str, Any]) -> str:
    return ":".join(
        (
            _required_text(row.get("target_type"), "target_type"),
            _required_text(row.get("target_id"), "target_id"),
        )
    )


def _retry_budget_exhausted_reason(error: str) -> str:
    message = str(error or "").strip()
    return f"market_tick_current_dirty_retry_budget_exhausted: {message}"[:2048]


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
