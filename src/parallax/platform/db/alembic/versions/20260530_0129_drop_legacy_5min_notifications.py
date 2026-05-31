"""Delete retired 5m token notification rows."""

from __future__ import annotations

from alembic import op

revision = "20260530_0129"
down_revision = "20260529_0128"
branch_labels = None
depends_on = None

LEGACY_5MIN_RULES = ("hot_quality_token_5m", "quality_token_5m")


def upgrade() -> None:
    quoted_rules = ", ".join(f"'{rule_id}'" for rule_id in LEGACY_5MIN_RULES)
    op.execute(
        f"""
        DELETE FROM notifications
        WHERE rule_id IN ({quoted_rules})
        """
    )


def downgrade() -> None:
    """No downgrade for the hard-cut removal of legacy 5m token notifications."""
