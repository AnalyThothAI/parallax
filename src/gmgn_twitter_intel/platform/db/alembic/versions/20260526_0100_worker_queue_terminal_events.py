"""Add worker queue terminal evidence table."""

from __future__ import annotations

from alembic import op

revision = "20260526_0100"
down_revision = "20260526_0099"
branch_labels = None
depends_on = None


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS worker_queue_terminal_events(
  terminal_id TEXT PRIMARY KEY,
  worker_name TEXT NOT NULL,
  source_table TEXT NOT NULL,
  target_key TEXT NOT NULL,
  source_row_json JSONB NOT NULL,
  source_row_hash TEXT NOT NULL,
  final_status TEXT NOT NULL,
  final_reason TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  payload_hash TEXT NOT NULL DEFAULT '',
  first_seen_at_ms BIGINT,
  last_attempted_at_ms BIGINT,
  terminalized_at_ms BIGINT NOT NULL,
  terminal_generation INTEGER NOT NULL DEFAULT 1,
  operator_action TEXT,
  operator_reason TEXT,
  operator_action_at_ms BIGINT
)
"""


_CREATE_INDEX_SQL = (
    """
    CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_worker_queue_terminal_source_snapshot
      ON worker_queue_terminal_events(
        worker_name, source_table, target_key, source_row_hash, terminal_generation
      )
    """,
    """
    CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_worker_queue_terminal_one_unresolved
      ON worker_queue_terminal_events(worker_name, source_table, target_key)
      WHERE operator_action IS NULL
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_worker_queue_terminal_unresolved
      ON worker_queue_terminal_events(worker_name, source_table, terminalized_at_ms DESC)
      WHERE operator_action IS NULL
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_worker_queue_terminal_source
      ON worker_queue_terminal_events(source_table, worker_name)
    """,
)


_DROP_INDEX_SQL = (
    "DROP INDEX CONCURRENTLY IF EXISTS idx_worker_queue_terminal_unresolved",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_worker_queue_terminal_source",
    "DROP INDEX CONCURRENTLY IF EXISTS uq_worker_queue_terminal_one_unresolved",
    "DROP INDEX CONCURRENTLY IF EXISTS uq_worker_queue_terminal_source_snapshot",
)


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")
    op.execute(_CREATE_TABLE_SQL)
    _backfill_existing_terminal_rows()

    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        for statement in _CREATE_INDEX_SQL:
            op.execute(statement)
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")

    op.execute("ANALYZE worker_queue_terminal_events")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        for statement in _DROP_INDEX_SQL:
            op.execute(statement)
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")

    op.execute("DROP TABLE IF EXISTS worker_queue_terminal_events")


def _backfill_existing_terminal_rows() -> None:
    statements = (
        """
        INSERT INTO worker_queue_terminal_events(
          terminal_id, worker_name, source_table, target_key, source_row_json,
          source_row_hash, final_status, final_reason, attempt_count, payload_hash,
          first_seen_at_ms, last_attempted_at_ms, terminalized_at_ms, terminal_generation
        )
        SELECT
          'wqte_' || md5('enrichment|enrichment_jobs|' || job_id || '|' || source_row_hash || '|1'),
          'enrichment',
          'enrichment_jobs',
          job_id,
          source_row_json,
          source_row_hash,
          status,
          COALESCE(NULLIF(last_error, ''), status),
          attempt_count,
          '',
          created_at_ms,
          updated_at_ms,
          updated_at_ms,
          1
        FROM (
          SELECT *, to_jsonb(enrichment_jobs) AS source_row_json,
                 'md5:' || md5(to_jsonb(enrichment_jobs)::text) AS source_row_hash
          FROM enrichment_jobs
          WHERE status = 'dead'
        ) AS rows
        ON CONFLICT DO NOTHING
        """,
        """
        INSERT INTO worker_queue_terminal_events(
          terminal_id, worker_name, source_table, target_key, source_row_json,
          source_row_hash, final_status, final_reason, attempt_count, payload_hash,
          first_seen_at_ms, last_attempted_at_ms, terminalized_at_ms, terminal_generation
        )
        SELECT
          'wqte_' || md5('pulse_candidate|pulse_agent_jobs|' || job_id || '|' || source_row_hash || '|1'),
          'pulse_candidate',
          'pulse_agent_jobs',
          job_id,
          source_row_json,
          source_row_hash,
          status,
          COALESCE(NULLIF(last_error, ''), status),
          attempt_count,
          '',
          created_at_ms,
          updated_at_ms,
          updated_at_ms,
          1
        FROM (
          SELECT *, to_jsonb(pulse_agent_jobs) AS source_row_json,
                 'md5:' || md5(to_jsonb(pulse_agent_jobs)::text) AS source_row_hash
          FROM pulse_agent_jobs
          WHERE status = 'dead'
        ) AS rows
        ON CONFLICT DO NOTHING
        """,
        """
        INSERT INTO worker_queue_terminal_events(
          terminal_id, worker_name, source_table, target_key, source_row_json,
          source_row_hash, final_status, final_reason, attempt_count, payload_hash,
          first_seen_at_ms, last_attempted_at_ms, terminalized_at_ms, terminal_generation
        )
        SELECT
          'wqte_' || md5(
            'event_anchor_backfill|event_anchor_backfill_jobs|' || target_key || '|' || source_row_hash || '|1'
          ),
          'event_anchor_backfill',
          'event_anchor_backfill_jobs',
          target_key,
          source_row_json,
          source_row_hash,
          status,
          COALESCE(NULLIF(last_reason, ''), status),
          attempt_count,
          '',
          created_at_ms,
          updated_at_ms,
          updated_at_ms,
          1
        FROM (
          SELECT *,
                 event_id || ':' || intent_id AS target_key,
                 to_jsonb(event_anchor_backfill_jobs) AS source_row_json,
                 'md5:' || md5(to_jsonb(event_anchor_backfill_jobs)::text) AS source_row_hash
          FROM event_anchor_backfill_jobs
          WHERE status IN ('failed', 'expired')
        ) AS rows
        ON CONFLICT DO NOTHING
        """,
        """
        INSERT INTO worker_queue_terminal_events(
          terminal_id, worker_name, source_table, target_key, source_row_json,
          source_row_hash, final_status, final_reason, attempt_count, payload_hash,
          first_seen_at_ms, last_attempted_at_ms, terminalized_at_ms, terminal_generation
        )
        SELECT
          'wqte_' || md5('mention_semantics|token_mention_semantics|' || semantic_id || '|' || source_row_hash || '|1'),
          'mention_semantics',
          'token_mention_semantics',
          semantic_id,
          source_row_json,
          source_row_hash,
          status,
          COALESCE(NULLIF(error, ''), status),
          attempt_count,
          '',
          COALESCE(queued_at_ms, source_received_at_ms),
          COALESCE(computed_at_ms, claimed_at_ms, source_received_at_ms),
          COALESCE(computed_at_ms, claimed_at_ms, source_received_at_ms),
          1
        FROM (
          SELECT *, to_jsonb(token_mention_semantics) AS source_row_json,
                 'md5:' || md5(to_jsonb(token_mention_semantics)::text) AS source_row_hash
          FROM token_mention_semantics
          WHERE status = 'semantic_unavailable'
        ) AS rows
        ON CONFLICT DO NOTHING
        """,
    )
    for statement in statements:
        op.execute(statement)
