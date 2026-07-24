"""Hard cut product AI and replace Macro with six evidence documents."""

from __future__ import annotations

from alembic import op

revision = "20260723_0191"
down_revision = "20260722_0190"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    _retire_news_product_ai()
    _retire_token_pseudo_ai()
    _replace_macro_read_models()
    op.execute("ANALYZE news_items")
    op.execute("ANALYZE news_page_rows")
    op.execute("ANALYZE token_radar_dirty_targets")
    op.execute("ANALYZE macro_projection_dirty_targets")


def downgrade() -> None:
    raise RuntimeError("20260723_0191 is an irreversible hard cut; restore the pre-migration backup to downgrade")


def _retire_news_product_ai() -> None:
    op.execute(
        "LOCK TABLE notifications, notification_deliveries, worker_queue_terminal_events IN SHARE ROW EXCLUSIVE MODE"
    )
    _archive_retired_news_queue_evidence()
    _retire_news_state_after_archiving_deliveries()


def _archive_retired_news_queue_evidence() -> None:
    op.execute(
        """
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        )
        UPDATE worker_queue_terminal_events
        SET operator_action = 'archive',
            operator_reason = 'queue_retired_by_0191',
            operator_action_at_ms = migration_clock.now_ms
        FROM migration_clock
        WHERE operator_action IS NULL
          AND (
            worker_name = 'news_story_brief'
            OR (
              source_table = 'news_projection_dirty_targets'
              AND source_row_json ->> 'projection_name' = 'story_brief'
            )
          )
        """
    )


