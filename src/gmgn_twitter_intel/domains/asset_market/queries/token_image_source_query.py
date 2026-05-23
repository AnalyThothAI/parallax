from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.asset_market.identity_evidence_policy import (
    EVIDENCE_GMGN_PAYLOAD_EXACT,
    EVIDENCE_OKX_DEX_EXACT_ADDRESS,
)

_PROJECTION_VERSION = "token-radar-v13-social-attention"
_RESOLVER_POLICY_VERSION = "token_radar_v5_identity_resolver"
_PROFILE_LOOKBACK_MS = 24 * 60 * 60 * 1000
_RECENT_RESOLUTION_SCAN_MULTIPLIER = 4


class TokenImageSourceQuery:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def candidate_sources(
        self,
        *,
        now_ms: int,
        source_limit: int,
        lookback_ms: int = _PROFILE_LOOKBACK_MS,
    ) -> list[dict[str, Any]]:
        resolved_limit = max(0, int(source_limit))
        if resolved_limit <= 0:
            return []

        since_ms = int(now_ms) - int(lookback_ms)
        recent_resolution_limit = max(
            resolved_limit,
            resolved_limit * _RECENT_RESOLUTION_SCAN_MULTIPLIER,
        )
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
                token_radar_current_rows.target_type,
                token_radar_current_rows.target_id,
                MIN(token_radar_current_rows.rank) AS best_radar_rank,
                MAX(token_radar_current_rows.computed_at_ms) AS latest_radar_computed_at_ms,
                MAX(token_radar_current_rows.source_max_received_at_ms) AS latest_event_received_at_ms
              FROM current_radar_sets
              JOIN token_radar_current_rows
                ON token_radar_current_rows.projection_version = %s
               AND token_radar_current_rows."window" = current_radar_sets."window"
               AND token_radar_current_rows.scope = current_radar_sets.scope
               AND token_radar_current_rows.computed_at_ms = current_radar_sets.computed_at_ms
              WHERE token_radar_current_rows.target_type IN ('Asset', 'CexToken')
                AND token_radar_current_rows.target_id IS NOT NULL
              GROUP BY token_radar_current_rows.target_type, token_radar_current_rows.target_id
            ),
            recent_resolution_rows AS MATERIALIZED (
              SELECT
                token_intent_resolutions.target_type,
                token_intent_resolutions.target_id,
                events.received_at_ms AS latest_event_received_at_ms
              FROM events
              JOIN token_intent_resolutions
                ON token_intent_resolutions.event_id = events.event_id
              WHERE events.received_at_ms >= %s
                AND token_intent_resolutions.is_current = true
                AND token_intent_resolutions.resolver_policy_version = %s
                AND token_intent_resolutions.target_type IN ('Asset', 'CexToken')
                AND token_intent_resolutions.target_id IS NOT NULL
              ORDER BY events.received_at_ms DESC, token_intent_resolutions.resolution_id DESC
              LIMIT %s
            ),
            recent_resolution_targets AS MATERIALIZED (
              SELECT
                target_type,
                target_id,
                NULL::integer AS best_radar_rank,
                NULL::bigint AS latest_radar_computed_at_ms,
                MAX(latest_event_received_at_ms) AS latest_event_received_at_ms
              FROM recent_resolution_rows
              GROUP BY target_type, target_id
            ),
            target_seeds AS (
              SELECT * FROM radar_targets
              UNION ALL
              SELECT * FROM recent_resolution_targets
            ),
            candidate_targets AS MATERIALIZED (
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
            ),
            asset_targets AS MATERIALIZED (
              SELECT *
              FROM candidate_targets
              WHERE target_type = 'Asset'
            ),
            cex_token_targets AS MATERIALIZED (
              SELECT *
              FROM candidate_targets
              WHERE target_type = 'CexToken'
            ),
            source_rows AS (
              SELECT
                NULLIF(btrim(asset_profiles.logo_url), '') AS source_url,
                asset_profiles.provider AS source_provider,
                'asset_profiles.logo_url' AS source_kind,
                jsonb_build_object(
                  'asset_id', asset_profiles.asset_id,
                  'provider', asset_profiles.provider
                ) AS raw_ref_json,
                asset_targets.best_radar_rank,
                asset_targets.latest_event_received_at_ms,
                10 AS source_priority
              FROM asset_targets
              JOIN asset_profiles
                ON asset_profiles.asset_id = asset_targets.target_id
              WHERE asset_profiles.provider IN ('gmgn_dex_profile', 'binance_web3_profile')
                AND asset_profiles.status = 'ready'
                AND NULLIF(btrim(asset_profiles.logo_url), '') IS NOT NULL

              UNION ALL

              SELECT
                NULLIF(btrim(asset_identity_evidence.raw_payload_json->>'i'), '') AS source_url,
                'gmgn_stream_snapshot' AS source_provider,
                'asset_identity_evidence.raw_payload_json.i' AS source_kind,
                jsonb_build_object(
                  'asset_id', asset_identity_evidence.asset_id,
                  'provider', asset_identity_evidence.provider,
                  'evidence_id', asset_identity_evidence.evidence_id,
                  'evidence_kind', asset_identity_evidence.evidence_kind
                ) AS raw_ref_json,
                asset_targets.best_radar_rank,
                asset_targets.latest_event_received_at_ms,
                30 AS source_priority
              FROM asset_targets
              JOIN asset_identity_evidence
                ON asset_identity_evidence.asset_id = asset_targets.target_id
              WHERE asset_identity_evidence.provider = 'gmgn'
                AND asset_identity_evidence.evidence_kind = %s
                AND asset_identity_evidence.raw_payload_json ? 'i'
                AND NULLIF(btrim(asset_identity_evidence.raw_payload_json->>'i'), '') IS NOT NULL

              UNION ALL

              SELECT
                NULLIF(btrim(asset_identity_evidence.raw_payload_json->>'tokenLogoUrl'), '') AS source_url,
                'okx_dex_evidence' AS source_provider,
                'asset_identity_evidence.raw_payload_json.tokenLogoUrl' AS source_kind,
                jsonb_build_object(
                  'asset_id', asset_identity_evidence.asset_id,
                  'provider', asset_identity_evidence.provider,
                  'evidence_id', asset_identity_evidence.evidence_id,
                  'evidence_kind', asset_identity_evidence.evidence_kind
                ) AS raw_ref_json,
                asset_targets.best_radar_rank,
                asset_targets.latest_event_received_at_ms,
                40 AS source_priority
              FROM asset_targets
              JOIN asset_identity_evidence
                ON asset_identity_evidence.asset_id = asset_targets.target_id
              WHERE asset_identity_evidence.provider = 'okx'
                AND asset_identity_evidence.evidence_kind = %s
                AND asset_identity_evidence.raw_payload_json ? 'tokenLogoUrl'
                AND NULLIF(btrim(asset_identity_evidence.raw_payload_json->>'tokenLogoUrl'), '') IS NOT NULL

              UNION ALL

              SELECT
                NULLIF(btrim(cex_token_profiles.logo_url), '') AS source_url,
                cex_token_profiles.provider AS source_provider,
                'cex_token_profiles.logo_url' AS source_kind,
                jsonb_build_object(
                  'cex_token_id', cex_token_profiles.cex_token_id,
                  'provider', cex_token_profiles.provider,
                  'source_ref', cex_token_profiles.source_ref
                ) AS raw_ref_json,
                cex_token_targets.best_radar_rank,
                cex_token_targets.latest_event_received_at_ms,
                20 AS source_priority
              FROM cex_token_targets
              JOIN cex_tokens
                ON cex_tokens.cex_token_id = cex_token_targets.target_id
              JOIN cex_token_profiles
                ON cex_token_profiles.cex_token_id = cex_tokens.cex_token_id
              WHERE cex_tokens.status IN ('candidate', 'canonical')
                AND cex_token_profiles.status = 'ready'
                AND NULLIF(btrim(cex_token_profiles.logo_url), '') IS NOT NULL
            ),
            deduped_sources AS (
              SELECT
                source_url,
                source_provider,
                source_kind,
                raw_ref_json,
                best_radar_rank,
                latest_event_received_at_ms,
                source_priority,
                row_number() OVER (
                  PARTITION BY source_url
                  ORDER BY
                    CASE WHEN best_radar_rank IS NULL THEN 1 ELSE 0 END ASC,
                    best_radar_rank ASC NULLS LAST,
                    latest_event_received_at_ms DESC NULLS LAST,
                    source_priority ASC,
                    source_provider ASC,
                    source_kind ASC
                ) AS source_row_number
              FROM source_rows
              WHERE source_url IS NOT NULL
            ),
            eligible_sources AS (
              SELECT deduped_sources.*
              FROM deduped_sources
              LEFT JOIN token_image_assets AS terminal_assets
                ON terminal_assets.source_url_hash = encode(
                  sha256(convert_to(deduped_sources.source_url, 'UTF8')),
                  'hex'
                )
               AND terminal_assets.status IN ('ready', 'unsupported')
              WHERE deduped_sources.source_row_number = 1
                AND terminal_assets.image_id IS NULL
            )
            SELECT
              source_url,
              source_provider,
              source_kind,
              raw_ref_json
            FROM eligible_sources
            ORDER BY
              CASE WHEN best_radar_rank IS NULL THEN 1 ELSE 0 END ASC,
              best_radar_rank ASC NULLS LAST,
              latest_event_received_at_ms DESC NULLS LAST,
              source_priority ASC,
              source_url ASC
            LIMIT %s
            """,
            (
                _PROJECTION_VERSION,
                _PROJECTION_VERSION,
                since_ms,
                _RESOLVER_POLICY_VERSION,
                recent_resolution_limit,
                resolved_limit,
                EVIDENCE_GMGN_PAYLOAD_EXACT,
                EVIDENCE_OKX_DEX_EXACT_ADDRESS,
                resolved_limit,
            ),
        ).fetchall()
        return [dict(row) for row in rows]
