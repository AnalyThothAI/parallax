"""Drop legacy asset stack and orphan price tables.

P0 follow-up to the 2026-05-16 backend architecture audit. The
closed-loop harness hard-cut (commit 1e4aec88) removed every runtime
writer to the legacy asset/market stack. This migration drops the
empty tables themselves and the FK columns on active tables that
referenced them.

Tables dropped (no runtime references after the harness hard-cut):
  - assets, asset_aliases, asset_venues, asset_market_snapshots
    (legacy asset registry; replaced by registry_assets + market_ticks)
  - asset_signal_snapshots, asset_signal_outcomes
    (replaced by harness_snapshots + harness_outcomes)
  - token_intent_resolution_candidates
    (resolution candidates live inline in token_intent_resolutions now)
  - market_provider_observations
    (provider observations are stored as market_ticks)
  - current_market_field_facts, token_market_price_baselines
    (orphans flagged by the audit; never wired into runtime)

FK columns dropped from active tables:
  - token_radar_rows.{asset_id, primary_venue_id}
  - token_intent_resolutions.{asset_id, primary_venue_id}

These columns were never populated by post-hard-cut code. Migration
20260507_0008 already made them nullable in anticipation of removal.

The duplicate-token audit indexes (idx_tir_*, idx_tirc_*, idx_trr_*,
idx_asssnap_*) added live on 2026-05-12 to make cascade SET NULL bulk
DELETE on `assets` survivable disappear with the columns they cover;
no alembic backfill is required.

Downgrade is a no-op. The dropped tables were already write-empty
before this migration. To revert, restore the database from a backup
taken prior to upgrade.
"""

from __future__ import annotations

from alembic import op

revision = "20260516_0050"
down_revision = "20260516_0049"
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
    # No data preserved; restore from backup if you need the legacy stack back.
    pass
