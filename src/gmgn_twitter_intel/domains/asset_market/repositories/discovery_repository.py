from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from contextlib import nullcontext
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.app.runtime.queue_terminal import terminalize_source_row

DISCOVERY_PROVIDER = "okx_dex_search"
RUNNING_LOOKUP_TIMEOUT_MS = 5 * 60 * 1000
DISCOVERY_LOOKUP_QUEUE_TABLE = "token_discovery_dirty_lookup_keys"


class DiscoveryRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def enqueue_lookup_keys(
        self,
        lookup_keys: Iterable[str],
        *,
        reason: str,
        now_ms: int,
        due_at_ms: int | None = None,
        latest_seen_ms: int | None = None,
        intent_count: int = 1,
        commit: bool = True,
    ) -> int:
        records = _lookup_key_records(
            lookup_keys,
            reason=reason,
            now_ms=now_ms,
            due_at_ms=due_at_ms,
            latest_seen_ms=latest_seen_ms,
            intent_count=intent_count,
        )
        if not records:
            return 0
        cursor = self.conn.execute(
            """
            WITH incoming(
              provider, lookup_key, lookup_type, dirty_reason, payload_hash,
              due_at_ms, latest_seen_ms, intent_count, refresh_priority
            ) AS (
              SELECT *
              FROM unnest(
                %(providers)s::text[],
                %(lookup_keys)s::text[],
                %(lookup_types)s::text[],
                %(dirty_reasons)s::text[],
                %(payload_hashes)s::text[],
                %(due_at_ms_values)s::bigint[],
                %(latest_seen_ms_values)s::bigint[],
                %(intent_counts)s::bigint[],
                %(refresh_priorities)s::integer[]
              )
            )
            INSERT INTO token_discovery_dirty_lookup_keys(
              provider,
              lookup_key,
              lookup_type,
              dirty_reason,
              payload_hash,
              due_at_ms,
              latest_seen_ms,
              intent_count,
              refresh_priority,
              leased_until_ms,
              lease_owner,
              attempt_count,
              last_error,
              first_dirty_at_ms,
              updated_at_ms
            )
            SELECT
              incoming.provider,
              incoming.lookup_key,
              incoming.lookup_type,
              incoming.dirty_reason,
              incoming.payload_hash,
              incoming.due_at_ms,
              incoming.latest_seen_ms,
              incoming.intent_count,
              incoming.refresh_priority,
              NULL,
              NULL,
              0,
              NULL,
              %(now_ms)s,
              %(now_ms)s
            FROM incoming
            ON CONFLICT(provider, lookup_key) DO UPDATE SET
              lookup_type = EXCLUDED.lookup_type,
              dirty_reason = EXCLUDED.dirty_reason,
              payload_hash = EXCLUDED.payload_hash,
              due_at_ms = LEAST(token_discovery_dirty_lookup_keys.due_at_ms, EXCLUDED.due_at_ms),
              latest_seen_ms = GREATEST(
                token_discovery_dirty_lookup_keys.latest_seen_ms,
                EXCLUDED.latest_seen_ms
              ),
              intent_count = GREATEST(token_discovery_dirty_lookup_keys.intent_count, EXCLUDED.intent_count),
              refresh_priority = LEAST(
                token_discovery_dirty_lookup_keys.refresh_priority,
                EXCLUDED.refresh_priority
              ),
              leased_until_ms = NULL,
              lease_owner = NULL,
              last_error = NULL,
              first_dirty_at_ms = token_discovery_dirty_lookup_keys.first_dirty_at_ms,
              updated_at_ms = EXCLUDED.updated_at_ms
            WHERE token_discovery_dirty_lookup_keys.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
               OR token_discovery_dirty_lookup_keys.dirty_reason IS DISTINCT FROM EXCLUDED.dirty_reason
               OR token_discovery_dirty_lookup_keys.due_at_ms > EXCLUDED.due_at_ms
               OR token_discovery_dirty_lookup_keys.latest_seen_ms < EXCLUDED.latest_seen_ms
               OR token_discovery_dirty_lookup_keys.intent_count < EXCLUDED.intent_count
               OR token_discovery_dirty_lookup_keys.refresh_priority > EXCLUDED.refresh_priority
               OR token_discovery_dirty_lookup_keys.leased_until_ms IS NOT NULL
               OR token_discovery_dirty_lookup_keys.last_error IS NOT NULL
            """,
            _lookup_key_params(records, now_ms=now_ms),
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def due_lookup_keys(
        self,
        *,
        since_ms: int,
        now_ms: int,
        limit: int,
        hot_since_ms: int | None = None,
        hot_not_found_retry_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              queue.lookup_key,
              queue.lookup_type,
              queue.provider,
              queue.latest_seen_ms,
              queue.intent_count,
              queue.refresh_priority,
              CASE
                WHEN %(hot_since_ms)s::bigint IS NOT NULL AND queue.latest_seen_ms >= %(hot_since_ms)s::bigint THEN 0
                ELSE 1
              END AS hot_priority,
              results.status,
              results.result_hash,
              results.next_refresh_at_ms,
              COALESCE(results.error_count, 0) AS error_count
            FROM token_discovery_dirty_lookup_keys queue
            LEFT JOIN token_discovery_results
              AS results
              ON results.provider = queue.provider
             AND results.lookup_key = queue.lookup_key
            WHERE queue.provider = %(provider)s
              AND queue.due_at_ms <= %(now_ms)s
              AND (queue.leased_until_ms IS NULL OR queue.leased_until_ms <= %(now_ms)s)
              AND (
                results.lookup_key IS NULL
                OR results.next_refresh_at_ms <= %(now_ms)s
               OR (
                 results.status = 'running'
                 AND results.updated_at_ms < %(running_expired_ms)s
               )
               OR (
                 %(hot_since_ms)s::bigint IS NOT NULL
                 AND %(hot_not_found_retry_ms)s::bigint IS NOT NULL
                 AND queue.latest_seen_ms >= %(hot_since_ms)s::bigint
                 AND results.status = 'not_found'
                 AND results.last_lookup_at_ms <= %(now_ms)s::bigint - %(hot_not_found_retry_ms)s::bigint
               )
              )
            ORDER BY
              hot_priority ASC,
              queue.refresh_priority ASC,
              queue.latest_seen_ms DESC,
              CASE
                WHEN results.lookup_key IS NULL THEN 0
                WHEN results.status = 'error' THEN 1
                ELSE 2
              END,
              queue.intent_count DESC,
              queue.lookup_key ASC
            LIMIT %(limit)s
            """,
            _due_params(
                now_ms=now_ms,
                limit=limit,
                hot_since_ms=hot_since_ms,
                hot_not_found_retry_ms=hot_not_found_retry_ms,
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def claim_due_lookup_keys(
        self,
        *,
        now_ms: int,
        limit: int,
        lease_ms: int,
        lease_owner: str,
        hot_since_ms: int | None = None,
        hot_not_found_retry_ms: int | None = None,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        params = _due_params(
            now_ms=now_ms,
            limit=limit,
            hot_since_ms=hot_since_ms,
            hot_not_found_retry_ms=hot_not_found_retry_ms,
        )
        params.update(
            {
                "lease_owner": str(lease_owner),
                "leased_until_ms": int(now_ms) + max(1, int(lease_ms)),
            }
        )
        rows = self.conn.execute(
            """
            WITH due AS (
              SELECT queue.provider, queue.lookup_key
              FROM token_discovery_dirty_lookup_keys queue
              LEFT JOIN token_discovery_results AS results
                ON results.provider = queue.provider
               AND results.lookup_key = queue.lookup_key
              WHERE queue.provider = %(provider)s
                AND queue.due_at_ms <= %(now_ms)s
                AND (queue.leased_until_ms IS NULL OR queue.leased_until_ms <= %(now_ms)s)
                AND (
                  results.lookup_key IS NULL
                  OR results.next_refresh_at_ms <= %(now_ms)s
                  OR (
                    results.status = 'running'
                    AND results.updated_at_ms < %(running_expired_ms)s
                  )
                  OR (
                    %(hot_since_ms)s::bigint IS NOT NULL
                    AND %(hot_not_found_retry_ms)s::bigint IS NOT NULL
                    AND queue.latest_seen_ms >= %(hot_since_ms)s::bigint
                    AND results.status = 'not_found'
                    AND results.last_lookup_at_ms <= %(now_ms)s::bigint - %(hot_not_found_retry_ms)s::bigint
                  )
                )
              ORDER BY
                CASE
                  WHEN %(hot_since_ms)s::bigint IS NOT NULL AND queue.latest_seen_ms >= %(hot_since_ms)s::bigint
                    THEN 0
                  ELSE 1
                END ASC,
                queue.refresh_priority ASC,
                queue.latest_seen_ms DESC,
                CASE
                  WHEN results.lookup_key IS NULL THEN 0
                  WHEN results.status = 'error' THEN 1
                  ELSE 2
                END,
                queue.intent_count DESC,
                queue.lookup_key ASC
              LIMIT %(limit)s
              FOR UPDATE OF queue SKIP LOCKED
            )
            UPDATE token_discovery_dirty_lookup_keys queue
            SET leased_until_ms = %(leased_until_ms)s,
                lease_owner = %(lease_owner)s,
                attempt_count = queue.attempt_count + 1,
                last_error = NULL,
                updated_at_ms = %(now_ms)s
            FROM due
            LEFT JOIN token_discovery_results AS results
              ON results.provider = due.provider
             AND results.lookup_key = due.lookup_key
            WHERE queue.provider = due.provider
              AND queue.lookup_key = due.lookup_key
            RETURNING
              queue.*,
              results.status,
              results.result_hash,
              results.next_refresh_at_ms,
              COALESCE(results.error_count, 0) AS error_count
            """,
            params,
        ).fetchall()
        if commit:
            self.conn.commit()
        return [dict(row) for row in rows]

    def mark_lookup_done(
        self,
        claims: Iterable[Mapping[str, Any]],
        *,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        records = _claim_records(claims)
        if not records:
            return 0
        cursor = self.conn.execute(
            """
            WITH done AS (
              SELECT *
              FROM unnest(
                %(providers)s::text[],
                %(lookup_keys)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS done(provider, lookup_key, payload_hash, lease_owner, attempt_count)
            )
            DELETE FROM token_discovery_dirty_lookup_keys queue
            USING done
            WHERE queue.provider = done.provider
              AND queue.lookup_key = done.lookup_key
              AND queue.payload_hash = done.payload_hash
              AND queue.lease_owner = done.lease_owner
              AND queue.attempt_count = done.attempt_count
            """,
            _claim_params(records),
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def reschedule_lookup_claims(
        self,
        claims: Iterable[Mapping[str, Any]],
        *,
        due_at_ms: int,
        now_ms: int,
        last_error: str | None = None,
        commit: bool = True,
    ) -> int:
        records = _claim_records(claims)
        if not records:
            return 0
        params = _claim_params(records)
        params.update(
            {
                "due_at_ms": int(due_at_ms),
                "now_ms": int(now_ms),
                "last_error": str(last_error)[:2048] if last_error else None,
            }
        )
        cursor = self.conn.execute(
            """
            WITH rescheduled AS (
              SELECT *
              FROM unnest(
                %(providers)s::text[],
                %(lookup_keys)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS rescheduled(provider, lookup_key, payload_hash, lease_owner, attempt_count)
            )
            UPDATE token_discovery_dirty_lookup_keys queue
            SET due_at_ms = %(due_at_ms)s,
                leased_until_ms = NULL,
                lease_owner = NULL,
                last_error = %(last_error)s,
                updated_at_ms = %(now_ms)s
            FROM rescheduled
            WHERE queue.provider = rescheduled.provider
              AND queue.lookup_key = rescheduled.lookup_key
              AND queue.payload_hash = rescheduled.payload_hash
              AND queue.lease_owner = rescheduled.lease_owner
              AND queue.attempt_count = rescheduled.attempt_count
            """,
            params,
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def terminalize_lookup_claims(
        self,
        claims: Iterable[Mapping[str, Any]],
        *,
        worker_name: str,
        final_status: str,
        final_reason: str,
        now_ms: int,
        commit: bool = True,
    ) -> dict[str, int]:
        claim_rows = [dict(claim) for claim in claims]
        records = _claim_records(claim_rows)
        if not records:
            return {"terminalized": 0, "deleted": 0}
        with _transaction(self.conn):
            deleted_rows = self._delete_lookup_claims_returning(records)
            if len(deleted_rows) != len(records):
                raise ValueError("terminalize_lookup_delete_mismatch")
            terminalized = 0
            for row in deleted_rows:
                provider = str(row.get("provider") or DISCOVERY_PROVIDER)
                lookup_key = str(row.get("lookup_key") or "").strip()
                if not lookup_key:
                    continue
                terminalize_source_row(
                    self.conn,
                    worker_name=worker_name,
                    source_table=DISCOVERY_LOOKUP_QUEUE_TABLE,
                    target_key=f"{provider}:{lookup_key}",
                    source_row=row,
                    final_status=final_status,
                    final_reason=final_reason,
                    now_ms=now_ms,
                    attempt_count=int(row.get("attempt_count") or 0),
                    payload_hash=str(row.get("payload_hash") or ""),
                    first_seen_at_ms=_optional_int(row.get("first_dirty_at_ms")),
                    last_attempted_at_ms=now_ms,
                    commit=False,
                )
                terminalized += 1
        if commit:
            self.conn.commit()
        return {"terminalized": terminalized, "deleted": len(deleted_rows)}

    def _delete_lookup_claims_returning(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH done AS (
              SELECT *
              FROM unnest(
                %(providers)s::text[],
                %(lookup_keys)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS done(provider, lookup_key, payload_hash, lease_owner, attempt_count)
            )
            DELETE FROM token_discovery_dirty_lookup_keys queue
            USING done
            WHERE queue.provider = done.provider
              AND queue.lookup_key = done.lookup_key
              AND queue.payload_hash = done.payload_hash
              AND queue.lease_owner = done.lease_owner
              AND queue.attempt_count = done.attempt_count
            RETURNING queue.*
            """,
            _claim_params(records),
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
        changed = (
            current is None
            or str(current.get("result_hash") or "") != result_hash
            or (current_status not in {"running", status})
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


def _lookup_key_records(
    lookup_keys: Iterable[str],
    *,
    reason: str,
    now_ms: int,
    due_at_ms: int | None,
    latest_seen_ms: int | None,
    intent_count: int,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw_key in sorted({str(key).strip() for key in lookup_keys if str(key).strip()}):
        lookup_type = _lookup_type(raw_key)
        if lookup_type is None:
            continue
        latest = int(latest_seen_ms if latest_seen_ms is not None else now_ms)
        record = {
            "provider": DISCOVERY_PROVIDER,
            "lookup_key": raw_key,
            "lookup_type": lookup_type,
            "dirty_reason": str(reason),
            "payload_hash": _payload_hash(raw_key, reason=str(reason), latest_seen_ms=latest),
            "due_at_ms": int(due_at_ms if due_at_ms is not None else now_ms),
            "latest_seen_ms": latest,
            "intent_count": max(1, int(intent_count)),
            "refresh_priority": 0 if raw_key.startswith("symbol:") else 1,
        }
        records.append(record)
    return records


def _lookup_type(lookup_key: str) -> str | None:
    if lookup_key.startswith("symbol:"):
        return "dex_symbol_lookup"
    if lookup_key.startswith("address:"):
        return "address_lookup"
    return None


def _payload_hash(lookup_key: str, *, reason: str, latest_seen_ms: int) -> str:
    payload = f"{DISCOVERY_PROVIDER}:{lookup_key}:{reason}:{int(latest_seen_ms)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _lookup_key_params(records: list[dict[str, Any]], *, now_ms: int) -> dict[str, Any]:
    return {
        "providers": [record["provider"] for record in records],
        "lookup_keys": [record["lookup_key"] for record in records],
        "lookup_types": [record["lookup_type"] for record in records],
        "dirty_reasons": [record["dirty_reason"] for record in records],
        "payload_hashes": [record["payload_hash"] for record in records],
        "due_at_ms_values": [record["due_at_ms"] for record in records],
        "latest_seen_ms_values": [record["latest_seen_ms"] for record in records],
        "intent_counts": [record["intent_count"] for record in records],
        "refresh_priorities": [record["refresh_priority"] for record in records],
        "now_ms": int(now_ms),
    }


def _due_params(
    *,
    now_ms: int,
    limit: int,
    hot_since_ms: int | None,
    hot_not_found_retry_ms: int | None,
) -> dict[str, Any]:
    return {
        "provider": DISCOVERY_PROVIDER,
        "now_ms": int(now_ms),
        "running_expired_ms": int(now_ms) - RUNNING_LOOKUP_TIMEOUT_MS,
        "hot_since_ms": int(hot_since_ms) if hot_since_ms is not None else None,
        "hot_not_found_retry_ms": int(hot_not_found_retry_ms) if hot_not_found_retry_ms is not None else None,
        "limit": max(0, int(limit)),
    }


def _claim_records(claims: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for claim in claims:
        provider = str(claim.get("provider") or DISCOVERY_PROVIDER)
        lookup_key = str(claim.get("lookup_key") or "")
        payload_hash = str(claim.get("payload_hash") or "")
        lease_owner = str(claim.get("lease_owner") or "")
        attempt_count = int(claim.get("attempt_count") or 0)
        if provider and lookup_key and payload_hash is not None and lease_owner and attempt_count > 0:
            records.append(
                {
                    "provider": provider,
                    "lookup_key": lookup_key,
                    "payload_hash": payload_hash,
                    "lease_owner": lease_owner,
                    "attempt_count": attempt_count,
                }
            )
    return records


def _claim_params(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "providers": [record["provider"] for record in records],
        "lookup_keys": [record["lookup_key"] for record in records],
        "payload_hashes": [record["payload_hash"] for record in records],
        "lease_owners": [record["lease_owner"] for record in records],
        "attempt_counts": [record["attempt_count"] for record in records],
    }


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _transaction(conn: Any):
    transaction = getattr(conn, "transaction", None)
    if callable(transaction):
        return transaction()
    return nullcontext()
