from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from parallax.domains.token_intel._constants import TOKEN_RADAR_PROJECTION_VERSION
from parallax.platform.current_read_model_payload_hash import stable_dirty_target_payload_hash
from parallax.platform.db.postgres_client import require_transaction
from parallax.platform.db.queue_terminal import terminalize_source_row
from parallax.platform.db.write_contract import expect_mutation_count, mutation_count
from parallax.platform.validation import require_nonnegative_int, require_positive_int

MARKET_DIRTY_MIN_INTERVAL_MS = 60_000

MARKET_DIRTY_REASONS = frozenset(
    {
        "market_tick_current_changed",
        "market_tick_current_updated",
        "market_tick_written",
        "ops_market_current_repair",
    }
)
REPAIR_DIRTY_REASONS = frozenset({"ops_repair", "ops_events_repair", "projection_catch_up"})


def dirty_kind_flags(reason: str) -> dict[str, bool]:
    normalized = str(reason or "").strip()
    repair_dirty = normalized in REPAIR_DIRTY_REASONS or (
        normalized.startswith("ops_") and normalized.endswith("_repair")
    )
    market_dirty = normalized in MARKET_DIRTY_REASONS or normalized.startswith("market_")
    return {
        "market_dirty": market_dirty,
        "repair_dirty": repair_dirty,
    }


def dirty_payload_hash(payload: Mapping[str, Any]) -> str:
    return stable_dirty_target_payload_hash(payload)


class TokenRadarDirtyTargetRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def enqueue_targets(
        self,
        rows: Iterable[Mapping[str, Any]],
        *,
        reason: str,
        now_ms: int,
        due_at_ms: int | None = None,
    ) -> int:
        require_transaction(self.conn, operation="enqueue_token_radar_dirty_targets")
        records = _dirty_records(rows, reason=reason, now_ms=int(now_ms), due_at_ms=due_at_ms)
        if not records:
            return 0
        cursor = self.conn.execute(
            _TARGET_DIRTY_INSERT_SQL,
            _target_dirty_params(records, reason=reason, now_ms=now_ms),
        )
        return mutation_count(cursor, error_code="token_radar_dirty_target_rowcount_invalid")

    def enqueue_market_product_targets(
        self,
        rows: Iterable[Mapping[str, Any] | tuple[str, str]],
        *,
        reason: str,
        now_ms: int,
    ) -> int:
        require_transaction(self.conn, operation="enqueue_token_radar_market_dirty_targets")
        records = _market_product_target_records(rows)
        if not records:
            return 0
        cursor = self.conn.execute(
            _MARKET_TARGET_INSERT_SQL,
            {
                "target_type_keys": [record["target_type_key"] for record in records],
                "identity_ids": [record["identity_id"] for record in records],
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "dirty_reason": str(reason),
                **dirty_kind_flags(reason),
                "now_ms": int(now_ms),
                "market_dirty_min_interval_ms": MARKET_DIRTY_MIN_INTERVAL_MS,
            },
        )
        return mutation_count(cursor, error_code="token_radar_dirty_target_rowcount_invalid")

    def claim_due(
        self,
        *,
        limit: int,
        lease_ms: int,
        now_ms: int,
        lease_owner: str,
    ) -> list[dict[str, Any]]:
        parsed_limit = require_nonnegative_int(
            limit,
            error_code="token_radar_dirty_target_claim_limit_required",
        )
        parsed_lease_ms = require_positive_int(
            lease_ms,
            error_code="token_radar_dirty_target_claim_lease_ms_required",
        )
        require_transaction(self.conn, operation="claim_token_radar_dirty_targets")

        cursor = self.conn.execute(
            """
            WITH due AS (
              SELECT target_type_key, identity_id
              FROM token_radar_dirty_targets
              WHERE due_at_ms <= %(now_ms)s
                AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
              ORDER BY due_at_ms ASC, updated_at_ms ASC, target_type_key ASC, identity_id ASC
              LIMIT %(limit)s
              FOR UPDATE SKIP LOCKED
            )
            UPDATE token_radar_dirty_targets queue
            SET leased_until_ms = %(leased_until_ms)s,
                lease_owner = %(lease_owner)s,
                attempt_count = queue.attempt_count + 1,
                last_error = NULL,
                updated_at_ms = %(now_ms)s
            FROM due
            WHERE queue.target_type_key = due.target_type_key
              AND queue.identity_id = due.identity_id
            RETURNING queue.*
            """,
            {
                "now_ms": int(now_ms),
                "leased_until_ms": int(now_ms) + parsed_lease_ms,
                "lease_owner": str(lease_owner),
                "limit": parsed_limit,
            },
        )
        rows = cursor.fetchall()
        expect_mutation_count(cursor, expected=len(rows), error_code="token_radar_dirty_target_rowcount_invalid")
        return [dict(row) for row in rows]

    def enqueue_recent_resolved_targets(
        self,
        *,
        since_ms: int,
        now_ms: int,
        limit: int,
        reason: str,
    ) -> int:
        require_transaction(self.conn, operation="enqueue_recent_token_radar_targets")
        parsed_limit = require_nonnegative_int(
            limit,
            error_code="token_radar_dirty_target_limit_required",
        )

        cursor = self.conn.execute(
            _RECENT_RESOLVED_TARGET_ENQUEUE_SQL,
            {
                "since_ms": int(since_ms),
                "now_ms": int(now_ms),
                "limit": parsed_limit,
                "dirty_reason": str(reason),
                **dirty_kind_flags(reason),
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
            },
        )
        return mutation_count(cursor, error_code="token_radar_dirty_target_rowcount_invalid")

    def count_recent_resolved_target_candidates(self, *, since_ms: int, now_ms: int, limit: int) -> int:
        parsed_limit = require_nonnegative_int(
            limit,
            error_code="token_radar_dirty_target_limit_required",
        )
        row = self.conn.execute(
            """
            WITH recent AS (
              SELECT
                token_intent_resolutions.target_type AS target_type_key,
                token_intent_resolutions.target_id AS identity_id,
                MAX(events.received_at_ms) AS source_max_received_at_ms
              FROM token_intent_resolutions
              JOIN token_intents ON token_intents.intent_id = token_intent_resolutions.intent_id
              JOIN events ON events.event_id = token_intents.event_id
              WHERE events.received_at_ms >= %(since_ms)s
                AND events.received_at_ms <= %(now_ms)s
                AND token_intent_resolutions.is_current = true
                AND token_intent_resolutions.target_type IN ('Asset', 'CexToken')
                AND token_intent_resolutions.target_id IS NOT NULL
              GROUP BY token_intent_resolutions.target_type, token_intent_resolutions.target_id
              ORDER BY MAX(events.received_at_ms) DESC,
                       token_intent_resolutions.target_type ASC,
                       token_intent_resolutions.target_id ASC
              LIMIT %(limit)s
            )
            SELECT COUNT(*) AS count
            FROM recent
            """,
            {"since_ms": int(since_ms), "now_ms": int(now_ms), "limit": parsed_limit},
        ).fetchone()
        return _count(row)

    def count_recent_resolved_target_enqueue_candidates(self, *, since_ms: int, now_ms: int, limit: int) -> int:
        parsed_limit = require_nonnegative_int(
            limit,
            error_code="token_radar_dirty_target_limit_required",
        )
        row = self.conn.execute(
            _RECENT_RESOLVED_TARGET_ELIGIBLE_CTES + "SELECT COUNT(*) AS count FROM eligible",
            {
                "since_ms": int(since_ms),
                "now_ms": int(now_ms),
                "limit": parsed_limit,
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
            },
        ).fetchone()
        return _count(row)

    def count_market_current_target_candidates(self, *, since_ms: int, now_ms: int, limit: int) -> int:
        parsed_limit = require_nonnegative_int(
            limit,
            error_code="token_radar_dirty_target_limit_required",
        )
        row = self.conn.execute(
            """
            WITH market_current_candidates AS (
              SELECT
                current_row.target_type,
                current_row.target_id,
                GREATEST(current_row.tick_observed_at_ms, current_row.updated_at_ms) AS watermark_ms
              FROM market_tick_current current_row
              WHERE GREATEST(current_row.tick_observed_at_ms, current_row.updated_at_ms) >= %(since_ms)s
                AND GREATEST(current_row.tick_observed_at_ms, current_row.updated_at_ms) <= %(now_ms)s
              ORDER BY watermark_ms DESC, current_row.target_type ASC, current_row.target_id ASC
              LIMIT %(limit)s
            )
            SELECT COUNT(*) AS count
            FROM market_current_candidates
            """,
            {"since_ms": int(since_ms), "now_ms": int(now_ms), "limit": parsed_limit},
        ).fetchone()
        return _count(row)

    def count_market_current_target_enqueue_candidates(self, *, since_ms: int, now_ms: int, limit: int) -> int:
        parsed_limit = require_nonnegative_int(
            limit,
            error_code="token_radar_dirty_target_limit_required",
        )
        row = self.conn.execute(
            _MARKET_CURRENT_ELIGIBLE_CTES + "SELECT COUNT(*) AS count FROM eligible",
            _market_current_params(
                since_ms=since_ms,
                now_ms=now_ms,
                limit=parsed_limit,
                reason="ops_market_current_repair",
            ),
        ).fetchone()
        return _count(row)

    def enqueue_market_current_targets(
        self,
        *,
        since_ms: int,
        now_ms: int,
        limit: int,
        reason: str,
    ) -> int:
        require_transaction(self.conn, operation="enqueue_token_radar_market_current_targets")
        parsed_limit = require_nonnegative_int(
            limit,
            error_code="token_radar_dirty_target_limit_required",
        )

        cursor = self.conn.execute(
            _MARKET_CURRENT_ENQUEUE_SQL,
            _market_current_params(
                since_ms=since_ms,
                now_ms=now_ms,
                limit=parsed_limit,
                reason=reason,
            ),
        )
        return mutation_count(cursor, error_code="token_radar_dirty_target_rowcount_invalid")

    def mark_done(
        self,
        keys: Iterable[Mapping[str, Any]],
        *,
        now_ms: int,
    ) -> int:
        require_transaction(self.conn, operation="complete_token_radar_dirty_targets")
        records = _key_records(keys)
        if not records:
            return 0

        cursor = self.conn.execute(
            """
            WITH done AS (
              SELECT *
              FROM unnest(
                %(target_type_keys)s::text[],
                %(identity_ids)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS done(target_type_key, identity_id, payload_hash, lease_owner, attempt_count)
            )
            DELETE FROM token_radar_dirty_targets queue
            USING done
            WHERE queue.target_type_key = done.target_type_key
              AND queue.identity_id = done.identity_id
              AND queue.payload_hash = done.payload_hash
              AND queue.lease_owner = done.lease_owner
              AND queue.attempt_count = done.attempt_count
            """,
            _key_params(records),
        )
        return mutation_count(cursor, error_code="token_radar_dirty_target_rowcount_invalid")

    def mark_error(
        self,
        keys: Iterable[Mapping[str, Any]],
        *,
        error: str,
        retry_ms: int,
        max_attempts: int,
        worker_name: str,
        now_ms: int,
    ) -> int:
        records = _key_records(keys)
        if not records:
            return 0
        parsed_max_attempts = _required_max_attempts(max_attempts)
        parsed_retry_ms = require_positive_int(
            retry_ms,
            error_code="token_radar_dirty_target_retry_ms_required",
        )
        parsed_worker_name = _required_text(worker_name, "worker_name")
        require_transaction(self.conn, operation="fail_token_radar_dirty_targets")
        retry_records = [record for record in records if int(record["attempt_count"]) < parsed_max_attempts]
        exhausted_records = [record for record in records if int(record["attempt_count"]) >= parsed_max_attempts]
        retry_params = {
            **_key_params(retry_records),
            "due_at_ms": int(now_ms) + parsed_retry_ms,
            "now_ms": int(now_ms),
            "last_error": str(error)[:2048],
        }

        changed = 0
        if retry_records:
            cursor = self.conn.execute(
                """
                    WITH failed AS (
                      SELECT *
                      FROM unnest(
                        %(target_type_keys)s::text[],
                        %(identity_ids)s::text[],
                        %(payload_hashes)s::text[],
                        %(lease_owners)s::text[],
                        %(attempt_counts)s::bigint[]
                      ) AS failed(target_type_key, identity_id, payload_hash, lease_owner, attempt_count)
                    )
                    UPDATE token_radar_dirty_targets queue
                    SET due_at_ms = %(due_at_ms)s,
                        leased_until_ms = NULL,
                        lease_owner = NULL,
                        last_error = %(last_error)s,
                        updated_at_ms = %(now_ms)s
                    FROM failed
                    WHERE queue.target_type_key = failed.target_type_key
                      AND queue.identity_id = failed.identity_id
                      AND queue.payload_hash = failed.payload_hash
                      AND queue.lease_owner = failed.lease_owner
                      AND queue.attempt_count = failed.attempt_count
                    """,
                retry_params,
            )
            changed += mutation_count(cursor, error_code="token_radar_dirty_target_rowcount_invalid")
        if exhausted_records:
            deleted_rows, deleted_count = self._delete_claims_returning(exhausted_records)
            changed += deleted_count
            for row in deleted_rows:
                terminalize_source_row(
                    self.conn,
                    worker_name=parsed_worker_name,
                    source_table="token_radar_dirty_targets",
                    target_key=_terminal_target_key(row),
                    source_row=row,
                    final_status="terminal",
                    final_reason=_retry_budget_exhausted_reason(error),
                    now_ms=now_ms,
                    attempt_count=int(row["attempt_count"]),
                    payload_hash=_completion_payload_hash(row),
                    first_seen_at_ms=_optional_int(row.get("first_dirty_at_ms")),
                    last_attempted_at_ms=now_ms,
                )
        return changed

    def _delete_claims_returning(self, records: list[dict[str, str | int]]) -> tuple[list[dict[str, Any]], int]:
        cursor = self.conn.execute(
            """
            WITH done AS (
              SELECT *
              FROM unnest(
                %(target_type_keys)s::text[],
                %(identity_ids)s::text[],
                %(payload_hashes)s::text[],
                %(lease_owners)s::text[],
                %(attempt_counts)s::bigint[]
              ) AS done(target_type_key, identity_id, payload_hash, lease_owner, attempt_count)
            )
            DELETE FROM token_radar_dirty_targets queue
            USING done
            WHERE queue.target_type_key = done.target_type_key
              AND queue.identity_id = done.identity_id
              AND queue.payload_hash = done.payload_hash
              AND queue.lease_owner = done.lease_owner
              AND queue.attempt_count = done.attempt_count
            RETURNING queue.*
            """,
            _key_params(records),
        )
        rows = cursor.fetchall()
        deleted_count = expect_mutation_count(
            cursor,
            expected=len(rows),
            error_code="token_radar_dirty_target_rowcount_invalid",
        )
        return [dict(row) for row in rows], deleted_count


