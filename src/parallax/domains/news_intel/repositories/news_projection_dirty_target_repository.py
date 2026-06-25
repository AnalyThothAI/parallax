from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
from typing import Any, cast

from parallax.platform.db.json_safety import postgres_safe_json
from parallax.platform.db.queue_terminal import terminalize_source_row

_ALLOWED_PROJECTION_NAMES = frozenset({"brief_input", "page", "source_quality", "story_brief"})


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
            default_due_at_ms=_required_dirty_due_at_ms(due_at_ms if due_at_ms is not None else now_ms),
        )
        if not records:
            return 0

        def _enqueue_targets() -> int:
            cursor = self.conn.execute(
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
                    WHEN EXCLUDED.source_watermark_ms >= news_projection_dirty_targets.source_watermark_ms
                      THEN EXCLUDED.dirty_reason
                    ELSE news_projection_dirty_targets.dirty_reason
                  END,
                  payload_hash = CASE
                    WHEN EXCLUDED.source_watermark_ms >= news_projection_dirty_targets.source_watermark_ms
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
                          EXCLUDED.source_watermark_ms >= news_projection_dirty_targets.source_watermark_ms
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
                          EXCLUDED.source_watermark_ms >= news_projection_dirty_targets.source_watermark_ms
                          AND (
                            news_projection_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                            OR news_projection_dirty_targets.dirty_reason IS DISTINCT FROM EXCLUDED.dirty_reason
                          )
                        )
                      )
                      THEN NULL
                    ELSE news_projection_dirty_targets.lease_owner
                  END,
                  attempt_count = CASE
                    WHEN EXCLUDED.source_watermark_ms >= news_projection_dirty_targets.source_watermark_ms
                      AND news_projection_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                      THEN 0
                    ELSE news_projection_dirty_targets.attempt_count
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
            return _cursor_rowcount(cursor)

        return _run_repository_write(self.conn, commit, _enqueue_targets)

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
        parsed_lease_ms = _required_positive_int(
            lease_ms,
            "news_projection_dirty_target_claim_lease_ms_required",
        )
        parsed_limit = _required_nonnegative_int(
            limit,
            "news_projection_dirty_target_claim_limit_required",
        )
        params: dict[str, Any] = {
            "now_ms": int(now_ms),
            "leased_until_ms": int(now_ms) + parsed_lease_ms,
            "lease_owner": str(lease_owner),
            "limit": parsed_limit,
        }
        if projection_name is not None:
            _validate_projection_name(str(projection_name))
            projection_filter = "AND projection_name = %(projection_name)s"
            params["projection_name"] = str(projection_name)

        def _claim_due() -> list[dict[str, Any]]:
            cursor = self.conn.execute(
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
            )
            rows = cursor.fetchall()
            _returned_rowcount(cursor, rows)
            claimed_rows = [dict(row) for row in rows]
            return claimed_rows

        return _run_repository_write(self.conn, commit, _claim_due)

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
            return _cursor_rowcount(cursor)

        return _run_repository_write(self.conn, commit, _mark_done)

    def delete_claimed_targets(self, keys: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        records = _key_records(keys)
        deleted_records, _deleted_count = self._delete_claimed_target_rows(records)
        return deleted_records

    def _delete_claimed_target_rows(self, records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        if not records:
            return [], 0
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
            RETURNING queue.*
            """,
            _key_params(records),
        )
        rows = cursor.fetchall()
        deleted_count = _returned_rowcount(cursor, rows)
        return [dict(row) for row in rows], deleted_count

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
        parsed_retry_ms = _required_positive_int(
            retry_ms,
            "news_projection_dirty_target_retry_ms_required",
        )
        params: dict[str, Any] = {
            **_key_params(records),
            "due_at_ms": int(now_ms) + parsed_retry_ms,
            "now_ms": int(now_ms),
            "last_error": str(error)[:2048],
            "attempt_increment": 1 if count_attempt else 0,
        }

        def _mark_error() -> int:
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
            return _cursor_rowcount(cursor)

        return _run_repository_write(self.conn, commit, _mark_error)

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

        def _terminalize_targets() -> int:
            deleted_records, deleted_count = self._delete_claimed_target_rows(records)
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
            return deleted_count

        return _run_repository_write(self.conn, commit, _terminalize_targets)

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
        projection_name = _dirty_record_text(row, field="projection_name")
        target_kind = _dirty_record_text(row, field="target_kind")
        target_id = _dirty_record_text(row, field="target_id")
        window = _dirty_record_window(row, projection_name=projection_name)
        _validate_projection_name(projection_name)
        _validate_projection_target(projection_name=projection_name, target_kind=target_kind)
        source_watermark_ms = _source_watermark_ms(
            row,
            required=_requires_source_watermark(
                projection_name=projection_name,
                target_kind=target_kind,
                window=window,
            ),
        )
        priority = _priority_value(row)
        target_due_at_ms = _dirty_due_at_ms(row, default_due_at_ms=default_due_at_ms)
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


def _dirty_record_text(row: Mapping[str, Any], *, field: str) -> str:
    try:
        value = row[field]
    except KeyError as exc:
        raise ValueError(f"news_projection_dirty_target_{field}_required") from exc
    if not isinstance(value, str):
        raise ValueError(f"news_projection_dirty_target_{field}_required")
    text = value.strip()
    if not text:
        raise ValueError(f"news_projection_dirty_target_{field}_required")
    return text


def _dirty_record_window(row: Mapping[str, Any], *, projection_name: str) -> str:
    if projection_name == "source_quality":
        return _dirty_record_text(row, field="window").lower()
    if "window" not in row:
        return ""
    if row["window"] != "":
        raise ValueError("news_projection_dirty_target_window_empty_required")
    return ""


def _requires_source_watermark(*, projection_name: str, target_kind: str, window: str) -> bool:
    if projection_name in {"page", "brief_input"}:
        return target_kind == "news_item"
    if projection_name == "story_brief":
        return target_kind == "story"
    if projection_name == "source_quality":
        return target_kind == "source" and window != "_refresh"
    return False


def _source_watermark_ms(row: Mapping[str, Any], *, required: bool) -> int:
    try:
        value = row["source_watermark_ms"]
    except KeyError as exc:
        if not required:
            return 0
        raise ValueError("news_projection_dirty_target_source_watermark_required") from exc
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("news_projection_dirty_target_source_watermark_required")
    if value <= 0:
        raise ValueError("news_projection_dirty_target_source_watermark_required")
    return int(value)


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
        projection_name = _completion_key_text(key, "projection_name")
        target_kind = _completion_key_text(key, "target_kind")
        target_id = _completion_key_text(key, "target_id")
        window = _completion_window_text(key)
        _validate_projection_name(projection_name)
        _validate_projection_target(projection_name=projection_name, target_kind=target_kind)
        if projection_name == "source_quality" and not window.strip():
            raise ValueError("news source_quality dirty target completion requires window from claim_due")
        if projection_name != "source_quality" and window != "":
            raise ValueError("news projection dirty target completion requires empty window from claim_due")
        payload_hash = _completion_payload_hash(key)
        lease_owner = _completion_lease_owner(key)
        attempt_count = _completion_attempt_count(key)
        if not payload_hash:
            raise ValueError("news projection dirty target completion requires payload_hash from claim_due")
        if not lease_owner:
            raise ValueError("news projection dirty target completion requires lease_owner from claim_due")
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


def _completion_key_text(key: Mapping[str, Any], field: str) -> str:
    try:
        value = key[field]
    except KeyError as exc:
        raise ValueError("news projection dirty target completion requires full target key from claim_due") from exc
    if not isinstance(value, str):
        raise ValueError("news projection dirty target completion requires full target key from claim_due")
    text = value.strip()
    if not text:
        raise ValueError("news projection dirty target completion requires full target key from claim_due")
    return text


def _completion_window_text(key: Mapping[str, Any]) -> str:
    try:
        value = key["window"]
    except KeyError as exc:
        raise ValueError("news projection dirty target completion requires window from claim_due") from exc
    if not isinstance(value, str):
        raise ValueError("news projection dirty target completion requires window from claim_due")
    return value


def _completion_attempt_count(key: Mapping[str, Any]) -> int:
    try:
        value = key["attempt_count"]
    except KeyError as exc:
        raise ValueError("news projection dirty target completion requires attempt_count from claim_due") from exc
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("news projection dirty target completion requires attempt_count from claim_due")
    return int(value)


def _completion_lease_owner(key: Mapping[str, Any]) -> str:
    try:
        value = key["lease_owner"]
    except KeyError as exc:
        raise ValueError("news projection dirty target completion requires lease_owner from claim_due") from exc
    if value is None:
        raise ValueError("news projection dirty target completion requires lease_owner from claim_due")
    lease_owner = str(value).strip()
    if not lease_owner:
        raise ValueError("news projection dirty target completion requires lease_owner from claim_due")
    return lease_owner


def _completion_payload_hash(key: Mapping[str, Any]) -> str:
    try:
        value = key["payload_hash"]
    except KeyError as exc:
        raise ValueError("news projection dirty target completion requires payload_hash from claim_due") from exc
    if value is None:
        raise ValueError("news projection dirty target completion requires payload_hash from claim_due")
    payload_hash = str(value).strip()
    if not payload_hash:
        raise ValueError("news projection dirty target completion requires payload_hash from claim_due")
    return payload_hash


def _validate_projection_name(projection_name: str) -> None:
    if projection_name not in _ALLOWED_PROJECTION_NAMES:
        raise ValueError(f"unsupported news projection_name: {projection_name}")


def _validate_projection_target(*, projection_name: str, target_kind: str) -> None:
    if projection_name in {"page", "brief_input"} and target_kind == "news_item":
        return
    if projection_name == "source_quality" and target_kind == "source":
        return
    if projection_name == "story_brief" and target_kind == "story":
        return
    raise ValueError(f"unsupported news projection target: {projection_name}/{target_kind}")


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("news_projection_dirty_target_transaction_required") from exc
    if not callable(transaction):
        raise RuntimeError("news_projection_dirty_target_transaction_required")
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
        raise TypeError("news_projection_dirty_target_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int):
        raise TypeError("news_projection_dirty_target_rowcount_invalid")
    if rowcount < 0:
        raise TypeError("news_projection_dirty_target_rowcount_invalid")
    return rowcount


def _returned_rowcount(cursor: Any, rows: list[Any]) -> int:
    count = _cursor_rowcount(cursor)
    if count != len(rows):
        raise TypeError("news_projection_dirty_target_rowcount_invalid")
    return count


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
    if raw_priority is None:
        return 100
    if not isinstance(raw_priority, int) or isinstance(raw_priority, bool):
        raise ValueError("news_projection_dirty_target_priority_required")
    return raw_priority


def _dirty_due_at_ms(row: Mapping[str, Any], *, default_due_at_ms: int) -> int:
    value = row.get("due_at_ms")
    if value is None:
        return default_due_at_ms
    return _required_dirty_due_at_ms(value)


def _required_dirty_due_at_ms(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("news_projection_dirty_target_due_at_ms_required")
    return value


def _required_positive_int(value: Any, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(error_code)
    return int(value)


def _required_nonnegative_int(value: Any, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(error_code)
    return int(value)


def _payload_hash(payload: Mapping[str, Any]) -> str:
    safe_payload = postgres_safe_json(dict(payload))
    encoded = json.dumps(safe_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
