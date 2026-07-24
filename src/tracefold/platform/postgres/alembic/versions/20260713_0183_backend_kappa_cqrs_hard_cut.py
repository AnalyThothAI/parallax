"""Hard-cut dead state and rebuildable caches behind stable product identities."""

from __future__ import annotations

from alembic import op

revision = "20260713_0183"
down_revision = "20260623_0182"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '10min'")
    op.execute("DROP TABLE IF EXISTS pulse_playbook_outcomes")
    op.execute("ALTER TABLE pulse_playbook_snapshots DROP COLUMN IF EXISTS outcome_status")
    op.execute("DROP TABLE IF EXISTS token_score_evaluations")
    op.execute("DROP TABLE IF EXISTS cex_derivative_series")
    op.execute("DROP TABLE IF EXISTS projection_dirty_ranges")
    op.execute("ALTER TABLE projection_runs DROP COLUMN dirty_ranges_written")
    op.execute("DROP TABLE IF EXISTS discussion_digest_dirty_targets")
    op.execute("DROP TABLE IF EXISTS token_discussion_digests")
    op.execute("DROP TABLE IF EXISTS token_mention_semantics")
    op.execute("DROP TABLE IF EXISTS narrative_model_runs")
    op.execute("DROP TABLE IF EXISTS model_runs")
    op.execute("DROP TABLE IF EXISTS registry_aliases")
    op.execute("DROP TABLE IF EXISTS registry_versions")
    op.execute("DROP TABLE IF EXISTS schema_migrations")
    op.execute("DROP TABLE IF EXISTS token_aliases")
    op.execute("DROP TABLE IF EXISTS token_flow_window_snapshots")
    op.execute("DROP TABLE IF EXISTS token_radar_publications")
    op.execute("DROP TABLE IF EXISTS token_radar_storage_maintenance_runs")
    op.execute("DROP TABLE IF EXISTS token_social_bucket_authors")
    op.execute("DROP TABLE IF EXISTS token_social_buckets")

    op.execute("ALTER TABLE registry_assets DROP COLUMN project_id")
    op.execute("ALTER TABLE cex_tokens DROP COLUMN project_id")
    op.execute("ALTER TABLE price_feeds DROP COLUMN base_project_id")
    op.execute("DROP TABLE IF EXISTS projects")

    op.execute("ALTER TABLE token_radar_target_features ADD COLUMN intent_json JSONB")
    op.execute("ALTER TABLE token_radar_target_features ADD COLUMN resolution_json JSONB")
    op.execute(
        """
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        ), current_targets AS (
          SELECT target_type_key, identity_id
          FROM token_radar_target_features
          WHERE btrim(target_type_key) <> ''
            AND btrim(identity_id) <> ''
          UNION
          SELECT target_type_key, identity_id
          FROM token_radar_current_rows
          WHERE btrim(target_type_key) <> ''
            AND btrim(identity_id) <> ''
        )
        INSERT INTO token_radar_dirty_targets(
          target_type_key,
          identity_id,
          dirty_reason,
          payload_hash,
          due_at_ms,
          leased_until_ms,
          lease_owner,
          attempt_count,
          last_error,
          first_dirty_at_ms,
          updated_at_ms,
          repair_dirty
        )
        SELECT target_type_key,
               identity_id,
               'schema_hard_cut_0183',
               'schema-hard-cut-0183:' || md5(target_type_key || ':' || identity_id),
               now_ms,
               NULL,
               NULL,
               0,
               NULL,
               now_ms,
               now_ms,
               true
        FROM current_targets
        CROSS JOIN migration_clock
        ON CONFLICT(target_type_key, identity_id) DO UPDATE SET
          dirty_reason = CASE
            WHEN token_radar_dirty_targets.dirty_reason = excluded.dirty_reason
              THEN token_radar_dirty_targets.dirty_reason
            ELSE 'mixed'
          END,
          payload_hash = excluded.payload_hash,
          due_at_ms = LEAST(token_radar_dirty_targets.due_at_ms, excluded.due_at_ms),
          leased_until_ms = NULL,
          lease_owner = NULL,
          attempt_count = 0,
          last_error = NULL,
          first_dirty_at_ms = LEAST(
            token_radar_dirty_targets.first_dirty_at_ms,
            excluded.first_dirty_at_ms
          ),
          updated_at_ms = excluded.updated_at_ms,
          repair_dirty = true
        """
    )

    op.execute(
        """
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        ), candidate_frontiers AS (
          SELECT queue.target_type,
                 queue.target_id,
                 current_rows.source_max_received_at_ms AS watermark
          FROM token_profile_current_dirty_targets AS queue
          JOIN token_radar_current_rows AS current_rows
            ON current_rows.target_type_key = queue.target_type
           AND current_rows.identity_id = queue.target_id
          WHERE queue.source_watermark_ms <= 0
            AND current_rows.source_max_received_at_ms > 0
          UNION ALL
          SELECT queue.target_type,
                 queue.target_id,
                 features.latest_event_received_at_ms
          FROM token_profile_current_dirty_targets AS queue
          JOIN token_radar_target_features AS features
            ON features.target_type_key = queue.target_type
           AND features.identity_id = queue.target_id
          WHERE queue.source_watermark_ms <= 0
            AND features.latest_event_received_at_ms > 0
          UNION ALL
          SELECT queue.target_type,
                 queue.target_id,
                 profiles.observed_at_ms
          FROM token_profile_current_dirty_targets AS queue
          JOIN token_profile_current AS profiles
            USING(target_type, target_id)
          WHERE queue.source_watermark_ms <= 0
            AND profiles.observed_at_ms > 0
          UNION ALL
          SELECT queue.target_type,
                 queue.target_id,
                 profiles.observed_at_ms
          FROM token_profile_current_dirty_targets AS queue
          JOIN asset_profiles AS profiles
            ON queue.target_type = 'Asset'
           AND profiles.asset_id = queue.target_id
          WHERE queue.source_watermark_ms <= 0
            AND profiles.observed_at_ms > 0
          UNION ALL
          SELECT queue.target_type,
                 queue.target_id,
                 profiles.observed_at_ms
          FROM token_profile_current_dirty_targets AS queue
          JOIN cex_token_profiles AS profiles
            ON queue.target_type = 'CexToken'
           AND profiles.cex_token_id = queue.target_id
          WHERE queue.source_watermark_ms <= 0
            AND profiles.observed_at_ms > 0
          UNION ALL
          SELECT queue.target_type,
                 queue.target_id,
                 refresh_targets.source_watermark_ms
          FROM token_profile_current_dirty_targets AS queue
          JOIN asset_profile_refresh_targets AS refresh_targets
            USING(target_type, target_id)
          WHERE queue.source_watermark_ms <= 0
            AND refresh_targets.source_watermark_ms > 0
          UNION ALL
          SELECT queue.target_type,
                 queue.target_id,
                 image_targets.source_watermark_ms
          FROM token_profile_current_dirty_targets AS queue
          JOIN token_image_source_dirty_targets AS image_targets
            USING(target_type, target_id)
          WHERE queue.source_watermark_ms <= 0
            AND image_targets.source_watermark_ms > 0
        ), recoverable AS (
          SELECT target_type,
                 target_id,
                 max(watermark)::bigint AS watermark
          FROM candidate_frontiers
          GROUP BY target_type, target_id
        )
        UPDATE token_profile_current_dirty_targets AS queue
        SET source_watermark_ms = recoverable.watermark,
            dirty_reason = 'schema_hard_cut_0183',
            payload_hash = 'schema-hard-cut-0183-profile:'
              || md5(queue.target_type || ':' || queue.target_id || ':' || recoverable.watermark::text),
            due_at_ms = LEAST(queue.due_at_ms, migration_clock.now_ms),
            leased_until_ms = NULL,
            lease_owner = NULL,
            attempt_count = 0,
            last_error = NULL,
            updated_at_ms = migration_clock.now_ms
        FROM recoverable
        CROSS JOIN migration_clock
        WHERE queue.target_type = recoverable.target_type
          AND queue.target_id = recoverable.target_id
          AND queue.source_watermark_ms <= 0
        """
    )
    op.execute("DELETE FROM token_profile_current_dirty_targets WHERE source_watermark_ms <= 0")
    op.execute("ALTER TABLE token_profile_current_dirty_targets ALTER COLUMN source_watermark_ms DROP DEFAULT")
    op.execute(
        """
        ALTER TABLE token_profile_current_dirty_targets
        ADD CONSTRAINT ck_token_profile_current_dirty_source_watermark_positive
        CHECK (source_watermark_ms > 0) NOT VALID
        """
    )
    op.execute(
        """
        ALTER TABLE token_profile_current_dirty_targets
        VALIDATE CONSTRAINT ck_token_profile_current_dirty_source_watermark_positive
        """
    )

    op.execute("TRUNCATE TABLE token_radar_target_features")
    op.execute("ALTER TABLE token_radar_target_features ALTER COLUMN intent_json SET NOT NULL")
    op.execute("ALTER TABLE token_radar_target_features ALTER COLUMN resolution_json SET NOT NULL")

    op.execute(
        """
        LOCK TABLE narrative_admissions, narrative_admission_dirty_targets
        IN ACCESS EXCLUSIVE MODE
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_narrative_admissions_due_semantics")
    op.execute("DROP INDEX IF EXISTS idx_narrative_admissions_due_digest")
    op.execute("ALTER TABLE narrative_admissions DROP COLUMN next_semantics_due_at_ms")
    op.execute("ALTER TABLE narrative_admissions DROP COLUMN next_digest_due_at_ms")
    op.execute("ALTER TABLE narrative_admissions DROP COLUMN suppressed_at_ms")
    op.execute(
        """
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        ), candidates AS (
          SELECT target_type,
                 target_id,
                 "window",
                 scope,
                 source_max_received_at_ms AS source_watermark_ms
          FROM narrative_admissions
          WHERE source_max_received_at_ms > 0
          UNION ALL
          SELECT target_type,
                 target_id,
                 "window",
                 scope,
                 source_watermark_ms
          FROM narrative_admission_dirty_targets
          WHERE source_watermark_ms > 0
        ), targets AS (
          SELECT target_type,
                 target_id,
                 "window",
                 scope,
                 max(source_watermark_ms)::bigint AS source_watermark_ms
          FROM candidates
          GROUP BY target_type, target_id, "window", scope
        )
        INSERT INTO narrative_admission_dirty_targets(
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
        SELECT target_type,
               target_id,
               "window",
               scope,
               'token-radar-v13-social-attention',
               'narrative_intel_v1',
               'schema_hard_cut_0183',
               'schema-hard-cut-0183-narrative:' || md5(
                 target_type || ':' || target_id || ':' || "window" || ':' || scope || ':'
                 || source_watermark_ms::text
               ),
               source_watermark_ms,
               40,
               now_ms,
               NULL,
               NULL,
               0,
               NULL,
               now_ms,
               now_ms
        FROM targets
        CROSS JOIN migration_clock
        ON CONFLICT(target_type, target_id, "window", scope) DO UPDATE SET
          projection_version = excluded.projection_version,
          schema_version = excluded.schema_version,
          dirty_reason = excluded.dirty_reason,
          payload_hash = excluded.payload_hash,
          source_watermark_ms = excluded.source_watermark_ms,
          priority = LEAST(narrative_admission_dirty_targets.priority, excluded.priority),
          due_at_ms = LEAST(narrative_admission_dirty_targets.due_at_ms, excluded.due_at_ms),
          leased_until_ms = NULL,
          lease_owner = NULL,
          attempt_count = 0,
          last_error = NULL,
          updated_at_ms = excluded.updated_at_ms
        """
    )
    op.execute(
        """
        DELETE FROM narrative_admissions
        WHERE schema_version IS DISTINCT FROM 'narrative_intel_v1'
        """
    )
    op.execute("DROP INDEX IF EXISTS ux_narrative_admissions_target")
    op.execute("ALTER TABLE narrative_admissions DROP CONSTRAINT narrative_admissions_pkey")
    op.execute("ALTER TABLE narrative_admissions DROP COLUMN admission_id")
    op.execute(
        """
        ALTER TABLE narrative_admissions
        ADD CONSTRAINT narrative_admissions_pkey
        PRIMARY KEY (target_type, target_id, "window", scope)
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_narrative_admissions_source_fingerprint")

    op.execute("DELETE FROM narrative_admission_dirty_targets WHERE source_watermark_ms <= 0")
    op.execute("ALTER TABLE narrative_admission_dirty_targets ALTER COLUMN source_watermark_ms DROP DEFAULT")
    op.execute(
        """
        ALTER TABLE narrative_admission_dirty_targets
        ADD CONSTRAINT ck_narrative_admission_dirty_source_watermark_positive
        CHECK (source_watermark_ms > 0) NOT VALID
        """
    )
    op.execute(
        """
        ALTER TABLE narrative_admission_dirty_targets
        VALIDATE CONSTRAINT ck_narrative_admission_dirty_source_watermark_positive
        """
    )

    op.execute("ALTER TABLE cex_detail_snapshots DROP CONSTRAINT cex_detail_snapshots_pkey")
    op.execute("ALTER TABLE cex_detail_snapshots DROP COLUMN snapshot_id")
    op.execute(
        """
        ALTER TABLE cex_detail_snapshots
        ADD CONSTRAINT cex_detail_snapshots_pkey
        PRIMARY KEY USING INDEX ux_cex_detail_snapshots_market
        """
    )

    op.execute("DROP INDEX IF EXISTS idx_macro_view_snapshots_latest_current")
    op.execute("ALTER TABLE macro_view_snapshots DROP CONSTRAINT IF EXISTS macro_view_snapshots_pkey")
    op.execute("ALTER TABLE macro_view_snapshots DROP CONSTRAINT IF EXISTS macro_view_snapshots_compact_pkey")
    op.execute("ALTER TABLE macro_view_snapshots DROP COLUMN snapshot_id")
    op.execute(
        """
        ALTER TABLE macro_view_snapshots
        ADD CONSTRAINT macro_view_snapshots_pkey
        PRIMARY KEY USING INDEX ux_macro_view_snapshots_current
        """
    )

    op.execute("ALTER TABLE account_quality_snapshots DROP CONSTRAINT account_quality_snapshots_pkey")
    op.execute("ALTER TABLE account_quality_snapshots DROP COLUMN snapshot_id")
    op.execute(
        """
        ALTER TABLE account_quality_snapshots
        ADD CONSTRAINT account_quality_snapshots_pkey
        PRIMARY KEY USING INDEX ux_account_quality_snapshots_handle_window
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_account_quality_snapshots_handle_window")


def downgrade() -> None:
    raise RuntimeError("20260713_0183 is an irreversible hard cut; restore a pre-migration backup to downgrade")