def _required_max_attempts(value: Any) -> int:
    return require_positive_int(value, error_code="token_radar_dirty_target_max_attempts_required")


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"token_radar_dirty_target_{field_name}_required")
    return text


def _terminal_target_key(row: Mapping[str, Any]) -> str:
    return f"{_completion_text(row, 'target_type_key')}:{_completion_text(row, 'identity_id')}"


def _retry_budget_exhausted_reason(error: str) -> str:
    message = str(error or "").strip()
    return f"token_radar_projection_retry_budget_exhausted: {message}"[:2048]


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


_TARGET_DIRTY_INSERT_SQL = """
WITH incoming AS (
  SELECT *
  FROM unnest(
    %(target_type_keys)s::text[],
    %(identity_ids)s::text[],
    %(payload_hashes)s::text[]
  ) AS incoming(target_type_key, identity_id, payload_hash)
)
INSERT INTO token_radar_dirty_targets(
  target_type_key,
  identity_id,
  dirty_reason,
  market_dirty,
  repair_dirty,
  payload_hash,
  due_at_ms,
  leased_until_ms,
  lease_owner,
  attempt_count,
  last_error,
  first_dirty_at_ms,
  updated_at_ms
)
SELECT
  incoming.target_type_key,
  incoming.identity_id,
  %(dirty_reason)s,
  %(market_dirty)s,
  %(repair_dirty)s,
  incoming.payload_hash,
  %(due_at_ms)s,
  NULL,
  NULL,
  0,
  NULL,
  %(now_ms)s,
  %(now_ms)s
FROM incoming
ON CONFLICT(target_type_key, identity_id) DO UPDATE SET
  dirty_reason = CASE
    WHEN token_radar_dirty_targets.dirty_reason = EXCLUDED.dirty_reason
    THEN token_radar_dirty_targets.dirty_reason
    ELSE 'mixed'
  END,
  market_dirty = token_radar_dirty_targets.market_dirty OR EXCLUDED.market_dirty,
  repair_dirty = token_radar_dirty_targets.repair_dirty OR EXCLUDED.repair_dirty,
  payload_hash = EXCLUDED.payload_hash,
  due_at_ms = LEAST(token_radar_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
  leased_until_ms = NULL,
  lease_owner = NULL,
  attempt_count = CASE
    WHEN token_radar_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
    THEN 0
    ELSE token_radar_dirty_targets.attempt_count
  END,
  last_error = NULL,
  first_dirty_at_ms = token_radar_dirty_targets.first_dirty_at_ms,
  updated_at_ms = EXCLUDED.updated_at_ms
WHERE token_radar_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
   OR token_radar_dirty_targets.dirty_reason IS DISTINCT FROM EXCLUDED.dirty_reason
   OR token_radar_dirty_targets.market_dirty IS DISTINCT FROM EXCLUDED.market_dirty
   OR token_radar_dirty_targets.repair_dirty IS DISTINCT FROM EXCLUDED.repair_dirty
   OR token_radar_dirty_targets.due_at_ms > EXCLUDED.due_at_ms
   OR token_radar_dirty_targets.leased_until_ms IS NOT NULL
   OR token_radar_dirty_targets.lease_owner IS NOT NULL
   OR token_radar_dirty_targets.last_error IS NOT NULL
"""


