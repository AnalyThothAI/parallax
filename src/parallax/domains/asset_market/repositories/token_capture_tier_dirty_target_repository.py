from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any


class TokenCaptureTierDirtyTargetRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def enqueue_rank_set(
        self,
        *,
        reason: str,
        rows: Iterable[Mapping[str, Any]],
        exited_rows: Iterable[Mapping[str, Any]] = (),
        now_ms: int,
        source_watermark_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, int | str]:
        row_records = list(rows)
        exited_records = list(exited_rows)
        payload_hash = token_capture_tier_rank_set_payload_hash(
            reason=reason,
            rows=row_records,
            exited_rows=exited_records,
        )
        max_watermark_ms = max(
            [
                int(source_watermark_ms or 0),
                *[
                    int(row.get("source_max_received_at_ms") or row.get("source_watermark_ms") or 0)
                    for row in row_records
                ],
                *[
                    int(row.get("source_max_received_at_ms") or row.get("source_watermark_ms") or 0)
                    for row in exited_records
                ],
            ],
            default=0,
        )
        cursor = self.conn.execute(
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
              %(source_watermark_ms)s,
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
            WHERE token_capture_tier_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
            """,
            {
                "reason": str(reason),
                "payload_hash": payload_hash,
                "now_ms": int(now_ms),
                "source_watermark_ms": int(max_watermark_ms),
            },
        )
        if commit:
            self.conn.commit()
        changed = int(getattr(cursor, "rowcount", 0) or 0)
        return {"targets": changed, "payload_hash": payload_hash}

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


def token_capture_tier_rank_set_payload_hash(
    *,
    reason: str,
    rows: Iterable[Mapping[str, Any]],
    exited_rows: Iterable[Mapping[str, Any]] = (),
) -> str:
    payload = {
        "reason": str(reason),
        "rows": sorted([_rank_row_payload(row, exited=False) for row in rows], key=_rank_payload_sort_key),
        "exited_rows": sorted([_rank_row_payload(row, exited=True) for row in exited_rows], key=_rank_payload_sort_key),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _rank_row_payload(row: Mapping[str, Any], *, exited: bool) -> dict[str, Any]:
    source_target_type = str(row.get("target_type") or row.get("target_type_key") or "").strip()
    source_target_id = str(row.get("target_id") or row.get("identity_id") or "").strip()
    capture_target_type, capture_target_id = _capture_rank_target(row, source_target_type=source_target_type)
    return {
        "source_target_type": source_target_type,
        "source_target_id": source_target_id,
        "capture_target_type": capture_target_type,
        "capture_target_id": capture_target_id,
        "lane": str(row.get("lane") or ""),
        "rank": row.get("rank"),
        "rank_score": row.get("rank_score", row.get("score")),
        "quality_status": row.get("quality_status"),
        "degraded_reasons_json": _json_ready(row.get("degraded_reasons_json") or []),
        "payload_hash": row.get("payload_hash"),
        "generation_id": row.get("generation_id") or row.get("current_generation_id"),
        "exited": bool(exited),
    }


def _capture_rank_target(row: Mapping[str, Any], *, source_target_type: str) -> tuple[str, str]:
    subject = _rank_subject(row)
    if source_target_type == "Asset":
        chain_id = str(
            row.get("chain_id")
            or row.get("asset_chain_id")
            or row.get("chain")
            or subject.get("chain_id")
            or subject.get("chain")
            or subject.get("asset_chain_id")
            or ""
        ).strip()
        address = str(
            row.get("address") or row.get("asset_address") or row.get("token_address") or subject.get("address") or ""
        ).strip()
        if chain_id and address:
            normalized_address = address.lower() if address.startswith(("0x", "0X")) else address
            return "chain_token", f"{chain_id}:{normalized_address}"
        return "", ""

    if source_target_type == "CexToken":
        provider = str(row.get("provider") or subject.get("provider") or "").strip().lower()
        native_market_id = str(row.get("native_market_id") or subject.get("native_market_id") or "").strip().upper()
        if provider and native_market_id:
            return "cex_symbol", f"{provider}:{native_market_id}"
        return "", ""

    return "", ""


def _rank_subject(row: Mapping[str, Any]) -> Mapping[str, Any]:
    snapshot = _json_ready(row.get("factor_snapshot_json"))
    if not isinstance(snapshot, Mapping):
        return {}
    subject = snapshot.get("subject")
    return subject if isinstance(subject, Mapping) else {}


def _rank_payload_sort_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(row.get("source_target_type") or ""),
        str(row.get("source_target_id") or ""),
        str(row.get("capture_target_type") or ""),
        str(row.get("capture_target_id") or ""),
        str(row.get("lane") or ""),
        str(row.get("exited") or ""),
    )


def _json_ready(value: Any) -> Any:
    raw = getattr(value, "obj", value)
    if isinstance(raw, Decimal):
        return str(raw)
    if isinstance(raw, Mapping):
        return {str(key): _json_ready(item) for key, item in raw.items()}
    if isinstance(raw, list | tuple | set):
        return [_json_ready(item) for item in raw]
    return raw
