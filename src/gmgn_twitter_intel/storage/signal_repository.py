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

    def token_seen_before(self, *, identity_key: str, author_handle: str | None, before_ms: int) -> tuple[bool, bool]:
        rows = self.conn.execute(
            """
            SELECT top_authors_json FROM token_windows
            WHERE identity_key = ? AND window = '1m' AND window_start_ms <= ?
            """,
            (identity_key, (before_ms // 60_000) * 60_000),
        ).fetchall()
        global_seen = bool(rows)
        author_seen = False
        if author_handle:
            for row in rows:
                authors = _json_loads(row["top_authors_json"], [])
                if any(item.get("handle") == author_handle for item in authors if isinstance(item, dict)):
                    author_seen = True
                    break
        return global_seen, author_seen

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

    def insert_event_token_mentions(
        self,
        *,
        event_id: str,
        token_mentions: list[Any],
        received_at_ms: int,
        author_handle: str | None,
        author_followers: int | None,
        is_watched: bool,
        commit: bool = True,
    ) -> int:
        now_ms = _now_ms()
        inserted = 0
        for mention in token_mentions:
            try:
                self.conn.execute(
                    """
                    INSERT INTO event_token_mentions(
                      mention_id, event_id, identity_key, token_id, identity_status, chain, address, symbol,
                      source, received_at_ms, author_handle, author_followers, is_watched, created_at_ms
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _id("event_token_mention", event_id, mention.identity_key),
                        event_id,
                        mention.identity_key,
                        mention.token_id,
                        mention.identity_status,
                        mention.chain,
                        mention.address,
                        mention.symbol,
                        mention.source,
                        received_at_ms,
                        author_handle,
                        author_followers,
                        1 if is_watched else 0,
                        now_ms,
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                continue
        if commit:
            self.conn.commit()
        return inserted

    def upsert_token_window(
        self,
        *,
        identity_key: str,
        token_id: str | None,
        identity_status: str,
        chain: str | None,
        address: str | None,
        symbol: str,
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
                "identity_key": identity_key,
                "token_id": token_id,
                "identity_status": identity_status,
                "chain": chain,
                "address": address,
                "symbol": symbol,
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

    def token_flow(self, *, window: str, limit: int, watched_only: bool = False) -> list[dict[str, Any]]:
        watched_clause = "AND tw.watched_mention_count > 0" if watched_only else ""
        rows = self.conn.execute(
            f"""
            SELECT
              tw.window_id,
              tw.identity_key,
              tw.token_id,
              tw.identity_status,
              tw.chain,
              tw.address,
              tw.symbol,
              tw.window,
              tw.window_start_ms,
              tw.window_end_ms,
              tw.mention_count,
              tw.watched_mention_count,
              tw.unique_author_count,
              tw.weighted_reach,
              CASE
                WHEN totals.total_mentions > 0
                THEN CAST(tw.mention_count AS REAL) / totals.total_mentions
                ELSE 0.0
              END AS market_mindshare,
              CASE
                WHEN totals.total_watched_mentions > 0
                THEN CAST(tw.watched_mention_count AS REAL) / totals.total_watched_mentions
                ELSE 0.0
              END AS watched_mindshare,
              tw.velocity,
              tw.top_authors_json,
              tw.top_events_json,
              tw.created_at_ms,
              tw.updated_at_ms
            FROM token_windows tw
            JOIN (
              SELECT
                window,
                window_start_ms,
                SUM(mention_count) AS total_mentions,
                SUM(watched_mention_count) AS total_watched_mentions
              FROM token_windows
              WHERE window = ?
              GROUP BY window, window_start_ms
            ) totals
              ON totals.window = tw.window
             AND totals.window_start_ms = tw.window_start_ms
            WHERE tw.window = ?
              {watched_clause}
            ORDER BY watched_mention_count DESC, velocity DESC, mention_count DESC, window_end_ms DESC
            LIMIT ?
            """,
            (window, window, max(0, int(limit))),
        ).fetchall()
        return self._hydrate_token_flow_evidence([_decode_json_fields(dict(row)) for row in rows])

    def token_window_history(
        self,
        *,
        identity_key: str,
        window: str,
        before_start_ms: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM token_windows
            WHERE identity_key = ? AND window = ? AND window_start_ms < ?
            ORDER BY window_start_ms DESC
            LIMIT ?
            """,
            (identity_key, window, before_start_ms, max(0, int(limit))),
        ).fetchall()
        return [_decode_json_fields(dict(row)) for row in rows]

    def token_mentions_by_ca(
        self,
        *,
        chain: str,
        address: str,
        limit: int,
        watched_only: bool = False,
    ) -> list[dict[str, Any]]:
        clauses = ["etm.chain = ?", "etm.address = ?"]
        params: list[Any] = [chain, address]
        if watched_only:
            clauses.append("etm.is_watched = 1")
        rows = self.conn.execute(
            f"""
            SELECT etm.*
            FROM event_token_mentions etm
            WHERE {" AND ".join(clauses)}
            ORDER BY etm.received_at_ms DESC
            LIMIT ?
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def token_mentions_by_symbol(
        self,
        *,
        symbol: str,
        limit: int,
        watched_only: bool = False,
    ) -> list[dict[str, Any]]:
        clauses = ["etm.symbol = ?"]
        params: list[Any] = [symbol.strip().lstrip("$").upper()]
        if watched_only:
            clauses.append("etm.is_watched = 1")
        rows = self.conn.execute(
            f"""
            SELECT etm.*
            FROM event_token_mentions etm
            WHERE {" AND ".join(clauses)}
            ORDER BY etm.received_at_ms DESC
            LIMIT ?
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def alerts_for_event(self, event_id: str) -> list[dict[str, Any]]:
        token_rows = self.conn.execute(
            "SELECT 'account_token' AS alert_type, * FROM account_token_alerts WHERE event_id = ?",
            (event_id,),
        ).fetchall()
        rows = [dict(row) for row in token_rows]
        rows.sort(key=lambda item: (item["alert_type"], item["normalized_value"]))
        return rows

    def rebuild_windows(self, *, window: str) -> int:
        size_ms = WINDOW_MS[window]
        with transaction(self.conn):
            self.conn.execute("DELETE FROM token_windows WHERE window = ?", (window,))
            rows = self.conn.execute(
                """
                SELECT * FROM event_token_mentions
                ORDER BY received_at_ms ASC, event_id ASC, identity_key ASC
                """
            ).fetchall()
            for row in rows:
                start_ms = (int(row["received_at_ms"]) // size_ms) * size_ms
                self.upsert_token_window(
                    identity_key=str(row["identity_key"]),
                    token_id=row["token_id"],
                    identity_status=str(row["identity_status"]),
                    chain=row["chain"],
                    address=row["address"],
                    symbol=str(row["symbol"]),
                    window=window,
                    window_start_ms=start_ms,
                    window_end_ms=start_ms + size_ms,
                    event_id=str(row["event_id"]),
                    author_handle=row["author_handle"],
                    author_followers=row["author_followers"],
                    is_watched=bool(row["is_watched"]),
                    commit=False,
                )
        return len(rows)

    def _hydrate_token_flow_evidence(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        event_ids = [
            str(item["event_id"])
            for row in rows
            for item in row.get("top_events", [])
            if isinstance(item, dict) and item.get("event_id")
        ]
        if not event_ids:
            return rows
        placeholders = ",".join("?" for _ in event_ids)
        event_rows = self.conn.execute(
            f"""
            SELECT event_id, author_handle, received_at_ms, text_clean, canonical_url
            FROM events
            WHERE event_id IN ({placeholders})
            """,
            event_ids,
        ).fetchall()
        by_event_id = {str(row["event_id"]): dict(row) for row in event_rows}
        for row in rows:
            hydrated = []
            for item in row.get("top_events", []):
                if not isinstance(item, dict):
                    continue
                event = by_event_id.get(str(item.get("event_id")))
                hydrated.append(item | event if event else item)
            row["top_events"] = hydrated
        return rows

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
            where = "identity_key = ? AND window = ? AND window_start_ms = ?"
            params = (identity["identity_key"], window, window_start_ms)
        else:
            raise ValueError(f"unsupported window table: {table}")
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
            row["window_id"] = _id("token_window", row["identity_key"], row["window"], str(row["window_start_ms"]))
            self.conn.execute(
                """
                INSERT INTO token_windows(
                  window_id, identity_key, token_id, identity_status, chain, address, symbol, window, window_start_ms,
                  window_end_ms, mention_count, watched_mention_count, unique_author_count, weighted_reach,
                  market_mindshare, watched_mindshare, velocity, top_authors_json, top_events_json,
                  created_at_ms, updated_at_ms
                )
                VALUES (
                  :window_id, :identity_key, :token_id, :identity_status, :chain, :address,
                  :symbol, :window, :window_start_ms,
                  :window_end_ms, :mention_count, :watched_mention_count, :unique_author_count, :weighted_reach,
                  :market_mindshare, :watched_mindshare, :velocity, :top_authors_json, :top_events_json,
                  :created_at_ms, :updated_at_ms
                )
                """,
                row,
            )
            self._refresh_token_bucket_mindshare(window=str(row["window"]), window_start_ms=int(row["window_start_ms"]))
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
        if table == "token_windows":
            self._refresh_token_bucket_mindshare(window=str(row["window"]), window_start_ms=int(row["window_start_ms"]))
        if commit:
            self.conn.commit()

    def _refresh_token_bucket_mindshare(self, *, window: str, window_start_ms: int) -> None:
        totals = self.conn.execute(
            """
            SELECT
              SUM(mention_count) AS total_mentions,
              SUM(watched_mention_count) AS total_watched_mentions
            FROM token_windows
            WHERE window = ? AND window_start_ms = ?
            """,
            (window, window_start_ms),
        ).fetchone()
        total_mentions = int(totals["total_mentions"] or 0)
        total_watched_mentions = int(totals["total_watched_mentions"] or 0)
        self.conn.execute(
            """
            UPDATE token_windows
            SET
              market_mindshare = CASE
                WHEN ? > 0 THEN CAST(mention_count AS REAL) / ?
                ELSE 0.0
              END,
              watched_mindshare = CASE
                WHEN ? > 0 THEN CAST(watched_mention_count AS REAL) / ?
                ELSE 0.0
              END
            WHERE window = ? AND window_start_ms = ?
            """,
            (
                total_mentions,
                total_mentions,
                total_watched_mentions,
                total_watched_mentions,
                window,
                window_start_ms,
            ),
        )

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