_MARKET_TARGET_INSERT_SQL = """
WITH incoming(target_type_key, identity_id) AS (
  SELECT *
  FROM unnest(%(target_type_keys)s::text[], %(identity_ids)s::text[])
),
latest_feature AS (
  SELECT
    features.target_type_key,
    features.identity_id,
    MAX(features.latest_market_observed_at_ms) AS latest_market_observed_at_ms
  FROM token_radar_target_features features
  JOIN incoming
    ON incoming.target_type_key = features.target_type_key
   AND incoming.identity_id = features.identity_id
  WHERE features.projection_version = %(projection_version)s
  GROUP BY features.target_type_key, features.identity_id
),
scheduled AS (
  SELECT
    incoming.*,
    CASE
      WHEN latest_feature.latest_market_observed_at_ms > %(now_ms)s - %(market_dirty_min_interval_ms)s
      THEN latest_feature.latest_market_observed_at_ms + %(market_dirty_min_interval_ms)s
      ELSE %(now_ms)s
    END AS due_at_ms
  FROM incoming
  LEFT JOIN latest_feature
    ON latest_feature.target_type_key = incoming.target_type_key
   AND latest_feature.identity_id = incoming.identity_id
)
INSERT INTO token_radar_dirty_targets(
  target_type_key,
  identity_id,
  dirty_reason,
  market_dirty,
  repair_dirty,
  payload_hash,
  due_at_ms,
  leased_until_ms,
  lease_owner,
  attempt_count,
  last_error,
  first_dirty_at_ms,
  updated_at_ms
)
SELECT
  scheduled.target_type_key,
  scheduled.identity_id,
  %(dirty_reason)s,
  %(market_dirty)s,
  %(repair_dirty)s,
  encode(
    sha256(convert_to(scheduled.target_type_key || ':' || scheduled.identity_id || ':' || %(dirty_reason)s, 'UTF8')),
    'hex'
  ),
  scheduled.due_at_ms,
  NULL,
  NULL,
  0,
  NULL,
  %(now_ms)s,
  %(now_ms)s
FROM scheduled
ON CONFLICT(target_type_key, identity_id) DO UPDATE SET
  dirty_reason = CASE
    WHEN token_radar_dirty_targets.dirty_reason = EXCLUDED.dirty_reason
    THEN token_radar_dirty_targets.dirty_reason
    ELSE 'mixed'
  END,
  market_dirty = token_radar_dirty_targets.market_dirty OR EXCLUDED.market_dirty,
  repair_dirty = token_radar_dirty_targets.repair_dirty OR EXCLUDED.repair_dirty,
  payload_hash = EXCLUDED.payload_hash,
  due_at_ms = LEAST(token_radar_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
  leased_until_ms = NULL,
  lease_owner = NULL,
  attempt_count = CASE
    WHEN token_radar_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
    THEN 0
    ELSE token_radar_dirty_targets.attempt_count
  END,
  last_error = NULL,
  first_dirty_at_ms = token_radar_dirty_targets.first_dirty_at_ms,
  updated_at_ms = EXCLUDED.updated_at_ms
WHERE token_radar_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
   OR token_radar_dirty_targets.dirty_reason IS DISTINCT FROM EXCLUDED.dirty_reason
   OR token_radar_dirty_targets.market_dirty IS DISTINCT FROM EXCLUDED.market_dirty
   OR token_radar_dirty_targets.repair_dirty IS DISTINCT FROM EXCLUDED.repair_dirty
   OR token_radar_dirty_targets.due_at_ms > EXCLUDED.due_at_ms
   OR token_radar_dirty_targets.leased_until_ms IS NOT NULL
   OR token_radar_dirty_targets.lease_owner IS NOT NULL
   OR token_radar_dirty_targets.last_error IS NOT NULL
"""


