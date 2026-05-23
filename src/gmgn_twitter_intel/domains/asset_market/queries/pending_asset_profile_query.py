from __future__ import annotations

from typing import Any

# Inlined to avoid circular import; must stay in sync with token_intel._constants.
_PROJECTION_VERSION = "token-radar-v13-social-attention"
_RESOLVER_POLICY_VERSION = "token_radar_v5_identity_resolver"

_PROFILE_HOT_LOOKBACK_MS = 24 * 60 * 60 * 1000
_MIN_RECENT_EVENT_SCAN_LIMIT = 50
_MAX_RECENT_EVENT_SCAN_LIMIT = 200
_RECENT_EVENT_SCAN_MULTIPLIER = 4


class PendingAssetProfileQuery:
    """Selects resolved DEX assets that need GMGN profile refresh."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def pending_rows(
        self,
        provider: str,
        now_ms: int,
        limit: int,
        hot_lookback_ms: int = _PROFILE_HOT_LOOKBACK_MS,
    ) -> list[dict[str, Any]]:
        hot_since_ms = int(now_ms) - int(hot_lookback_ms)
        row_limit = max(0, int(limit))
        recent_event_scan_limit = _recent_event_scan_limit(row_limit)
        rows = self.conn.execute(
            """
            WITH current_radar_sets AS MATERIALIZED (
              SELECT
                "window",
                scope,
                computed_at_ms
              FROM token_radar_projection_coverage
              WHERE projection_version = %s
                AND status = 'ready'
                AND computed_at_ms IS NOT NULL
            ),
            radar_assets AS MATERIALIZED (
              SELECT
                rows.target_id AS asset_id,
                MIN(rows.rank) AS best_radar_rank,
                MAX(rows.computed_at_ms) AS latest_radar_computed_at_ms,
                MAX(rows.source_max_received_at_ms) AS latest_event_received_at_ms
              FROM current_radar_sets
              JOIN token_radar_current_rows rows
                ON rows.projection_version = %s
               AND rows."window" = current_radar_sets."window"
               AND rows.scope = current_radar_sets.scope
               AND rows.computed_at_ms = current_radar_sets.computed_at_ms
              WHERE rows.target_type = 'Asset'
                AND rows.target_id IS NOT NULL
              GROUP BY rows.target_id
            ),
            recent_events AS MATERIALIZED (
              SELECT
                event_id,
                received_at_ms
              FROM events
              WHERE received_at_ms >= %s
              ORDER BY received_at_ms DESC
              LIMIT %s
            ),
            recent_resolution_assets AS MATERIALIZED (
              SELECT
                tir.target_id AS asset_id,
                MAX(recent_events.received_at_ms) AS latest_event_received_at_ms
              FROM recent_events
              JOIN token_intent_resolutions tir ON tir.event_id = recent_events.event_id
              WHERE tir.is_current = true
                AND tir.resolver_policy_version = %s
                AND tir.target_type = 'Asset'
                AND tir.target_id IS NOT NULL
              GROUP BY tir.target_id
            ),
            candidate_asset_seeds AS (
              SELECT
                asset_id,
                latest_event_received_at_ms,
                best_radar_rank,
                latest_radar_computed_at_ms
              FROM radar_assets
              UNION ALL
              SELECT
                asset_id,
                latest_event_received_at_ms,
                NULL::integer AS best_radar_rank,
                NULL::bigint AS latest_radar_computed_at_ms
              FROM recent_resolution_assets
            ),
            candidate_assets AS MATERIALIZED (
              SELECT
                asset_id,
                MAX(latest_event_received_at_ms) AS latest_event_received_at_ms,
                MIN(best_radar_rank) AS best_radar_rank,
                MAX(latest_radar_computed_at_ms) AS latest_radar_computed_at_ms
              FROM candidate_asset_seeds
              GROUP BY asset_id
            ),
            due_assets AS (
              SELECT
                candidate_assets.asset_id,
                registry_assets.chain_id,
                registry_assets.address,
                asset_identity_current.canonical_symbol AS symbol,
                candidate_assets.latest_event_received_at_ms,
                asset_profiles.status AS profile_status,
                asset_profiles.next_refresh_at_ms,
                candidate_assets.best_radar_rank,
                candidate_assets.latest_radar_computed_at_ms
              FROM candidate_assets
              JOIN registry_assets
                ON registry_assets.asset_id = candidate_assets.asset_id
              LEFT JOIN asset_identity_current
                ON asset_identity_current.asset_id = candidate_assets.asset_id
              LEFT JOIN asset_profiles
                ON asset_profiles.asset_id = candidate_assets.asset_id
               AND asset_profiles.provider = %s
              WHERE registry_assets.chain_id IS NOT NULL
                AND registry_assets.address IS NOT NULL
                AND (
                  asset_profiles.asset_id IS NULL
                  OR asset_profiles.next_refresh_at_ms <= %s
                )
            )
            SELECT
              asset_id,
              chain_id,
              address,
              symbol,
              latest_event_received_at_ms,
              profile_status,
              next_refresh_at_ms,
              best_radar_rank,
              latest_radar_computed_at_ms
            FROM due_assets
            ORDER BY
              CASE WHEN best_radar_rank IS NULL THEN 1 ELSE 0 END ASC,
              best_radar_rank ASC NULLS LAST,
              latest_event_received_at_ms DESC NULLS LAST,
              asset_id ASC
            LIMIT %s
            """,
            (
                _PROJECTION_VERSION,
                _PROJECTION_VERSION,
                hot_since_ms,
                recent_event_scan_limit,
                _RESOLVER_POLICY_VERSION,
                _required_provider(provider),
                int(now_ms),
                row_limit,
            ),
        ).fetchall()
        return [dict(row) for row in rows]


def _recent_event_scan_limit(limit: int) -> int:
    if limit <= 0:
        return 0
    return min(
        _MAX_RECENT_EVENT_SCAN_LIMIT,
        max(_MIN_RECENT_EVENT_SCAN_LIMIT, limit * _RECENT_EVENT_SCAN_MULTIPLIER),
    )


def _required_provider(value: str) -> str:
    return str(value).strip()
