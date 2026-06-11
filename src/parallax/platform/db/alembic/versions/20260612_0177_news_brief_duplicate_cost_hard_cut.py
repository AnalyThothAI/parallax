"""Hard-cut duplicate-cost News brief retries."""

from alembic import op

revision = "20260612_0177"
down_revision = "20260609_0176"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        CREATE TEMP TABLE _news_brief_terminal_current_items ON COMMIT DROP AS
        WITH ranked AS (
            SELECT targets.projection_name,
                   targets.target_kind,
                   targets.target_id,
                   targets."window",
                   targets.payload_hash,
                   targets.source_watermark_ms,
                   runs.run_id,
                   runs.news_item_id,
                   runs.input_hash,
                   runs.artifact_version_hash,
                   runs.prompt_version,
                   runs.schema_version,
                   runs.validator_version,
                   runs.error_class,
                   runs.error,
                   runs.finished_at_ms,
                   ROW_NUMBER() OVER (
                       PARTITION BY targets.projection_name, targets.target_kind, targets.target_id, targets."window"
                       ORDER BY runs.finished_at_ms DESC, runs.run_id DESC
                   ) AS row_number
              FROM news_projection_dirty_targets AS targets
              JOIN news_item_agent_runs AS runs
                ON runs.news_item_id = targets.target_id
               AND runs.input_hash = targets.payload_hash
             WHERE targets.projection_name = 'brief_input'
               AND targets.target_kind = 'news_item'
               AND targets."window" = ''
               AND targets.payload_hash <> ''
               AND runs.execution_started = true
               AND runs.status = 'failed'
               AND runs.outcome = 'failed'
               AND runs.error_class IN ('timeout', 'schema_invalid', 'domain_validation_failed',
                                        'provider_error', 'transport_error')
               AND NOT EXISTS (
                   SELECT 1
                     FROM news_item_agent_briefs AS briefs
                    WHERE briefs.news_item_id = targets.target_id
                      AND briefs.input_hash = targets.payload_hash
                      AND briefs.artifact_version_hash = runs.artifact_version_hash
                      AND briefs.prompt_version = runs.prompt_version
                      AND briefs.schema_version = runs.schema_version
                      AND briefs.validator_version = runs.validator_version
                      AND briefs.status IN ('ready', 'insufficient', 'failed')
               )
        )
        SELECT *
          FROM ranked
         WHERE row_number = 1
        """
    )
    op.execute(
        """
        INSERT INTO news_item_agent_briefs (
            news_item_id, agent_run_id, status, direction, decision_class, brief_json,
            input_hash, artifact_version_hash, prompt_version, schema_version,
            validator_version, computed_at_ms, created_at_ms, updated_at_ms
        )
        SELECT terminal.news_item_id,
               terminal.run_id,
               'failed',
               'neutral',
               'discard',
               jsonb_build_object(
                   'status', 'failed',
                   'direction', 'neutral',
                   'decision_class', 'discard',
                   'event_type', NULL,
                   'summary_zh', '',
                   'market_read_zh', '',
                   'market_domains', '[]'::jsonb,
                   'transmission_paths', '[]'::jsonb,
                   'market_impacts', '[]'::jsonb,
                   'bull_view', jsonb_build_object('strength', 'absent', 'thesis_zh', '', 'evidence_refs', '[]'::jsonb),
                   'bear_view', jsonb_build_object('strength', 'absent', 'thesis_zh', '', 'evidence_refs', '[]'::jsonb),
                   'affected_entities', '[]'::jsonb,
                   'watch_triggers', '[]'::jsonb,
                   'invalidation_conditions', '[]'::jsonb,
                   'data_gaps', jsonb_build_array(
                       jsonb_build_object(
                           'description_zh',
                           '新闻条目智能摘要不可发布，终态原因：' ||
                           COALESCE(NULLIF(terminal.error_class, ''), 'agent_brief_failed') ||
                           CASE
                             WHEN COALESCE(NULLIF(terminal.error, ''), '') <> ''
                               THEN '；原因：' || left(terminal.error, 120)
                             ELSE ''
                           END,
                           'severity', 'high'
                       )
                   ),
                   'evidence_refs', '[]'::jsonb
               ),
               terminal.input_hash,
               terminal.artifact_version_hash,
               terminal.prompt_version,
               terminal.schema_version,
               terminal.validator_version,
               terminal.finished_at_ms,
               terminal.finished_at_ms,
               terminal.finished_at_ms
          FROM _news_brief_terminal_current_items AS terminal
        ON CONFLICT (news_item_id) DO UPDATE
           SET agent_run_id = EXCLUDED.agent_run_id,
               status = EXCLUDED.status,
               direction = EXCLUDED.direction,
               decision_class = EXCLUDED.decision_class,
               brief_json = EXCLUDED.brief_json,
               input_hash = EXCLUDED.input_hash,
               artifact_version_hash = EXCLUDED.artifact_version_hash,
               prompt_version = EXCLUDED.prompt_version,
               schema_version = EXCLUDED.schema_version,
               validator_version = EXCLUDED.validator_version,
               computed_at_ms = EXCLUDED.computed_at_ms,
               updated_at_ms = EXCLUDED.updated_at_ms
        """
    )
    op.execute(
        """
        DELETE FROM news_projection_dirty_targets AS targets
         USING news_item_agent_briefs AS briefs
         WHERE targets.projection_name = 'brief_input'
           AND targets.target_kind = 'news_item'
           AND targets."window" = ''
           AND briefs.news_item_id = targets.target_id
           AND briefs.input_hash = targets.payload_hash
           AND briefs.artifact_version_hash <> ''
           AND briefs.prompt_version <> ''
           AND briefs.schema_version <> ''
           AND briefs.validator_version <> ''
           AND briefs.status IN ('ready', 'insufficient', 'failed')
        """
    )
    op.execute(
        """
        WITH runtime_now AS (
            SELECT (EXTRACT(EPOCH FROM now()) * 1000)::bigint AS now_ms
        )
        INSERT INTO news_projection_dirty_targets (
            projection_name, target_kind, target_id, "window",
            dirty_reason, payload_hash, source_watermark_ms, priority,
            due_at_ms, leased_until_ms, lease_owner, attempt_count, last_error,
            first_dirty_at_ms, updated_at_ms
        )
        SELECT 'page',
               'news_item',
               terminal.news_item_id,
               '',
               'news_brief_duplicate_cost_hard_cut',
               md5(terminal.news_item_id || ':news_brief_duplicate_cost_hard_cut:' || terminal.input_hash),
               GREATEST(terminal.source_watermark_ms, terminal.finished_at_ms),
               100,
               runtime_now.now_ms,
               NULL,
               NULL,
               0,
               NULL,
               runtime_now.now_ms,
               runtime_now.now_ms
          FROM _news_brief_terminal_current_items AS terminal,
               runtime_now
        ON CONFLICT (projection_name, target_kind, target_id, "window") DO UPDATE
           SET dirty_reason = EXCLUDED.dirty_reason,
               payload_hash = EXCLUDED.payload_hash,
               source_watermark_ms = GREATEST(
                   news_projection_dirty_targets.source_watermark_ms,
                   EXCLUDED.source_watermark_ms
               ),
               priority = EXCLUDED.priority,
               due_at_ms = EXCLUDED.due_at_ms,
               leased_until_ms = NULL,
               lease_owner = NULL,
               attempt_count = 0,
               last_error = NULL,
               updated_at_ms = EXCLUDED.updated_at_ms
        """
    )
    op.execute("ANALYZE news_item_agent_runs")
    op.execute("ANALYZE news_item_agent_briefs")
    op.execute("ANALYZE news_projection_dirty_targets")


def downgrade() -> None:
    pass
