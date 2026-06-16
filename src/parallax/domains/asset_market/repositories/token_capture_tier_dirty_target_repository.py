from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
from decimal import Decimal
from typing import Any, cast

from parallax.platform.current_read_model_payload_hash import stable_current_payload_hash


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
        max_watermark_ms = _source_watermark_ms(source_watermark_ms)

        def _write() -> dict[str, int | str]:
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
            changed = _cursor_rowcount(cursor)
            return {"targets": changed, "payload_hash": payload_hash}

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
            return [dict(row) for row in rows]

        return _run_repository_write(self.conn, commit, _write)

    def mark_done(self, claims: Iterable[Mapping[str, Any]], *, now_ms: int, commit: bool = True) -> int:
        records = list(claims)
        if not records:
            return 0

        def _write() -> int:
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
            return _cursor_rowcount(cursor)

        return _run_repository_write(self.conn, commit, _write)

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


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("token_capture_tier_dirty_target_transaction_required") from exc
    if not callable(transaction):
        raise RuntimeError("token_capture_tier_dirty_target_transaction_required")
    return cast(AbstractContextManager[Any], transaction())


def _run_repository_write[T](conn: Any, commit: bool, write: Callable[[], T]) -> T:
    if commit:
        with _transaction(conn):
            return write()
    return write()


def _claim_params(records: list[Mapping[str, Any]]) -> dict[str, list[Any]]:
    return {
        "work_names": [str(record["work_name"]) for record in records],
        "partition_keys": [str(record["partition_key"]) for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "lease_owners": [str(record["lease_owner"]) for record in records],
        "attempt_counts": [int(record["attempt_count"]) for record in records],
    }


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("token_capture_tier_dirty_target_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int):
        raise TypeError("token_capture_tier_dirty_target_rowcount_invalid")
    if rowcount < 0:
        raise TypeError("token_capture_tier_dirty_target_rowcount_invalid")
    return int(rowcount)


def _source_watermark_ms(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("token_capture_tier_dirty_target_source_watermark_required")
    if value <= 0:
        raise ValueError("token_capture_tier_dirty_target_source_watermark_required")
    return int(value)


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
    return stable_current_payload_hash(payload)


def _rank_row_payload(row: Mapping[str, Any], *, exited: bool) -> dict[str, Any]:
    source_target_type = _required_rank_row_text(row, "target_type_key")
    source_target_id = _required_rank_row_text(row, "identity_id")
    capture_target_type, capture_target_id = _capture_rank_target(row, source_target_type=source_target_type)
    payload = {
        "source_target_type": source_target_type,
        "source_target_id": source_target_id,
        "capture_target_type": capture_target_type,
        "capture_target_id": capture_target_id,
        "lane": str(row.get("lane") or ""),
        "rank": row.get("rank"),
        "rank_score": _rank_score_payload(row.get("rank_score", row.get("score"))),
        "decision": row.get("decision"),
        "quality_status": row.get("quality_status"),
        "degraded_reasons_json": row.get("degraded_reasons_json") or [],
        "exited": bool(exited),
    }
    payload["row_payload_hash"] = _rank_row_product_payload_hash(row, rank_payload=payload)
    return payload


def _required_rank_row_text(row: Mapping[str, Any], field_name: str) -> str:
    try:
        value = row[field_name]
    except KeyError as exc:
        raise RuntimeError("token_capture_tier_rank_set_identity_required") from exc
    if value is None:
        raise RuntimeError("token_capture_tier_rank_set_identity_required")
    text = str(value).strip()
    if not text:
        raise RuntimeError("token_capture_tier_rank_set_identity_required")
    return text


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
        pricefeed_provider, pricefeed_market_id = _cex_pricefeed_target(
            row.get("pricefeed_id") or subject.get("pricefeed_id")
        )
        provider = str(row.get("provider") or subject.get("provider") or pricefeed_provider or "").strip().lower()
        native_market_id = (
            str(row.get("native_market_id") or subject.get("native_market_id") or pricefeed_market_id or "")
            .strip()
            .upper()
        )
        if provider and native_market_id:
            return "cex_symbol", f"{provider}:{native_market_id}"
        return "", ""

    return "", ""


def _rank_subject(row: Mapping[str, Any]) -> Mapping[str, Any]:
    snapshot = row.get("factor_snapshot_json")
    if not isinstance(snapshot, Mapping):
        return {}
    subject = snapshot.get("subject")
    return subject if isinstance(subject, Mapping) else {}


def _rank_row_product_payload_hash(row: Mapping[str, Any], *, rank_payload: Mapping[str, Any]) -> str:
    payload = {
        **dict(rank_payload),
        "pricefeed_id": row.get("pricefeed_id"),
        "factor_snapshot_json": _stable_factor_snapshot(row.get("factor_snapshot_json")),
        "source_event_ids_json": row.get("source_event_ids_json") or [],
        "data_health_json": row.get("data_health_json") or {},
        "resolution_json": row.get("resolution_json") or {},
    }
    return stable_current_payload_hash(payload)


def _rank_score_payload(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        normalized = Decimal(str(value)).normalize()
    except Exception:
        return str(value)
    return format(normalized, "f")


def _stable_factor_snapshot(value: Any) -> Any:
    snapshot = value
    if not isinstance(snapshot, Mapping):
        return snapshot
    stable = dict(snapshot)
    provenance = stable.get("provenance")
    if isinstance(provenance, Mapping):
        stable["provenance"] = {key: item for key, item in provenance.items() if key != "computed_at_ms"}
    return stable


def _cex_pricefeed_target(value: Any) -> tuple[str | None, str | None]:
    parts = str(value or "").strip().split(":")
    if len(parts) < 5 or parts[0] != "pricefeed" or parts[1] != "cex":
        return None, None
    return parts[2].strip().lower() or None, parts[-1].strip().upper() or None


def _rank_payload_sort_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(row.get("source_target_type") or ""),
        str(row.get("source_target_id") or ""),
        str(row.get("capture_target_type") or ""),
        str(row.get("capture_target_id") or ""),
        str(row.get("lane") or ""),
        str(row.get("exited") or ""),
    )