_RECENT_RESOLVED_TARGET_ELIGIBLE_CTES = """
WITH recent AS (
  SELECT
    token_intent_resolutions.target_type AS target_type_key,
    token_intent_resolutions.target_id AS identity_id,
    MAX(events.received_at_ms) AS source_max_received_at_ms
  FROM token_intent_resolutions
  JOIN token_intents ON token_intents.intent_id = token_intent_resolutions.intent_id
  JOIN events ON events.event_id = token_intents.event_id
  WHERE events.received_at_ms >= %(since_ms)s
    AND events.received_at_ms <= %(now_ms)s
    AND token_intent_resolutions.is_current = true
    AND token_intent_resolutions.target_type IN ('Asset', 'CexToken')
    AND token_intent_resolutions.target_id IS NOT NULL
  GROUP BY token_intent_resolutions.target_type, token_intent_resolutions.target_id
  ORDER BY MAX(events.received_at_ms) DESC,
           token_intent_resolutions.target_type ASC,
           token_intent_resolutions.target_id ASC
  LIMIT %(limit)s
),
latest_feature AS (
  SELECT
    features.target_type_key,
    features.identity_id,
    MAX(features.latest_event_received_at_ms) AS latest_event_received_at_ms
  FROM token_radar_target_features features
  JOIN recent
    ON recent.target_type_key = features.target_type_key
   AND recent.identity_id = features.identity_id
  WHERE features.projection_version = %(projection_version)s
  GROUP BY features.target_type_key, features.identity_id
),
eligible AS (
  SELECT recent.*
  FROM recent
  LEFT JOIN latest_feature
    ON latest_feature.target_type_key = recent.target_type_key
   AND latest_feature.identity_id = recent.identity_id
  WHERE COALESCE(latest_feature.latest_event_received_at_ms, 0) < recent.source_max_received_at_ms
)
"""


