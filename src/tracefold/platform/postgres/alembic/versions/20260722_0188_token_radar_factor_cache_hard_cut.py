"""Rebuild Token Radar private factor cache after the strict snapshot hard cut."""

from __future__ import annotations

from alembic import op

revision = "20260722_0188"
down_revision = "20260722_0187"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        ), rebuild_targets AS MATERIALIZED (
          SELECT target_type_key, identity_id
          FROM token_radar_target_features
          WHERE projection_version = 'token-radar-v13-social-attention'
            AND btrim(target_type_key) <> ''
            AND btrim(identity_id) <> ''
          UNION
          SELECT target_type_key, identity_id
          FROM token_radar_current_rows
          WHERE projection_version = 'token-radar-v13-social-attention'
            AND btrim(target_type_key) <> ''
            AND btrim(identity_id) <> ''
          UNION
          SELECT target_type_key, identity_id
          FROM token_radar_rank_source_events
          WHERE projection_version = 'token-radar-v13-social-attention'
            AND btrim(target_type_key) <> ''
            AND btrim(identity_id) <> ''
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
          rebuild_targets.target_type_key,
          rebuild_targets.identity_id,
          'schema_hard_cut_0188',
          false,
          true,
          'schema-hard-cut-0188:' || md5(
            rebuild_targets.target_type_key || ':' || rebuild_targets.identity_id
          ),
          migration_clock.now_ms,
          NULL,
          NULL,
          0,
          NULL,
          migration_clock.now_ms,
          migration_clock.now_ms
        FROM rebuild_targets
        CROSS JOIN migration_clock
        ON CONFLICT(target_type_key, identity_id) DO UPDATE SET
          dirty_reason = CASE
            WHEN token_radar_dirty_targets.dirty_reason = EXCLUDED.dirty_reason
              THEN token_radar_dirty_targets.dirty_reason
            ELSE 'mixed'
          END,
          market_dirty = token_radar_dirty_targets.market_dirty,
          repair_dirty = true,
          payload_hash = EXCLUDED.payload_hash,
          due_at_ms = LEAST(token_radar_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
          leased_until_ms = NULL,
          lease_owner = NULL,
          attempt_count = 0,
          last_error = NULL,
          first_dirty_at_ms = LEAST(
            token_radar_dirty_targets.first_dirty_at_ms,
            EXCLUDED.first_dirty_at_ms
          ),
          updated_at_ms = EXCLUDED.updated_at_ms
        """
    )
    op.execute("TRUNCATE TABLE token_radar_target_features")


def downgrade() -> None:
    raise RuntimeError("20260722_0188 is an irreversible private-cache hard cut")
