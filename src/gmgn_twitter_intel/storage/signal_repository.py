from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from typing import Any

from ..pipeline.entity_extractor import EVM_QUERY_CHAINS


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
        global_seen = self.conn.execute(
            """
            SELECT 1 FROM event_token_mentions
            WHERE identity_key = ?
              AND received_at_ms < ?
            LIMIT 1
            """,
            (identity_key, before_ms),
        ).fetchone() is not None
        author_seen = False
        if author_handle:
            author_seen = (
                self.conn.execute(
                    """
                    SELECT 1 FROM event_token_mentions
                    WHERE identity_key = ?
                      AND author_handle = ?
                      AND received_at_ms < ?
                    LIMIT 1
                    """,
                    (identity_key, author_handle, before_ms),
                ).fetchone()
                is not None
            )
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

    def token_mentions_for_event(self, event_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM event_token_mentions
            WHERE event_id = ?
            ORDER BY received_at_ms, mention_id
            """,
            (event_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def symbol_mention_rows(self, *, symbol: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM event_token_mentions
            WHERE symbol = ?
              AND token_id IS NULL
              AND identity_key = ?
            ORDER BY received_at_ms, mention_id
            """,
            (_normalize_symbol(symbol), f"symbol:{_normalize_symbol(symbol)}"),
        ).fetchall()
        return [dict(row) for row in rows]

    def attribution_rebuild_rows(
        self,
        *,
        symbol: str | None = None,
        direct_only: bool = False,
        symbol_only: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if symbol:
            clauses.append("symbol = ?")
            params.append(_normalize_symbol(symbol))
        if direct_only:
            clauses.append("token_id IS NOT NULL")
        if symbol_only:
            clauses.append("token_id IS NULL")
            if symbol:
                clauses.append("identity_key = ?")
                params.append(f"symbol:{_normalize_symbol(symbol)}")
            else:
                clauses.append("identity_key LIKE 'symbol:%'")
        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT ?"
            params.append(max(0, int(limit)))
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM event_token_mentions
            {where_clause}
            ORDER BY received_at_ms, mention_id
            {limit_clause}
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def replace_token_attributions(
        self,
        *,
        mention_ids: list[str],
        attributions: list[Any],
        commit: bool = True,
    ) -> int:
        if not mention_ids:
            return 0
        placeholders = ",".join("?" for _ in mention_ids)
        self.conn.execute(
            f"DELETE FROM event_token_attributions WHERE mention_id IN ({placeholders})",
            mention_ids,
        )
        now_ms = _now_ms()
        inserted = 0
        for attribution in attributions:
            payload = _attribution_payload(attribution, now_ms=now_ms)
            self.conn.execute(
                """
                INSERT INTO event_token_attributions(
                  attribution_id, mention_id, event_id, mention_identity_key, identity_key, token_id,
                  identity_status, chain, address, symbol, source, attribution_status,
                  attribution_confidence, attribution_weight, attribution_rank, candidate_count,
                  score_features_json, reasons_json, risks_json, received_at_ms, author_handle,
                  author_followers, is_watched, created_at_ms
                )
                VALUES (
                  :attribution_id, :mention_id, :event_id, :mention_identity_key, :identity_key, :token_id,
                  :identity_status, :chain, :address, :symbol, :source, :attribution_status,
                  :attribution_confidence, :attribution_weight, :attribution_rank, :candidate_count,
                  :score_features_json, :reasons_json, :risks_json, :received_at_ms, :author_handle,
                  :author_followers, :is_watched, :created_at_ms
                )
                """,
                payload,
            )
            inserted += 1
        if commit:
            self.conn.commit()
        return inserted

    def token_attribution_bounds(self, *, identity_key: str) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT
              MIN(received_at_ms) AS first_seen_ms,
              MAX(received_at_ms) AS latest_seen_ms,
              MIN(CASE WHEN is_watched = 1 THEN received_at_ms END) AS first_watched_seen_ms
            FROM event_token_attributions
            WHERE identity_key = ?
              AND token_id IS NOT NULL
              AND attribution_status IN ('direct', 'selected')
              AND attribution_weight > 0
            """,
            (identity_key,),
        ).fetchone()
        return dict(row) if row else {"first_seen_ms": None, "latest_seen_ms": None, "first_watched_seen_ms": None}

    def direct_token_mention_count(
        self,
        *,
        token_id: str,
        since_ms: int,
        before_ms: int,
    ) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM event_token_attributions
            WHERE token_id = ?
              AND received_at_ms >= ?
              AND received_at_ms < ?
              AND attribution_status = 'direct'
            """,
            (token_id, since_ms, before_ms),
        ).fetchone()
        return int(row["count"] or 0) if row else 0

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

    def token_flow(
        self,
        *,
        window: str,
        limit: int,
        watched_only: bool = False,
        now_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        from ..retrieval.rolling_token_flow import RollingTokenFlow

        return RollingTokenFlow(self.conn).token_flow(
            window=window,
            limit=limit,
            watched_only=watched_only,
            now_ms=now_ms,
        )

    def token_mentions_by_ca(
        self,
        *,
        chain: str,
        address: str,
        limit: int,
        watched_only: bool = False,
    ) -> list[dict[str, Any]]:
        clauses = ["etm.address = ?"]
        params: list[Any] = [address]
        if chain == "evm_unknown":
            placeholders = ",".join("?" for _ in EVM_QUERY_CHAINS)
            clauses.append(f"etm.chain IN ({placeholders})")
            params.extend(sorted(EVM_QUERY_CHAINS))
        else:
            clauses.append("etm.chain = ?")
            params.append(chain)
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

    def token_attributions_for_event(self, event_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              attribution_id,
              event_id,
              mention_identity_key,
              identity_key,
              token_id,
              identity_status,
              chain,
              address,
              symbol,
              source,
              attribution_status,
              attribution_confidence,
              attribution_weight,
              attribution_rank,
              candidate_count,
              received_at_ms,
              author_handle,
              author_followers,
              is_watched
            FROM event_token_attributions
            WHERE event_id = ?
              AND attribution_status IN ('direct', 'selected')
              AND attribution_weight > 0
            ORDER BY attribution_weight DESC, attribution_confidence DESC, attribution_rank ASC
            """,
            (event_id,),
        ).fetchall()
        return [dict(row) for row in rows]

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

def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _normalize_symbol(symbol: str) -> str:
    text = symbol.strip().lstrip("$")
    return text.upper() if text.isascii() else text


def _attribution_payload(attribution: Any, *, now_ms: int) -> dict[str, Any]:
    if hasattr(attribution, "__dataclass_fields__"):
        data = asdict(attribution)
    elif hasattr(attribution, "__dict__"):
        data = dict(attribution.__dict__)
    else:
        data = dict(attribution)
    data["score_features_json"] = json.dumps(data.pop("score_features", {}), ensure_ascii=False, sort_keys=True)
    data["reasons_json"] = json.dumps(data.pop("reasons", []), ensure_ascii=False, sort_keys=True)
    data["risks_json"] = json.dumps(data.pop("risks", []), ensure_ascii=False, sort_keys=True)
    data["is_watched"] = 1 if data.get("is_watched") else 0
    data["created_at_ms"] = now_ms
    return data
