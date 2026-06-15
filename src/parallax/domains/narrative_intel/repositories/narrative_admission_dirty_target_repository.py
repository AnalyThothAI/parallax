from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import AbstractContextManager
from typing import Any, cast

from parallax.platform.current_read_model_payload_hash import stable_dirty_target_payload_hash


class _NarrativeDirtyTargetRepository:
    table_name: str
    error_label: str

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
        target_list = list(targets)
        records = _target_records(
            target_list,
            reason=reason,
            now_ms=int(now_ms),
            default_due_at_ms=int(due_at_ms if due_at_ms is not None else now_ms),
        )
        if not records:
            return {"targets": 0}
        if commit:
            with _transaction(self.conn):
                return self.enqueue_targets(
                    target_list,
                    reason=reason,
                    now_ms=now_ms,
                    due_at_ms=due_at_ms,
                    commit=False,
                )
        table = self.table_name
        self.conn.execute(
            f"""
            WITH incoming AS (
              SELECT *
              FROM unnest(
                %(target_types)s::text[],
                %(target_ids)s::text[],
                %(windows)s::text[],
                %(scopes)s::text[],
                %(projection_versions)s::text[],
                %(schema_versions)s::text[],
                %(payload_hashes)s::text[],
                %(source_watermark_ms_values)s::bigint[],
                %(priorities)s::integer[],
                %(due_at_ms_values)s::bigint[]
              ) AS incoming(
                target_type,
                target_id,
                "window",
                scope,
                projection_version,
                schema_version,
                payload_hash,
                source_watermark_ms,
                priority,
                due_at_ms
              )
            )
            INSERT INTO {table}(
              target_type,
              target_id,
              "window",
              scope,
              projection_version,
              schema_version,
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
              incoming.target_type,
              incoming.target_id,
              incoming."window",
              incoming.scope,
              incoming.projection_version,
              incoming.schema_version,
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
            ON CONFLICT(target_type, target_id, "window", scope) DO UPDATE SET
              projection_version = CASE
                WHEN {table}.source_watermark_ms = 0
                  OR EXCLUDED.source_watermark_ms >= {table}.source_watermark_ms
                  THEN EXCLUDED.projection_version
                ELSE {table}.projection_version
              END,
              schema_version = CASE
                WHEN {table}.source_watermark_ms = 0
                  OR EXCLUDED.source_watermark_ms >= {table}.source_watermark_ms
                  THEN EXCLUDED.schema_version
                ELSE {table}.schema_version
              END,
              dirty_reason = CASE
                WHEN {table}.source_watermark_ms = 0
                  OR EXCLUDED.source_watermark_ms >= {table}.source_watermark_ms
                  THEN EXCLUDED.dirty_reason
                ELSE {table}.dirty_reason
              END,
              payload_hash = CASE
                WHEN {table}.source_watermark_ms = 0
                  OR EXCLUDED.source_watermark_ms >= {table}.source_watermark_ms
                  THEN EXCLUDED.payload_hash
                ELSE {table}.payload_hash
              END,
              source_watermark_ms = GREATEST(
                {table}.source_watermark_ms,
                EXCLUDED.source_watermark_ms
              ),
              priority = LEAST({table}.priority, EXCLUDED.priority),
              due_at_ms = LEAST({table}.due_at_ms, EXCLUDED.due_at_ms),
              leased_until_ms = CASE
                WHEN {table}.leased_until_ms IS NOT NULL
                  AND (
                    EXCLUDED.source_watermark_ms > {table}.source_watermark_ms
                    OR (
                      (
                        {table}.source_watermark_ms = 0
                        OR EXCLUDED.source_watermark_ms >= {table}.source_watermark_ms
                      )
                      AND (
                        {table}.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                        OR {table}.dirty_reason IS DISTINCT FROM EXCLUDED.dirty_reason
                        OR {table}.projection_version IS DISTINCT FROM EXCLUDED.projection_version
                        OR {table}.schema_version IS DISTINCT FROM EXCLUDED.schema_version
                      )
                    )
                  )
                  THEN NULL
                ELSE {table}.leased_until_ms
              END,
              lease_owner = CASE
                WHEN {table}.leased_until_ms IS NOT NULL
                  AND (
                    EXCLUDED.source_watermark_ms > {table}.source_watermark_ms
                    OR (
                      (
                        {table}.source_watermark_ms = 0
                        OR EXCLUDED.source_watermark_ms >= {table}.source_watermark_ms
                      )
                      AND (
                        {table}.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                        OR {table}.dirty_reason IS DISTINCT FROM EXCLUDED.dirty_reason
                        OR {table}.projection_version IS DISTINCT FROM EXCLUDED.projection_version
                        OR {table}.schema_version IS DISTINCT FROM EXCLUDED.schema_version
                      )
                    )
                  )
                  THEN NULL
                ELSE {table}.lease_owner
              END,
              last_error = NULL,
              first_dirty_at_ms = {table}.first_dirty_at_ms,
              updated_at_ms = EXCLUDED.updated_at_ms
            """,
            {
                **_target_params(records),
                "dirty_reason": str(reason),
                "now_ms": int(now_ms),
            },
        )
        return {"targets": len(records)}

    def claim_due(
        self,
        *,
        now_ms: int,
        limit: int,
        lease_owner: str,
        lease_ms: int,
        windows: tuple[str, ...] | None = None,
        scopes: tuple[str, ...] | None = None,
        projection_version: str | None = None,
        schema_version: str | None = None,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        if commit:
            with _transaction(self.conn):
                return self.claim_due(
                    now_ms=now_ms,
                    limit=limit,
                    lease_owner=lease_owner,
                    lease_ms=lease_ms,
                    windows=windows,
                    scopes=scopes,
                    projection_version=projection_version,
                    schema_version=schema_version,
                    commit=False,
                )
        table = self.table_name
        rows = self.conn.execute(
            f"""
            WITH due AS (
              SELECT target_type, target_id, "window", scope
              FROM {table}
            WHERE due_at_ms <= %(now_ms)s
                AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
                AND (%(windows)s::text[] IS NULL OR "window" = ANY(%(windows)s::text[]))
                AND (%(scopes)s::text[] IS NULL OR scope = ANY(%(scopes)s::text[]))
                AND (%(projection_version)s::text IS NULL OR projection_version = %(projection_version)s)
                AND (%(schema_version)s::text IS NULL OR schema_version = %(schema_version)s)
              ORDER BY priority ASC,
                       due_at_ms ASC,
                       updated_at_ms ASC,
                       projection_version ASC,
                       schema_version ASC,
                       target_type ASC,
                       target_id ASC,
                       "window" ASC,
                       scope ASC
              LIMIT %(limit)s
              FOR UPDATE SKIP LOCKED
            )
            UPDATE {table}
            SET leased_until_ms = %(leased_until_ms)s,
                lease_owner = %(lease_owner)s,
                attempt_count = {table}.attempt_count + 1,
                last_error = NULL,
                updated_at_ms = %(now_ms)s
            FROM due
            WHERE {table}.target_type = due.target_type
              AND {table}.target_id = due.target_id
              AND {table}."window" = due."window"
              AND {table}.scope = due.scope
            RETURNING {table}.*
            """,
            {
                "now_ms": int(now_ms),
                "leased_until_ms": int(now_ms) + max(1, int(lease_ms)),
                "lease_owner": str(lease_owner),
                "limit": max(0, int(limit)),
                "windows": list(windows) if windows else None,
                "scopes": list(scopes) if scopes else None,
                "projection_version": projection_version,
                "schema_version": schema_version,
            },
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_done(
        self,
        claims: Iterable[Mapping[str, Any]],
        *,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        claim_list = list(claims)
        records = _claim_records(claim_list, label=self.error_label)
        if not records:
            return 0
        if commit:
            with _transaction(self.conn):
                return self.mark_done(claim_list, now_ms=now_ms, commit=False)
        table = self.table_name
        cursor = self.conn.execute(
            f"""
            WITH done AS (
              SELECT *
              FROM unnest(
                %(target_types)s::text[],
                %(target_ids)s::text[],
                %(windows)s::text[],
                %(scopes)s::text[],
                %(projection_versions)s::text[],
                %(schema_versions)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS done(
                target_type,
                target_id,
                "window",
                scope,
                projection_version,
                schema_version,
                payload_hash,
                lease_owner,
                attempt_count
              )
            )
            DELETE FROM {table} queue
            USING done
            WHERE queue.target_type = done.target_type
              AND queue.target_id = done.target_id
              AND queue."window" = done."window"
              AND queue.scope = done.scope
              AND queue.projection_version = done.projection_version
              AND queue.schema_version = done.schema_version
              AND queue.payload_hash = done.payload_hash
              AND queue.lease_owner = done.lease_owner
              AND queue.attempt_count = done.attempt_count
            """,
            _claim_params(records),
        )
        return _cursor_rowcount(cursor)

    def mark_error(
        self,
        claims: Iterable[Mapping[str, Any]],
        *,
        error: str,
        now_ms: int,
        retry_ms: int,
        commit: bool = True,
    ) -> int:
        claim_list = list(claims)
        records = _claim_records(claim_list, label=self.error_label)
        if not records:
            return 0
        if commit:
            with _transaction(self.conn):
                return self.mark_error(
                    claim_list,
                    error=error,
                    now_ms=now_ms,
                    retry_ms=retry_ms,
                    commit=False,
                )
        params: dict[str, Any] = {
            **_claim_params(records),
            "due_at_ms": int(now_ms) + max(1, int(retry_ms)),
            "now_ms": int(now_ms),
            "last_error": str(error)[:2048],
        }
        table = self.table_name
        cursor = self.conn.execute(
            f"""
            WITH failed AS (
              SELECT *
              FROM unnest(
                %(target_types)s::text[],
                %(target_ids)s::text[],
                %(windows)s::text[],
                %(scopes)s::text[],
                %(projection_versions)s::text[],
                %(schema_versions)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS failed(
                target_type,
                target_id,
                "window",
                scope,
                projection_version,
                schema_version,
                payload_hash,
                lease_owner,
                attempt_count
              )
            )
            UPDATE {table} queue
            SET due_at_ms = %(due_at_ms)s,
                leased_until_ms = NULL,
                lease_owner = NULL,
                last_error = %(last_error)s,
                updated_at_ms = %(now_ms)s
            FROM failed
            WHERE queue.target_type = failed.target_type
              AND queue.target_id = failed.target_id
              AND queue."window" = failed."window"
              AND queue.scope = failed.scope
              AND queue.projection_version = failed.projection_version
              AND queue.schema_version = failed.schema_version
              AND queue.payload_hash = failed.payload_hash
              AND queue.lease_owner = failed.lease_owner
              AND queue.attempt_count = failed.attempt_count
            """,
            params,
        )
        return _cursor_rowcount(cursor)

    def reschedule(
        self,
        claims: Iterable[Mapping[str, Any]],
        *,
        due_at_ms: int,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        claim_list = list(claims)
        records = _claim_records(claim_list, label=self.error_label)
        if not records:
            return 0
        if commit:
            with _transaction(self.conn):
                return self.reschedule(
                    claim_list,
                    due_at_ms=due_at_ms,
                    now_ms=now_ms,
                    commit=False,
                )
        params: dict[str, Any] = {
            **_claim_params(records),
            "due_at_ms": int(due_at_ms),
            "now_ms": int(now_ms),
        }
        table = self.table_name
        cursor = self.conn.execute(
            f"""
            WITH rescheduled AS (
              SELECT *
              FROM unnest(
                %(target_types)s::text[],
                %(target_ids)s::text[],
                %(windows)s::text[],
                %(scopes)s::text[],
                %(projection_versions)s::text[],
                %(schema_versions)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS rescheduled(
                target_type,
                target_id,
                "window",
                scope,
                projection_version,
                schema_version,
                payload_hash,
                lease_owner,
                attempt_count
              )
            )
            UPDATE {table} queue
            SET due_at_ms = %(due_at_ms)s,
                leased_until_ms = NULL,
                lease_owner = NULL,
                updated_at_ms = %(now_ms)s
            FROM rescheduled
            WHERE queue.target_type = rescheduled.target_type
              AND queue.target_id = rescheduled.target_id
              AND queue."window" = rescheduled."window"
              AND queue.scope = rescheduled.scope
              AND queue.projection_version = rescheduled.projection_version
              AND queue.schema_version = rescheduled.schema_version
              AND queue.payload_hash = rescheduled.payload_hash
              AND queue.lease_owner = rescheduled.lease_owner
              AND queue.attempt_count = rescheduled.attempt_count
            """,
            params,
        )
        return _cursor_rowcount(cursor)

    def queue_depth(
        self,
        *,
        now_ms: int,
        windows: tuple[str, ...] | None = None,
        scopes: tuple[str, ...] | None = None,
        projection_version: str | None = None,
        schema_version: str | None = None,
    ) -> int:
        row = self.conn.execute(
            f"""
            SELECT count(*) AS count
            FROM {self.table_name}
            WHERE due_at_ms <= %(now_ms)s
              AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
              AND (%(windows)s::text[] IS NULL OR "window" = ANY(%(windows)s::text[]))
              AND (%(scopes)s::text[] IS NULL OR scope = ANY(%(scopes)s::text[]))
              AND (%(projection_version)s::text IS NULL OR projection_version = %(projection_version)s)
              AND (%(schema_version)s::text IS NULL OR schema_version = %(schema_version)s)
            """,
            {
                "now_ms": int(now_ms),
                "windows": list(windows) if windows else None,
                "scopes": list(scopes) if scopes else None,
                "projection_version": projection_version,
                "schema_version": schema_version,
            },
        ).fetchone()
        return int(row["count"] if row else 0)


class NarrativeAdmissionDirtyTargetRepository(_NarrativeDirtyTargetRepository):
    table_name = "narrative_admission_dirty_targets"
    error_label = "narrative admission dirty target"


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("narrative_admission_dirty_target_transaction_required") from exc
    if not callable(transaction):
        raise RuntimeError("narrative_admission_dirty_target_transaction_required")
    return cast(AbstractContextManager[Any], transaction())


def _target_records(
    targets: Iterable[Mapping[str, Any]],
    *,
    reason: str,
    now_ms: int,
    default_due_at_ms: int,
) -> list[dict[str, Any]]:
    records: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for target in targets:
        target_type = str(target.get("target_type") or "").strip()
        target_id = str(target.get("target_id") or "").strip()
        window = str(target.get("window") or "").strip()
        scope = str(target.get("scope") or "").strip()
        projection_version = str(target.get("projection_version") or "").strip()
        schema_version = str(target.get("schema_version") or "").strip()
        missing = [
            key
            for key, value in (
                ("target_type", target_type),
                ("target_id", target_id),
                ("window", window),
                ("scope", scope),
                ("projection_version", projection_version),
                ("schema_version", schema_version),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"{reason} dirty target missing required fields: {', '.join(missing)}")
        source_watermark_ms = int(target.get("source_watermark_ms") or 0)
        priority = _priority_value(target)
        due_at_ms = int(target.get("due_at_ms") or default_due_at_ms)
        record = {
            "target_type": target_type,
            "target_id": target_id,
            "window": window,
            "scope": scope,
            "projection_version": projection_version,
            "schema_version": schema_version,
            "source_watermark_ms": source_watermark_ms,
            "priority": priority,
            "due_at_ms": due_at_ms,
        }
        record["payload_hash"] = str(target.get("payload_hash") or _payload_hash({**record, "dirty_reason": reason}))
        key = (target_type, target_id, window, scope)
        existing = records.get(key)
        if existing is None:
            records[key] = record
            continue
        if source_watermark_ms >= int(existing["source_watermark_ms"]):
            record["priority"] = min(int(existing["priority"]), priority)
            record["due_at_ms"] = min(int(existing["due_at_ms"]), due_at_ms)
            records[key] = record
        else:
            existing["priority"] = min(int(existing["priority"]), priority)
            existing["due_at_ms"] = min(int(existing["due_at_ms"]), due_at_ms)
    return list(records.values())


def _target_params(records: list[dict[str, Any]]) -> dict[str, list[Any]]:
    return {
        "target_types": [str(record["target_type"]) for record in records],
        "target_ids": [str(record["target_id"]) for record in records],
        "windows": [str(record["window"]) for record in records],
        "scopes": [str(record["scope"]) for record in records],
        "projection_versions": [str(record["projection_version"]) for record in records],
        "schema_versions": [str(record["schema_version"]) for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "source_watermark_ms_values": [int(record["source_watermark_ms"]) for record in records],
        "priorities": [int(record["priority"]) for record in records],
        "due_at_ms_values": [int(record["due_at_ms"]) for record in records],
    }


def _claim_records(claims: Iterable[Mapping[str, Any]], *, label: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for claim in claims:
        target_type = str(claim.get("target_type") or "").strip()
        target_id = str(claim.get("target_id") or "").strip()
        window = str(claim.get("window") or "").strip()
        scope = str(claim.get("scope") or "").strip()
        projection_version = str(claim.get("projection_version") or "").strip()
        schema_version = str(claim.get("schema_version") or "").strip()
        if not target_type or not target_id or not window or not scope:
            raise ValueError(f"{label} completion requires full target key from claim_due")
        if not projection_version:
            raise ValueError(f"{label} completion requires projection_version from claim_due")
        if not schema_version:
            raise ValueError(f"{label} completion requires schema_version from claim_due")
        payload_hash = _completion_payload_hash(claim, label=label)
        lease_owner = _completion_lease_owner(claim, label=label)
        attempt_count = _completion_attempt_count(claim, label=label)
        if not payload_hash:
            raise ValueError(f"{label} completion requires payload_hash from claim_due")
        if not lease_owner:
            raise ValueError(f"{label} completion requires lease_owner from claim_due")
        if attempt_count <= 0:
            raise ValueError(f"{label} completion requires attempt_count from claim_due")
        records.append(
            {
                "target_type": target_type,
                "target_id": target_id,
                "window": window,
                "scope": scope,
                "projection_version": projection_version,
                "schema_version": schema_version,
                "payload_hash": payload_hash,
                "lease_owner": lease_owner,
                "attempt_count": attempt_count,
            }
        )
    return records


def _completion_attempt_count(claim: Mapping[str, Any], *, label: str) -> int:
    try:
        attempt_count = int(claim["attempt_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} completion requires attempt_count from claim_due") from exc
    if attempt_count <= 0:
        raise ValueError(f"{label} completion requires attempt_count from claim_due")
    return attempt_count


def _completion_lease_owner(claim: Mapping[str, Any], *, label: str) -> str:
    try:
        value = claim["lease_owner"]
    except KeyError as exc:
        raise ValueError(f"{label} completion requires lease_owner from claim_due") from exc
    if value is None:
        raise ValueError(f"{label} completion requires lease_owner from claim_due")
    lease_owner = str(value).strip()
    if not lease_owner:
        raise ValueError(f"{label} completion requires lease_owner from claim_due")
    return lease_owner


def _completion_payload_hash(claim: Mapping[str, Any], *, label: str) -> str:
    try:
        value = claim["payload_hash"]
    except KeyError as exc:
        raise ValueError(f"{label} completion requires payload_hash from claim_due") from exc
    if value is None:
        raise ValueError(f"{label} completion requires payload_hash from claim_due")
    payload_hash = str(value).strip()
    if not payload_hash:
        raise ValueError(f"{label} completion requires payload_hash from claim_due")
    return payload_hash


def _claim_params(records: list[dict[str, Any]]) -> dict[str, list[Any]]:
    return {
        "target_types": [str(record["target_type"]) for record in records],
        "target_ids": [str(record["target_id"]) for record in records],
        "windows": [str(record["window"]) for record in records],
        "scopes": [str(record["scope"]) for record in records],
        "projection_versions": [str(record["projection_version"]) for record in records],
        "schema_versions": [str(record["schema_version"]) for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "lease_owners": [str(record["lease_owner"]) for record in records],
        "attempt_counts": [int(record["attempt_count"]) for record in records],
    }


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("narrative_admission_dirty_target_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int):
        raise TypeError("narrative_admission_dirty_target_rowcount_invalid")
    if rowcount < 0:
        raise TypeError("narrative_admission_dirty_target_rowcount_invalid")
    return rowcount


def _priority_value(row: Mapping[str, Any]) -> int:
    raw_priority = row.get("priority")
    if raw_priority in (None, ""):
        return 100
    return int(str(raw_priority))


def _payload_hash(payload: Mapping[str, Any]) -> str:
    return stable_dirty_target_payload_hash(payload)
