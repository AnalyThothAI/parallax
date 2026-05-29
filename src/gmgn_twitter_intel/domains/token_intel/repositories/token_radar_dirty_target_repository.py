from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from gmgn_twitter_intel.domains.token_intel._constants import TOKEN_RADAR_PROJECTION_VERSION
from gmgn_twitter_intel.platform.db.json_safety import postgres_safe_json

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
DIRTY_PAYLOAD_LIFECYCLE_FIELDS = frozenset(
    {
        "dirty_at_ms",
        "due_at_ms",
        "leased_until_ms",
        "lease_owner",
        "attempt_count",
        "updated_at_ms",
        "first_dirty_at_ms",
        "last_error",
    }
)


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
    stable_payload = {
        str(key): postgres_safe_json(value)
        for key, value in payload.items()
        if str(key) not in DIRTY_PAYLOAD_LIFECYCLE_FIELDS
    }
    encoded = json.dumps(stable_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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
        commit: bool = True,
    ) -> int:
        records = _dirty_records(rows, reason=reason, now_ms=int(now_ms), due_at_ms=due_at_ms)
        if not records:
            return 0
        self.conn.execute(_TARGET_DIRTY_INSERT_SQL, _target_dirty_params(records, reason=reason, now_ms=now_ms))
        if commit:
            self.conn.commit()
        return len(records)

    def enqueue_market_targets(
        self,
        rows: Iterable[Mapping[str, Any] | tuple[str, str]],
        *,
        reason: str,
        now_ms: int,
        due_at_ms: int | None = None,
        commit: bool = True,
    ) -> int:
        records = _market_target_records(rows)
        if not records:
            return 0
        cursor = self.conn.execute(
            _MARKET_TARGET_INSERT_SQL,
            {
                "target_types": [record["target_type"] for record in records],
                "target_ids": [record["target_id"] for record in records],
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "dirty_reason": str(reason),
                **dirty_kind_flags(reason),
                "due_at_ms": int(due_at_ms if due_at_ms is not None else now_ms),
                "now_ms": int(now_ms),
                "market_dirty_min_interval_ms": MARKET_DIRTY_MIN_INTERVAL_MS,
            },
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def claim_due(
        self,
        *,
        limit: int,
        lease_ms: int,
        now_ms: int,
        lease_owner: str,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
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
                "leased_until_ms": int(now_ms) + max(1, int(lease_ms)),
                "lease_owner": str(lease_owner),
                "limit": max(0, int(limit)),
            },
        ).fetchall()
        if commit:
            self.conn.commit()
        return [dict(row) for row in rows]

    def enqueue_recent_resolved_targets(
        self,
        *,
        since_ms: int,
        now_ms: int,
        limit: int,
        reason: str,
        commit: bool = True,
    ) -> int:
        cursor = self.conn.execute(
            _RECENT_RESOLVED_TARGET_ENQUEUE_SQL,
            {
                "since_ms": int(since_ms),
                "now_ms": int(now_ms),
                "limit": max(0, int(limit)),
                "dirty_reason": str(reason),
                **dirty_kind_flags(reason),
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
            },
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def count_recent_resolved_target_candidates(self, *, since_ms: int, now_ms: int, limit: int) -> int:
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
            {"since_ms": int(since_ms), "now_ms": int(now_ms), "limit": max(0, int(limit))},
        ).fetchone()
        return _count(row)

    def count_recent_resolved_target_enqueue_candidates(self, *, since_ms: int, now_ms: int, limit: int) -> int:
        row = self.conn.execute(
            _RECENT_RESOLVED_TARGET_ELIGIBLE_CTES + "SELECT COUNT(*) AS count FROM eligible",
            {
                "since_ms": int(since_ms),
                "now_ms": int(now_ms),
                "limit": max(0, int(limit)),
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
            },
        ).fetchone()
        return _count(row)

    def count_market_current_target_candidates(self, *, since_ms: int, now_ms: int, limit: int) -> int:
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
            {"since_ms": int(since_ms), "now_ms": int(now_ms), "limit": max(0, int(limit))},
        ).fetchone()
        return _count(row)

    def count_market_current_target_enqueue_candidates(self, *, since_ms: int, now_ms: int, limit: int) -> int:
        row = self.conn.execute(
            _MARKET_CURRENT_ELIGIBLE_CTES + "SELECT COUNT(*) AS count FROM eligible",
            _market_current_params(since_ms=since_ms, now_ms=now_ms, limit=limit, reason="ops_market_current_repair"),
        ).fetchone()
        return _count(row)

    def enqueue_market_current_targets(
        self,
        *,
        since_ms: int,
        now_ms: int,
        limit: int,
        reason: str,
        commit: bool = True,
    ) -> int:
        cursor = self.conn.execute(
            _MARKET_CURRENT_ENQUEUE_SQL,
            _market_current_params(since_ms=since_ms, now_ms=now_ms, limit=limit, reason=reason),
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def mark_done(
        self,
        keys: Iterable[Mapping[str, Any]],
        *,
        now_ms: int,
        commit: bool = True,
    ) -> int:
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
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def mark_error(
        self,
        keys: Iterable[Mapping[str, Any]],
        *,
        error: str,
        retry_ms: int,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        records = _key_records(keys)
        if not records:
            return 0
        params = _key_params(records)
        params.update(
            {
                "due_at_ms": int(now_ms) + max(1, int(retry_ms)),
                "now_ms": int(now_ms),
                "last_error": str(error)[:2048],
            }
        )
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
            params,
        )
        if commit:
            self.conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)


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
WITH incoming(target_type, target_id) AS (
  SELECT *
  FROM unnest(%(target_types)s::text[], %(target_ids)s::text[])
),
mapped AS (
  SELECT DISTINCT
    'Asset'::text AS target_type_key,
    registry_assets.asset_id AS identity_id
  FROM incoming
  JOIN registry_assets
    ON incoming.target_type = 'chain_token'
   AND lower(registry_assets.chain_id || ':' || registry_assets.address) = lower(incoming.target_id)
  UNION
  SELECT DISTINCT
    'CexToken'::text AS target_type_key,
    price_feeds.subject_id AS identity_id
  FROM incoming
  JOIN price_feeds
    ON incoming.target_type = 'cex_symbol'
   AND price_feeds.subject_type = 'CexToken'
   AND lower(price_feeds.provider || ':' || price_feeds.native_market_id) = lower(incoming.target_id)
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
  SELECT mapped.*
  FROM mapped
  LEFT JOIN latest_feature
    ON latest_feature.target_type_key = mapped.target_type_key
   AND latest_feature.identity_id = mapped.identity_id
  WHERE mapped.identity_id IS NOT NULL
    AND (
      latest_feature.latest_market_observed_at_ms IS NULL
      OR latest_feature.latest_market_observed_at_ms <= %(now_ms)s - %(market_dirty_min_interval_ms)s
    )
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
  eligible.target_type_key,
  eligible.identity_id,
  %(dirty_reason)s,
  %(market_dirty)s,
  %(repair_dirty)s,
  encode(
    sha256(convert_to(eligible.target_type_key || ':' || eligible.identity_id || ':' || %(dirty_reason)s, 'UTF8')),
    'hex'
  ),
  %(due_at_ms)s,
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
   AND lower(registry_assets.chain_id || ':' || registry_assets.address) = lower(market_current_candidates.target_id)
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
   AND lower(price_feeds.provider || ':' || price_feeds.native_market_id) = lower(market_current_candidates.target_id)
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
  SELECT mapped.*
  FROM mapped
  LEFT JOIN latest_feature
    ON latest_feature.target_type_key = mapped.target_type_key
   AND latest_feature.identity_id = mapped.identity_id
  WHERE mapped.identity_id IS NOT NULL
    AND mapped.market_current_watermark_ms >= %(since_ms)s
    AND (
      latest_feature.latest_market_observed_at_ms IS NULL
      OR latest_feature.latest_market_observed_at_ms <= %(now_ms)s - %(market_dirty_min_interval_ms)s
    )
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
        if not identity_id:
            continue
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
        target_type_key, identity_id = _target_key(key)
        payload_hash = str(key.get("payload_hash") or "")
        lease_owner = str(key.get("lease_owner") or "")
        attempt_count = int(key.get("attempt_count") or 0)
        if not identity_id:
            continue
        if not payload_hash:
            raise ValueError("token radar dirty target completion requires payload_hash from claim_due")
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


def _key_params(records: list[dict[str, str | int]]) -> dict[str, Any]:
    return {
        "target_type_keys": [str(record["target_type_key"]) for record in records],
        "identity_ids": [str(record["identity_id"]) for record in records],
        "payload_hashes": [str(record["payload_hash"]) for record in records],
        "lease_owners": [str(record["lease_owner"]) for record in records],
        "attempt_counts": [int(record["attempt_count"]) for record in records],
    }


def _market_target_records(rows: Iterable[Mapping[str, Any] | tuple[str, str]]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if isinstance(row, tuple):
            target_type, target_id = row
        else:
            target_type = str(row.get("target_type") or "")
            target_id = str(row.get("target_id") or "")
        key = (str(target_type or ""), str(target_id or ""))
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        records.append({"target_type": key[0], "target_id": key[1]})
    return records


def _target_key(row: Mapping[str, Any]) -> tuple[str, str]:
    target_type_key = str(row.get("target_type_key") or row.get("target_type") or "")
    identity_id = str(row.get("identity_id") or row.get("target_id") or row.get("intent_id") or "")
    return target_type_key, identity_id


def _market_current_params(*, since_ms: int, now_ms: int, limit: int, reason: str) -> dict[str, Any]:
    return {
        "since_ms": int(since_ms),
        "now_ms": int(now_ms),
        "limit": max(0, int(limit)),
        "dirty_reason": str(reason),
        **dirty_kind_flags(reason),
        "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
        "market_dirty_min_interval_ms": MARKET_DIRTY_MIN_INTERVAL_MS,
    }


def _count(row: Mapping[str, Any] | None) -> int:
    if not row:
        return 0
    return int(row.get("count") or 0)
