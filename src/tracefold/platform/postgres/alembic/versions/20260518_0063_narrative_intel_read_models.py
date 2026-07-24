"""Add narrative intelligence read model tables."""

from __future__ import annotations

from alembic import op

revision = "20260518_0063"
down_revision = "20260518_0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS narrative_admissions (
          admission_id TEXT PRIMARY KEY,
          target_type TEXT NOT NULL,
          target_id TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          schema_version TEXT NOT NULL,
          status TEXT NOT NULL,
          reason TEXT NOT NULL,
          priority BIGINT NOT NULL DEFAULT 0,
          last_radar_rank BIGINT,
          last_rank_score DOUBLE PRECISION,
          source_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          source_fingerprint TEXT,
          source_max_received_at_ms BIGINT,
          admitted_at_ms BIGINT NOT NULL,
          last_seen_at_ms BIGINT NOT NULL,
          next_semantics_due_at_ms BIGINT NOT NULL DEFAULT 0,
          next_digest_due_at_ms BIGINT NOT NULL DEFAULT 0,
          suppressed_at_ms BIGINT,
          updated_at_ms BIGINT NOT NULL,
          CHECK ("window" IN ('5m', '1h', '4h', '24h')),
          CHECK (scope IN ('all', 'matched')),
          CHECK (status IN ('admitted', 'suppressed'))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_narrative_admissions_target
          ON narrative_admissions(target_type, target_id, "window", scope, schema_version)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_narrative_admissions_due_semantics
          ON narrative_admissions(status, next_semantics_due_at_ms, priority DESC, last_seen_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_narrative_admissions_due_digest
          ON narrative_admissions(status, next_digest_due_at_ms, priority DESC, last_seen_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS narrative_model_runs (
          run_id TEXT PRIMARY KEY,
          stage TEXT NOT NULL,
          target_type TEXT,
          target_id TEXT,
          "window" TEXT,
          scope TEXT,
          provider TEXT NOT NULL,
          model TEXT NOT NULL,
          schema_version TEXT NOT NULL,
          prompt_version TEXT NOT NULL,
          artifact_version_hash TEXT,
          input_hash TEXT NOT NULL,
          output_hash TEXT,
          evidence_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          request_json JSONB NOT NULL,
          response_json JSONB,
          usage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          trace_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          status TEXT NOT NULL,
          error TEXT,
          started_at_ms BIGINT NOT NULL,
          finished_at_ms BIGINT NOT NULL,
          latency_ms BIGINT NOT NULL DEFAULT 0,
          CHECK (stage IN ('mention_semantics', 'discussion_digest')),
          CHECK (status IN ('done', 'failed'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_narrative_model_runs_target
          ON narrative_model_runs(target_type, target_id, "window", scope, finished_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_narrative_model_runs_stage_finished
          ON narrative_model_runs(stage, finished_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_mention_semantics (
          semantic_id TEXT PRIMARY KEY,
          event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
          target_type TEXT NOT NULL,
          target_id TEXT NOT NULL,
          schema_version TEXT NOT NULL,
          model_version TEXT NOT NULL,
          text_fingerprint TEXT NOT NULL,
          language TEXT,
          status TEXT NOT NULL,
          trade_stance TEXT NOT NULL DEFAULT 'unknown',
          attention_valence TEXT NOT NULL DEFAULT 'unknown',
          narrative_cluster_key TEXT,
          claim_type TEXT NOT NULL DEFAULT 'other',
          evidence_type TEXT NOT NULL DEFAULT 'unknown',
          semantic_confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
          co_mentioned_targets_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          evidence_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          raw_label_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          model_run_id TEXT REFERENCES narrative_model_runs(run_id) ON DELETE SET NULL,
          source_received_at_ms BIGINT NOT NULL,
          queued_at_ms BIGINT,
          computed_at_ms BIGINT,
          retry_count BIGINT NOT NULL DEFAULT 0,
          next_retry_at_ms BIGINT NOT NULL DEFAULT 0,
          error TEXT,
          CHECK (status IN ('queued', 'labeled', 'retryable_error', 'semantic_unavailable', 'stale')),
          CHECK (
            trade_stance IN (
              'bullish', 'bearish', 'neutral', 'skeptical', 'exit-risk', 'research-only', 'unknown'
            )
          ),
          CHECK (
            attention_valence IN (
              'positive', 'negative', 'mixed', 'ironic', 'hostile', 'panic', 'celebratory',
              'informational', 'unknown'
            )
          )
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_token_mention_semantics_identity
          ON token_mention_semantics(event_id, target_type, target_id, schema_version, text_fingerprint)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_mention_semantics_due
          ON token_mention_semantics(status, next_retry_at_ms, source_received_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_mention_semantics_target_time
          ON token_mention_semantics(target_type, target_id, source_received_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_mention_semantics_cluster
          ON token_mention_semantics(target_type, target_id, narrative_cluster_key, source_received_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_discussion_digests (
          digest_id TEXT PRIMARY KEY,
          target_type TEXT NOT NULL,
          target_id TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          schema_version TEXT NOT NULL,
          model_version TEXT NOT NULL,
          status TEXT NOT NULL,
          is_current BOOLEAN NOT NULL DEFAULT true,
          source_fingerprint TEXT,
          label_fingerprint TEXT,
          headline_zh TEXT,
          dominant_narratives_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          bull_view_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          bear_view_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          stance_mix_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          attention_valence_mix_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          propagation_read_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          reflexivity_read_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          watch_triggers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          invalidation_conditions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          data_gaps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          semantic_coverage DOUBLE PRECISION NOT NULL DEFAULT 0,
          source_event_count BIGINT NOT NULL DEFAULT 0,
          labeled_event_count BIGINT NOT NULL DEFAULT 0,
          independent_author_count BIGINT NOT NULL DEFAULT 0,
          evidence_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          model_run_id TEXT REFERENCES narrative_model_runs(run_id) ON DELETE SET NULL,
          computed_at_ms BIGINT NOT NULL,
          expires_at_ms BIGINT,
          superseded_at_ms BIGINT,
          CHECK ("window" IN ('5m', '1h', '4h', '24h')),
          CHECK (scope IN ('all', 'matched')),
          CHECK (status IN ('ready', 'pending', 'insufficient', 'semantic_unavailable', 'stale'))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_token_discussion_digests_current
          ON token_discussion_digests(target_type, target_id, "window", scope, schema_version)
          WHERE is_current
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_discussion_digests_target_history
          ON token_discussion_digests(target_type, target_id, "window", scope, computed_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_discussion_digests_status
          ON token_discussion_digests(status, computed_at_ms DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_token_discussion_digests_status")
    op.execute("DROP INDEX IF EXISTS idx_token_discussion_digests_target_history")
    op.execute("DROP INDEX IF EXISTS ux_token_discussion_digests_current")
    op.execute("DROP TABLE IF EXISTS token_discussion_digests")
    op.execute("DROP INDEX IF EXISTS idx_token_mention_semantics_cluster")
    op.execute("DROP INDEX IF EXISTS idx_token_mention_semantics_target_time")
    op.execute("DROP INDEX IF EXISTS idx_token_mention_semantics_due")
    op.execute("DROP INDEX IF EXISTS ux_token_mention_semantics_identity")
    op.execute("DROP TABLE IF EXISTS token_mention_semantics")
    op.execute("DROP INDEX IF EXISTS idx_narrative_model_runs_stage_finished")
    op.execute("DROP INDEX IF EXISTS idx_narrative_model_runs_target")
    op.execute("DROP TABLE IF EXISTS narrative_model_runs")
    op.execute("DROP INDEX IF EXISTS idx_narrative_admissions_due_digest")
    op.execute("DROP INDEX IF EXISTS idx_narrative_admissions_due_semantics")
    op.execute("DROP INDEX IF EXISTS ux_narrative_admissions_target")
    op.execute("DROP TABLE IF EXISTS narrative_admissions")