_RECENT_RESOLVED_TARGET_ENQUEUE_SQL = (
    _RECENT_RESOLVED_TARGET_ELIGIBLE_CTES
    + """
INSERT INTO token_radar_dirty_targets(
  target_type_key,
  identity_id,
  dirty_reason,
  market_dirty,
  repair_dirty,
  payload_hash,
  due_at_ms,
  leased_until_ms,
  lease_owner,
  attempt_count,
  last_error,
  first_dirty_at_ms,
  updated_at_ms
)
SELECT
  eligible.target_type_key,
  eligible.identity_id,
  %(dirty_reason)s,
  %(market_dirty)s,
  %(repair_dirty)s,
  encode(
    sha256(
      convert_to(
        eligible.target_type_key || ':' ||
        eligible.identity_id || ':' ||
        %(dirty_reason)s || ':' ||
        eligible.source_max_received_at_ms::text,
        'UTF8'
      )
    ),
    'hex'
  ),
  %(now_ms)s,
  NULL,
  NULL,
  0,
  NULL,
  %(now_ms)s,
  %(now_ms)s
FROM eligible
ON CONFLICT(target_type_key, identity_id) DO UPDATE SET
  dirty_reason = CASE
    WHEN token_radar_dirty_targets.dirty_reason = EXCLUDED.dirty_reason
    THEN token_radar_dirty_targets.dirty_reason
    ELSE 'mixed'
  END,
  market_dirty = token_radar_dirty_targets.market_dirty OR EXCLUDED.market_dirty,
  repair_dirty = token_radar_dirty_targets.repair_dirty OR EXCLUDED.repair_dirty,
  payload_hash = EXCLUDED.payload_hash,
  due_at_ms = LEAST(token_radar_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
  leased_until_ms = NULL,
  lease_owner = NULL,
  attempt_count = CASE
    WHEN token_radar_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
    THEN 0
    ELSE token_radar_dirty_targets.attempt_count
  END,
  last_error = NULL,
  first_dirty_at_ms = token_radar_dirty_targets.first_dirty_at_ms,
  updated_at_ms = EXCLUDED.updated_at_ms
WHERE token_radar_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
   OR token_radar_dirty_targets.dirty_reason IS DISTINCT FROM EXCLUDED.dirty_reason
   OR token_radar_dirty_targets.market_dirty IS DISTINCT FROM EXCLUDED.market_dirty
   OR token_radar_dirty_targets.repair_dirty IS DISTINCT FROM EXCLUDED.repair_dirty
   OR token_radar_dirty_targets.due_at_ms > EXCLUDED.due_at_ms
   OR token_radar_dirty_targets.leased_until_ms IS NOT NULL
   OR token_radar_dirty_targets.lease_owner IS NOT NULL
   OR token_radar_dirty_targets.last_error IS NOT NULL
"""
)


_MARKET_CURRENT_ELIGIBLE_CTES = """
WITH market_current_candidates AS (
  SELECT
    current_row.target_type,
    current_row.target_id,
    GREATEST(current_row.tick_observed_at_ms, current_row.updated_at_ms) AS watermark_ms
  FROM market_tick_current current_row
  WHERE GREATEST(current_row.tick_observed_at_ms, current_row.updated_at_ms) >= %(since_ms)s
    AND GREATEST(current_row.tick_observed_at_ms, current_row.updated_at_ms) <= %(now_ms)s
  ORDER BY watermark_ms DESC, current_row.target_type ASC, current_row.target_id ASC
  LIMIT %(limit)s
),
mapped AS (
  SELECT DISTINCT
    'Asset'::text AS target_type_key,
    registry_assets.asset_id AS identity_id,
    MAX(market_current_candidates.watermark_ms) AS market_current_watermark_ms
  FROM market_current_candidates
  JOIN registry_assets
    ON market_current_candidates.target_type = 'chain_token'
   AND registry_assets.chain_id || ':' || registry_assets.address = market_current_candidates.target_id
   AND registry_assets.status IN ('candidate', 'canonical')
  GROUP BY registry_assets.asset_id
  UNION
  SELECT DISTINCT
    'CexToken'::text AS target_type_key,
    price_feeds.subject_id AS identity_id,
    MAX(market_current_candidates.watermark_ms) AS market_current_watermark_ms
  FROM market_current_candidates
  JOIN price_feeds
    ON market_current_candidates.target_type = 'cex_symbol'
   AND price_feeds.subject_type = 'CexToken'
   AND price_feeds.provider || ':' || price_feeds.native_market_id = market_current_candidates.target_id
   AND price_feeds.provider = 'binance'
   AND price_feeds.feed_type = 'cex_swap'
   AND price_feeds.quote_symbol = 'USDT'
   AND price_feeds.status = 'canonical'
  GROUP BY price_feeds.subject_id
),
latest_feature AS (
  SELECT
    features.target_type_key,
    features.identity_id,
    MAX(features.latest_market_observed_at_ms) AS latest_market_observed_at_ms
  FROM token_radar_target_features features
  JOIN mapped
    ON mapped.target_type_key = features.target_type_key
   AND mapped.identity_id = features.identity_id
  WHERE features.projection_version = %(projection_version)s
  GROUP BY features.target_type_key, features.identity_id
),
eligible AS (
  SELECT
    mapped.*,
    CASE
      WHEN latest_feature.latest_market_observed_at_ms > %(now_ms)s - %(market_dirty_min_interval_ms)s
      THEN latest_feature.latest_market_observed_at_ms + %(market_dirty_min_interval_ms)s
      ELSE %(now_ms)s
    END AS due_at_ms
  FROM mapped
  LEFT JOIN latest_feature
    ON latest_feature.target_type_key = mapped.target_type_key
   AND latest_feature.identity_id = mapped.identity_id
  WHERE mapped.identity_id IS NOT NULL
    AND mapped.market_current_watermark_ms >= %(since_ms)s
)
"""


