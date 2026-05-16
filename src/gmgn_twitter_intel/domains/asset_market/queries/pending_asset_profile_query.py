from __future__ import annotations

from typing import Any

# Inlined to avoid circular import; must stay in sync with TOKEN_RADAR_RESOLVER_POLICY_VERSION
_RESOLVER_POLICY_VERSION = "token_radar_v5_identity_resolver"

_PROFILE_HOT_LOOKBACK_MS = 24 * 60 * 60 * 1000


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
        rows = self.conn.execute(
            """
            WITH latest_radar AS (
              SELECT MAX(computed_at_ms) AS computed_at_ms
              FROM token_radar_rows
              WHERE target_type = 'Asset'
            ),
            radar_assets AS (
              SELECT
                token_radar_rows.target_id AS asset_id,
                MIN(token_radar_rows.rank) AS best_radar_rank,
                MAX(token_radar_rows.computed_at_ms) AS latest_radar_computed_at_ms
              FROM token_radar_rows
              JOIN latest_radar
                ON latest_radar.computed_at_ms = token_radar_rows.computed_at_ms
              WHERE token_radar_rows.target_type = 'Asset'
                AND token_radar_rows.target_id IS NOT NULL
              GROUP BY token_radar_rows.target_id
            ),
            due_assets AS (
              SELECT
                tir.target_id AS asset_id,
                registry_assets.chain_id,
                registry_assets.address,
                asset_identity_current.canonical_symbol AS symbol,
                MAX(events.received_at_ms) AS latest_event_received_at_ms,
                asset_profiles.status AS profile_status,
                asset_profiles.next_refresh_at_ms,
                radar_assets.best_radar_rank,
                radar_assets.latest_radar_computed_at_ms
              FROM token_intent_resolutions tir
              JOIN events ON events.event_id = tir.event_id
              JOIN registry_assets
                ON tir.target_type = 'Asset'
               AND registry_assets.asset_id = tir.target_id
              LEFT JOIN asset_identity_current
                ON asset_identity_current.asset_id = tir.target_id
              LEFT JOIN asset_profiles
                ON asset_profiles.asset_id = tir.target_id
               AND asset_profiles.provider = %s
              LEFT JOIN radar_assets
                ON radar_assets.asset_id = tir.target_id
              WHERE tir.is_current = true
                AND tir.resolver_policy_version = %s
                AND tir.target_type = 'Asset'
                AND tir.target_id IS NOT NULL
                AND registry_assets.chain_id IS NOT NULL
                AND registry_assets.address IS NOT NULL
                AND events.received_at_ms >= %s
                AND (
                  asset_profiles.asset_id IS NULL
                  OR asset_profiles.next_refresh_at_ms <= %s
                )
              GROUP BY
                tir.target_id,
                registry_assets.chain_id,
                registry_assets.address,
                asset_identity_current.canonical_symbol,
                asset_profiles.status,
                asset_profiles.next_refresh_at_ms,
                radar_assets.best_radar_rank,
                radar_assets.latest_radar_computed_at_ms
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
              latest_event_received_at_ms DESC,
              asset_id ASC
            LIMIT %s
            """,
            (_required_provider(provider), _RESOLVER_POLICY_VERSION, hot_since_ms, int(now_ms), max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]


def _required_provider(value: str) -> str:
    return str(value).strip()
