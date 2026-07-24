"""Add the collector durable raw-to-event processing carrier."""

from __future__ import annotations

from alembic import op

revision = "20260722_0189"
down_revision = "20260722_0188"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")
    op.execute(
        """
        CREATE TABLE collector_pending_items (
          source TEXT NOT NULL,
          channel TEXT NOT NULL,
          item_key TEXT NOT NULL,
          internal_id TEXT,
          item_json JSONB NOT NULL,
          received_at_ms BIGINT NOT NULL,
          frame_item_index BIGINT NOT NULL,
          payload_hash TEXT NOT NULL,
          due_at_ms BIGINT NOT NULL,
          snapshot_state TEXT NOT NULL,
          leased_until_ms BIGINT,
          lease_owner TEXT,
          attempt_count BIGINT NOT NULL DEFAULT 0,
          last_error TEXT,
          first_observed_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(source, channel, item_key),
          CONSTRAINT ck_collector_pending_items_source_nonblank CHECK (btrim(source) <> ''),
          CONSTRAINT ck_collector_pending_items_channel_nonblank CHECK (btrim(channel) <> ''),
          CONSTRAINT ck_collector_pending_items_key_nonblank CHECK (btrim(item_key) <> ''),
          CONSTRAINT ck_collector_pending_items_internal_id_nonblank
            CHECK (internal_id IS NULL OR btrim(internal_id) <> ''),
          CONSTRAINT ck_collector_pending_items_json_object CHECK (jsonb_typeof(item_json) = 'object'),
          CONSTRAINT ck_collector_pending_items_received_at_positive CHECK (received_at_ms > 0),
          CONSTRAINT ck_collector_pending_items_frame_item_index_nonnegative CHECK (frame_item_index >= 0),
          CONSTRAINT ck_collector_pending_items_payload_hash CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
          CONSTRAINT ck_collector_pending_items_due_at_positive CHECK (due_at_ms > 0),
          CONSTRAINT ck_collector_pending_items_snapshot_state
            CHECK (snapshot_state IN ('partial', 'complete', 'immediate')),
          CONSTRAINT ck_collector_pending_items_lease_pair
            CHECK ((leased_until_ms IS NULL) = (lease_owner IS NULL)),
          CONSTRAINT ck_collector_pending_items_lease_positive
            CHECK (leased_until_ms IS NULL OR leased_until_ms > 0),
          CONSTRAINT ck_collector_pending_items_attempt_nonnegative CHECK (attempt_count >= 0),
          CONSTRAINT ck_collector_pending_items_first_observed_positive CHECK (first_observed_at_ms > 0),
          CONSTRAINT ck_collector_pending_items_updated_positive CHECK (updated_at_ms > 0)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_collector_pending_items_due_lease
        ON collector_pending_items(
          due_at_ms, leased_until_ms, first_observed_at_ms, frame_item_index, source, channel, item_key
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_collector_pending_items_internal_id
        ON collector_pending_items(source, channel, internal_id)
        WHERE internal_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE collector_pending_items")
