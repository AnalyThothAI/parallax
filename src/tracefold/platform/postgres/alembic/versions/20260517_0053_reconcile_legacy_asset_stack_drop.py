"""Reconcile legacy asset stack drop after duplicate local 0050 revision.

Some local/dev databases were stamped with revision ``20260516_0050`` while
the repository temporarily contained two different migrations with that same
revision id. After the pulse-agent-desk migration was linearized to
``20260516_0051``, those databases could advance to head without ever running
the legacy asset stack drop from ``20260516_0050_drop_legacy_asset_stack``.

This reconciliation migration repeats that drop idempotently. Databases that
already applied the original drop see only no-op ``IF EXISTS`` statements;
databases that missed it converge to the intended schema.
"""

from __future__ import annotations

from alembic import op

revision = "20260517_0053"
down_revision = "20260517_0052"
branch_labels = None
depends_on = None


_DROP_COLUMNS = (
    ("token_radar_rows", "asset_id"),
    ("token_radar_rows", "primary_venue_id"),
    ("token_intent_resolutions", "asset_id"),
    ("token_intent_resolutions", "primary_venue_id"),
)

_DROP_TABLES = (
    "asset_signal_outcomes",
    "asset_signal_snapshots",
    "token_intent_resolution_candidates",
    "market_provider_observations",
    "asset_market_snapshots",
    "asset_aliases",
    "asset_venues",
    "assets",
    "current_market_field_facts",
    "token_market_price_baselines",
)


def upgrade() -> None:
    for table, column in _DROP_COLUMNS:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}")
    for table in _DROP_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


def downgrade() -> None:
    # No data preserved; restore from backup if the legacy stack is required.
    pass
