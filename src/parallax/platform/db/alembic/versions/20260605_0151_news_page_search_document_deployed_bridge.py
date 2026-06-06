"""Bridge deployed News page search document revision."""

from __future__ import annotations

revision = "20260605_0151"
down_revision = "20260605_0150"
branch_labels = None
depends_on = None


def upgrade() -> None:
    return None


def downgrade() -> None:
    raise RuntimeError(
        "20260605_0151 is a deployed News page search document bridge revision and is not safely reversible"
    )
