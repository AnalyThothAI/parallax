from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from .sqlite_client import transaction

WINDOW_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "1h": 3_600_000,
    "24h": 86_400_000,
}


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
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def token_seen_before(self, *, entity_key: str, author_handle: str | None, before_ms: int) -> tuple[bool, bool]:
        global_count = self.conn.execute(
            """
            SELECT COUNT(*) FROM event_entities
            WHERE received_at_ms < ? AND entity_type IN ('ca', 'symbol')
              AND (
                CASE
                  WHEN chain IS NULL THEN entity_type || ':' || normalized_value
                  ELSE entity_type || ':' || chain || ':' || normalized_value
                END
              ) = ?
            """,
            (before_ms, entity_key),
        ).fetchone()[0]
        author_count = 0
        if author_handle:
            author_count = self.conn.execute(
                """
                SELECT COUNT(*) FROM event_entities
                WHERE received_at_ms < ? AND author_handle = ? AND entity_type IN ('ca', 'symbol')
                  AND (
                    CASE
                      WHEN chain IS NULL THEN entity_type || ':' || normalized_value
                      ELSE entity_type || ':' || chain || ':' || normalized_value
                    END
                  ) = ?
                """,
                (before_ms, author_handle, entity_key),
            ).fetchone()[0]
        return bool(global_count), bool(author_count)

    def keyword_seen_before(self, *, keyword: str, author_handle: str | None, before_ms: int) -> tuple[bool, bool]:
        global_count = self.conn.execute(
            """
            SELECT COUNT(*) FROM event_entities
            WHERE received_at_ms < ? AND entity_type = 'keyword' AND normalized_value = ?
            """,
            (before_ms, keyword),
        ).fetchone()[0]
        author_count = 0
        if author_handle:
            author_count = self.conn.execute(
                """
                SELECT COUNT(*) FROM event_entities
                WHERE received_at_ms < ? AND author_handle = ? AND entity_type = 'keyword' AND normalized_value = ?
                """,
                (before_ms, author_handle, keyword),
            ).fetchone()[0]
        return bool(global_count), bool(author_count)

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
        try:
            self.conn.execute(
                """
                INSERT INTO account_token_alerts(
                  alert_id, event_id, author_handle, entity_key, entity_type, normalized_value, chain,
                  token_resolution_status, is_first_seen_global, is_first_seen_by_author, received_at_ms, created_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    1 if is_first_seen_global else 0,
                    1 if is_first_seen_by_author else 0,
                    received_at_ms,
                    now_ms,
                ),
            )
            if commit:
                self.conn.commit()
        except sqlite3.IntegrityError:
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

    def insert_account_keyword_alert(
        self,
        *,
        event_id: str,
        author_handle: str,
        keyword: str,
        is_first_seen_global: bool,
        is_first_seen_by_author: bool,
        received_at_ms: int,
        commit: bool = True,
    ) -> SignalAlert | None:
        now_ms = _now_ms()
        alert_id = _id("account_keyword", event_id, keyword)
        try:
            self.conn.execute(
                """
                INSERT INTO account_keyword_alerts(
                  alert_id, event_id, author_handle, keyword, is_first_seen_global,
                  is_first_seen_by_author, received_at_ms, created_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert_id,
                    event_id,
                    author_handle,
                    keyword,
                    1 if is_first_seen_global else 0,
                    1 if is_first_seen_by_author else 0,
                    received_at_ms,
                    now_ms,
                ),
            )
            if commit:
                self.conn.commit()
        except sqlite3.IntegrityError:
            return None
        return SignalAlert(
            alert_type="account_keyword",
            event_id=event_id,
            author_handle=author_handle,
            entity_key=None,
            normalized_value=keyword,
            received_at_ms=received_at_ms,
            is_first_seen_global=is_first_seen_global,
            is_first_seen_by_author=is_first_seen_by_author,
        )

    def upsert_token_window(
        self,
        *,
        entity_key: str,
        entity_type: str,
        normalized_value: str,
        chain: str | None,
        window: str,
        window_start_ms: int,
        window_end_ms: int,
        event_id: str,
        author_handle: str | None,
        author_followers: int | None,
        is_watched: bool,
        commit: bool = True,
    ) -> None:
        self._upsert_window(
            table="token_windows",
            identity={
                "entity_key": entity_key,
                "entity_type": entity_type,
                "normalized_value": normalized_value,
                "chain": chain,
            },
            window=window,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            event_id=event_id,
            author_handle=author_handle,
            author_followers=author_followers,
            is_watched=is_watched,
            commit=commit,
        )

    def upsert_keyword_window(
        self,
        *,
        keyword: str,
        window: str,
        window_start_ms: int,
        window_end_ms: int,
        event_id: str,
        author_handle: str | None,
        author_followers: int | None,
        is_watched: bool,
        commit: bool = True,
    ) -> None:
        self._upsert_window(
            table="keyword_windows",
            identity={"keyword": keyword},
            window=window,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            event_id=event_id,
            author_handle=author_handle,
            author_followers=author_followers,
            is_watched=is_watched,
            commit=commit,
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
        if alert_type in {None, "account_keyword", "keyword"}:
            rows.extend(self._account_keyword_alerts(since_ms=since, limit=limit, handles=handles))
        rows.sort(key=lambda item: int(item.get("received_at_ms") or 0), reverse=True)
        return rows[: max(0, int(limit))]

    def token_flow(self, *, window: str, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM token_windows
            WHERE window = ?
            ORDER BY watched_mention_count DESC, velocity DESC, mention_count DESC, window_end_ms DESC
            LIMIT ?
            """,
            (window, max(0, int(limit))),
        ).fetchall()
        return [_decode_json_fields(dict(row)) for row in rows]

    def alerts_for_event(self, event_id: str) -> list[dict[str, Any]]:
        token_rows = self.conn.execute(
            "SELECT 'account_token' AS alert_type, * FROM account_token_alerts WHERE event_id = ?",
            (event_id,),
        ).fetchall()
        keyword_rows = self.conn.execute(
            """
            SELECT 'account_keyword' AS alert_type, alert_id, event_id, author_handle,
                   NULL AS entity_key, keyword AS normalized_value, is_first_seen_global,
                   is_first_seen_by_author, received_at_ms, created_at_ms
            FROM account_keyword_alerts
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchall()
        rows = [dict(row) for row in token_rows] + [dict(row) for row in keyword_rows]
        rows.sort(key=lambda item: (item["alert_type"], item["normalized_value"]))
        return rows

    def keyword_flow(self, *, window: str, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM keyword_windows
            WHERE window = ?
            ORDER BY watched_mention_count DESC, velocity DESC, mention_count DESC, window_end_ms DESC
            LIMIT ?
            """,
            (window, max(0, int(limit))),
        ).fetchall()
        return [_decode_json_fields(dict(row)) for row in rows]

    def rebuild_windows(self, *, window: str) -> int:
        size_ms = WINDOW_MS[window]
        rebuilt = 0
        with transaction(self.conn):
            self.conn.execute("DELETE FROM token_windows WHERE window = ?", (window,))
            self.conn.execute("DELETE FROM keyword_windows WHERE window = ?", (window,))
            rows = self.conn.execute(
                """
                SELECT
                  ee.entity_type,
                  ee.normalized_value,
                  ee.chain,
                  ee.received_at_ms,
                  ee.event_id,
                  ee.author_handle,
                  ee.is_watched,
                  e.author_followers
                FROM event_entities ee
                JOIN events e ON e.event_id = ee.event_id
                WHERE ee.entity_type IN ('ca', 'symbol', 'keyword')
                ORDER BY ee.received_at_ms ASC
                """
            ).fetchall()
            for row in rows:
                start_ms = (int(row["received_at_ms"]) // size_ms) * size_ms
                if row["entity_type"] == "keyword":
                    self.upsert_keyword_window(
                        keyword=str(row["normalized_value"]),
                        window=window,
                        window_start_ms=start_ms,
                        window_end_ms=start_ms + size_ms,
                        event_id=str(row["event_id"]),
                        author_handle=row["author_handle"],
                        author_followers=row["author_followers"],
                        is_watched=bool(row["is_watched"]),
                        commit=False,
                    )
                else:
                    key = _entity_key(
                        entity_type=str(row["entity_type"]),
                        chain=row["chain"],
                        normalized_value=str(row["normalized_value"]),
                    )
                    self.upsert_token_window(
                        entity_key=key,
                        entity_type=str(row["entity_type"]),
                        normalized_value=str(row["normalized_value"]),
                        chain=row["chain"],
                        window=window,
                        window_start_ms=start_ms,
                        window_end_ms=start_ms + size_ms,
                        event_id=str(row["event_id"]),
                        author_handle=row["author_handle"],
                        author_followers=row["author_followers"],
                        is_watched=bool(row["is_watched"]),
                        commit=False,
                    )
                rebuilt += 1
        return rebuilt

    def _upsert_window(
        self,
        *,
        table: str,
        identity: dict[str, Any],
        window: str,
        window_start_ms: int,
        window_end_ms: int,
        event_id: str,
        author_handle: str | None,
        author_followers: int | None,
        is_watched: bool,
        commit: bool,
    ) -> None:
        now_ms = _now_ms()
        if table == "token_windows":
            where = "entity_key = ? AND window = ? AND window_start_ms = ?"
            params = (identity["entity_key"], window, window_start_ms)
        else:
            where = "keyword = ? AND window = ? AND window_start_ms = ?"
            params = (identity["keyword"], window, window_start_ms)
        existing = self.conn.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchone()
        if existing is None:
            row = {
                **identity,
                "window": window,
                "window_start_ms": window_start_ms,
                "window_end_ms": window_end_ms,
                "mention_count": 0,
                "watched_mention_count": 0,
                "unique_author_count": 0,
                "weighted_reach": 0.0,
                "market_mindshare": 0.0,
                "watched_mindshare": 0.0,
                "velocity": 0.0,
                "top_authors_json": "[]",
                "top_events_json": "[]",
                "created_at_ms": now_ms,
                "updated_at_ms": now_ms,
            }
            self._insert_window_row(table, row, event_id, author_handle, author_followers, is_watched, commit)
            return

        row = dict(existing)
        self._update_window_row(table, row, event_id, author_handle, author_followers, is_watched, commit)

    def _insert_window_row(
        self,
        table: str,
        row: dict[str, Any],
        event_id: str,
        author_handle: str | None,
        author_followers: int | None,
        is_watched: bool,
        commit: bool,
    ) -> None:
        _apply_window_increment(row, event_id, author_handle, author_followers, is_watched)
        if table == "token_windows":
            row["window_id"] = _id("token_window", row["entity_key"], row["window"], str(row["window_start_ms"]))
            self.conn.execute(
                """
                INSERT INTO token_windows(
                  window_id, entity_key, entity_type, normalized_value, chain, window, window_start_ms,
                  window_end_ms, mention_count, watched_mention_count, unique_author_count, weighted_reach,
                  market_mindshare, watched_mindshare, velocity, top_authors_json, top_events_json,
                  created_at_ms, updated_at_ms
                )
                VALUES (
                  :window_id, :entity_key, :entity_type, :normalized_value, :chain, :window, :window_start_ms,
                  :window_end_ms, :mention_count, :watched_mention_count, :unique_author_count, :weighted_reach,
                  :market_mindshare, :watched_mindshare, :velocity, :top_authors_json, :top_events_json,
                  :created_at_ms, :updated_at_ms
                )
                """,
                row,
            )
        else:
            row["window_id"] = _id("keyword_window", row["keyword"], row["window"], str(row["window_start_ms"]))
            self.conn.execute(
                """
                INSERT INTO keyword_windows(
                  window_id, keyword, window, window_start_ms, window_end_ms, mention_count,
                  watched_mention_count, unique_author_count, weighted_reach, market_mindshare,
                  watched_mindshare, velocity, top_authors_json, top_events_json, created_at_ms, updated_at_ms
                )
                VALUES (
                  :window_id, :keyword, :window, :window_start_ms, :window_end_ms, :mention_count,
                  :watched_mention_count, :unique_author_count, :weighted_reach, :market_mindshare,
                  :watched_mindshare, :velocity, :top_authors_json, :top_events_json, :created_at_ms, :updated_at_ms
                )
                """,
                row,
            )
        if commit:
            self.conn.commit()

    def _update_window_row(
        self,
        table: str,
        row: dict[str, Any],
        event_id: str,
        author_handle: str | None,
        author_followers: int | None,
        is_watched: bool,
        commit: bool,
    ) -> None:
        _apply_window_increment(row, event_id, author_handle, author_followers, is_watched)
        row["updated_at_ms"] = _now_ms()
        self.conn.execute(
            f"""
            UPDATE {table}
            SET mention_count = :mention_count,
                watched_mention_count = :watched_mention_count,
                unique_author_count = :unique_author_count,
                weighted_reach = :weighted_reach,
                market_mindshare = :market_mindshare,
                watched_mindshare = :watched_mindshare,
                velocity = :velocity,
                top_authors_json = :top_authors_json,
                top_events_json = :top_events_json,
                updated_at_ms = :updated_at_ms
            WHERE window_id = :window_id
            """,
            row,
        )
        if commit:
            self.conn.commit()

    def _account_token_alerts(self, *, since_ms: int, limit: int, handles: set[str] | None) -> list[dict[str, Any]]:
        clauses = ["received_at_ms >= ?"]
        params: list[Any] = [since_ms]
        if handles:
            normalized = sorted(handle.strip().lstrip("@").lower() for handle in handles if handle.strip())
            if normalized:
                placeholders = ",".join("?" for _ in normalized)
                clauses.append(f"author_handle IN ({placeholders})")
                params.extend(normalized)
        rows = self.conn.execute(
            f"""
            SELECT 'account_token' AS alert_type, * FROM account_token_alerts
            WHERE {" AND ".join(clauses)}
            ORDER BY received_at_ms DESC
            LIMIT ?
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def _account_keyword_alerts(self, *, since_ms: int, limit: int, handles: set[str] | None) -> list[dict[str, Any]]:
        clauses = ["received_at_ms >= ?"]
        params: list[Any] = [since_ms]
        if handles:
            normalized = sorted(handle.strip().lstrip("@").lower() for handle in handles if handle.strip())
            if normalized:
                placeholders = ",".join("?" for _ in normalized)
                clauses.append(f"author_handle IN ({placeholders})")
                params.extend(normalized)
        rows = self.conn.execute(
            f"""
            SELECT 'account_keyword' AS alert_type, alert_id, event_id, author_handle,
                   NULL AS entity_key, keyword AS normalized_value, is_first_seen_global,
                   is_first_seen_by_author, received_at_ms, created_at_ms
            FROM account_keyword_alerts
            WHERE {" AND ".join(clauses)}
            ORDER BY received_at_ms DESC
            LIMIT ?
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]


def _apply_window_increment(
    row: dict[str, Any],
    event_id: str,
    author_handle: str | None,
    author_followers: int | None,
    is_watched: bool,
) -> None:
    top_events = _json_loads(row.get("top_events_json"), [])
    if event_id in {item.get("event_id") for item in top_events if isinstance(item, dict)}:
        return
    top_events.append({"event_id": event_id})
    top_events = top_events[-20:]
    authors = _json_loads(row.get("top_authors_json"), [])
    author_map = {item.get("handle"): dict(item) for item in authors if isinstance(item, dict) and item.get("handle")}
    if author_handle:
        current = author_map.get(
            author_handle,
            {"handle": author_handle, "count": 0, "followers": author_followers or 0},
        )
        current["count"] = int(current.get("count") or 0) + 1
        current["followers"] = max(int(current.get("followers") or 0), int(author_followers or 0))
        author_map[author_handle] = current
    row["mention_count"] = int(row.get("mention_count") or 0) + 1
    row["watched_mention_count"] = int(row.get("watched_mention_count") or 0) + (1 if is_watched else 0)
    row["unique_author_count"] = len(author_map)
    row["weighted_reach"] = float(row.get("weighted_reach") or 0.0) + float(author_followers or 0)
    row["market_mindshare"] = float(row["mention_count"])
    row["watched_mindshare"] = float(row["watched_mention_count"])
    window_ms = max(1, int(row["window_end_ms"]) - int(row["window_start_ms"]))
    row["velocity"] = float(row["mention_count"]) / (window_ms / 60_000)
    sorted_authors = sorted(
        author_map.values(),
        key=lambda item: (item.get("count") or 0, item.get("followers") or 0),
        reverse=True,
    )
    row["top_authors_json"] = json.dumps(
        sorted_authors[:20],
        ensure_ascii=False,
        sort_keys=True,
    )
    row["top_events_json"] = json.dumps(top_events, ensure_ascii=False, sort_keys=True)


def _decode_json_fields(row: dict[str, Any]) -> dict[str, Any]:
    row["top_authors"] = _json_loads(row.pop("top_authors_json", None), [])
    row["top_events"] = _json_loads(row.pop("top_events_json", None), [])
    return row


def _json_loads(value: Any, default: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _entity_key(*, entity_type: str, chain: str | None, normalized_value: str) -> str:
    if chain:
        return f"{entity_type}:{chain}:{normalized_value}"
    return f"{entity_type}:{normalized_value}"


def _now_ms() -> int:
    return int(time.time() * 1000)
