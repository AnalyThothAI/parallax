"""Store macro projected source timestamps as source text."""

from __future__ import annotations

from alembic import op

revision = "20260526_0102"
down_revision = "20260526_0101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")
    op.execute(
        """
        ALTER TABLE macro_observation_series_rows
          ALTER COLUMN source_ts TYPE TEXT
          USING source_ts::text
        """
    )
    op.execute("ANALYZE macro_observation_series_rows")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")
    op.execute(
        """
        ALTER TABLE macro_observation_series_rows
          ALTER COLUMN source_ts TYPE TIMESTAMPTZ
          USING NULLIF(source_ts, '')::timestamptz
        """
    )
    op.execute("ANALYZE macro_observation_series_rows")