def _retire_news_state_after_archiving_deliveries() -> None:
    op.execute(
        """
        DO $$
        DECLARE
          running_count integer;
        BEGIN
          SELECT count(*)
          INTO running_count
          FROM notification_deliveries AS delivery
          JOIN notifications AS notification
            ON notification.notification_id = delivery.notification_id
          WHERE notification.rule_id = 'news_high_signal'
            AND delivery.status = 'running';

          IF running_count > 0 THEN
            RAISE EXCEPTION
              '0191 cannot retire news_high_signal while notification delivery is running';
          END IF;
        END
        $$
        """
    )
    op.execute(
        """
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        ), archived_deliveries AS MATERIALIZED (
          SELECT
            delivery.*,
            notification.dedup_key,
            to_jsonb(delivery) || jsonb_build_object(
              'notification', to_jsonb(notification)
            ) AS source_row_json
          FROM notification_deliveries AS delivery
          JOIN notifications AS notification
            ON notification.notification_id = delivery.notification_id
          WHERE notification.rule_id = 'news_high_signal'
            AND delivery.status IN ('pending', 'failed')
        ), hashed_deliveries AS MATERIALIZED (
          SELECT
            archived_deliveries.*,
            'md5:' || md5(source_row_json::text) AS source_row_hash
          FROM archived_deliveries
        )
        INSERT INTO worker_queue_terminal_events(
          terminal_id,
          worker_name,
          source_table,
          target_key,
          source_row_json,
          source_row_hash,
          final_status,
          final_reason,
          final_reason_bucket,
          attempt_count,
          payload_hash,
          first_seen_at_ms,
          last_attempted_at_ms,
          terminalized_at_ms,
          terminal_generation,
          operator_action,
          operator_reason,
          operator_action_at_ms
        )
        SELECT
          'wqte_' || md5(
            'notification_delivery|notification_deliveries|' || delivery_id || '|'
            || source_row_hash || '|1'
          ),
          'notification_delivery',
          'notification_deliveries',
          delivery_id,
          source_row_json,
          source_row_hash,
          status,
          'notification_rule_retired_by_0191',
          'other',
          attempt_count,
          dedup_key,
          created_at_ms,
          COALESCE(last_attempt_at_ms, updated_at_ms),
          migration_clock.now_ms,
          1,
          'archive',
          'queue_retired_by_0191',
          migration_clock.now_ms
        FROM hashed_deliveries
        CROSS JOIN migration_clock
        ON CONFLICT DO NOTHING
        """
    )

    op.execute("DELETE FROM notifications WHERE rule_id = 'news_high_signal'")
    op.execute("DELETE FROM news_projection_dirty_targets WHERE projection_name = 'story_brief'")
    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
          DROP CONSTRAINT news_projection_dirty_targets_projection_name_check,
          DROP CONSTRAINT news_projection_dirty_targets_check,
          ADD CONSTRAINT news_projection_dirty_targets_projection_name_check
            CHECK (projection_name = 'page'),
          ADD CONSTRAINT news_projection_dirty_targets_check
            CHECK (projection_name = 'page' AND target_kind = 'news_item' AND "window" = '')
        """
    )

    op.execute("DROP TABLE news_story_agent_briefs")
    op.execute("DROP TABLE news_story_agent_runs")

    op.execute("DROP INDEX idx_news_page_rows_direction_time")
    op.execute("DROP INDEX ix_news_page_rows_alert_ready_latest")
    op.execute("DROP INDEX ix_news_page_rows_agent_admission")
    op.execute("DROP INDEX ix_news_page_rows_macro_event_flow_latest")
    op.execute("DROP INDEX ix_news_page_rows_signal_direction")
    op.execute("DROP INDEX ix_news_page_rows_signal_score")
    op.execute("DROP INDEX ix_news_items_agent_admission_published")

    op.execute("DELETE FROM news_page_rows")
    op.execute(
        """
        ALTER TABLE news_page_rows
          DROP COLUMN agent_brief_json,
          DROP COLUMN agent_status,
          DROP COLUMN agent_brief_computed_at_ms,
          DROP COLUMN signal_json,
          DROP COLUMN token_impacts_json,
          DROP COLUMN agent_admission_status,
          DROP COLUMN agent_admission_reason,
          DROP COLUMN agent_admission_json,
          DROP COLUMN agent_representative_news_item_id,
          DROP COLUMN macro_event_flow_json
        """
    )
    op.execute(
        """
        ALTER TABLE news_items
          DROP COLUMN agent_admission_status,
          DROP COLUMN agent_admission_reason,
          DROP COLUMN agent_admission_json,
          DROP COLUMN agent_admission_version,
          DROP COLUMN agent_representative_news_item_id,
          DROP COLUMN agent_admission_computed_at_ms
        """
    )
    op.execute(
        """
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        )
        INSERT INTO news_projection_dirty_targets(
          projection_name,
          target_kind,
          target_id,
          "window",
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
        SELECT
          'page',
          'news_item',
          items.news_item_id,
          '',
          'schema_hard_cut_0191',
          'schema-hard-cut-0191:' || md5(items.news_item_id),
          items.updated_at_ms,
          0,
          migration_clock.now_ms,
          NULL,
          NULL,
          0,
          NULL,
          migration_clock.now_ms,
          migration_clock.now_ms
        FROM news_items AS items
        CROSS JOIN migration_clock
        WHERE items.lifecycle_status = 'processed'
        ON CONFLICT(projection_name, target_kind, target_id, "window") DO UPDATE SET
          dirty_reason = EXCLUDED.dirty_reason,
          payload_hash = EXCLUDED.payload_hash,
          source_watermark_ms = GREATEST(
            news_projection_dirty_targets.source_watermark_ms,
            EXCLUDED.source_watermark_ms
          ),
          priority = LEAST(news_projection_dirty_targets.priority, EXCLUDED.priority),
          due_at_ms = LEAST(news_projection_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
          leased_until_ms = NULL,
          lease_owner = NULL,
          attempt_count = 0,
          last_error = NULL,
          updated_at_ms = EXCLUDED.updated_at_ms
        """
    )


def _retire_token_pseudo_ai() -> None:
    op.execute(
        """
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        ), rebuild_targets AS MATERIALIZED (
          SELECT target_type_key, identity_id
          FROM token_radar_target_features
          WHERE btrim(target_type_key) <> '' AND btrim(identity_id) <> ''
          UNION
          SELECT target_type_key, identity_id
          FROM token_radar_current_rows
          WHERE btrim(target_type_key) <> '' AND btrim(identity_id) <> ''
          UNION
          SELECT target_type_key, identity_id
          FROM token_radar_rank_source_events
          WHERE btrim(target_type_key) <> '' AND btrim(identity_id) <> ''
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
          'schema_hard_cut_0191',
          false,
          true,
          'schema-hard-cut-0191:' || md5(
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
    op.execute("DELETE FROM token_radar_target_features")
    op.execute("DELETE FROM token_radar_current_rows")
    op.execute("DELETE FROM token_radar_publication_state")
    _migrate_token_first_seen()
    op.execute("DELETE FROM token_radar_rank_source_events")
    op.execute(
        """
        ALTER TABLE token_radar_target_features
          DROP COLUMN semantic_catalyst_raw_score,
          DROP COLUMN semantic_catalyst_weight
        """
    )


def _migrate_token_first_seen() -> None:
    op.execute(
        """
        CREATE TEMP TABLE token_radar_first_seen_0191 ON COMMIT DROP AS
        SELECT
          "window",
          scope,
          venue,
          target_type_key,
          identity_id,
          MIN(first_seen_ms) AS first_seen_ms,
          MAX(last_seen_ms) AS last_seen_ms,
          (array_agg(first_row_id ORDER BY first_seen_ms ASC, created_at_ms ASC)
            FILTER (WHERE first_row_id IS NOT NULL))[1] AS first_row_id,
          (array_agg(latest_row_id ORDER BY last_seen_ms DESC, updated_at_ms DESC)
            FILTER (WHERE latest_row_id IS NOT NULL))[1] AS latest_row_id,
          MIN(created_at_ms) AS created_at_ms,
          MAX(updated_at_ms) AS updated_at_ms
        FROM token_radar_target_first_seen
        GROUP BY "window", scope, venue, target_type_key, identity_id
        """
    )
    op.execute("DELETE FROM token_radar_target_first_seen")
    op.execute(
        """
        INSERT INTO token_radar_target_first_seen(
          projection_version,
          "window",
          scope,
          venue,
          target_type_key,
          identity_id,
          first_seen_ms,
          last_seen_ms,
          first_row_id,
          latest_row_id,
          created_at_ms,
          updated_at_ms
        )
        SELECT
          'token-radar-v14-transparent-factors',
          "window",
          scope,
          venue,
          target_type_key,
          identity_id,
          first_seen_ms,
          last_seen_ms,
          first_row_id,
          latest_row_id,
          created_at_ms,
          updated_at_ms
        FROM token_radar_first_seen_0191
        """
    )


def _replace_macro_read_models() -> None:
    op.execute("DELETE FROM macro_projection_dirty_targets")
    op.execute("DELETE FROM macro_observation_series_rows")
    op.execute("DELETE FROM macro_observation_series_publication_state")
    op.execute("DROP TABLE macro_view_snapshots")
    op.execute(
        """
        CREATE TABLE macro_view_snapshots (
          snapshot_key TEXT PRIMARY KEY,
          projection_version TEXT NOT NULL,
          fact_watermark DATE,
          market_cutoff DATE,
          computed_at_ms BIGINT NOT NULL,
          overview_json JSONB NOT NULL,
          cross_asset_json JSONB NOT NULL,
          rates_inflation_json JSONB NOT NULL,
          growth_labor_json JSONB NOT NULL,
          liquidity_funding_json JSONB NOT NULL,
          credit_json JSONB NOT NULL,
          payload_hash TEXT NOT NULL,
          CONSTRAINT macro_view_snapshots_current_key_check
            CHECK (snapshot_key = 'current'),
          CONSTRAINT macro_view_snapshots_overview_object_check
            CHECK (jsonb_typeof(overview_json) = 'object'),
          CONSTRAINT macro_view_snapshots_cross_asset_object_check
            CHECK (jsonb_typeof(cross_asset_json) = 'object'),
          CONSTRAINT macro_view_snapshots_rates_inflation_object_check
            CHECK (jsonb_typeof(rates_inflation_json) = 'object'),
          CONSTRAINT macro_view_snapshots_growth_labor_object_check
            CHECK (jsonb_typeof(growth_labor_json) = 'object'),
          CONSTRAINT macro_view_snapshots_liquidity_funding_object_check
            CHECK (jsonb_typeof(liquidity_funding_json) = 'object'),
          CONSTRAINT macro_view_snapshots_credit_object_check
            CHECK (jsonb_typeof(credit_json) = 'object')
        )
        """
    )
    op.execute(
        """
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        ), fact_watermark AS (
          SELECT
            COALESCE(MAX(ingested_at_ms), 0)::bigint AS source_watermark_ms,
            MIN(observed_at) AS min_observed_at,
            MAX(observed_at) AS max_observed_at
          FROM macro_observations
        )
        INSERT INTO macro_projection_dirty_targets(
          projection_name,
          projection_version,
          target_kind,
          target_id,
          payload_hash,
          dirty_reason,
          source_watermark_ms,
          priority,
          due_at_ms,
          leased_until_ms,
          lease_owner,
          attempt_count,
          last_error,
          created_at_ms,
          updated_at_ms,
          concept_key,
          min_observed_at,
          max_observed_at,
          source_watermark_date
        )
        SELECT
          'macro_evidence',
          'macro_evidence_v1',
          'current',
          'current',
          'schema-hard-cut-0191:macro-evidence-v1',
          'schema_hard_cut_0191',
          fact_watermark.source_watermark_ms,
          0,
          migration_clock.now_ms,
          NULL,
          NULL,
          0,
          NULL,
          migration_clock.now_ms,
          migration_clock.now_ms,
          NULL,
          fact_watermark.min_observed_at,
          fact_watermark.max_observed_at,
          fact_watermark.max_observed_at
        FROM migration_clock
        CROSS JOIN fact_watermark
        """
    )
