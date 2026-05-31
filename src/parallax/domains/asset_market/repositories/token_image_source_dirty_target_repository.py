from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from psycopg.types.json import Jsonb

from parallax.platform.db.json_safety import postgres_safe_json, postgres_safe_text


class TokenImageSourceDirtyTargetRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def enqueue_targets(
        self,
        targets: Iterable[Mapping[str, Any]],
        *,
        reason: str,
        now_ms: int,
        due_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, int]:
        records = _target_records(
            targets,
            reason=reason,
            now_ms=int(now_ms),
            default_due_at_ms=int(due_at_ms if due_at_ms is not None else now_ms),
        )
        if not records:
            return {"targets": 0}
        self.conn.execute(
            """
            WITH incoming AS (
              SELECT *
              FROM unnest(
                %(source_url_hashes)s::text[],
                %(source_urls)s::text[],
                %(source_providers)s::text[],
                %(source_kinds)s::text[],
                %(target_types)s::text[],
                %(target_ids)s::text[],
                %(raw_refs)s::jsonb[],
                %(payload_hashes)s::text[],
                %(source_watermark_ms_values)s::bigint[],
                %(priorities)s::integer[],
                %(due_at_ms_values)s::bigint[]
              ) AS incoming(
                source_url_hash,
                source_url,
                source_provider,
                source_kind,
                target_type,
                target_id,
                raw_ref_json,
                payload_hash,
                source_watermark_ms,
                priority,
                due_at_ms
              )
            )
            INSERT INTO token_image_source_dirty_targets(
              source_url_hash,
              source_url,
              source_provider,
              source_kind,
              target_type,
              target_id,
              raw_ref_json,
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
              incoming.source_url_hash,
              incoming.source_url,
              incoming.source_provider,
              incoming.source_kind,
              incoming.target_type,
              incoming.target_id,
              incoming.raw_ref_json,
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
            ON CONFLICT(source_url_hash, target_type, target_id) DO UPDATE SET
              source_url = EXCLUDED.source_url,
              source_provider = EXCLUDED.source_provider,
              source_kind = EXCLUDED.source_kind,
              raw_ref_json = EXCLUDED.raw_ref_json,
              dirty_reason = EXCLUDED.dirty_reason,
              payload_hash = EXCLUDED.payload_hash,
              source_watermark_ms = GREATEST(
                token_image_source_dirty_targets.source_watermark_ms,
                EXCLUDED.source_watermark_ms
              ),
              priority = LEAST(token_image_source_dirty_targets.priority, EXCLUDED.priority),
              due_at_ms = LEAST(token_image_source_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
              leased_until_ms = CASE
                WHEN token_image_source_dirty_targets.leased_until_ms IS NOT NULL
                  AND (
                    EXCLUDED.source_watermark_ms > token_image_source_dirty_targets.source_watermark_ms
                    OR token_image_source_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                  )
                  THEN NULL
                ELSE token_image_source_dirty_targets.leased_until_ms
              END,
              lease_owner = CASE
                WHEN token_image_source_dirty_targets.leased_until_ms IS NOT NULL
                  AND (
                    EXCLUDED.source_watermark_ms > token_image_source_dirty_targets.source_watermark_ms
                    OR token_image_source_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                  )
                  THEN NULL
                ELSE token_image_source_dirty_targets.lease_owner
              END,
              last_error = NULL,
              first_dirty_at_ms = token_image_source_dirty_targets.first_dirty_at_ms,
              updated_at_ms = EXCLUDED.updated_at_ms
            """,
            {**_target_params(records), "dirty_reason": str(reason), "now_ms": int(now_ms)},
        )
        if commit:
            self.conn.commit()
        return {"targets": len(records)}

    def claim_due(
        self,
        *,
        now_ms: int,
        limit: int,
        lease_owner: str,
        lease_ms: int,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH due AS (
              SELECT source_url_hash, target_type, target_id
              FROM token_image_source_dirty_targets
              WHERE due_at_ms <= %(now_ms)s
                AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
              ORDER BY priority ASC,
                       due_at_ms ASC,
                       updated_at_ms ASC,
                       source_url_hash ASC,
                       target_type ASC,
                       target_id ASC
              LIMIT %(limit)s
              FOR UPDATE SKIP LOCKED
            )
            UPDATE token_image_source_dirty_targets
            SET leased_until_ms = %(leased_until_ms)s,
                lease_owner = %(lease_owner)s,
                attempt_count = token_image_source_dirty_targets.attempt_count + 1,
                last_error = NULL,
                updated_at_ms = %(now_ms)s
            FROM due
            WHERE token_image_source_dirty_targets.source_url_hash = due.source_url_hash
              AND token_image_source_dirty_targets.target_type = due.target_type
              AND token_image_source_dirty_targets.target_id = due.target_id
            RETURNING token_image_source_dirty_targets.*
            """,
            {
                "now_ms": int(now_ms),
                "leased_until_ms": int(now_ms) + max(1, int(lease_ms)),
                "lease_owner": str(lease_owner),
                "limit": max(0, int(limit)),
            },
        ).fetchall()
        if commit:
            self.conn.commit()
        return [dict(row) for row in rows]

    def existing_by_source_targets(
        self,
        targets: Iterable[Mapping[str, Any]],
    ) -> dict[tuple[str, str, str], dict[str, Any]]:
        records = _target_identity_records(targets)
        if not records:
            return {}
        rows = self.conn.execute(
            """
            WITH incoming AS (
              SELECT *
              FROM unnest(
                %(source_url_hashes)s::text[],
                %(target_types)s::text[],
                %(target_ids)s::text[]
              ) AS incoming(source_url_hash, target_type, target_id)
            )
            SELECT queue.*
            FROM token_image_source_dirty_targets queue
            JOIN incoming
              ON queue.source_url_hash = incoming.source_url_hash
             AND queue.target_type = incoming.target_type
             AND queue.target_id = incoming.target_id
            """,
            {
                "source_url_hashes": [record["source_url_hash"] for record in records],
                "target_types": [record["target_type"] for record in records],
                "target_ids": [record["target_id"] for record in records],
            },
        ).fetchall()
        return {
            (str(row["source_url_hash"]), str(row["target_type"]), str(row["target_id"])): dict(row) for row in rows
        }

    def mark_done(self, claims: Iterable[Mapping[str, Any]], *, now_ms: int, commit: bool = True) -> int:
        records = _claim_records(claims)
        if not records:
            return 0
        cursor = self.conn.execute(
            """
            WITH done AS (
              SELECT *
              FROM unnest(
                %(source_url_hashes)s::text[],
                %(target_types)s::text[],
                %(target_ids)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS done(source_url_hash, target_type, target_id, payload_hash, lease_owner, attempt_count)
            )
            DELETE FROM token_image_source_dirty_targets queue
            USING done
            WHERE queue.source_url_hash = done.source_url_hash
              AND queue.target_type = done.target_type
              AND queue.target_id = done.target_id
              AND queue.payload_hash = done.payload_hash
              AND queue.lease_owner = done.lease_owner
              AND queue.attempt_count = done.attempt_count
            """,
            _claim_params(records),
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def mark_error(
        self,
        claims: Iterable[Mapping[str, Any]],
        *,
        error: str,
        now_ms: int,
        retry_ms: int,
        commit: bool = True,
    ) -> int:
        records = _claim_records(claims)
        if not records:
            return 0
        params = {
            **_claim_params(records),
            "due_at_ms": int(now_ms) + max(1, int(retry_ms)),
            "now_ms": int(now_ms),
            "last_error": str(error)[:2048],
        }
        cursor = self.conn.execute(
            """
            WITH failed AS (
              SELECT *
              FROM unnest(
                %(source_url_hashes)s::text[],
                %(target_types)s::text[],
                %(target_ids)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS failed(source_url_hash, target_type, target_id, payload_hash, lease_owner, attempt_count)
            )
            UPDATE token_image_source_dirty_targets queue
            SET due_at_ms = %(due_at_ms)s,
                leased_until_ms = NULL,
                lease_owner = NULL,
                last_error = %(last_error)s,
                updated_at_ms = %(now_ms)s
            FROM failed
            WHERE queue.source_url_hash = failed.source_url_hash
              AND queue.target_type = failed.target_type
              AND queue.target_id = failed.target_id
              AND queue.payload_hash = failed.payload_hash
              AND queue.lease_owner = failed.lease_owner
              AND queue.attempt_count = failed.attempt_count
            """,
            params,
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def queue_depth(self, *, now_ms: int) -> int:
        row = self.conn.execute(
            """
            SELECT count(*) AS count
            FROM token_image_source_dirty_targets
            WHERE due_at_ms <= %(now_ms)s
              AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
            """,
            {"now_ms": int(now_ms)},
        ).fetchone()
        return int(row["count"] if row else 0)


def _target_records(
    targets: Iterable[Mapping[str, Any]],
    *,
    reason: str,
    now_ms: int,
    default_due_at_ms: int,
) -> list[dict[str, Any]]:
    records: dict[tuple[str, str, str], dict[str, Any]] = {}
    for target in targets:
        source_url = _required_source_url(target.get("source_url"))
        target_type = _required_text(target.get("target_type"), field_name="target_type")
        target_id = _required_text(target.get("target_id"), field_name="target_id")
        source_provider = _required_text(target.get("source_provider"), field_name="source_provider")
        source_kind = _required_text(target.get("source_kind"), field_name="source_kind")
        raw_ref_json = postgres_safe_json(target.get("raw_ref_json") or {})
        source_watermark_ms = int(target.get("source_watermark_ms") or target.get("observed_at_ms") or now_ms)
        record = {
            "source_url_hash": _source_url_hash(source_url),
            "source_url": source_url,
            "source_provider": source_provider,
            "source_kind": source_kind,
            "target_type": target_type,
            "target_id": target_id,
            "raw_ref_json": raw_ref_json,
            "source_watermark_ms": source_watermark_ms,
            "priority": _priority_value(target),
            "due_at_ms": int(target.get("due_at_ms") or default_due_at_ms),
        }
        record["payload_hash"] = str(target.get("payload_hash") or _payload_hash({**record, "dirty_reason": reason}))
        records[(record["source_url_hash"], target_type, target_id)] = record
    return list(records.values())


def _target_identity_records(targets: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    records: dict[tuple[str, str, str], dict[str, str]] = {}
    for target in targets:
        source_url = _required_source_url(target.get("source_url"))
        target_type = _required_text(target.get("target_type"), field_name="target_type")
        target_id = _required_text(target.get("target_id"), field_name="target_id")
        source_url_hash = _source_url_hash(source_url)
        records[(source_url_hash, target_type, target_id)] = {
            "source_url_hash": source_url_hash,
            "target_type": target_type,
            "target_id": target_id,
        }
    return list(records.values())


def _target_params(records: list[dict[str, Any]]) -> dict[str, list[Any]]:
    return {
        "source_url_hashes": [str(record["source_url_hash"]) for record in records],
        "source_urls": [str(record["source_url"]) for record in records],
        "source_providers": [str(record["source_provider"]) for record in records],
        "source_kinds": [str(record["source_kind"]) for record in records],
        "target_types": [str(record["target_type"]) for record in records],
        "target_ids": [str(record["target_id"]) for record in records],
        "raw_refs": [Jsonb(record["raw_ref_json"]) for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "source_watermark_ms_values": [int(record["source_watermark_ms"]) for record in records],
        "priorities": [int(record["priority"]) for record in records],
        "due_at_ms_values": [int(record["due_at_ms"]) for record in records],
    }


def _claim_records(claims: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for claim in claims:
        source_url_hash = str(claim.get("source_url_hash") or _source_url_hash(str(claim.get("source_url") or "")))
        target_type = str(claim.get("target_type") or "").strip()
        target_id = str(claim.get("target_id") or "").strip()
        payload_hash = str(claim.get("payload_hash") or "")
        lease_owner = str(claim.get("lease_owner") or "")
        attempt_count = int(claim.get("attempt_count") or 0)
        if not source_url_hash or not target_type or not target_id:
            raise ValueError("token image source dirty target completion requires full target key from claim_due")
        if not payload_hash:
            raise ValueError("token image source dirty target completion requires payload_hash from claim_due")
        if not lease_owner:
            raise ValueError("token image source dirty target completion requires lease_owner from claim_due")
        if attempt_count <= 0:
            raise ValueError("token image source dirty target completion requires attempt_count from claim_due")
        records.append(
            {
                "source_url_hash": source_url_hash,
                "target_type": target_type,
                "target_id": target_id,
                "payload_hash": payload_hash,
                "lease_owner": lease_owner,
                "attempt_count": attempt_count,
            }
        )
    return records


def _claim_params(records: list[dict[str, Any]]) -> dict[str, list[Any]]:
    return {
        "source_url_hashes": [str(record["source_url_hash"]) for record in records],
        "target_types": [str(record["target_type"]) for record in records],
        "target_ids": [str(record["target_id"]) for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "lease_owners": [str(record["lease_owner"]) for record in records],
        "attempt_counts": [int(record["attempt_count"]) for record in records],
    }


def _priority_value(target: Mapping[str, Any]) -> int:
    raw_priority = target.get("priority")
    if raw_priority in (None, ""):
        return 100
    return int(str(raw_priority))


def _required_source_url(value: Any) -> str:
    text = _required_text(value, field_name="source_url")
    if not text.startswith(("http://", "https://")):
        raise ValueError("token image source_url must be an absolute URL")
    return text


def _required_text(value: Any, *, field_name: str) -> str:
    text = postgres_safe_text(value).strip()
    if not text:
        raise ValueError(f"token image source dirty target {field_name} is required")
    return text


def _source_url_hash(source_url: str) -> str:
    return hashlib.sha256(source_url.encode("utf-8")).hexdigest()


def _payload_hash(payload: Mapping[str, Any]) -> str:
    safe_payload = postgres_safe_json(dict(payload))
    encoded = json.dumps(safe_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
