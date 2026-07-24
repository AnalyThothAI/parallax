"""Allow macro event text series rows without numeric values."""

from __future__ import annotations

from alembic import op

revision = "20260616_0180"
down_revision = "20260612_0179"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE macro_observation_series_rows ALTER COLUMN value_numeric DROP NOT NULL")
    op.execute("ANALYZE macro_observation_series_rows")


def downgrade() -> None:
    op.execute("UPDATE macro_observation_series_rows SET value_numeric = 0 WHERE value_numeric IS NULL")
    op.execute("ALTER TABLE macro_observation_series_rows ALTER COLUMN value_numeric SET NOT NULL")
    op.execute("ANALYZE macro_observation_series_rows")
