from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SignalAlert:
    alert_type: str
    event_id: str
    author_handle: str
    entity_key: str | None
    normalized_value: str
    received_at_ms: int
    is_first_seen_global: bool
    is_first_seen_by_author: bool


class SignalRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def insert_account_token_alert(
        self,
        *,
        event_id: str,
        author_handle: str,
        entity_key: str,
        entity_type: str,
        normalized_value: str,
        chain: str | None,
        token_resolution_status: str,
        is_first_seen_global: bool,
        is_first_seen_by_author: bool,
        received_at_ms: int,
        commit: bool = True,
    ) -> SignalAlert | None:
        now_ms = _now_ms()
        alert_id = _id("account_token", event_id, entity_key)
        cursor = self.conn.execute(
            """
            INSERT INTO account_token_alerts(
              alert_id, event_id, author_handle, entity_key, entity_type, normalized_value, chain,
              token_resolution_status, is_first_seen_global, is_first_seen_by_author, received_at_ms, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(alert_id) DO NOTHING
            """,
            (
                alert_id,
                event_id,
                author_handle,
                entity_key,
                entity_type,
                normalized_value,
                chain,
                token_resolution_status,
                is_first_seen_global,
                is_first_seen_by_author,
                received_at_ms,
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()
        if cursor.rowcount == 0:
            return None
        return SignalAlert(
            alert_type="account_token",
            event_id=event_id,
            author_handle=author_handle,
            entity_key=entity_key,
            normalized_value=normalized_value,
            received_at_ms=received_at_ms,
            is_first_seen_global=is_first_seen_global,
            is_first_seen_by_author=is_first_seen_by_author,
        )

    def account_alerts(
        self,
        *,
        window_ms: int,
        now_ms: int | None = None,
        limit: int,
        handles: set[str] | None = None,
        alert_type: str | None = None,
    ) -> list[dict[str, Any]]:
        now = now_ms if now_ms is not None else _now_ms()
        since = now - window_ms
        rows: list[dict[str, Any]] = []
        if alert_type in {None, "account_token", "token"}:
            rows.extend(self._account_token_alerts(since_ms=since, limit=limit, handles=handles))
        rows.sort(key=lambda item: int(item.get("received_at_ms") or 0), reverse=True)
        return rows[: max(0, int(limit))]

    def alerts_for_event(self, event_id: str) -> list[dict[str, Any]]:
        token_rows = self.conn.execute(
            "SELECT 'account_token' AS alert_type, * FROM account_token_alerts WHERE event_id = %s",
            (event_id,),
        ).fetchall()
        rows = [dict(row) for row in token_rows]
        rows.sort(key=lambda item: (item["alert_type"], item["normalized_value"]))
        return rows

    def _account_token_alerts(self, *, since_ms: int, limit: int, handles: set[str] | None) -> list[dict[str, Any]]:
        clauses = ["received_at_ms >= %s"]
        params: list[Any] = [since_ms]
        if handles:
            normalized = sorted(handle.strip().lstrip("@").lower() for handle in handles if handle.strip())
            if normalized:
                placeholders = ",".join("%s" for _ in normalized)
                clauses.append(f"author_handle IN ({placeholders})")
                params.extend(normalized)
        rows = self.conn.execute(
            f"""
            SELECT 'account_token' AS alert_type, * FROM account_token_alerts
            WHERE {" AND ".join(clauses)}
            ORDER BY received_at_ms DESC
            LIMIT %s
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)
