from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, cast

from psycopg.types.json import Jsonb

SEVERITY_RANK = {"info": 0, "warning": 1, "high": 2, "critical": 3}
_AGGREGATION_SOURCE_REFS_KEY = "_aggregation_source_refs"


@dataclass(frozen=True, slots=True)
class NotificationInsertOutcome:
    row: dict[str, Any] | None
    created: bool
    aggregated: bool


class NotificationRepository:
    def __init__(
        self,
        conn: Any,
        *,
        running_timeout_ms: int,
        stale_running_terminalization_batch_size: int,
    ):
        self.conn = conn
        self.running_timeout_ms = _required_positive_int(
            running_timeout_ms,
            error_code="notification_delivery_running_timeout_ms_required",
        )
        self.stale_running_terminalization_batch_size = _required_positive_int(
            stale_running_terminalization_batch_size,
            error_code="notification_delivery_stale_running_terminalization_batch_size_required",
        )

    def insert_notification(
        self,
        *,
        dedup_key: str,
        rule_id: str,
        severity: str,
        title: str,
        body: str,
        entity_type: str | None,
        entity_key: str | None,
        author_handle: str | None = None,
        symbol: str | None = None,
        chain: str | None = None,
        address: str | None = None,
        event_id: str | None = None,
        source_table: str,
        source_id: str,
        occurrence_at_ms: int,
        payload: dict[str, Any] | None = None,
        channels: list[str] | tuple[str, ...] = ("in_app",),
        commit: bool = True,
    ) -> dict[str, Any] | None:
        outcome = self.insert_notification_with_outcome(
            dedup_key=dedup_key,
            rule_id=rule_id,
            severity=severity,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_key=entity_key,
            author_handle=author_handle,
            symbol=symbol,
            chain=chain,
            address=address,
            event_id=event_id,
            source_table=source_table,
            source_id=source_id,
            occurrence_at_ms=occurrence_at_ms,
            payload=payload,
            channels=channels,
            commit=commit,
        )
        return outcome.row if outcome.created else None

    def insert_notification_with_outcome(
        self,
        *,
        dedup_key: str,
        rule_id: str,
        severity: str,
        title: str,
        body: str,
        entity_type: str | None,
        entity_key: str | None,
        author_handle: str | None = None,
        symbol: str | None = None,
        chain: str | None = None,
        address: str | None = None,
        event_id: str | None = None,
        source_table: str,
        source_id: str,
        occurrence_at_ms: int,
        payload: dict[str, Any] | None = None,
        channels: list[str] | tuple[str, ...] = ("in_app",),
        commit: bool = True,
    ) -> NotificationInsertOutcome:
        def write() -> NotificationInsertOutcome:
            now_ms = _now_ms()
            notification_id = _id("notification", dedup_key)
            normalized_severity = _normalize_severity(severity)
            normalized_channels = tuple(str(channel).strip() for channel in channels if str(channel).strip()) or (
                "in_app",
            )
            normalized_payload = dict(payload or {})
            semantic_duplicate = self._semantic_signature_duplicate(
                rule_id=rule_id,
                payload=normalized_payload,
            )
            if semantic_duplicate is not None:
                aggregated = self._aggregate_notification_row(
                    existing=semantic_duplicate,
                    normalized_severity=normalized_severity,
                    title=title,
                    body=body,
                    author_handle=_normalize_handle(author_handle),
                    symbol=_normalize_symbol(symbol),
                    chain=_normalize_chain(chain),
                    address=_normalize_address(address),
                    event_id=event_id,
                    source_table=source_table,
                    source_id=source_id,
                    occurrence_at_ms=int(occurrence_at_ms),
                    payload=normalized_payload,
                    channels=list(normalized_channels),
                    now_ms=now_ms,
                )
                row = (
                    self.notification_by_id(str(semantic_duplicate["notification_id"]), subscriber_key=None)
                    if aggregated
                    else None
                )
                return NotificationInsertOutcome(row=row, created=False, aggregated=aggregated)
            if self._external_push_cooldown_duplicate(rule_id=rule_id, payload=normalized_payload):
                normalized_payload = {
                    **normalized_payload,
                    "external_push_eligible": False,
                    "external_push_suppression_reason": "external_cooldown_duplicate",
                }
                normalized_channels = ("in_app",)
            cursor = self.conn.execute(
                """
                INSERT INTO notifications(
                  notification_id, dedup_key, rule_id, severity, title, body, entity_type, entity_key,
                  author_handle, symbol, chain, address, event_id, source_table, source_id,
                  occurrence_count, first_seen_at_ms, last_seen_at_ms, payload_json, channels_json,
                  created_at_ms, updated_at_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(dedup_key) DO NOTHING
                """,
                (
                    notification_id,
                    dedup_key,
                    rule_id,
                    normalized_severity,
                    title,
                    body,
                    entity_type,
                    entity_key,
                    _normalize_handle(author_handle),
                    _normalize_symbol(symbol),
                    _normalize_chain(chain),
                    _normalize_address(address),
                    event_id,
                    source_table,
                    source_id,
                    1,
                    int(occurrence_at_ms),
                    int(occurrence_at_ms),
                    _json(normalized_payload),
                    _json(list(normalized_channels)),
                    now_ms,
                    now_ms,
                ),
            )
            inserted = _single_row_write_count(
                cursor,
                required_error="notification_insert_rowcount_required",
                invalid_error="notification_insert_rowcount_invalid",
            )
            if inserted == 0:
                existing = self.conn.execute(
                    "SELECT * FROM notifications WHERE dedup_key = %s FOR UPDATE",
                    (dedup_key,),
                ).fetchone()
                existing_dict = dict(existing) if existing is not None else None
                aggregated = self._aggregate_notification_row(
                    existing=existing_dict,
                    normalized_severity=normalized_severity,
                    title=title,
                    body=body,
                    author_handle=_normalize_handle(author_handle),
                    symbol=_normalize_symbol(symbol),
                    chain=_normalize_chain(chain),
                    address=_normalize_address(address),
                    event_id=event_id,
                    source_table=source_table,
                    source_id=source_id,
                    occurrence_at_ms=int(occurrence_at_ms),
                    payload=normalized_payload,
                    channels=list(normalized_channels),
                    now_ms=now_ms,
                )
                row = (
                    self.notification_by_id(str(existing_dict["notification_id"]), subscriber_key=None)
                    if aggregated and existing_dict is not None
                    else None
                )
                return NotificationInsertOutcome(row=row, created=False, aggregated=aggregated)
            return NotificationInsertOutcome(
                row=self.notification_by_id(notification_id, subscriber_key=None),
                created=True,
                aggregated=False,
            )

        return _run_repository_write(self.conn, commit, write)

    def _semantic_signature_duplicate(
        self,
        *,
        rule_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        signature_key_sql = "payload_json->>'semantic_signature'"
        semantic_signature = str(payload.get("semantic_signature") or "").strip()
        if not semantic_signature:
            return None
        external_clause = ""
        params: tuple[Any, ...]
        if rule_id == "news_high_signal":
            params = (rule_id, semantic_signature)
        else:
            external_push_signature = str(payload.get("external_push_signature") or "").strip() or "in_app"
            external_clause = "AND COALESCE(payload_json->>'external_push_signature', 'in_app') = %s"
            params = (rule_id, semantic_signature, external_push_signature)
        row = self.conn.execute(
            f"""
            SELECT *
            FROM notifications
            WHERE rule_id = %s
              AND {signature_key_sql} = %s
              {external_clause}
            ORDER BY last_seen_at_ms DESC, created_at_ms DESC
            LIMIT 1
            FOR UPDATE
            """,
            params,
        ).fetchone()
        if row is not None:
            return dict(row)
        return None

    def _external_push_cooldown_duplicate(
        self,
        *,
        rule_id: str,
        payload: dict[str, Any],
    ) -> bool:
        if payload.get("external_push_eligible") is not True:
            return False
        external_push_signature = str(payload.get("external_push_signature") or "").strip()
        if not external_push_signature:
            return False
        row = self.conn.execute(
            """
            SELECT notification_id
            FROM notifications
            WHERE rule_id = %s
              AND payload_json->>'external_push_signature' = %s
            ORDER BY last_seen_at_ms DESC, created_at_ms DESC
            LIMIT 1
            FOR UPDATE
            """,
            (rule_id, external_push_signature),
        ).fetchone()
        return row is not None

    def _aggregate_notification_row(
        self,
        *,
        existing: dict[str, Any] | None,
        normalized_severity: str,
        title: str,
        body: str,
        author_handle: str | None,
        symbol: str | None,
        chain: str | None,
        address: str | None,
        event_id: str | None,
        source_table: str,
        source_id: str,
        occurrence_at_ms: int,
        payload: dict[str, Any],
        channels: list[str],
        now_ms: int,
    ) -> bool:
        if existing is None:
            return False
        existing_payload = _payload_dict(existing.get("payload_json"))
        existing_refs = _aggregation_source_refs(existing_payload)
        existing_ref = _aggregation_source_ref(
            str(existing.get("source_table") or ""),
            str(existing.get("source_id") or ""),
            existing.get("event_id"),
        )
        if existing_ref:
            existing_refs = _append_unique(existing_refs, existing_ref)
        incoming_ref = _aggregation_source_ref(source_table, source_id, event_id)
        same_source_ref_seen = bool(incoming_ref and incoming_ref in existing_refs)
        if same_source_ref_seen and not _external_push_upgrade(existing_payload, payload):
            return False
        merged_refs = _append_unique(existing_refs, incoming_ref)
        next_payload = dict(payload)
        if merged_refs:
            next_payload[_AGGREGATION_SOURCE_REFS_KEY] = merged_refs[-100:]
        cursor = self.conn.execute(
            """
            UPDATE notifications
            SET severity = %s,
                title = %s,
                body = %s,
                author_handle = %s,
                symbol = %s,
                chain = %s,
                address = %s,
                event_id = %s,
                source_table = %s,
                source_id = %s,
                occurrence_count = occurrence_count + %s,
                last_seen_at_ms = GREATEST(last_seen_at_ms, %s),
                payload_json = %s,
                channels_json = %s,
                updated_at_ms = %s
            WHERE notification_id = %s
            """,
            (
                normalized_severity,
                title,
                body,
                author_handle,
                symbol,
                chain,
                address,
                event_id,
                source_table,
                source_id,
                0 if same_source_ref_seen else 1,
                int(occurrence_at_ms),
                _json(next_payload),
                _json(channels),
                now_ms,
                existing["notification_id"],
            ),
        )
        updated = _single_row_write_count(
            cursor,
            required_error="notification_aggregate_rowcount_required",
            invalid_error="notification_aggregate_rowcount_invalid",
        )
        if updated != 1:
            raise TypeError("notification_aggregate_rowcount_invalid")
        return True

    def notification_by_id(
        self,
        notification_id: str,
        *,
        subscriber_key: str | None = "local",
    ) -> dict[str, Any] | None:
        rows = self._select_notifications(
            where="n.notification_id = %s",
            params=[notification_id],
            limit=1,
            subscriber_key=subscriber_key,
        )
        return rows[0] if rows else None

    def list_notifications(
        self,
        *,
        limit: int,
        subscriber_key: str | None = "local",
        unread_only: bool = False,
        since_ms: int | None = None,
        rule_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if since_ms is not None:
            clauses.append("n.last_seen_at_ms >= %s")
            params.append(int(since_ms))
        if rule_id:
            clauses.append("n.rule_id = %s")
            params.append(rule_id)
        if unread_only:
            clauses.append("r.read_at_ms IS NULL")
        where = " AND ".join(clauses)
        return self._select_notifications(
            where=where,
            params=params,
            limit=limit,
            subscriber_key=subscriber_key,
        )

    def summary(self, *, subscriber_key: str = "local", since_ms: int | None = None) -> dict[str, Any]:
        clauses = ["r.read_at_ms IS NULL"]
        params: list[Any] = [subscriber_key]
        if since_ms is not None:
            clauses.append("n.last_seen_at_ms >= %s")
            params.append(int(since_ms))
        where = " AND ".join(clauses)
        aggregate_row = self.conn.execute(
            f"""
            SELECT
              COUNT(*) AS unread_count,
              COUNT(*) FILTER (WHERE n.severity = 'high') AS high_unread_count,
              COUNT(*) FILTER (WHERE n.severity = 'critical') AS critical_unread_count,
              MAX(
                CASE n.severity
                  WHEN 'critical' THEN 3
                  WHEN 'high' THEN 2
                  WHEN 'warning' THEN 1
                  WHEN 'info' THEN 0
                  ELSE NULL
                END
              ) AS highest_unread_rank
            FROM notifications n
            LEFT JOIN notification_reads r
              ON r.notification_id = n.notification_id
             AND r.subscriber_key = %s
            WHERE {where}
            """,
            params,
        ).fetchone()
        account_where = " AND ".join([*clauses, "n.author_handle IS NOT NULL"])
        account_rows = self.conn.execute(
            f"""
            SELECT n.author_handle, COUNT(*) AS unread_count
            FROM notifications n
            LEFT JOIN notification_reads r
              ON r.notification_id = n.notification_id
             AND r.subscriber_key = %s
            WHERE {account_where}
            GROUP BY n.author_handle
            ORDER BY n.author_handle ASC
            """,
            params,
        ).fetchall()
        highest_rank = aggregate_row["highest_unread_rank"] if aggregate_row is not None else None
        account_counts = {str(row["author_handle"]): int(row["unread_count"]) for row in account_rows}
        return {
            "subscriber_key": subscriber_key,
            "unread_count": int(aggregate_row["unread_count"] if aggregate_row is not None else 0),
            "high_unread_count": int(aggregate_row["high_unread_count"] if aggregate_row is not None else 0),
            "critical_unread_count": int(aggregate_row["critical_unread_count"] if aggregate_row is not None else 0),
            "highest_unread_severity": _severity_from_rank(int(highest_rank)) if highest_rank is not None else None,
            "account_unread_counts": account_counts,
        }

    def mark_read(self, *, notification_id: str, subscriber_key: str = "local", read_at_ms: int | None = None) -> bool:
        def write() -> bool:
            row = self.conn.execute(
                "SELECT notification_id FROM notifications WHERE notification_id = %s",
                (notification_id,),
            ).fetchone()
            if row is None:
                return False
            cursor = self.conn.execute(
                """
                INSERT INTO notification_reads(notification_id, subscriber_key, read_at_ms)
                VALUES (%s, %s, %s)
                ON CONFLICT(notification_id, subscriber_key) DO UPDATE SET
                  read_at_ms = excluded.read_at_ms
                WHERE notification_reads.read_at_ms IS DISTINCT FROM excluded.read_at_ms
                """,
                (notification_id, subscriber_key, int(read_at_ms if read_at_ms is not None else _now_ms())),
            )
            _single_row_write_count(
                cursor,
                required_error="notification_read_mark_rowcount_required",
                invalid_error="notification_read_mark_rowcount_invalid",
            )
            return True

        return _run_repository_write(self.conn, True, write)

    def mark_all_read(self, *, subscriber_key: str = "local", read_at_ms: int | None = None) -> int:
        def write() -> int:
            now_ms = int(read_at_ms if read_at_ms is not None else _now_ms())
            cursor = self.conn.execute(
                """
                WITH unread AS (
                  SELECT n.notification_id
                  FROM notifications n
                  LEFT JOIN notification_reads r
                    ON r.notification_id = n.notification_id
                   AND r.subscriber_key = %s
                  WHERE r.read_at_ms IS NULL
                )
                INSERT INTO notification_reads(notification_id, subscriber_key, read_at_ms)
                SELECT notification_id, %s, %s
                FROM unread
                ON CONFLICT(notification_id, subscriber_key) DO UPDATE SET
                  read_at_ms = excluded.read_at_ms
                WHERE notification_reads.read_at_ms IS DISTINCT FROM excluded.read_at_ms
                RETURNING notification_id
                """,
                (subscriber_key, subscriber_key, now_ms),
            )
            rows = cursor.fetchall()
            return _returned_write_count(
                cursor,
                rows,
                required_error="notification_read_bulk_rowcount_required",
                invalid_error="notification_read_bulk_rowcount_invalid",
            )

        return _run_repository_write(self.conn, True, write)

    def mark_author_read(
        self,
        *,
        author_handle: str,
        subscriber_key: str = "local",
        read_at_ms: int | None = None,
    ) -> int:
        normalized_handle = _normalize_handle(author_handle)
        if not normalized_handle:
            return 0

        def write() -> int:
            now_ms = int(read_at_ms if read_at_ms is not None else _now_ms())
            cursor = self.conn.execute(
                """
                WITH unread AS (
                  SELECT n.notification_id
                  FROM notifications n
                  LEFT JOIN notification_reads r
                    ON r.notification_id = n.notification_id
                   AND r.subscriber_key = %s
                  WHERE r.read_at_ms IS NULL
                    AND n.author_handle = %s
                )
                INSERT INTO notification_reads(notification_id, subscriber_key, read_at_ms)
                SELECT notification_id, %s, %s
                FROM unread
                ON CONFLICT(notification_id, subscriber_key) DO UPDATE SET
                  read_at_ms = excluded.read_at_ms
                WHERE notification_reads.read_at_ms IS DISTINCT FROM excluded.read_at_ms
                RETURNING notification_id
                """,
                (subscriber_key, normalized_handle, subscriber_key, now_ms),
            )
            rows = cursor.fetchall()
            return _returned_write_count(
                cursor,
                rows,
                required_error="notification_read_bulk_rowcount_required",
                invalid_error="notification_read_bulk_rowcount_invalid",
            )

        return _run_repository_write(self.conn, True, write)

    def enqueue_delivery(
        self,
        *,
        notification_id: str,
        channel_id: str,
        provider: str,
        max_attempts: int,
        next_run_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        required_max_attempts = _required_positive_int(
            max_attempts,
            error_code="notification_delivery_max_attempts_required",
        )

        def write() -> dict[str, Any] | None:
            now_ms = _now_ms()
            delivery_id = _id("delivery", notification_id, channel_id)
            cursor = self.conn.execute(
                """
                INSERT INTO notification_deliveries(
                  delivery_id, notification_id, channel_id, provider, status, attempt_count, max_attempts,
                  next_run_at_ms, last_attempt_at_ms, delivered_at_ms, last_error, created_at_ms, updated_at_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(notification_id, channel_id) DO NOTHING
                """,
                (
                    delivery_id,
                    notification_id,
                    channel_id,
                    provider,
                    "pending",
                    0,
                    required_max_attempts,
                    int(next_run_at_ms if next_run_at_ms is not None else now_ms),
                    None,
                    None,
                    None,
                    now_ms,
                    now_ms,
                ),
            )
            inserted = _single_row_write_count(
                cursor,
                required_error="notification_delivery_enqueue_rowcount_required",
                invalid_error="notification_delivery_enqueue_rowcount_invalid",
            )
            if inserted == 0:
                return None
            return self.delivery_by_id(delivery_id)

        return _run_delivery_write(self.conn, commit, write)

    def enqueue_or_requeue_delivery(
        self,
        *,
        notification_id: str,
        channel_id: str,
        provider: str,
        max_attempts: int,
        next_run_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        required_max_attempts = _required_positive_int(
            max_attempts,
            error_code="notification_delivery_max_attempts_required",
        )

        def write() -> dict[str, Any] | None:
            now_ms = _now_ms()
            delivery_id = _id("delivery", notification_id, channel_id)
            cursor = self.conn.execute(
                """
                INSERT INTO notification_deliveries(
                  delivery_id, notification_id, channel_id, provider, status, attempt_count, max_attempts,
                  next_run_at_ms, last_attempt_at_ms, delivered_at_ms, last_error, created_at_ms, updated_at_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(notification_id, channel_id) DO UPDATE SET
                  provider = EXCLUDED.provider,
                  status = 'pending',
                  attempt_count = 0,
                  max_attempts = EXCLUDED.max_attempts,
                  next_run_at_ms = EXCLUDED.next_run_at_ms,
                  last_attempt_at_ms = NULL,
                  delivered_at_ms = NULL,
                  last_error = NULL,
                  updated_at_ms = EXCLUDED.updated_at_ms
                WHERE notification_deliveries.status IN ('failed', 'dead')
                RETURNING *
                """,
                (
                    delivery_id,
                    notification_id,
                    channel_id,
                    provider,
                    "pending",
                    0,
                    required_max_attempts,
                    int(next_run_at_ms if next_run_at_ms is not None else now_ms),
                    None,
                    None,
                    None,
                    now_ms,
                    now_ms,
                ),
            )
            row = cursor.fetchone()
            return _optional_returning_row(
                cursor,
                row,
                required_error="notification_delivery_requeue_rowcount_required",
                invalid_error="notification_delivery_requeue_rowcount_invalid",
            )

        return _run_delivery_write(self.conn, commit, write)

    def delivery_by_id(self, delivery_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM notification_deliveries WHERE delivery_id = %s",
            (delivery_id,),
        ).fetchone()
        return dict(row) if row else None

    def claim_next_delivery(self, *, now_ms: int | None = None, commit: bool = True) -> dict[str, Any] | None:
        now = int(now_ms if now_ms is not None else _now_ms())

        def write() -> dict[str, Any] | None:
            stale_before = now - self.running_timeout_ms
            terminalize_cursor = self.conn.execute(
                """
                WITH expired AS (
                  SELECT delivery_id
                  FROM notification_deliveries
                  WHERE status = 'running'
                    AND updated_at_ms < %s
                    AND attempt_count >= max_attempts
                  ORDER BY updated_at_ms ASC, delivery_id ASC
                  LIMIT %s
                  FOR UPDATE SKIP LOCKED
                )
                UPDATE notification_deliveries AS delivery
                SET status = 'dead',
                    last_error = 'stale_running_timeout',
                    updated_at_ms = %s
                FROM expired
                WHERE delivery.delivery_id = expired.delivery_id
                """,
                (stale_before, self.stale_running_terminalization_batch_size, now),
            )
            _bounded_write_count(
                terminalize_cursor,
                limit=self.stale_running_terminalization_batch_size,
                required_error="notification_delivery_stale_terminalize_rowcount_required",
                invalid_error="notification_delivery_stale_terminalize_rowcount_invalid",
            )
            cursor = self.conn.execute(
                """
                WITH picked AS (
                  SELECT delivery_id
                  FROM notification_deliveries
                  WHERE (
                      status IN ('pending', 'failed')
                      AND attempt_count < max_attempts
                      AND next_run_at_ms <= %s
                    )
                    OR (
                      status = 'running'
                      AND updated_at_ms < %s
                      AND attempt_count < max_attempts
                    )
                  ORDER BY next_run_at_ms ASC, created_at_ms ASC, delivery_id ASC
                  LIMIT 1
                  FOR UPDATE SKIP LOCKED
                )
                UPDATE notification_deliveries AS delivery
                SET status = 'running',
                    attempt_count = delivery.attempt_count + 1,
                    last_attempt_at_ms = %s,
                    updated_at_ms = %s,
                    last_error = NULL
                FROM picked
                WHERE delivery.delivery_id = picked.delivery_id
                  AND (
                    (
                      delivery.status IN ('pending', 'failed')
                      AND delivery.attempt_count < delivery.max_attempts
                      AND delivery.next_run_at_ms <= %s
                    )
                    OR (
                      delivery.status = 'running'
                      AND delivery.updated_at_ms < %s
                      AND delivery.attempt_count < delivery.max_attempts
                    )
                  )
                RETURNING delivery.*
                """,
                (now, stale_before, now, now, now, stale_before),
            )
            row = cursor.fetchone()
            return _optional_returning_row(
                cursor,
                row,
                required_error="notification_delivery_claim_rowcount_required",
                invalid_error="notification_delivery_claim_rowcount_invalid",
            )

        return _run_delivery_write(self.conn, commit, write)

    def complete_delivery(
        self,
        delivery: dict[str, Any],
        *,
        delivered_at_ms: int | None = None,
        commit: bool = True,
    ) -> None:
        now = int(delivered_at_ms if delivered_at_ms is not None else _now_ms())
        delivery_id, claim_attempt_count, claim_updated_at_ms = _delivery_claim_contract(delivery)

        def write() -> None:
            cursor = self.conn.execute(
                """
                UPDATE notification_deliveries
                SET status = 'delivered',
                    delivered_at_ms = %s,
                    last_error = NULL,
                    updated_at_ms = %s
                WHERE delivery_id = %s
                  AND status = 'running'
                  AND attempt_count = %s
                  AND updated_at_ms = %s
                """,
                (now, now, delivery_id, claim_attempt_count, claim_updated_at_ms),
            )
            _single_row_write_count(
                cursor,
                required_error="notification_delivery_complete_rowcount_required",
                invalid_error="notification_delivery_complete_rowcount_invalid",
            )

        _run_delivery_write(self.conn, commit, write)

    def fail_delivery(
        self,
        delivery: dict[str, Any],
        *,
        error: str,
        now_ms: int | None = None,
        commit: bool = True,
    ) -> None:
        now = int(now_ms if now_ms is not None else _now_ms())
        attempts, max_attempts = _delivery_attempt_contract(delivery)
        delivery_id, claim_attempt_count, claim_updated_at_ms = _delivery_claim_contract(delivery)
        status = "dead" if attempts >= max_attempts else "failed"
        delay_ms = min(15 * 60_000, 30_000 * max(1, attempts))

        def write() -> None:
            cursor = self.conn.execute(
                """
                UPDATE notification_deliveries
                SET status = %s,
                    next_run_at_ms = %s,
                    last_error = %s,
                    updated_at_ms = %s
                WHERE delivery_id = %s
                  AND status = 'running'
                  AND attempt_count = %s
                  AND updated_at_ms = %s
                """,
                (
                    status,
                    now + delay_ms,
                    str(error)[:1000],
                    now,
                    delivery_id,
                    claim_attempt_count,
                    claim_updated_at_ms,
                ),
            )
            _single_row_write_count(
                cursor,
                required_error="notification_delivery_fail_rowcount_required",
                invalid_error="notification_delivery_fail_rowcount_invalid",
            )

        _run_delivery_write(self.conn, commit, write)

    def list_deliveries(self, *, limit: int, status: str | None = None) -> list[dict[str, Any]]:
        parsed_limit = _required_nonnegative_int(limit, error_code="notification_delivery_list_limit_required")
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = %s")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM notification_deliveries
            {where}
            ORDER BY updated_at_ms DESC, created_at_ms DESC
            LIMIT %s
            """,
            (*params, parsed_limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def _select_notifications(
        self,
        *,
        where: str,
        params: list[Any],
        limit: int,
        subscriber_key: str | None,
    ) -> list[dict[str, Any]]:
        parsed_limit = _required_nonnegative_int(limit, error_code="notification_list_limit_required")
        join = ""
        select_read = "NULL AS read_at_ms"
        query_params = list(params)
        if subscriber_key is not None:
            join = """
            LEFT JOIN notification_reads r
              ON r.notification_id = n.notification_id
             AND r.subscriber_key = %s
            """
            select_read = "r.read_at_ms AS read_at_ms"
            query_params = [subscriber_key, *query_params]
        where_clause = f"WHERE {where}" if where else ""
        rows = self.conn.execute(
            f"""
            SELECT n.*, {select_read}
            FROM notifications n
            {join}
            {where_clause}
            ORDER BY n.last_seen_at_ms DESC, n.created_at_ms DESC
            LIMIT %s
            """,
            (*query_params, parsed_limit),
        ).fetchall()
        return [dict(row) for row in rows]


def _json(value: Any) -> Jsonb:
    return Jsonb(value, dumps=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))


def _payload_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _aggregation_source_refs(payload: dict[str, Any]) -> list[str]:
    values = payload.get(_AGGREGATION_SOURCE_REFS_KEY)
    if not isinstance(values, list):
        return []
    refs: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in refs:
            refs.append(item)
    return refs


def _aggregation_source_ref(source_table: str, source_id: str, event_id: str | None) -> str | None:
    source = str(source_id or event_id or "").strip()
    table = str(source_table or "").strip()
    if not source:
        return None
    return f"{table}:{source}" if table else source


def _external_push_upgrade(existing_payload: dict[str, Any], incoming_payload: dict[str, Any]) -> bool:
    return (
        existing_payload.get("external_push_eligible") is not True
        and incoming_payload.get("external_push_eligible") is True
    )


def _append_unique(values: list[str], value: str | None) -> list[str]:
    result = list(values)
    if value and value not in result:
        result.append(value)
    return result


def _connection_transaction(conn: Any, *, error_code: str) -> AbstractContextManager[Any]:
    try:
        conn_transaction = conn.transaction
    except AttributeError as exc:
        raise RuntimeError(error_code) from exc
    if not callable(conn_transaction):
        raise RuntimeError(error_code)
    return cast(AbstractContextManager[Any], conn_transaction())


def _notification_repository_transaction(conn: Any) -> AbstractContextManager[Any]:
    return _connection_transaction(conn, error_code="notification_repository_transaction_required")


def _delivery_repository_transaction(conn: Any) -> AbstractContextManager[Any]:
    return _connection_transaction(conn, error_code="notification_delivery_repository_transaction_required")


def _run_repository_write[T](conn: Any, commit: bool, write: Callable[[], T]) -> T:
    if commit:
        with _notification_repository_transaction(conn):
            return write()
    return write()


def _run_delivery_write[T](conn: Any, commit: bool, write: Callable[[], T]) -> T:
    if commit:
        with _delivery_repository_transaction(conn):
            return write()
    return write()


def _write_count(cursor: Any, *, required_error: str, invalid_error: str) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError(required_error) from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int):
        raise TypeError(invalid_error)
    if rowcount < 0:
        raise TypeError(invalid_error)
    return rowcount


def _single_row_write_count(cursor: Any, *, required_error: str, invalid_error: str) -> int:
    rowcount = _write_count(cursor, required_error=required_error, invalid_error=invalid_error)
    if rowcount not in (0, 1):
        raise TypeError(invalid_error)
    return rowcount


def _bounded_write_count(cursor: Any, *, limit: int, required_error: str, invalid_error: str) -> int:
    rowcount = _write_count(cursor, required_error=required_error, invalid_error=invalid_error)
    if rowcount > limit:
        raise TypeError(invalid_error)
    return rowcount


def _returned_write_count(
    cursor: Any,
    rows: Sequence[Any],
    *,
    required_error: str,
    invalid_error: str,
) -> int:
    rowcount = _write_count(cursor, required_error=required_error, invalid_error=invalid_error)
    if rowcount != len(rows):
        raise TypeError(invalid_error)
    return rowcount


def _optional_returning_row(
    cursor: Any,
    row: Any,
    *,
    required_error: str,
    invalid_error: str,
) -> dict[str, Any] | None:
    rowcount = _single_row_write_count(cursor, required_error=required_error, invalid_error=invalid_error)
    if rowcount == 0:
        if row is not None:
            raise TypeError(invalid_error)
        return None
    if row is None:
        raise TypeError(invalid_error)
    return dict(row)


def _delivery_attempt_contract(delivery: dict[str, Any]) -> tuple[int, int]:
    try:
        attempts = int(delivery["attempt_count"])
        max_attempts = int(delivery["max_attempts"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("notification_delivery_attempt_contract_required") from exc
    if attempts < 0 or max_attempts < 1:
        raise RuntimeError("notification_delivery_attempt_contract_required")
    return attempts, max_attempts


def _delivery_claim_contract(delivery: dict[str, Any]) -> tuple[str, int, int]:
    try:
        delivery_id = str(delivery["delivery_id"])
        attempts = int(delivery["attempt_count"])
        updated_at_ms = int(delivery["updated_at_ms"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("notification_delivery_claim_contract_required") from exc
    if not delivery_id or attempts < 1 or updated_at_ms <= 0:
        raise RuntimeError("notification_delivery_claim_contract_required")
    return delivery_id, attempts, updated_at_ms


def _required_positive_int(value: Any, *, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(error_code)
    if value <= 0:
        raise RuntimeError(error_code)
    return int(value)


def _required_nonnegative_int(value: Any, *, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(error_code)
    if value < 0:
        raise RuntimeError(error_code)
    return int(value)


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _normalize_severity(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in SEVERITY_RANK:
        raise ValueError("notification severity must be info, warning, high, or critical")
    return normalized


def _severity_from_rank(rank: int) -> str | None:
    if rank >= 3:
        return "critical"
    if rank == 2:
        return "high"
    if rank == 1:
        return "warning"
    if rank == 0:
        return "info"
    return None


def _normalize_handle(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lstrip("@").lower()
    return normalized or None


def _normalize_symbol(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lstrip("$").upper()
    return normalized or None


def _normalize_chain(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized or None


def _normalize_address(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _now_ms() -> int:
    return int(time.time() * 1000)
