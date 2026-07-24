"""Rebuild profiles that can now use address-bound OKX symbol candidate icons."""

from __future__ import annotations

from alembic import op

revision = "20260531_0136"
down_revision = "20260531_0134"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        WITH targets AS (
          SELECT DISTINCT ON (evidence.asset_id)
            evidence.asset_id,
            evidence.observed_at_ms,
            evidence.evidence_id,
            evidence.raw_payload_json->>'tokenLogoUrl' AS logo_url
          FROM asset_identity_evidence AS evidence
          LEFT JOIN token_profile_current AS current_profile
            ON current_profile.target_type = 'Asset'
           AND current_profile.target_id = evidence.asset_id
          WHERE evidence.provider = 'okx'
            AND evidence.evidence_kind = 'okx_dex_symbol_candidate'
            AND evidence.raw_payload_json->>'tokenLogoUrl' LIKE 'http%'
            AND (
              current_profile.target_id IS NULL
              OR current_profile.logo_url IS NULL
              OR current_profile.quality_flags_json ? 'source_without_logo'
            )
          ORDER BY evidence.asset_id, evidence.observed_at_ms DESC, evidence.evidence_id DESC
        )
        INSERT INTO token_profile_current_dirty_targets(
          target_type, target_id, dirty_reason, payload_hash, source_watermark_ms,
          priority, due_at_ms, leased_until_ms, lease_owner, attempt_count,
          last_error, first_dirty_at_ms, updated_at_ms
        )
        SELECT
          'Asset',
          targets.asset_id,
          'okx_symbol_candidate_profile_icon_policy',
          md5(targets.asset_id || ':' || targets.evidence_id || ':' || targets.logo_url),
          targets.observed_at_ms,
          15,
          0,
          NULL,
          NULL,
          0,
          NULL,
          0,
          0
        FROM targets
        ON CONFLICT(target_type, target_id) DO UPDATE SET
          dirty_reason = EXCLUDED.dirty_reason,
          payload_hash = EXCLUDED.payload_hash,
          source_watermark_ms = GREATEST(
            token_profile_current_dirty_targets.source_watermark_ms,
            EXCLUDED.source_watermark_ms
          ),
          priority = LEAST(token_profile_current_dirty_targets.priority, EXCLUDED.priority),
          due_at_ms = LEAST(token_profile_current_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
          leased_until_ms = NULL,
          lease_owner = NULL,
          last_error = NULL,
          updated_at_ms = EXCLUDED.updated_at_ms
        """
    )
    op.execute("ANALYZE token_profile_current_dirty_targets")


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM token_profile_current_dirty_targets
        WHERE dirty_reason = 'okx_symbol_candidate_profile_icon_policy'
        """
    )