_MARKET_CURRENT_ENQUEUE_SQL = (
    _MARKET_CURRENT_ELIGIBLE_CTES
    + """
INSERT INTO token_radar_dirty_targets(
  target_type_key,
  identity_id,
  dirty_reason,
  market_dirty,
  repair_dirty,
  payload_hash,
  due_at_ms,
  leased_until_ms,
  lease_owner,
  attempt_count,
  last_error,
  first_dirty_at_ms,
  updated_at_ms
)
SELECT
  eligible.target_type_key,
  eligible.identity_id,
  %(dirty_reason)s,
  %(market_dirty)s,
  %(repair_dirty)s,
  encode(
    sha256(
      convert_to(
        eligible.target_type_key || ':' ||
        eligible.identity_id || ':' ||
        %(dirty_reason)s || ':' ||
        eligible.market_current_watermark_ms::text,
        'UTF8'
      )
    ),
    'hex'
  ),
  eligible.due_at_ms,
  NULL,
  NULL,
  0,
  NULL,
  %(now_ms)s,
  %(now_ms)s
FROM eligible
ON CONFLICT(target_type_key, identity_id) DO UPDATE SET
  dirty_reason = CASE
    WHEN token_radar_dirty_targets.dirty_reason = EXCLUDED.dirty_reason
    THEN token_radar_dirty_targets.dirty_reason
    ELSE 'mixed'
  END,
  market_dirty = token_radar_dirty_targets.market_dirty OR EXCLUDED.market_dirty,
  repair_dirty = token_radar_dirty_targets.repair_dirty OR EXCLUDED.repair_dirty,
  payload_hash = EXCLUDED.payload_hash,
  due_at_ms = LEAST(token_radar_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
  leased_until_ms = NULL,
  lease_owner = NULL,
  attempt_count = CASE
    WHEN token_radar_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
    THEN 0
    ELSE token_radar_dirty_targets.attempt_count
  END,
  last_error = NULL,
  first_dirty_at_ms = token_radar_dirty_targets.first_dirty_at_ms,
  updated_at_ms = EXCLUDED.updated_at_ms
WHERE token_radar_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
   OR token_radar_dirty_targets.dirty_reason IS DISTINCT FROM EXCLUDED.dirty_reason
   OR token_radar_dirty_targets.market_dirty IS DISTINCT FROM EXCLUDED.market_dirty
   OR token_radar_dirty_targets.repair_dirty IS DISTINCT FROM EXCLUDED.repair_dirty
   OR token_radar_dirty_targets.due_at_ms > EXCLUDED.due_at_ms
   OR token_radar_dirty_targets.leased_until_ms IS NOT NULL
   OR token_radar_dirty_targets.lease_owner IS NOT NULL
   OR token_radar_dirty_targets.last_error IS NOT NULL
"""
)


def _target_dirty_params(records: list[dict[str, Any]], *, reason: str, now_ms: int) -> dict[str, Any]:
    due_at_ms = records[0]["due_at_ms"] if records else now_ms
    return {
        "target_type_keys": [record["target_type_key"] for record in records],
        "identity_ids": [record["identity_id"] for record in records],
        "payload_hashes": [record["payload_hash"] for record in records],
        "dirty_reason": str(reason),
        **dirty_kind_flags(reason),
        "due_at_ms": int(due_at_ms),
        "now_ms": int(now_ms),
    }


def _dirty_records(
    rows: Iterable[Mapping[str, Any]],
    *,
    reason: str,
    now_ms: int,
    due_at_ms: int | None,
) -> list[dict[str, Any]]:
    records: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        target_type_key, identity_id = _target_key(row)
        payload_hash = dirty_payload_hash(
            {
                "target_type_key": target_type_key,
                "identity_id": identity_id,
                "dirty_reason": str(reason),
                "dirty_at_ms": int(now_ms),
            }
        )
        records[(target_type_key, identity_id)] = {
            "target_type_key": target_type_key,
            "identity_id": identity_id,
            "payload_hash": payload_hash,
            "due_at_ms": int(due_at_ms if due_at_ms is not None else now_ms),
        }
    return list(records.values())


