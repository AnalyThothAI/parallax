from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

DISCOVERY_PROVIDER = "okx_dex_search"
RUNNING_LOOKUP_TIMEOUT_MS = 5 * 60 * 1000


class DiscoveryRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def due_lookup_keys(self, *, since_ms: int, now_ms: int, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH recent_unresolved AS (
              SELECT
                token_intent_lookup_keys.lookup_key,
                MAX(events.received_at_ms) AS latest_seen_ms,
                COUNT(DISTINCT token_intent_lookup_keys.intent_id) AS intent_count
              FROM token_intent_lookup_keys
              JOIN token_intents
                ON token_intents.intent_id = token_intent_lookup_keys.intent_id
              JOIN events
                ON events.event_id = token_intents.event_id
              LEFT JOIN token_intent_resolutions current_resolution
                ON current_resolution.intent_id = token_intents.intent_id
               AND current_resolution.is_current = true
              WHERE events.received_at_ms >= %s
                AND (
                  current_resolution.resolution_id IS NULL
                  OR current_resolution.resolution_status = 'NIL'
                )
                AND (
                  token_intent_lookup_keys.lookup_key LIKE 'symbol:%%'
                  OR token_intent_lookup_keys.lookup_key LIKE 'address:%%'
                )
              GROUP BY token_intent_lookup_keys.lookup_key
            )
            SELECT
              recent_unresolved.lookup_key,
              CASE
                WHEN recent_unresolved.lookup_key LIKE 'symbol:%%' THEN 'dex_symbol_lookup'
                ELSE 'address_lookup'
              END AS lookup_type,
              %s AS provider,
              recent_unresolved.latest_seen_ms,
              recent_unresolved.intent_count,
              token_discovery_results.status,
              token_discovery_results.result_hash,
              token_discovery_results.next_refresh_at_ms
            FROM recent_unresolved
            LEFT JOIN token_discovery_results
              ON token_discovery_results.provider = %s
             AND token_discovery_results.lookup_key = recent_unresolved.lookup_key
            WHERE token_discovery_results.lookup_key IS NULL
               OR token_discovery_results.next_refresh_at_ms <= %s
               OR (
                 token_discovery_results.status = 'running'
                 AND token_discovery_results.updated_at_ms < %s
               )
            ORDER BY
              CASE
                WHEN token_discovery_results.lookup_key IS NULL THEN 0
                WHEN token_discovery_results.status = 'error' THEN 1
                ELSE 2
              END,
              recent_unresolved.latest_seen_ms DESC,
              recent_unresolved.intent_count DESC,
              recent_unresolved.lookup_key ASC
            LIMIT %s
            """,
            (
                int(since_ms),
                DISCOVERY_PROVIDER,
                DISCOVERY_PROVIDER,
                int(now_ms),
                int(now_ms) - RUNNING_LOOKUP_TIMEOUT_MS,
                max(0, int(limit)),
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def start_lookup(
        self,
        *,
        provider: str,
        lookup_key: str,
        lookup_type: str,
        now_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        self.conn.execute(
            """
            INSERT INTO token_discovery_results(
              provider, lookup_key, lookup_type, status, candidate_count, candidate_ids_json,
              result_hash, last_lookup_at_ms, next_refresh_at_ms, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, 'running', 0, '[]'::jsonb, NULL, %s, %s, %s, %s)
            ON CONFLICT(provider, lookup_key) DO UPDATE SET
              lookup_type = excluded.lookup_type,
              status = 'running',
              last_lookup_at_ms = excluded.last_lookup_at_ms,
              next_refresh_at_ms = excluded.next_refresh_at_ms,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                provider,
                lookup_key,
                lookup_type,
                int(now_ms),
                int(now_ms) + RUNNING_LOOKUP_TIMEOUT_MS,
                int(now_ms),
                int(now_ms),
            ),
        )
        if commit:
            self.conn.commit()
        return self.result(provider=provider, lookup_key=lookup_key) or {}

    def finish_lookup(
        self,
        *,
        provider: str,
        lookup_key: str,
        lookup_type: str,
        status: str,
        candidate_ids: list[str],
        result_hash: str,
        next_refresh_at_ms: int,
        now_ms: int,
        commit: bool = True,
    ) -> bool:
        current = self.result(provider=provider, lookup_key=lookup_key)
        current_status = str((current or {}).get("status") or "")
        changed = current is None or str(current.get("result_hash") or "") != result_hash or (
            current_status != "running" and current_status != status
        )
        self.conn.execute(
            """
            INSERT INTO token_discovery_results(
              provider, lookup_key, lookup_type, status, candidate_count, candidate_ids_json,
              result_hash, last_lookup_at_ms, next_refresh_at_ms, last_error, error_count,
              created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, 0, %s, %s)
            ON CONFLICT(provider, lookup_key) DO UPDATE SET
              lookup_type = excluded.lookup_type,
              status = excluded.status,
              candidate_count = excluded.candidate_count,
              candidate_ids_json = excluded.candidate_ids_json,
              result_hash = excluded.result_hash,
              last_lookup_at_ms = excluded.last_lookup_at_ms,
              next_refresh_at_ms = excluded.next_refresh_at_ms,
              last_error = NULL,
              error_count = 0,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                provider,
                lookup_key,
                lookup_type,
                status,
                len(candidate_ids),
                Jsonb(sorted(set(candidate_ids))),
                result_hash,
                int(now_ms),
                int(next_refresh_at_ms),
                int(now_ms),
                int(now_ms),
            ),
        )
        if commit:
            self.conn.commit()
        return changed

    def fail_lookup(
        self,
        *,
        provider: str,
        lookup_key: str,
        lookup_type: str,
        last_error: str,
        next_refresh_at_ms: int,
        now_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        self.conn.execute(
            """
            INSERT INTO token_discovery_results(
              provider, lookup_key, lookup_type, status, candidate_count, candidate_ids_json,
              result_hash, last_lookup_at_ms, next_refresh_at_ms, last_error, error_count,
              created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, 'error', 0, '[]'::jsonb, NULL, %s, %s, %s, 1, %s, %s)
            ON CONFLICT(provider, lookup_key) DO UPDATE SET
              lookup_type = excluded.lookup_type,
              status = 'error',
              last_lookup_at_ms = excluded.last_lookup_at_ms,
              next_refresh_at_ms = excluded.next_refresh_at_ms,
              last_error = excluded.last_error,
              error_count = token_discovery_results.error_count + 1,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                provider,
                lookup_key,
                lookup_type,
                int(now_ms),
                int(next_refresh_at_ms),
                last_error[:500],
                int(now_ms),
                int(now_ms),
            ),
        )
        if commit:
            self.conn.commit()
        return self.result(provider=provider, lookup_key=lookup_key) or {}

    def counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM token_discovery_results
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}

    def result(self, *, provider: str, lookup_key: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM token_discovery_results
            WHERE provider = %s AND lookup_key = %s
            """,
            (provider, lookup_key),
        ).fetchone()
        return dict(row) if row else None
