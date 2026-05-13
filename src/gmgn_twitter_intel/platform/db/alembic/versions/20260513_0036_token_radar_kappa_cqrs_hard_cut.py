"""Hard-cut Token Radar market facts into Kappa/CQRS observation roles."""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "20260513_0036"
down_revision = "20260513_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    month_bounds = _decision_latest_month_bounds(bind)

    with op.get_context().autocommit_block():
        for name in (
            "uq_price_observations_message_anchor_resolution",
            "idx_price_observations_anchor_subject_time",
            "idx_price_observations_subject_kind_latest",
            "idx_price_observations_subject_latest_any",
            "idx_price_observations_subject_time_kind",
            "idx_price_observations_subject_latest",
            "idx_token_market_price_baselines_resolution",
        ):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")

    op.execute("ALTER TABLE price_observations RENAME TO price_observations_legacy")
    _create_partitioned_price_observations()
    for start_ms, end_ms in month_bounds:
        op.execute(
            f"""
            CREATE TABLE IF NOT EXISTS price_observations_decision_latest_{_month_suffix(start_ms)}
              PARTITION OF price_observations_decision_latest
              FOR VALUES FROM ({start_ms}) TO ({end_ms})
            """
        )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS price_observations_decision_latest_default
          PARTITION OF price_observations_decision_latest
          DEFAULT
        """
    )
    op.execute(
        """
        INSERT INTO price_observations (
          observation_id, pricefeed_id, provider, observed_at_ms, subject_type, subject_id,
          price_usd, price_quote, quote_symbol, price_basis, market_cap_usd, liquidity_usd,
          volume_24h_usd, open_interest_usd, holders, raw_payload_json, created_at_ms,
          source_event_id, source_intent_id, source_resolution_id, observation_kind,
          event_received_at_ms, observation_lag_ms
        )
        SELECT
          observation_id, pricefeed_id, provider, observed_at_ms, subject_type, subject_id,
          price_usd, price_quote, quote_symbol, price_basis, market_cap_usd, liquidity_usd,
          volume_24h_usd, open_interest_usd, holders, raw_payload_json, created_at_ms,
          source_event_id, source_intent_id, source_resolution_id,
          CASE WHEN observation_kind = 'message_anchor' OR observation_kind IS NULL
            THEN 'event_anchor'
            ELSE observation_kind
          END AS observation_kind,
          event_received_at_ms, observation_lag_ms
        FROM price_observations_legacy
        """
    )
    op.execute("DROP TABLE price_observations_legacy")
    op.execute("DROP TABLE IF EXISTS token_market_price_baselines")

    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_price_observations_event_anchor_resolution
              ON price_observations_event_anchor(source_resolution_id)
              WHERE source_resolution_id IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_event_anchor_observation_id
              ON price_observations_event_anchor(observation_id)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_event_anchor_subject_latest
              ON price_observations_event_anchor(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
            """
        )
        for start_ms, _end_ms in month_bounds:
            suffix = _month_suffix(start_ms)
            op.execute(
                f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_decision_latest_{suffix}_observation_id
                  ON price_observations_decision_latest_{suffix}(observation_id)
                """
            )
            op.execute(
                f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_decision_latest_{suffix}_subject_latest
                  ON price_observations_decision_latest_{suffix}(
                    subject_type, subject_id, observed_at_ms DESC, observation_id DESC
                  )
                """
            )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_decision_latest_default_observation_id
              ON price_observations_decision_latest_default(observation_id)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_decision_latest_default_subject_latest
              ON price_observations_decision_latest_default(
                subject_type, subject_id, observed_at_ms DESC, observation_id DESC
              )
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name in (
            "idx_price_observations_decision_latest_default_subject_latest",
            "idx_price_observations_decision_latest_default_observation_id",
            "idx_price_observations_event_anchor_subject_latest",
            "idx_price_observations_event_anchor_observation_id",
            "uq_price_observations_event_anchor_resolution",
        ):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")

    op.execute("ALTER TABLE price_observations RENAME TO price_observations_partitioned")
    _create_legacy_price_observations()
    op.execute(
        """
        INSERT INTO price_observations (
          observation_id, pricefeed_id, provider, observed_at_ms, subject_type, subject_id,
          price_usd, price_quote, quote_symbol, price_basis, market_cap_usd, liquidity_usd,
          volume_24h_usd, open_interest_usd, holders, raw_payload_json, created_at_ms,
          source_event_id, source_intent_id, source_resolution_id, observation_kind,
          event_received_at_ms, observation_lag_ms
        )
        SELECT
          observation_id, pricefeed_id, provider, observed_at_ms, subject_type, subject_id,
          price_usd, price_quote, quote_symbol, price_basis, market_cap_usd, liquidity_usd,
          volume_24h_usd, open_interest_usd, holders, raw_payload_json, created_at_ms,
          source_event_id, source_intent_id, source_resolution_id,
          CASE WHEN observation_kind = 'event_anchor'
            THEN 'message_anchor'
            ELSE observation_kind
          END AS observation_kind,
          event_received_at_ms, observation_lag_ms
        FROM price_observations_partitioned
        """
    )
    op.execute("DROP TABLE price_observations_partitioned CASCADE")
    _create_token_market_price_baselines()
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_price_observations_message_anchor_resolution
            ON price_observations(source_resolution_id)
            WHERE observation_kind = 'message_anchor' AND source_resolution_id IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_anchor_subject_time
            ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
            WHERE observation_kind = 'message_anchor'
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_market_price_baselines_resolution
            ON token_market_price_baselines(resolution_id)
            """
        )


def _create_partitioned_price_observations() -> None:
    op.execute(
        """
        CREATE TABLE price_observations (
          observation_id TEXT NOT NULL,
          pricefeed_id TEXT REFERENCES price_feeds(pricefeed_id) ON DELETE SET NULL,
          provider TEXT NOT NULL,
          observed_at_ms BIGINT NOT NULL,
          subject_type TEXT NOT NULL,
          subject_id TEXT NOT NULL,
          price_usd NUMERIC,
          price_quote NUMERIC,
          quote_symbol TEXT,
          price_basis TEXT NOT NULL DEFAULT 'unavailable',
          market_cap_usd NUMERIC,
          liquidity_usd NUMERIC,
          volume_24h_usd NUMERIC,
          open_interest_usd NUMERIC,
          holders BIGINT,
          raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at_ms BIGINT NOT NULL,
          source_event_id TEXT REFERENCES events(event_id) ON DELETE SET NULL,
          source_intent_id TEXT REFERENCES token_intents(intent_id) ON DELETE SET NULL,
          source_resolution_id TEXT REFERENCES token_intent_resolutions(resolution_id) ON DELETE SET NULL,
          observation_kind TEXT NOT NULL,
          event_received_at_ms BIGINT,
          observation_lag_ms BIGINT
        ) PARTITION BY LIST (observation_kind)
        """
    )
    op.execute(
        """
        CREATE TABLE price_observations_event_anchor
          PARTITION OF price_observations
          FOR VALUES IN ('event_anchor')
        """
    )
    op.execute(
        """
        CREATE TABLE price_observations_decision_latest
          PARTITION OF price_observations
          FOR VALUES IN ('decision_latest')
          PARTITION BY RANGE (observed_at_ms)
        """
    )
    op.execute(
        """
        CREATE TABLE price_observations_other
          PARTITION OF price_observations
          DEFAULT
        """
    )


def _create_legacy_price_observations() -> None:
    op.execute(
        """
        CREATE TABLE price_observations (
          observation_id TEXT PRIMARY KEY,
          pricefeed_id TEXT REFERENCES price_feeds(pricefeed_id) ON DELETE SET NULL,
          provider TEXT NOT NULL,
          observed_at_ms BIGINT NOT NULL,
          subject_type TEXT NOT NULL,
          subject_id TEXT NOT NULL,
          price_usd NUMERIC,
          price_quote NUMERIC,
          quote_symbol TEXT,
          price_basis TEXT NOT NULL DEFAULT 'unavailable',
          market_cap_usd NUMERIC,
          liquidity_usd NUMERIC,
          volume_24h_usd NUMERIC,
          open_interest_usd NUMERIC,
          holders BIGINT,
          raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at_ms BIGINT NOT NULL,
          source_event_id TEXT REFERENCES events(event_id) ON DELETE SET NULL,
          source_intent_id TEXT REFERENCES token_intents(intent_id) ON DELETE SET NULL,
          source_resolution_id TEXT REFERENCES token_intent_resolutions(resolution_id) ON DELETE SET NULL,
          observation_kind TEXT,
          event_received_at_ms BIGINT,
          observation_lag_ms BIGINT
        )
        """
    )


def _create_token_market_price_baselines() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_market_price_baselines (
          resolution_id TEXT PRIMARY KEY,
          event_id TEXT NOT NULL,
          target_type TEXT NOT NULL,
          target_id TEXT NOT NULL,
          event_received_at_ms BIGINT NOT NULL,
          first_price_observed_at_ms BIGINT,
          first_price_usd DOUBLE PRECISION,
          first_price_quote DOUBLE PRECISION,
          first_price_quote_symbol TEXT,
          first_price_basis TEXT,
          event_price_observation_id TEXT,
          event_price_observation_kind TEXT,
          event_price_provider TEXT,
          event_price_observed_at_ms BIGINT,
          event_price_usd DOUBLE PRECISION,
          event_price_quote DOUBLE PRECISION,
          event_price_quote_symbol TEXT,
          event_price_basis TEXT,
          before_event_price_observed_at_ms BIGINT,
          before_event_price_usd DOUBLE PRECISION,
          before_event_price_quote DOUBLE PRECISION,
          before_event_price_quote_symbol TEXT,
          before_event_price_basis TEXT,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )


def _decision_latest_month_bounds(bind: sa.Connection) -> list[tuple[int, int]]:
    row = (
        bind.execute(
            sa.text(
                """
            SELECT MIN(observed_at_ms) AS min_ms, MAX(observed_at_ms) AS max_ms
            FROM price_observations
            WHERE observation_kind NOT IN ('message_anchor')
            """
            )
        )
        .mappings()
        .first()
    )
    current_start = _month_start(datetime.now(tz=UTC))
    starts = {current_start, _next_month(current_start)}
    if row:
        if row.get("min_ms") is not None:
            starts.add(_month_start(datetime.fromtimestamp(int(row["min_ms"]) / 1000, tz=UTC)))
        if row.get("max_ms") is not None:
            max_start = _month_start(datetime.fromtimestamp(int(row["max_ms"]) / 1000, tz=UTC))
            starts.add(max_start)
            starts.add(_next_month(max_start))
    return [(start, _next_month(start)) for start in sorted(starts)]


def _month_start(value: datetime) -> int:
    start = value.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp() * 1000)


def _next_month(start_ms: int) -> int:
    value = datetime.fromtimestamp(start_ms / 1000, tz=UTC)
    year = value.year + 1 if value.month == 12 else value.year
    month = 1 if value.month == 12 else value.month + 1
    return int(value.replace(year=year, month=month).timestamp() * 1000)


def _month_suffix(start_ms: int) -> str:
    return datetime.fromtimestamp(start_ms / 1000, tz=UTC).strftime("%Y_%m")