def _key_records(keys: Iterable[Mapping[str, Any]]) -> list[dict[str, str | int]]:
    records: list[dict[str, str | int]] = []
    for key in keys:
        target_type_key, identity_id = _completion_target_key(key)
        payload_hash = _completion_payload_hash(key)
        if not payload_hash:
            raise ValueError("token radar dirty target completion requires payload_hash from claim_due")
        lease_owner = _completion_lease_owner(key)
        attempt_count = _completion_attempt_count(key)
        if not lease_owner:
            raise ValueError("token radar dirty target completion requires lease_owner from claim_due")
        if attempt_count <= 0:
            raise ValueError("token radar dirty target completion requires attempt_count from claim_due")
        records.append(
            {
                "target_type_key": str(target_type_key),
                "identity_id": str(identity_id),
                "payload_hash": payload_hash,
                "lease_owner": lease_owner,
                "attempt_count": attempt_count,
            }
        )
    return records


def _completion_target_key(key: Mapping[str, Any]) -> tuple[str, str]:
    return (
        _completion_text(key, "target_type_key"),
        _completion_text(key, "identity_id"),
    )


def _completion_text(key: Mapping[str, Any], field: str) -> str:
    try:
        value = key[field]
    except KeyError as exc:
        raise ValueError(f"token radar dirty target completion requires {field} from claim_due") from exc
    if value is None:
        raise ValueError(f"token radar dirty target completion requires {field} from claim_due")
    text = str(value).strip()
    if not text:
        raise ValueError(f"token radar dirty target completion requires {field} from claim_due")
    return text


def _completion_attempt_count(key: Mapping[str, Any]) -> int:
    try:
        value = key["attempt_count"]
    except KeyError as exc:
        raise ValueError("token radar dirty target completion requires attempt_count from claim_due") from exc
    return require_positive_int(
        value,
        error_code="token radar dirty target completion requires attempt_count from claim_due",
    )


def _completion_lease_owner(key: Mapping[str, Any]) -> str:
    try:
        value = key["lease_owner"]
    except KeyError as exc:
        raise ValueError("token radar dirty target completion requires lease_owner from claim_due") from exc
    if value is None:
        raise ValueError("token radar dirty target completion requires lease_owner from claim_due")
    lease_owner = str(value).strip()
    if not lease_owner:
        raise ValueError("token radar dirty target completion requires lease_owner from claim_due")
    return lease_owner


def _completion_payload_hash(key: Mapping[str, Any]) -> str:
    try:
        value = key["payload_hash"]
    except KeyError as exc:
        raise ValueError("token radar dirty target completion requires payload_hash from claim_due") from exc
    if value is None:
        raise ValueError("token radar dirty target completion requires payload_hash from claim_due")
    payload_hash = str(value).strip()
    if not payload_hash:
        raise ValueError("token radar dirty target completion requires payload_hash from claim_due")
    return payload_hash


def _key_params(records: list[dict[str, str | int]]) -> dict[str, Any]:
    return {
        "target_type_keys": [str(record["target_type_key"]) for record in records],
        "identity_ids": [str(record["identity_id"]) for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "lease_owners": [str(record["lease_owner"]) for record in records],
        "attempt_counts": [int(record["attempt_count"]) for record in records],
    }


def _market_product_target_records(
    rows: Iterable[Mapping[str, Any] | tuple[str, str]],
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if isinstance(row, tuple):
            target_type_key, identity_id = row
        else:
            target_type_key = str(row.get("target_type_key") or "")
            identity_id = str(row.get("identity_id") or "")
        key = (str(target_type_key or ""), str(identity_id or ""))
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        records.append({"target_type_key": key[0], "identity_id": key[1]})
    return records


def _target_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return _required_enqueue_text(row, "target_type_key"), _required_enqueue_text(row, "identity_id")


def _required_enqueue_text(row: Mapping[str, Any], field_name: str) -> str:
    try:
        value = row[field_name]
    except KeyError as exc:
        raise ValueError("token_radar_dirty_target_enqueue_identity_required") from exc
    if value is None:
        raise ValueError("token_radar_dirty_target_enqueue_identity_required")
    text = str(value).strip()
    if not text:
        raise ValueError("token_radar_dirty_target_enqueue_identity_required")
    return text


def _market_current_params(*, since_ms: int, now_ms: int, limit: int, reason: str) -> dict[str, Any]:
    return {
        "since_ms": int(since_ms),
        "now_ms": int(now_ms),
        "limit": limit,
        "dirty_reason": str(reason),
        **dirty_kind_flags(reason),
        "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
        "market_dirty_min_interval_ms": MARKET_DIRTY_MIN_INTERVAL_MS,
    }


def _count(row: Mapping[str, Any] | None) -> int:
    if not row:
        return 0
    return int(row.get("count") or 0)
