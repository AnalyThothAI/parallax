from __future__ import annotations

import hashlib
import sqlite3
import time
from typing import Any

RUNNING_TIMEOUT_MS = 120_000
UNTRADEABLE_CHAINS = {"unknown", "evm", "evm_unknown"}


class MarketObservationRepository:
    def __init__(self, conn: sqlite3.Connection, *, running_timeout_ms: int = RUNNING_TIMEOUT_MS):
        self.conn = conn
        self.running_timeout_ms = running_timeout_ms

    def enqueue_for_attributions(
        self,
        attributions: list[dict[str, Any]],
        *,
        now_ms: int | None = None,
        commit: bool = True,
    ) -> int:
        now = now_ms if now_ms is not None else _now_ms()
        inserted = 0
        for attribution in attributions:
            if not _should_observe(attribution):
                continue
            cursor = self.conn.execute(
                """
                INSERT OR IGNORE INTO token_market_observations(
                  observation_id, attribution_id, event_id, token_id, chain, address, symbol,
                  target_received_at_ms, status, priority, provider, source_channel, snapshot_id,
                  attempt_count, max_attempts, next_run_at_ms, last_error, created_at_ms, updated_at_ms
                )
                VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 100, NULL,
                  'gmgn_openapi_token_info', NULL, 0, 5, ?, NULL, ?, ?
                )
                """,
                (
                    _id("market_observation", str(attribution["attribution_id"])),
                    str(attribution["attribution_id"]),
                    str(attribution["event_id"]),
                    str(attribution["token_id"]),
                    str(attribution["chain"]).strip().lower(),
                    str(attribution["address"]),
                    str(attribution["symbol"]).strip().lstrip("$").upper(),
                    int(attribution["received_at_ms"]),
                    now,
                    now,
                    now,
                ),
            )
            inserted += int(cursor.rowcount == 1)
        if commit:
            self.conn.commit()
        return inserted

    def claim_next(self, *, now_ms: int | None = None) -> dict[str, Any] | None:
        now = now_ms if now_ms is not None else _now_ms()
        stale_before = now - self.running_timeout_ms
        row = self.conn.execute(
            """
            SELECT *
            FROM token_market_observations
            WHERE (
                status IN ('pending', 'provider_error', 'rate_limited')
                AND next_run_at_ms <= ?
              )
              OR (
                status = 'running'
                AND updated_at_ms < ?
              )
            ORDER BY priority ASC, next_run_at_ms ASC, created_at_ms ASC
            LIMIT 1
            """,
            (now, stale_before),
        ).fetchone()
        if row is None:
            return None
        should_count_reclaim = str(row["status"]) == "running"
        self.conn.execute(
            """
            UPDATE token_market_observations
            SET status = 'running',
                attempt_count = attempt_count + ?,
                updated_at_ms = ?
            WHERE observation_id = ?
            """,
            (1 if should_count_reclaim else 0, now, row["observation_id"]),
        )
        self.conn.commit()
        updated = self.conn.execute(
            "SELECT * FROM token_market_observations WHERE observation_id = ?",
            (row["observation_id"],),
        ).fetchone()
        return dict(updated) if updated else None

    def complete(
        self,
        observation: dict[str, Any],
        *,
        snapshot_id: str | None,
        status: str,
        provider: str | None,
        now_ms: int | None = None,
        commit: bool = True,
    ) -> None:
        now = now_ms if now_ms is not None else _now_ms()
        self.conn.execute(
            """
            UPDATE token_market_observations
            SET status = ?,
                provider = ?,
                snapshot_id = ?,
                last_error = NULL,
                updated_at_ms = ?
            WHERE observation_id = ?
            """,
            (status, provider, snapshot_id, now, observation["observation_id"]),
        )
        if commit:
            self.conn.commit()

    def fail(
        self,
        observation: dict[str, Any],
        *,
        error: str,
        status: str = "provider_error",
        now_ms: int | None = None,
        commit: bool = True,
    ) -> None:
        now = now_ms if now_ms is not None else _now_ms()
        attempt_count = int(observation.get("attempt_count") or 0)
        max_attempts = int(observation.get("max_attempts") or 5)
        next_attempt_count = attempt_count + 1
        if next_attempt_count >= max_attempts:
            next_status = "dead"
            next_run_at_ms = now
        else:
            base_ms = 30_000 if status == "rate_limited" else 5_000
            cap_ms = 1_800_000 if status == "rate_limited" else 300_000
            next_status = status
            next_run_at_ms = now + min(cap_ms, (2**attempt_count) * base_ms)
        self.conn.execute(
            """
            UPDATE token_market_observations
            SET status = ?,
                attempt_count = ?,
                next_run_at_ms = ?,
                last_error = ?,
                updated_at_ms = ?
            WHERE observation_id = ?
            """,
            (next_status, next_attempt_count, next_run_at_ms, error, now, observation["observation_id"]),
        )
        if commit:
            self.conn.commit()

    def counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM token_market_observations
            GROUP BY status
            """
        ).fetchall()
        counts = {str(row["status"]): int(row["count"] or 0) for row in rows}
        for status in [
            "pending",
            "running",
            "ready",
            "cached",
            "provider_not_configured",
            "provider_not_found",
            "provider_error",
            "rate_limited",
            "dead",
        ]:
            counts.setdefault(status, 0)
        return counts

    def list_observations(self, *, limit: int, status: str | None = None) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(0, int(limit)))
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM token_market_observations
            {where_clause}
            ORDER BY updated_at_ms DESC, target_received_at_ms DESC, observation_id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def pending_backfill_rows(self, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT eta.*
            FROM event_token_attributions eta
            LEFT JOIN token_market_observations tmo
              ON tmo.attribution_id = eta.attribution_id
            WHERE tmo.observation_id IS NULL
              AND eta.attribution_status IN ('direct', 'selected')
              AND eta.token_id IS NOT NULL
              AND eta.chain IS NOT NULL
              AND eta.address IS NOT NULL
              AND eta.chain NOT IN ('unknown', 'evm', 'evm_unknown')
            ORDER BY eta.received_at_ms ASC, eta.attribution_id ASC
            LIMIT ?
            """,
            (max(0, int(limit)),),
        ).fetchall()
        return [dict(row) for row in rows]


def _should_observe(attribution: dict[str, Any]) -> bool:
    if attribution.get("attribution_status") not in {"direct", "selected"}:
        return False
    token_id = attribution.get("token_id")
    chain = attribution.get("chain")
    address = attribution.get("address")
    if not token_id or not chain or not address:
        return False
    return str(chain).strip().lower() not in UNTRADEABLE_CHAINS


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)
