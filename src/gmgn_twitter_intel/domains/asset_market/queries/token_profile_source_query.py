from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.asset_market.identity_evidence_policy import (
    EVIDENCE_GMGN_PAYLOAD_EXACT,
    EVIDENCE_OKX_DEX_EXACT_ADDRESS,
)
from gmgn_twitter_intel.domains.asset_market.services.token_profile_current_projection import (
    select_gmgn_stream_source,
    select_okx_dex_source,
)

_PROJECTION_VERSION = "token-radar-v13-social-attention"
_RESOLVER_POLICY_VERSION = "token_radar_v5_identity_resolver"
_PROFILE_LOOKBACK_MS = 24 * 60 * 60 * 1000


class TokenProfileSourceQuery:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def recent_profile_targets(
        self,
        *,
        now_ms: int,
        limit: int,
        lookback_ms: int = _PROFILE_LOOKBACK_MS,
    ) -> list[dict[str, Any]]:
        since_ms = int(now_ms) - int(lookback_ms)
        rows = self.conn.execute(
            """
            WITH current_radar_sets AS MATERIALIZED (
              SELECT "window", scope, computed_at_ms
              FROM token_radar_projection_coverage
              WHERE projection_version = %s
                AND status = 'ready'
                AND computed_at_ms IS NOT NULL
            ),
            radar_targets AS MATERIALIZED (
              SELECT
                token_radar_rows.target_type,
                token_radar_rows.target_id,
                MIN(token_radar_rows.rank) AS best_radar_rank,
                MAX(token_radar_rows.computed_at_ms) AS latest_radar_computed_at_ms,
                MAX(token_radar_rows.source_max_received_at_ms) AS latest_event_received_at_ms
              FROM current_radar_sets
              JOIN token_radar_rows
                ON token_radar_rows.projection_version = %s
               AND token_radar_rows."window" = current_radar_sets."window"
               AND token_radar_rows.scope = current_radar_sets.scope
               AND token_radar_rows.computed_at_ms = current_radar_sets.computed_at_ms
              WHERE token_radar_rows.target_type IN ('Asset', 'CexToken')
                AND token_radar_rows.target_id IS NOT NULL
              GROUP BY token_radar_rows.target_type, token_radar_rows.target_id
            ),
            recent_resolution_targets AS MATERIALIZED (
              SELECT
                token_intent_resolutions.target_type,
                token_intent_resolutions.target_id,
                NULL::integer AS best_radar_rank,
                NULL::bigint AS latest_radar_computed_at_ms,
                MAX(events.received_at_ms) AS latest_event_received_at_ms
              FROM events
              JOIN token_intent_resolutions
                ON token_intent_resolutions.event_id = events.event_id
              WHERE events.received_at_ms >= %s
                AND token_intent_resolutions.is_current = true
                AND token_intent_resolutions.resolver_policy_version = %s
                AND token_intent_resolutions.target_type IN ('Asset', 'CexToken')
                AND token_intent_resolutions.target_id IS NOT NULL
              GROUP BY token_intent_resolutions.target_type, token_intent_resolutions.target_id
            ),
            target_seeds AS (
              SELECT * FROM radar_targets
              UNION ALL
              SELECT * FROM recent_resolution_targets
            )
            SELECT
              target_type,
              target_id,
              MIN(best_radar_rank) AS best_radar_rank,
              MAX(latest_radar_computed_at_ms) AS latest_radar_computed_at_ms,
              MAX(latest_event_received_at_ms) AS latest_event_received_at_ms
            FROM target_seeds
            WHERE target_type IN ('Asset', 'CexToken')
            GROUP BY target_type, target_id
            ORDER BY
              CASE WHEN MIN(best_radar_rank) IS NULL THEN 1 ELSE 0 END ASC,
              MIN(best_radar_rank) ASC NULLS LAST,
              MAX(latest_event_received_at_ms) DESC NULLS LAST,
              target_type ASC,
              target_id ASC
            LIMIT %s
            """,
            (
                _PROJECTION_VERSION,
                _PROJECTION_VERSION,
                since_ms,
                _RESOLVER_POLICY_VERSION,
                max(0, int(limit)),
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def gmgn_openapi_profiles(self, asset_ids: list[str]) -> dict[str, dict[str, Any]]:
        requested = _dedupe(asset_ids)
        if not requested:
            return {}
        rows = self.conn.execute(
            """
            SELECT *
            FROM asset_profiles
            WHERE provider = 'gmgn_dex_profile'
              AND status = 'ready'
              AND asset_id = ANY(%s)
            """,
            (requested,),
        ).fetchall()
        return {str(row["asset_id"]): dict(row) for row in rows}

    def gmgn_stream_profiles(self, asset_ids: list[str]) -> dict[str, dict[str, Any]]:
        rows_by_asset = self._identity_evidence_rows(
            asset_ids=asset_ids,
            provider="gmgn",
            evidence_kind=EVIDENCE_GMGN_PAYLOAD_EXACT,
            raw_key="i",
        )
        return {
            asset_id: selected
            for asset_id, rows in rows_by_asset.items()
            if (selected := select_gmgn_stream_source(rows)) is not None
        }

    def okx_dex_profiles(self, asset_ids: list[str]) -> dict[str, dict[str, Any]]:
        rows_by_asset = self._identity_evidence_rows(
            asset_ids=asset_ids,
            provider="okx",
            evidence_kind=EVIDENCE_OKX_DEX_EXACT_ADDRESS,
            raw_key="tokenLogoUrl",
        )
        return {
            asset_id: selected
            for asset_id, rows in rows_by_asset.items()
            if (selected := select_okx_dex_source(rows)) is not None
        }

    def _identity_evidence_rows(
        self,
        *,
        asset_ids: list[str],
        provider: str,
        evidence_kind: str,
        raw_key: str,
    ) -> dict[str, list[dict[str, Any]]]:
        requested = _dedupe(asset_ids)
        if not requested:
            return {}
        rows = self.conn.execute(
            """
            SELECT *
            FROM asset_identity_evidence
            WHERE provider = %s
              AND evidence_kind = %s
              AND raw_payload_json ? %s
              AND asset_id = ANY(%s)
            ORDER BY asset_id ASC, observed_at_ms DESC, evidence_id DESC
            """,
            (provider, evidence_kind, raw_key, requested),
        ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            item = dict(row)
            grouped.setdefault(str(item.get("asset_id")), []).append(item)
        return grouped


def _dedupe(values: list[str]) -> list[str]:
    return [value for value in dict.fromkeys(str(item).strip() for item in values) if value]
