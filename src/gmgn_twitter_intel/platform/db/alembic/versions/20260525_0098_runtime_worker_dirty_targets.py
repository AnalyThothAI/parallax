"""Add runtime worker dirty target queues."""

from __future__ import annotations

from alembic import op

revision = "20260525_0098"
down_revision = "20260525_0097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pulse_trigger_dirty_targets (
          target_type TEXT NOT NULL,
          target_id TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          dirty_reason TEXT NOT NULL,
          payload_hash TEXT NOT NULL,
          source_watermark_ms BIGINT NOT NULL DEFAULT 0,
          priority INTEGER NOT NULL DEFAULT 100,
          due_at_ms BIGINT NOT NULL,
          leased_until_ms BIGINT,
          lease_owner TEXT,
          attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          last_error TEXT,
          first_dirty_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY (target_type, target_id, "window", scope)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE pulse_trigger_dirty_targets SET (
          fillfactor = 70,
          autovacuum_vacuum_scale_factor = 0.02,
          autovacuum_analyze_scale_factor = 0.02
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_trigger_dirty_due
          ON pulse_trigger_dirty_targets(
            priority ASC,
            due_at_ms ASC,
            updated_at_ms ASC,
            target_type,
            target_id,
            "window",
            scope
          )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_trigger_dirty_lease
          ON pulse_trigger_dirty_targets(leased_until_ms)
          WHERE leased_until_ms IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS narrative_admission_dirty_targets (
          target_type TEXT NOT NULL,
          target_id TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          projection_version TEXT NOT NULL,
          schema_version TEXT NOT NULL,
          dirty_reason TEXT NOT NULL,
          payload_hash TEXT NOT NULL,
          source_watermark_ms BIGINT NOT NULL DEFAULT 0,
          priority INTEGER NOT NULL DEFAULT 100,
          due_at_ms BIGINT NOT NULL,
          leased_until_ms BIGINT,
          lease_owner TEXT,
          attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          last_error TEXT,
          first_dirty_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY (target_type, target_id, "window", scope)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE narrative_admission_dirty_targets SET (
          fillfactor = 70,
          autovacuum_vacuum_scale_factor = 0.02,
          autovacuum_analyze_scale_factor = 0.02
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_narrative_admission_dirty_due
          ON narrative_admission_dirty_targets(
            priority ASC,
            due_at_ms ASC,
            updated_at_ms ASC,
            projection_version,
            schema_version,
            "window",
            scope,
            target_type,
            target_id
          )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_narrative_admission_dirty_lease
          ON narrative_admission_dirty_targets(
            leased_until_ms,
            projection_version,
            schema_version,
            "window",
            scope,
            target_type,
            target_id
          )
          WHERE leased_until_ms IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS discussion_digest_dirty_targets (
          target_type TEXT NOT NULL,
          target_id TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          projection_version TEXT NOT NULL,
          schema_version TEXT NOT NULL,
          dirty_reason TEXT NOT NULL,
          payload_hash TEXT NOT NULL,
          source_watermark_ms BIGINT NOT NULL DEFAULT 0,
          priority INTEGER NOT NULL DEFAULT 100,
          due_at_ms BIGINT NOT NULL,
          leased_until_ms BIGINT,
          lease_owner TEXT,
          attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          last_error TEXT,
          first_dirty_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY (target_type, target_id, "window", scope)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE discussion_digest_dirty_targets SET (
          fillfactor = 70,
          autovacuum_vacuum_scale_factor = 0.02,
          autovacuum_analyze_scale_factor = 0.02
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_discussion_digest_dirty_due
          ON discussion_digest_dirty_targets(
            priority ASC,
            due_at_ms ASC,
            updated_at_ms ASC,
            projection_version,
            schema_version,
            "window",
            scope,
            target_type,
            target_id
          )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_discussion_digest_dirty_lease
          ON discussion_digest_dirty_targets(
            leased_until_ms,
            projection_version,
            schema_version,
            "window",
            scope,
            target_type,
            target_id
          )
          WHERE leased_until_ms IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_profile_current_dirty_targets (
          target_type TEXT NOT NULL,
          target_id TEXT NOT NULL,
          dirty_reason TEXT NOT NULL,
          payload_hash TEXT NOT NULL,
          source_watermark_ms BIGINT NOT NULL DEFAULT 0,
          priority INTEGER NOT NULL DEFAULT 100,
          due_at_ms BIGINT NOT NULL,
          leased_until_ms BIGINT,
          lease_owner TEXT,
          attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          last_error TEXT,
          first_dirty_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY (target_type, target_id)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE token_profile_current_dirty_targets SET (
          fillfactor = 70,
          autovacuum_vacuum_scale_factor = 0.02,
          autovacuum_analyze_scale_factor = 0.02
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_profile_current_dirty_due
          ON token_profile_current_dirty_targets(
            priority ASC,
            due_at_ms ASC,
            updated_at_ms ASC,
            target_type,
            target_id
          )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_profile_current_dirty_lease
          ON token_profile_current_dirty_targets(leased_until_ms)
          WHERE leased_until_ms IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_image_source_dirty_targets (
          source_url_hash TEXT NOT NULL,
          source_url TEXT NOT NULL,
          source_provider TEXT NOT NULL,
          source_kind TEXT NOT NULL,
          target_type TEXT NOT NULL,
          target_id TEXT NOT NULL,
          raw_ref_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          dirty_reason TEXT NOT NULL,
          payload_hash TEXT NOT NULL,
          source_watermark_ms BIGINT NOT NULL DEFAULT 0,
          priority INTEGER NOT NULL DEFAULT 100,
          due_at_ms BIGINT NOT NULL,
          leased_until_ms BIGINT,
          lease_owner TEXT,
          attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          last_error TEXT,
          first_dirty_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY (source_url_hash, target_type, target_id)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE token_image_source_dirty_targets SET (
          fillfactor = 70,
          autovacuum_vacuum_scale_factor = 0.02,
          autovacuum_analyze_scale_factor = 0.02
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_image_source_dirty_due
          ON token_image_source_dirty_targets(
            priority ASC,
            due_at_ms ASC,
            updated_at_ms ASC,
            source_url_hash,
            target_type,
            target_id
          )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_image_source_dirty_lease
          ON token_image_source_dirty_targets(leased_until_ms)
          WHERE leased_until_ms IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_profile_refresh_targets (
          provider TEXT NOT NULL,
          target_type TEXT NOT NULL,
          target_id TEXT NOT NULL,
          chain_id TEXT NOT NULL,
          address TEXT NOT NULL,
          symbol TEXT,
          dirty_reason TEXT NOT NULL,
          payload_hash TEXT NOT NULL,
          source_watermark_ms BIGINT NOT NULL DEFAULT 0,
          priority INTEGER NOT NULL DEFAULT 100,
          due_at_ms BIGINT NOT NULL,
          leased_until_ms BIGINT,
          lease_owner TEXT,
          attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          last_error TEXT,
          first_dirty_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY (provider, target_type, target_id)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE asset_profile_refresh_targets SET (
          fillfactor = 70,
          autovacuum_vacuum_scale_factor = 0.02,
          autovacuum_analyze_scale_factor = 0.02
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_profile_refresh_targets_due
          ON asset_profile_refresh_targets(
            provider,
            priority ASC,
            due_at_ms ASC,
            updated_at_ms ASC,
            target_type,
            target_id
          )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_profile_refresh_targets_lease
          ON asset_profile_refresh_targets(leased_until_ms, provider)
          WHERE leased_until_ms IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_capture_tier_dirty_targets (
          work_name TEXT NOT NULL,
          partition_key TEXT NOT NULL,
          dirty_reason TEXT NOT NULL,
          payload_hash TEXT NOT NULL,
          source_watermark_ms BIGINT NOT NULL DEFAULT 0,
          priority INTEGER NOT NULL DEFAULT 100,
          due_at_ms BIGINT NOT NULL,
          leased_until_ms BIGINT,
          lease_owner TEXT,
          attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          last_error TEXT,
          first_dirty_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY (work_name, partition_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_capture_tier_dirty_due
          ON token_capture_tier_dirty_targets(
            priority ASC,
            due_at_ms ASC,
            updated_at_ms ASC,
            work_name,
            partition_key
          )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_capture_tier_dirty_lease
          ON token_capture_tier_dirty_targets(leased_until_ms)
          WHERE leased_until_ms IS NOT NULL
        """
    )
    op.execute("ALTER TABLE token_mention_semantics ADD COLUMN IF NOT EXISTS leased_until_ms BIGINT")
    op.execute("ALTER TABLE token_mention_semantics ADD COLUMN IF NOT EXISTS lease_owner TEXT")
    op.execute("ALTER TABLE token_mention_semantics ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE token_mention_semantics ADD COLUMN IF NOT EXISTS claimed_at_ms BIGINT")
    op.execute("ALTER TABLE token_mention_semantics ADD COLUMN IF NOT EXISTS last_error TEXT")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_mention_semantics_control_due
          ON token_mention_semantics(
            status,
            next_retry_at_ms,
            source_received_at_ms DESC,
            schema_version,
            target_type,
            target_id
          )
          WHERE status IN ('queued', 'retryable_error')
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_mention_semantics_lease
          ON token_mention_semantics(
            leased_until_ms,
            status,
            next_retry_at_ms,
            schema_version,
            target_type,
            target_id
          )
          WHERE leased_until_ms IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_token_capture_tier_dirty_lease")
    op.execute("DROP INDEX IF EXISTS idx_token_capture_tier_dirty_due")
    op.execute("DROP TABLE IF EXISTS token_capture_tier_dirty_targets")
    op.execute("DROP INDEX IF EXISTS idx_asset_profile_refresh_targets_lease")
    op.execute("DROP INDEX IF EXISTS idx_asset_profile_refresh_targets_due")
    op.execute("DROP TABLE IF EXISTS asset_profile_refresh_targets")
    op.execute("DROP INDEX IF EXISTS idx_token_image_source_dirty_lease")
    op.execute("DROP INDEX IF EXISTS idx_token_image_source_dirty_due")
    op.execute("DROP TABLE IF EXISTS token_image_source_dirty_targets")
    op.execute("DROP INDEX IF EXISTS idx_token_profile_current_dirty_lease")
    op.execute("DROP INDEX IF EXISTS idx_token_profile_current_dirty_due")
    op.execute("DROP TABLE IF EXISTS token_profile_current_dirty_targets")
    op.execute("DROP INDEX IF EXISTS idx_token_mention_semantics_lease")
    op.execute("DROP INDEX IF EXISTS idx_token_mention_semantics_control_due")
    op.execute("ALTER TABLE token_mention_semantics DROP COLUMN IF EXISTS last_error")
    op.execute("ALTER TABLE token_mention_semantics DROP COLUMN IF EXISTS claimed_at_ms")
    op.execute("ALTER TABLE token_mention_semantics DROP COLUMN IF EXISTS attempt_count")
    op.execute("ALTER TABLE token_mention_semantics DROP COLUMN IF EXISTS lease_owner")
    op.execute("ALTER TABLE token_mention_semantics DROP COLUMN IF EXISTS leased_until_ms")
    op.execute("DROP INDEX IF EXISTS idx_discussion_digest_dirty_lease")
    op.execute("DROP INDEX IF EXISTS idx_discussion_digest_dirty_due")
    op.execute("DROP TABLE IF EXISTS discussion_digest_dirty_targets")
    op.execute("DROP INDEX IF EXISTS idx_narrative_admission_dirty_lease")
    op.execute("DROP INDEX IF EXISTS idx_narrative_admission_dirty_due")
    op.execute("DROP TABLE IF EXISTS narrative_admission_dirty_targets")
    op.execute("DROP INDEX IF EXISTS idx_pulse_trigger_dirty_lease")
    op.execute("DROP INDEX IF EXISTS idx_pulse_trigger_dirty_due")
    op.execute("DROP TABLE IF EXISTS pulse_trigger_dirty_targets")
