from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from contextlib import nullcontext
from typing import Any

from parallax.platform.db.json_safety import postgres_safe_json
from parallax.platform.db.queue_terminal import terminalize_source_row

_ALLOWED_PROJECTION_NAMES = frozenset({"brief_input", "page", "source_quality"})


class NewsProjectionDirtyTargetRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def enqueue_targets(
        self,
        rows: Iterable[Mapping[str, Any]],
        *,
        reason: str,
        now_ms: int,
        due_at_ms: int | None = None,
        commit: bool = True,
    ) -> int:
        records = _dirty_records(
            rows,
            reason=reason,
            now_ms=now_ms,
            default_due_at_ms=int(due_at_ms if due_at_ms is not None else now_ms),
        )
        if not records:
            return 0
        self.conn.execute(
            """
            WITH incoming AS (
              SELECT *
              FROM unnest(
                %(projection_names)s::text[],
                %(target_kinds)s::text[],
                %(target_ids)s::text[],
                %(windows)s::text[],
                %(payload_hashes)s::text[],
                %(source_watermark_ms_values)s::bigint[],
                %(priorities)s::integer[],
                %(due_at_ms_values)s::bigint[]
              ) AS incoming(
                projection_name,
                target_kind,
                target_id,
                "window",
                payload_hash,
                source_watermark_ms,
                priority,
                due_at_ms
              )
            )
            INSERT INTO news_projection_dirty_targets(
              projection_name,
              target_kind,
              target_id,
              "window",
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
              incoming.projection_name,
              incoming.target_kind,
              incoming.target_id,
              incoming."window",
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
            ON CONFLICT(projection_name, target_kind, target_id, "window") DO UPDATE SET
              dirty_reason = CASE
                WHEN news_projection_dirty_targets.source_watermark_ms = 0
                  OR EXCLUDED.source_watermark_ms >= news_projection_dirty_targets.source_watermark_ms
                  THEN EXCLUDED.dirty_reason
                ELSE news_projection_dirty_targets.dirty_reason
              END,
              payload_hash = CASE
                WHEN news_projection_dirty_targets.source_watermark_ms = 0
                  OR EXCLUDED.source_watermark_ms >= news_projection_dirty_targets.source_watermark_ms
                  THEN EXCLUDED.payload_hash
                ELSE news_projection_dirty_targets.payload_hash
              END,
              source_watermark_ms = GREATEST(
                news_projection_dirty_targets.source_watermark_ms,
                EXCLUDED.source_watermark_ms
              ),
              priority = LEAST(news_projection_dirty_targets.priority, EXCLUDED.priority),
              due_at_ms = LEAST(news_projection_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
              leased_until_ms = CASE
                WHEN news_projection_dirty_targets.leased_until_ms IS NOT NULL
                  AND (
                    EXCLUDED.source_watermark_ms > news_projection_dirty_targets.source_watermark_ms
                    OR (
                      (
                        news_projection_dirty_targets.source_watermark_ms = 0
                        OR EXCLUDED.source_watermark_ms >= news_projection_dirty_targets.source_watermark_ms
                      )
                      AND (
                        news_projection_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                        OR news_projection_dirty_targets.dirty_reason IS DISTINCT FROM EXCLUDED.dirty_reason
                      )
                    )
                  )
                  THEN NULL
                ELSE news_projection_dirty_targets.leased_until_ms
              END,
              lease_owner = CASE
                WHEN news_projection_dirty_targets.leased_until_ms IS NOT NULL
                  AND (
                    EXCLUDED.source_watermark_ms > news_projection_dirty_targets.source_watermark_ms
                    OR (
                      (
                        news_projection_dirty_targets.source_watermark_ms = 0
                        OR EXCLUDED.source_watermark_ms >= news_projection_dirty_targets.source_watermark_ms
                      )
                      AND (
                        news_projection_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                        OR news_projection_dirty_targets.dirty_reason IS DISTINCT FROM EXCLUDED.dirty_reason
                      )
                    )
                  )
                  THEN NULL
                ELSE news_projection_dirty_targets.lease_owner
              END,
              last_error = NULL,
              first_dirty_at_ms = news_projection_dirty_targets.first_dirty_at_ms,
              updated_at_ms = EXCLUDED.updated_at_ms
            """,
            {
                **_dirty_params(records),
                "dirty_reason": str(reason),
                "now_ms": int(now_ms),
            },
        )
        if commit:
            self.conn.commit()
        return len(records)

    def claim_due(
        self,
        *,
        limit: int,
        lease_ms: int,
        now_ms: int,
        lease_owner: str,
        projection_name: str | None = None,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        projection_filter = ""
        params: dict[str, Any] = {
            "now_ms": int(now_ms),
            "leased_until_ms": int(now_ms) + max(1, int(lease_ms)),
            "lease_owner": str(lease_owner),
            "limit": max(0, int(limit)),
        }
        if projection_name is not None:
            _validate_projection_name(str(projection_name))
            projection_filter = "AND projection_name = %(projection_name)s"
            params["projection_name"] = str(projection_name)
        rows = self.conn.execute(
            f"""
            WITH due AS (
              SELECT projection_name, target_kind, target_id, "window"
              FROM news_projection_dirty_targets
              WHERE due_at_ms <= %(now_ms)s
                AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
                {projection_filter}
              ORDER BY priority ASC,
                       source_watermark_ms DESC,
                       due_at_ms ASC,
                       updated_at_ms ASC,
                       projection_name ASC,
                       target_kind ASC,
                       target_id ASC,
                       "window" ASC
              LIMIT %(limit)s
              FOR UPDATE SKIP LOCKED
            )
            UPDATE news_projection_dirty_targets
            SET leased_until_ms = %(leased_until_ms)s,
                lease_owner = %(lease_owner)s,
                last_error = NULL,
                updated_at_ms = %(now_ms)s
            FROM due
            WHERE news_projection_dirty_targets.projection_name = due.projection_name
              AND news_projection_dirty_targets.target_kind = due.target_kind
              AND news_projection_dirty_targets.target_id = due.target_id
              AND news_projection_dirty_targets."window" = due."window"
            RETURNING news_projection_dirty_targets.*
            """,
            params,
        ).fetchall()
        if commit:
            self.conn.commit()
        return [dict(row) for row in rows]

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
        cursor = self.conn.execute(
            """
            WITH done AS (
              SELECT *
              FROM unnest(
                %(projection_names)s::text[],
                %(target_kinds)s::text[],
                %(target_ids)s::text[],
                %(windows)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS done(
                projection_name,
                target_kind,
                target_id,
                "window",
                payload_hash,
                lease_owner,
                attempt_count
              )
            )
            DELETE FROM news_projection_dirty_targets queue
            USING done
            WHERE queue.projection_name = done.projection_name
              AND queue.target_kind = done.target_kind
              AND queue.target_id = done.target_id
              AND queue."window" = done."window"
              AND queue.payload_hash = done.payload_hash
              AND queue.lease_owner = done.lease_owner
              AND queue.attempt_count = done.attempt_count
            """,
            _key_params(records),
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def delete_claimed_targets(self, keys: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        records = _key_records(keys)
        if not records:
            return []
        rows = self.conn.execute(
            """
            WITH done AS (
              SELECT *
              FROM unnest(
                %(projection_names)s::text[],
                %(target_kinds)s::text[],
                %(target_ids)s::text[],
                %(windows)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS done(
                projection_name,
                target_kind,
                target_id,
                "window",
                payload_hash,
                lease_owner,
                attempt_count
              )
            )
            DELETE FROM news_projection_dirty_targets queue
            USING done
            WHERE queue.projection_name = done.projection_name
              AND queue.target_kind = done.target_kind
              AND queue.target_id = done.target_id
              AND queue."window" = done."window"
              AND queue.payload_hash = done.payload_hash
              AND queue.lease_owner = done.lease_owner
              AND queue.attempt_count = done.attempt_count
            RETURNING queue.*
            """,
            _key_params(records),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_error(
        self,
        keys: Iterable[Mapping[str, Any]],
        *,
        error: str,
        retry_ms: int,
        now_ms: int,
        count_attempt: bool = True,
        commit: bool = True,
    ) -> int:
        records = _key_records(keys)
        if not records:
            return 0
        params: dict[str, Any] = {
            **_key_params(records),
            "due_at_ms": int(now_ms) + max(1, int(retry_ms)),
            "now_ms": int(now_ms),
            "last_error": str(error)[:2048],
            "attempt_increment": 1 if count_attempt else 0,
        }
        cursor = self.conn.execute(
            """
            WITH failed AS (
              SELECT *
              FROM unnest(
                %(projection_names)s::text[],
                %(target_kinds)s::text[],
                %(target_ids)s::text[],
                %(windows)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS failed(
                projection_name,
                target_kind,
                target_id,
                "window",
                payload_hash,
                lease_owner,
                attempt_count
              )
            )
            UPDATE news_projection_dirty_targets queue
            SET due_at_ms = %(due_at_ms)s,
                leased_until_ms = NULL,
                lease_owner = NULL,
                attempt_count = queue.attempt_count + %(attempt_increment)s,
                last_error = %(last_error)s,
                updated_at_ms = %(now_ms)s
            FROM failed
            WHERE queue.projection_name = failed.projection_name
              AND queue.target_kind = failed.target_kind
              AND queue.target_id = failed.target_id
              AND queue."window" = failed."window"
              AND queue.payload_hash = failed.payload_hash
              AND queue.lease_owner = failed.lease_owner
              AND queue.attempt_count = failed.attempt_count
            """,
            params,
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def terminalize_targets(
        self,
        keys: Iterable[Mapping[str, Any]],
        *,
        worker_name: str,
        final_reason: str,
        final_reason_bucket: str,
        now_ms: int,
        semantic_payload_hash: str | None = None,
        terminal_attempt_count: int | None = None,
        commit: bool = True,
    ) -> int:
        records = _key_records(keys)
        if not records:
            return 0
        transaction_factory = getattr(self.conn, "transaction", None)
        transaction = transaction_factory() if commit and callable(transaction_factory) else nullcontext()
        with transaction:
            deleted_records = self.delete_claimed_targets(records)
            for record in deleted_records:
                target_key = _terminal_target_key(record, semantic_payload_hash=semantic_payload_hash)
                terminalize_source_row(
                    self.conn,
                    worker_name=worker_name,
                    source_table="news_projection_dirty_targets",
                    target_key=target_key,
                    source_row=record,
                    final_status="terminal",
                    final_reason=final_reason,
                    final_reason_bucket=final_reason_bucket,
                    now_ms=int(now_ms),
                    attempt_count=int(
                        terminal_attempt_count if terminal_attempt_count is not None else record["attempt_count"]
                    ),
                    payload_hash=str(semantic_payload_hash or record["payload_hash"]),
                    commit=False,
                )
        if commit and transaction_factory is None:
            self.conn.commit()
        return len(deleted_records)

    def queue_depth(
        self,
        *,
        now_ms: int,
        projection_name: str | None = None,
    ) -> int:
        projection_filter = ""
        params: dict[str, Any] = {"now_ms": int(now_ms)}
        if projection_name is not None:
            _validate_projection_name(str(projection_name))
            projection_filter = "AND projection_name = %(projection_name)s"
            params["projection_name"] = str(projection_name)
        row = self.conn.execute(
            f"""
            SELECT count(*) AS count
            FROM news_projection_dirty_targets
            WHERE due_at_ms <= %(now_ms)s
              AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
              {projection_filter}
            """,
            params,
        ).fetchone()
        return int(row["count"] if row else 0)


def _dirty_records(
    rows: Iterable[Mapping[str, Any]],
    *,
    reason: str,
    now_ms: int,
    default_due_at_ms: int,
) -> list[dict[str, Any]]:
    records: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        projection_name = str(row.get("projection_name") or "")
        target_kind = str(row.get("target_kind") or "")
        target_id = str(row.get("target_id") or "")
        window = str(row.get("window") or "")
        if projection_name != "source_quality":
            window = ""
        if not projection_name or not target_kind or not target_id:
            continue
        _validate_projection_name(projection_name)
        source_watermark_ms = int(row.get("source_watermark_ms") or 0)
        priority = _priority_value(row)
        target_due_at_ms = int(row.get("due_at_ms") or default_due_at_ms)
        key = (projection_name, target_kind, target_id, window)
        existing = records.get(key)
        record = {
            "projection_name": projection_name,
            "target_kind": target_kind,
            "target_id": target_id,
            "window": window,
            "source_watermark_ms": source_watermark_ms,
            "priority": priority,
            "due_at_ms": target_due_at_ms,
            "_payload_hash_explicit": bool(row.get("payload_hash")),
        }
        record["payload_hash"] = str(row.get("payload_hash") or _dirty_payload_hash(record, reason=reason))
        if existing is None:
            records[key] = record
            continue
        if source_watermark_ms >= int(existing["source_watermark_ms"]):
            record["priority"] = min(int(existing["priority"]), priority)
            record["due_at_ms"] = min(int(existing["due_at_ms"]), target_due_at_ms)
            if not record["_payload_hash_explicit"]:
                record["payload_hash"] = _dirty_payload_hash(record, reason=reason)
            records[key] = record
        else:
            existing["priority"] = min(int(existing["priority"]), priority)
            existing["due_at_ms"] = min(int(existing["due_at_ms"]), target_due_at_ms)
            if not existing["_payload_hash_explicit"]:
                existing["payload_hash"] = _dirty_payload_hash(existing, reason=reason)
    return list(records.values())


def _dirty_params(records: list[dict[str, Any]]) -> dict[str, list[Any]]:
    return {
        "projection_names": [str(record["projection_name"]) for record in records],
        "target_kinds": [str(record["target_kind"]) for record in records],
        "target_ids": [str(record["target_id"]) for record in records],
        "windows": [str(record["window"]) for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "source_watermark_ms_values": [int(record["source_watermark_ms"]) for record in records],
        "priorities": [int(record["priority"]) for record in records],
        "due_at_ms_values": [int(record["due_at_ms"]) for record in records],
    }


def _key_records(keys: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for key in keys:
        projection_name = str(key.get("projection_name") or "")
        target_kind = str(key.get("target_kind") or "")
        target_id = str(key.get("target_id") or "")
        has_window = "window" in key
        window = str(key.get("window") or "") if has_window else ""
        payload_hash = str(key.get("payload_hash") or "")
        lease_owner = str(key.get("lease_owner") or "")
        attempt_count = int(key.get("attempt_count") or 0)
        if not projection_name or not target_kind or not target_id:
            raise ValueError("news projection dirty target completion requires full target key from claim_due")
        _validate_projection_name(projection_name)
        if not has_window:
            raise ValueError("news projection dirty target completion requires window from claim_due")
        if projection_name == "source_quality" and not window:
            raise ValueError("news source_quality dirty target completion requires window from claim_due")
        if projection_name != "source_quality":
            window = ""
        if not payload_hash:
            raise ValueError("news projection dirty target completion requires payload_hash from claim_due")
        if not lease_owner:
            raise ValueError("news projection dirty target completion requires lease_owner from claim_due")
        if attempt_count < 0:
            raise ValueError("news projection dirty target completion requires attempt_count from claim_due")
        records.append(
            {
                "projection_name": projection_name,
                "target_kind": target_kind,
                "target_id": target_id,
                "window": window,
                "payload_hash": payload_hash,
                "lease_owner": lease_owner,
                "attempt_count": attempt_count,
            }
        )
    return records


def _validate_projection_name(projection_name: str) -> None:
    if projection_name not in _ALLOWED_PROJECTION_NAMES:
        raise ValueError(f"unsupported news projection_name: {projection_name}")


def _key_params(records: list[dict[str, Any]]) -> dict[str, list[Any]]:
    return {
        "projection_names": [str(record["projection_name"]) for record in records],
        "target_kinds": [str(record["target_kind"]) for record in records],
        "target_ids": [str(record["target_id"]) for record in records],
        "windows": [str(record["window"]) for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "lease_owners": [str(record["lease_owner"]) for record in records],
        "attempt_counts": [int(record["attempt_count"]) for record in records],
    }


def _terminal_target_key(record: Mapping[str, Any], *, semantic_payload_hash: str | None) -> str:
    return "|".join(
        [
            str(record["projection_name"]),
            str(record["target_kind"]),
            str(record["target_id"]),
            str(record["window"]),
            str(semantic_payload_hash or record["payload_hash"]),
        ]
    )


def _dirty_payload_hash(record: Mapping[str, Any], *, reason: str) -> str:
    return _payload_hash(
        {
            "projection_name": record["projection_name"],
            "target_kind": record["target_kind"],
            "target_id": record["target_id"],
            "window": record["window"],
            "dirty_reason": str(reason),
            "source_watermark_ms": int(record["source_watermark_ms"]),
        }
    )


def _priority_value(row: Mapping[str, Any]) -> int:
    raw_priority = row.get("priority")
    if raw_priority in (None, ""):
        return 100
    return int(str(raw_priority))


def _payload_hash(payload: Mapping[str, Any]) -> str:
    safe_payload = postgres_safe_json(dict(payload))
    encoded = json.dumps(safe_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
