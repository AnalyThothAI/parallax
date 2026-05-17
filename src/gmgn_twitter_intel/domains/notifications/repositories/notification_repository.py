from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.platform.db.postgres_client import transaction

SEVERITY_RANK = {"info": 0, "warning": 1, "high": 2, "critical": 3}
_AGGREGATION_SOURCE_REFS_KEY = "_aggregation_source_refs"
_SIGNAL_PULSE_RULE_ID = "signal_pulse_candidate"


class NotificationRepository:
    def __init__(self, conn: Any, *, running_timeout_ms: int = 300_000):
        self.conn = conn
        self.running_timeout_ms = int(running_timeout_ms)

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
        now_ms = _now_ms()
        notification_id = _id("notification", dedup_key)
        normalized_severity = _normalize_severity(severity)
        normalized_channels = tuple(str(channel).strip() for channel in channels if str(channel).strip()) or ("in_app",)
        normalized_payload = dict(payload or {})
        semantic_duplicate = self._pulse_signature_duplicate(
            rule_id=rule_id,
            payload=normalized_payload,
        )
        if semantic_duplicate is not None:
            self._aggregate_notification_row(
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
            if commit:
                self.conn.commit()
            return None
        if self._pulse_external_cooldown_duplicate(rule_id=rule_id, payload=normalized_payload):
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
        if cursor.rowcount == 0:
            existing = self.conn.execute(
                "SELECT * FROM notifications WHERE dedup_key = %s FOR UPDATE",
                (dedup_key,),
            ).fetchone()
            self._aggregate_notification_row(
                existing=dict(existing) if existing is not None else None,
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
            if commit:
                self.conn.commit()
            return None
        if commit:
            self.conn.commit()
        return self.notification_by_id(notification_id, subscriber_key=None)

    def _pulse_signature_duplicate(
        self,
        *,
        rule_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        if rule_id != _SIGNAL_PULSE_RULE_ID:
            return None
        in_app_signature = str(payload.get("in_app_signature") or payload.get("notification_signature") or "").strip()
        if not in_app_signature:
            return None
        external_push_signature = str(payload.get("external_push_signature") or "").strip() or "in_app"
        row = self.conn.execute(
            """
            SELECT *
            FROM notifications
            WHERE rule_id = %s
              AND COALESCE(payload_json->>'in_app_signature', payload_json->>'notification_signature') = %s
              AND COALESCE(payload_json->>'external_push_signature', 'in_app') = %s
            ORDER BY last_seen_at_ms DESC, created_at_ms DESC
            LIMIT 1
            FOR UPDATE
            """,
            (rule_id, in_app_signature, external_push_signature),
        ).fetchone()
        return dict(row) if row is not None else None

    def _pulse_external_cooldown_duplicate(
        self,
        *,
        rule_id: str,
        payload: dict[str, Any],
    ) -> bool:
        if rule_id != _SIGNAL_PULSE_RULE_ID:
            return False
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
    ) -> None:
        if existing is None:
            return
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
        if incoming_ref and incoming_ref in existing_refs:
            return
        merged_refs = _append_unique(existing_refs, incoming_ref)
        next_payload = dict(payload)
        if merged_refs:
            next_payload[_AGGREGATION_SOURCE_REFS_KEY] = merged_refs[-100:]
        self.conn.execute(
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
                occurrence_count = occurrence_count + 1,
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
                int(occurrence_at_ms),
                _json(next_payload),
                _json(channels),
                now_ms,
                existing["notification_id"],
            ),
        )

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
        rows = self.conn.execute(
            f"""
            SELECT n.notification_id, n.severity, n.author_handle
            FROM notifications n
            LEFT JOIN notification_reads r
              ON r.notification_id = n.notification_id
             AND r.subscriber_key = %s
            WHERE {where}
            """,
            params,
        ).fetchall()
        account_counts: dict[str, int] = {}
        highest: str | None = None
        high_count = 0
        critical_count = 0
        for row in rows:
            severity = str(row["severity"])
            if severity == "high":
                high_count += 1
            if severity == "critical":
                critical_count += 1
            if highest is None or SEVERITY_RANK[severity] > SEVERITY_RANK[highest]:
                highest = severity
            handle = row["author_handle"]
            if handle:
                account_counts[str(handle)] = account_counts.get(str(handle), 0) + 1
        return {
            "subscriber_key": subscriber_key,
            "unread_count": len(rows),
            "high_unread_count": high_count,
            "critical_unread_count": critical_count,
            "highest_unread_severity": highest,
            "account_unread_counts": dict(sorted(account_counts.items())),
        }

    def mark_read(self, *, notification_id: str, subscriber_key: str = "local", read_at_ms: int | None = None) -> bool:
        row = self.conn.execute(
            "SELECT notification_id FROM notifications WHERE notification_id = %s",
            (notification_id,),
        ).fetchone()
        if row is None:
            return False
        self.conn.execute(
            """
            INSERT INTO notification_reads(notification_id, subscriber_key, read_at_ms)
            VALUES (%s, %s, %s)
            ON CONFLICT(notification_id, subscriber_key) DO UPDATE SET
              read_at_ms = excluded.read_at_ms
            """,
            (notification_id, subscriber_key, int(read_at_ms if read_at_ms is not None else _now_ms())),
        )
        self.conn.commit()
        return True

    def mark_all_read(self, *, subscriber_key: str = "local", read_at_ms: int | None = None) -> int:
        now_ms = int(read_at_ms if read_at_ms is not None else _now_ms())
        rows = self.conn.execute(
            """
            SELECT n.notification_id
            FROM notifications n
            LEFT JOIN notification_reads r
              ON r.notification_id = n.notification_id
             AND r.subscriber_key = %s
            WHERE r.read_at_ms IS NULL
            """,
            (subscriber_key,),
        ).fetchall()
        with transaction(self.conn):
            for row in rows:
                self.conn.execute(
                    """
                    INSERT INTO notification_reads(notification_id, subscriber_key, read_at_ms)
                    VALUES (%s, %s, %s)
                    ON CONFLICT(notification_id, subscriber_key) DO UPDATE SET
                      read_at_ms = excluded.read_at_ms
                    """,
                    (row["notification_id"], subscriber_key, now_ms),
                )
        return len(rows)

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
                max(1, int(max_attempts)),
                int(next_run_at_ms if next_run_at_ms is not None else now_ms),
                None,
                None,
                None,
                now_ms,
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()
        if cursor.rowcount == 0:
            return None
        return self.delivery_by_id(delivery_id)

    def delivery_by_id(self, delivery_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM notification_deliveries WHERE delivery_id = %s",
            (delivery_id,),
        ).fetchone()
        return dict(row) if row else None

    def claim_next_delivery(self, *, now_ms: int | None = None) -> dict[str, Any] | None:
        now = int(now_ms if now_ms is not None else _now_ms())
        stale_before = now - self.running_timeout_ms
        self.conn.execute(
            """
            UPDATE notification_deliveries
            SET status = 'dead',
                last_error = 'stale_running_timeout',
                updated_at_ms = %s
            WHERE status = 'running'
              AND updated_at_ms < %s
              AND attempt_count >= max_attempts
            """,
            (now, stale_before),
        )
        row = self.conn.execute(
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
        ).fetchone()
        return dict(row) if row else None

    def complete_delivery(self, delivery: dict[str, Any], *, delivered_at_ms: int | None = None) -> None:
        now = int(delivered_at_ms if delivered_at_ms is not None else _now_ms())
        self.conn.execute(
            """
            UPDATE notification_deliveries
            SET status = 'delivered',
                delivered_at_ms = %s,
                last_error = NULL,
                updated_at_ms = %s
            WHERE delivery_id = %s
            """,
            (now, now, delivery["delivery_id"]),
        )
        self.conn.commit()

    def fail_delivery(self, delivery: dict[str, Any], *, error: str, now_ms: int | None = None) -> None:
        now = int(now_ms if now_ms is not None else _now_ms())
        attempts = int(delivery.get("attempt_count") or 0)
        max_attempts = int(delivery.get("max_attempts") or 5)
        status = "dead" if attempts >= max_attempts else "failed"
        delay_ms = min(15 * 60_000, 30_000 * max(1, attempts))
        self.conn.execute(
            """
            UPDATE notification_deliveries
            SET status = %s,
                next_run_at_ms = %s,
                last_error = %s,
                updated_at_ms = %s
            WHERE delivery_id = %s
            """,
            (status, now + delay_ms, str(error)[:1000], now, delivery["delivery_id"]),
        )
        self.conn.commit()

    def list_deliveries(self, *, limit: int, status: str | None = None) -> list[dict[str, Any]]:
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
            (*params, max(0, int(limit))),
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
            (*query_params, max(0, int(limit))),
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


def _append_unique(values: list[str], value: str | None) -> list[str]:
    result = list(values)
    if value and value not in result:
        result.append(value)
    return result


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _normalize_severity(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in SEVERITY_RANK:
        raise ValueError("notification severity must be info, warning, high, or critical")
    return normalized


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
