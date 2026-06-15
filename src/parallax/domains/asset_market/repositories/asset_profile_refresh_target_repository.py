from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
from typing import Any, cast

from parallax.platform.current_read_model_payload_hash import stable_dirty_target_payload_hash
from parallax.platform.db.json_safety import postgres_safe_text


class AssetProfileRefreshTargetRepository:
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
        records = _target_records(targets, reason=reason, now_ms=int(now_ms), due_at_ms=due_at_ms)
        if not records:
            return {"targets": 0}

        def _write() -> dict[str, int]:
            self.conn.execute(
                """
                WITH incoming AS (
                  SELECT *
                  FROM unnest(
                    %(providers)s::text[],
                    %(target_types)s::text[],
                    %(target_ids)s::text[],
                    %(chain_ids)s::text[],
                    %(addresses)s::text[],
                    %(symbols)s::text[],
                    %(payload_hashes)s::text[],
                    %(source_watermark_ms_values)s::bigint[],
                    %(priorities)s::integer[],
                    %(due_at_ms_values)s::bigint[]
                  ) AS incoming(
                    provider,
                    target_type,
                    target_id,
                    chain_id,
                    address,
                    symbol,
                    payload_hash,
                    source_watermark_ms,
                    priority,
                    due_at_ms
                  )
                )
                INSERT INTO asset_profile_refresh_targets(
                  provider,
                  target_type,
                  target_id,
                  chain_id,
                  address,
                  symbol,
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
                  provider,
                  target_type,
                  target_id,
                  chain_id,
                  address,
                  symbol,
                  %(dirty_reason)s,
                  payload_hash,
                  source_watermark_ms,
                  priority,
                  due_at_ms,
                  NULL,
                  NULL,
                  0,
                  NULL,
                  %(now_ms)s,
                  %(now_ms)s
                FROM incoming
                ON CONFLICT(provider, target_type, target_id) DO UPDATE SET
                  chain_id = EXCLUDED.chain_id,
                  address = EXCLUDED.address,
                  symbol = EXCLUDED.symbol,
                  dirty_reason = EXCLUDED.dirty_reason,
                  payload_hash = EXCLUDED.payload_hash,
                  source_watermark_ms = GREATEST(
                    asset_profile_refresh_targets.source_watermark_ms,
                    EXCLUDED.source_watermark_ms
                  ),
                  priority = LEAST(asset_profile_refresh_targets.priority, EXCLUDED.priority),
                  due_at_ms = LEAST(asset_profile_refresh_targets.due_at_ms, EXCLUDED.due_at_ms),
                  leased_until_ms = CASE
                    WHEN asset_profile_refresh_targets.leased_until_ms IS NOT NULL
                      AND asset_profile_refresh_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                      THEN NULL
                    ELSE asset_profile_refresh_targets.leased_until_ms
                  END,
                  lease_owner = CASE
                    WHEN asset_profile_refresh_targets.leased_until_ms IS NOT NULL
                      AND asset_profile_refresh_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                      THEN NULL
                    ELSE asset_profile_refresh_targets.lease_owner
                  END,
                  last_error = NULL,
                  first_dirty_at_ms = asset_profile_refresh_targets.first_dirty_at_ms,
                  updated_at_ms = EXCLUDED.updated_at_ms
                """,
                {**_target_params(records), "dirty_reason": str(reason), "now_ms": int(now_ms)},
            )
            return {"targets": len(records)}

        return _run_repository_write(self.conn, commit, _write)

    def claim_due(
        self,
        *,
        provider: str,
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
                  SELECT provider, target_type, target_id
                  FROM asset_profile_refresh_targets
                  WHERE provider = %(provider)s
                    AND due_at_ms <= %(now_ms)s
                    AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
                  ORDER BY priority ASC,
                           due_at_ms ASC,
                           updated_at_ms ASC,
                           target_type ASC,
                           target_id ASC
                  LIMIT %(limit)s
                  FOR UPDATE SKIP LOCKED
                )
                UPDATE asset_profile_refresh_targets
                SET leased_until_ms = %(leased_until_ms)s,
                    lease_owner = %(lease_owner)s,
                    attempt_count = asset_profile_refresh_targets.attempt_count + 1,
                    last_error = NULL,
                    updated_at_ms = %(now_ms)s
                FROM due
                WHERE asset_profile_refresh_targets.provider = due.provider
                  AND asset_profile_refresh_targets.target_type = due.target_type
                  AND asset_profile_refresh_targets.target_id = due.target_id
                RETURNING asset_profile_refresh_targets.*
                """,
                {
                    "provider": str(provider),
                    "now_ms": int(now_ms),
                    "leased_until_ms": int(now_ms) + max(1, int(lease_ms)),
                    "lease_owner": str(lease_owner),
                    "limit": max(0, int(limit)),
                },
            ).fetchall()
            return [dict(row) for row in rows]

        return _run_repository_write(self.conn, commit, _write)

    def reschedule(
        self,
        claims: Iterable[Mapping[str, Any]],
        *,
        due_at_ms: int,
        now_ms: int,
        reason: str | None = None,
        commit: bool = True,
    ) -> int:
        records = _claim_records(claims)
        if not records:
            return 0
        params = {**_claim_params(records), "due_at_ms": int(due_at_ms), "now_ms": int(now_ms), "reason": reason}

        def _write() -> int:
            cursor = self.conn.execute(
                """
                WITH rescheduled AS (
                  SELECT *
                  FROM unnest(
                    %(providers)s::text[],
                    %(target_types)s::text[],
                    %(target_ids)s::text[],
                    %(payload_hashes)s::text[],
                    %(lease_owners)s::text[],
                    %(attempt_counts)s::bigint[]
                  ) AS rescheduled(provider, target_type, target_id, payload_hash, lease_owner, attempt_count)
                )
                UPDATE asset_profile_refresh_targets queue
                SET due_at_ms = %(due_at_ms)s,
                    leased_until_ms = NULL,
                    lease_owner = NULL,
                    dirty_reason = COALESCE(%(reason)s, queue.dirty_reason),
                    updated_at_ms = %(now_ms)s
                FROM rescheduled
                WHERE queue.provider = rescheduled.provider
                  AND queue.target_type = rescheduled.target_type
                  AND queue.target_id = rescheduled.target_id
                  AND queue.payload_hash = rescheduled.payload_hash
                  AND queue.lease_owner = rescheduled.lease_owner
                  AND queue.attempt_count = rescheduled.attempt_count
                """,
                params,
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
        params = {
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
                    %(providers)s::text[],
                    %(target_types)s::text[],
                    %(target_ids)s::text[],
                    %(payload_hashes)s::text[],
                    %(lease_owners)s::text[],
                    %(attempt_counts)s::bigint[]
                  ) AS failed(provider, target_type, target_id, payload_hash, lease_owner, attempt_count)
                )
                UPDATE asset_profile_refresh_targets queue
                SET due_at_ms = %(due_at_ms)s,
                    leased_until_ms = NULL,
                    lease_owner = NULL,
                    last_error = %(last_error)s,
                    updated_at_ms = %(now_ms)s
                FROM failed
                WHERE queue.provider = failed.provider
                  AND queue.target_type = failed.target_type
                  AND queue.target_id = failed.target_id
                  AND queue.payload_hash = failed.payload_hash
                  AND queue.lease_owner = failed.lease_owner
                  AND queue.attempt_count = failed.attempt_count
                """,
                params,
            )
            return _cursor_rowcount(cursor)

        return _run_repository_write(self.conn, commit, _write)

    def queue_depth(self, *, provider: str, now_ms: int) -> int:
        row = self.conn.execute(
            """
            SELECT count(*) AS count
            FROM asset_profile_refresh_targets
            WHERE provider = %(provider)s
              AND due_at_ms <= %(now_ms)s
              AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
            """,
            {"provider": str(provider), "now_ms": int(now_ms)},
        ).fetchone()
        return int(row["count"] if row else 0)


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("asset_profile_refresh_target_transaction_required") from exc
    if not callable(transaction):
        raise RuntimeError("asset_profile_refresh_target_transaction_required")
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
        raise TypeError("asset_profile_refresh_target_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int):
        raise TypeError("asset_profile_refresh_target_rowcount_invalid")
    if rowcount < 0:
        raise TypeError("asset_profile_refresh_target_rowcount_invalid")
    return int(rowcount)


def _target_records(
    targets: Iterable[Mapping[str, Any]],
    *,
    reason: str,
    now_ms: int,
    due_at_ms: int | None,
) -> list[dict[str, Any]]:
    records: dict[tuple[str, str, str], dict[str, Any]] = {}
    for target in targets:
        provider = _required_text(target.get("provider"), field_name="provider")
        target_type = _required_text(target.get("target_type") or "Asset", field_name="target_type")
        target_id = _required_text(target.get("target_id") or target.get("asset_id"), field_name="target_id")
        chain_id = _required_text(target.get("chain_id"), field_name="chain_id")
        address = _required_text(target.get("address"), field_name="address")
        record = {
            "provider": provider,
            "target_type": target_type,
            "target_id": target_id,
            "chain_id": chain_id,
            "address": address,
            "symbol": _optional_text(target.get("symbol")),
            "source_watermark_ms": int(target.get("source_watermark_ms") or target.get("updated_at_ms") or now_ms),
            "priority": int(target.get("priority") or 100),
            "due_at_ms": int(target.get("due_at_ms") or due_at_ms or now_ms),
        }
        record["payload_hash"] = str(target.get("payload_hash") or _payload_hash({**record, "dirty_reason": reason}))
        records[(provider, target_type, target_id)] = record
    return list(records.values())


def _target_params(records: list[dict[str, Any]]) -> dict[str, list[Any]]:
    return {
        "providers": [str(record["provider"]) for record in records],
        "target_types": [str(record["target_type"]) for record in records],
        "target_ids": [str(record["target_id"]) for record in records],
        "chain_ids": [str(record["chain_id"]) for record in records],
        "addresses": [str(record["address"]) for record in records],
        "symbols": [record["symbol"] for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "source_watermark_ms_values": [int(record["source_watermark_ms"]) for record in records],
        "priorities": [int(record["priority"]) for record in records],
        "due_at_ms_values": [int(record["due_at_ms"]) for record in records],
    }


def _claim_records(claims: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for claim in claims:
        provider = str(claim.get("provider") or "").strip()
        target_type = str(claim.get("target_type") or "").strip()
        target_id = str(claim.get("target_id") or "").strip()
        if not provider or not target_type or not target_id:
            raise ValueError("asset profile refresh target completion requires full target key from claim_due")
        payload_hash = _completion_payload_hash(claim)
        lease_owner = _completion_lease_owner(claim)
        attempt_count = _completion_attempt_count(claim)
        if not payload_hash:
            raise ValueError("asset profile refresh target completion requires payload_hash from claim_due")
        if not lease_owner:
            raise ValueError("asset profile refresh target completion requires lease_owner from claim_due")
        if attempt_count <= 0:
            raise ValueError("asset profile refresh target completion requires attempt_count from claim_due")
        records.append(
            {
                "provider": provider,
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
        raise ValueError("asset profile refresh target completion requires attempt_count from claim_due") from exc
    if attempt_count <= 0:
        raise ValueError("asset profile refresh target completion requires attempt_count from claim_due")
    return attempt_count


def _completion_lease_owner(claim: Mapping[str, Any]) -> str:
    try:
        value = claim["lease_owner"]
    except KeyError as exc:
        raise ValueError("asset profile refresh target completion requires lease_owner from claim_due") from exc
    if value is None:
        raise ValueError("asset profile refresh target completion requires lease_owner from claim_due")
    lease_owner = str(value).strip()
    if not lease_owner:
        raise ValueError("asset profile refresh target completion requires lease_owner from claim_due")
    return lease_owner


def _completion_payload_hash(claim: Mapping[str, Any]) -> str:
    try:
        value = claim["payload_hash"]
    except KeyError as exc:
        raise ValueError("asset profile refresh target completion requires payload_hash from claim_due") from exc
    if value is None:
        raise ValueError("asset profile refresh target completion requires payload_hash from claim_due")
    payload_hash = str(value).strip()
    if not payload_hash:
        raise ValueError("asset profile refresh target completion requires payload_hash from claim_due")
    return payload_hash


def _claim_params(records: list[dict[str, Any]]) -> dict[str, list[Any]]:
    return {
        "providers": [str(record["provider"]) for record in records],
        "target_types": [str(record["target_type"]) for record in records],
        "target_ids": [str(record["target_id"]) for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "lease_owners": [str(record["lease_owner"]) for record in records],
        "attempt_counts": [int(record["attempt_count"]) for record in records],
    }


def _required_text(value: Any, *, field_name: str) -> str:
    text = postgres_safe_text(value).strip()
    if not text:
        raise ValueError(f"asset profile refresh target {field_name} is required")
    return text


def _optional_text(value: Any) -> str | None:
    text = postgres_safe_text(value).strip()
    return text or None


def _payload_hash(payload: Mapping[str, Any]) -> str:
    return stable_dirty_target_payload_hash(payload)
