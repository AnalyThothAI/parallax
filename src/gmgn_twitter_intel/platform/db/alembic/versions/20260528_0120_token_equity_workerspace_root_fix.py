"""Add token/equity WorkerSpace root-fix schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260528_0120"
down_revision = "20260528_0116"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "token_radar_rank_source_events",
        sa.Column("source_payload_hash", sa.Text(), nullable=False, server_default=""),
    )
    op.alter_column(
        "token_radar_rank_source_events",
        "source_payload_hash",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default=None,
    )
    op.add_column(
        "token_radar_dirty_targets",
        sa.Column("source_dirty", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "token_radar_dirty_targets",
        sa.Column("market_dirty", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "token_radar_dirty_targets",
        sa.Column("repair_dirty", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    for column_name in ("source_dirty", "market_dirty", "repair_dirty"):
        op.alter_column(
            "token_radar_dirty_targets",
            column_name,
            existing_type=sa.Boolean(),
            existing_nullable=False,
            server_default=None,
        )

    op.create_table(
        "equity_event_process_jobs",
        sa.Column("event_document_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("due_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("lease_owner", sa.Text(), nullable=True),
        sa.Column("leased_until_ms", sa.BigInteger(), nullable=True),
        sa.Column("input_payload_hash", sa.Text(), nullable=False),
        sa.Column("started_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("finished_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("terminal_reason", sa.Text(), nullable=True),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("event_document_id"),
    )
    op.create_index(
        "idx_equity_event_process_jobs_due",
        "equity_event_process_jobs",
        ["due_at_ms", "created_at_ms", "event_document_id"],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'failed_retryable')"),
    )
    op.create_index(
        "idx_equity_event_process_jobs_running",
        "equity_event_process_jobs",
        ["started_at_ms", "leased_until_ms", "event_document_id"],
        unique=False,
        postgresql_where=sa.text("status = 'running'"),
    )

    op.add_column("equity_event_documents", sa.Column("provider_title", sa.Text(), nullable=True))
    op.add_column("equity_event_documents", sa.Column("provider_summary", sa.Text(), nullable=True))
    op.add_column("equity_event_documents", sa.Column("primary_document_url", sa.Text(), nullable=True))

    op.add_column(
        "equity_event_evidence_artifacts",
        sa.Column("artifact_payload_hash", sa.Text(), nullable=False, server_default=""),
    )
    op.alter_column(
        "equity_event_evidence_artifacts",
        "artifact_payload_hash",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default=None,
    )

    op.add_column("event_anchor_backfill_jobs", sa.Column("lease_owner", sa.Text(), nullable=True))
    op.add_column("event_anchor_backfill_jobs", sa.Column("leased_until_ms", sa.BigInteger(), nullable=True))
    op.execute("DROP INDEX IF EXISTS idx_event_anchor_backfill_jobs_due")
    op.create_index(
        "idx_event_anchor_backfill_jobs_due",
        "event_anchor_backfill_jobs",
        ["next_run_at_ms", "created_at_ms", "event_id", "intent_id"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "idx_event_anchor_backfill_jobs_running",
        "event_anchor_backfill_jobs",
        ["leased_until_ms", "updated_at_ms", "event_id", "intent_id"],
        unique=False,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    raise RuntimeError(
        "20260528_0120 token/equity WorkerSpace root-fix hard cut is not safely reversible; "
        "restore from backup or rebuild Token Radar and Equity Event facts from provider inputs."
    )
