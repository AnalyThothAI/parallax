"""Drop pre-venue Token Radar current-row unique constraints."""

from __future__ import annotations

from alembic import op

revision = "20260529_0127"
down_revision = "20260529_0126"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL truncates long auto-generated constraint names, so drop by
    # definition. These old identities block per-venue rank/target rows.
    op.execute(
        """
        DO $$
        DECLARE
          constraint_name TEXT;
        BEGIN
          FOR constraint_name IN
            SELECT conname
            FROM pg_constraint
            WHERE conrelid = 'public.token_radar_current_rows'::regclass
              AND contype = 'u'
              AND pg_get_constraintdef(oid) IN (
                'UNIQUE (projection_version, "window", scope, lane, rank)',
                'UNIQUE (projection_version, "window", scope, lane, target_type_key, identity_id)'
              )
          LOOP
            EXECUTE format(
              'ALTER TABLE token_radar_current_rows DROP CONSTRAINT %I',
              constraint_name
            );
          END LOOP;
        END $$;
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_token_radar_current_rows_read")

    # Current/publication rows and first-seen rows are derived and were partly
    # repopulated under the stale constraints during the first 0126 rollout.
    op.execute("DELETE FROM token_radar_current_rows")
    op.execute("DELETE FROM token_radar_target_first_seen")
    op.execute("DELETE FROM token_radar_publication_state")
    op.execute(
        """
        UPDATE token_radar_source_dirty_events
        SET attempt_count = 0,
            last_error = NULL,
            leased_until_ms = NULL,
            lease_owner = NULL,
            due_at_ms = (extract(epoch from clock_timestamp()) * 1000)::bigint,
            updated_at_ms = (extract(epoch from clock_timestamp()) * 1000)::bigint
        WHERE last_error IS NOT NULL OR leased_until_ms IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE token_radar_dirty_targets
        SET attempt_count = 0,
            last_error = NULL,
            leased_until_ms = NULL,
            lease_owner = NULL,
            due_at_ms = (extract(epoch from clock_timestamp()) * 1000)::bigint,
            updated_at_ms = (extract(epoch from clock_timestamp()) * 1000)::bigint
        WHERE last_error IS NOT NULL OR leased_until_ms IS NOT NULL
        """
    )


def downgrade() -> None:
    """No compatibility downgrade for the hard-cut derived read models."""
