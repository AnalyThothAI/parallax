"""Remove runtime-only market projections and duplicated current payloads."""

from __future__ import annotations

from alembic import op

revision = "20260722_0186"
down_revision = "20260721_0185"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    _canonicalize_chain_identity()
    _archive_retired_queue_evidence()
    _reconcile_market_tick_current_backlog()
    op.execute("DROP TABLE market_tick_current_dirty_targets")
    op.execute("DROP TABLE token_capture_tier_dirty_targets")
    op.execute("DROP TABLE token_capture_tier")
    _reset_macro_module_views()
    op.execute(
        """
        ALTER TABLE market_tick_current
          DROP COLUMN raw_payload_json,
          DROP COLUMN payload_hash
        """
    )
    op.execute("ALTER TABLE macro_view_snapshots DROP COLUMN assets_brief_json")


def downgrade() -> None:
    raise RuntimeError("20260722_0186 is an irreversible hard cut; restore a pre-migration backup to downgrade")


def _canonicalize_chain_identity() -> None:
    op.execute(
        """
        UPDATE registry_assets
        SET address = lower(address)
        WHERE chain_id LIKE 'eip155:%' AND address <> lower(address);

        UPDATE price_feeds
        SET address = lower(address)
        WHERE chain_id LIKE 'eip155:%' AND address IS NOT NULL AND address <> lower(address);

        DROP INDEX ux_registry_assets_identity;
        CREATE UNIQUE INDEX ux_registry_assets_identity
          ON registry_assets(chain_id, address);

        DROP INDEX ux_price_feeds_token_identity;
        CREATE UNIQUE INDEX ux_price_feeds_token_identity
          ON price_feeds(provider, feed_type, chain_id, address)
          WHERE address IS NOT NULL;

        ALTER TABLE registry_assets
          ADD CONSTRAINT ck_registry_assets_evm_address_canonical
          CHECK (chain_id NOT LIKE 'eip155:%' OR address = lower(address));

        ALTER TABLE price_feeds
          ADD CONSTRAINT ck_price_feeds_evm_address_canonical
          CHECK (address IS NULL OR chain_id NOT LIKE 'eip155:%' OR address = lower(address));
        """
    )


def _archive_retired_queue_evidence() -> None:
    op.execute(
        """
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        )
        UPDATE worker_queue_terminal_events
        SET operator_action = 'archive',
            operator_reason = 'queue_retired_by_0186',
            operator_action_at_ms = migration_clock.now_ms
        FROM migration_clock
        WHERE operator_action IS NULL
          AND source_table IN (
            'market_tick_current_dirty_targets',
            'token_capture_tier_dirty_targets'
          )
        """
    )


def _reconcile_market_tick_current_backlog() -> None:
    op.execute(
        """
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        ),
        backlog_targets AS MATERIALIZED (
          SELECT target_type, target_id
          FROM market_tick_current_dirty_targets
          UNION
          SELECT
            source_row_json ->> 'target_type' AS target_type,
            source_row_json ->> 'target_id' AS target_id
          FROM worker_queue_terminal_events
          WHERE source_table = 'market_tick_current_dirty_targets'
            AND operator_action = 'archive'
            AND operator_reason = 'queue_retired_by_0186'
            AND jsonb_typeof(source_row_json) = 'object'
            AND nullif(source_row_json ->> 'target_type', '') IS NOT NULL
            AND nullif(source_row_json ->> 'target_id', '') IS NOT NULL
        ),
        latest_ticks AS MATERIALIZED (
          SELECT latest.*
          FROM backlog_targets AS dirty
          CROSS JOIN LATERAL (
            SELECT ticks.*
            FROM market_ticks AS ticks
            WHERE ticks.target_type = dirty.target_type
              AND ticks.target_id = dirty.target_id
            ORDER BY ticks.observed_at_ms DESC, ticks.received_at_ms DESC, ticks.tick_id DESC
            LIMIT 1
          ) AS latest
        ),
        changed_current AS (
          INSERT INTO market_tick_current(
            target_type,
            target_id,
            tick_observed_at_ms,
            tick_id,
            source_tier,
            source_provider,
            chain,
            token_address,
            exchange,
            instrument,
            pricefeed_id,
            price_usd,
            liquidity_usd,
            volume_24h_usd,
            open_interest_usd,
            market_cap_usd,
            holders,
            raw_payload_json,
            payload_hash,
            updated_at_ms,
            created_at_ms
          )
          SELECT
            latest_ticks.target_type,
            latest_ticks.target_id,
            latest_ticks.observed_at_ms,
            latest_ticks.tick_id,
            latest_ticks.source_tier,
            latest_ticks.source_provider,
            latest_ticks.chain,
            latest_ticks.token_address,
            latest_ticks.exchange,
            latest_ticks.instrument,
            latest_ticks.pricefeed_id,
            latest_ticks.price_usd,
            latest_ticks.liquidity_usd,
            latest_ticks.volume_24h_usd,
            latest_ticks.open_interest_usd,
            latest_ticks.market_cap_usd,
            latest_ticks.holders,
            latest_ticks.raw_payload_json,
            latest_ticks.payload_hash,
            latest_ticks.received_at_ms,
            latest_ticks.created_at_ms
          FROM latest_ticks
          ON CONFLICT(target_type, target_id) DO UPDATE SET
            tick_observed_at_ms = EXCLUDED.tick_observed_at_ms,
            tick_id = EXCLUDED.tick_id,
            source_tier = EXCLUDED.source_tier,
            source_provider = EXCLUDED.source_provider,
            chain = EXCLUDED.chain,
            token_address = EXCLUDED.token_address,
            exchange = EXCLUDED.exchange,
            instrument = EXCLUDED.instrument,
            pricefeed_id = EXCLUDED.pricefeed_id,
            price_usd = EXCLUDED.price_usd,
            liquidity_usd = EXCLUDED.liquidity_usd,
            volume_24h_usd = EXCLUDED.volume_24h_usd,
            open_interest_usd = EXCLUDED.open_interest_usd,
            market_cap_usd = EXCLUDED.market_cap_usd,
            holders = EXCLUDED.holders,
            raw_payload_json = EXCLUDED.raw_payload_json,
            payload_hash = EXCLUDED.payload_hash,
            updated_at_ms = EXCLUDED.updated_at_ms,
            created_at_ms = EXCLUDED.created_at_ms
          WHERE (
            EXCLUDED.tick_observed_at_ms,
            EXCLUDED.updated_at_ms,
            EXCLUDED.tick_id
          ) > (
            market_tick_current.tick_observed_at_ms,
            market_tick_current.updated_at_ms,
            market_tick_current.tick_id
          )
          OR (
            (
              EXCLUDED.tick_observed_at_ms,
              EXCLUDED.updated_at_ms,
              EXCLUDED.tick_id
            ) = (
              market_tick_current.tick_observed_at_ms,
              market_tick_current.updated_at_ms,
              market_tick_current.tick_id
            )
            AND ROW(
              market_tick_current.source_tier,
              market_tick_current.source_provider,
              market_tick_current.chain,
              market_tick_current.token_address,
              market_tick_current.exchange,
              market_tick_current.instrument,
              market_tick_current.pricefeed_id,
              market_tick_current.price_usd,
              market_tick_current.liquidity_usd,
              market_tick_current.volume_24h_usd,
              market_tick_current.open_interest_usd,
              market_tick_current.market_cap_usd,
              market_tick_current.holders,
              market_tick_current.raw_payload_json,
              market_tick_current.payload_hash,
              market_tick_current.created_at_ms
            ) IS DISTINCT FROM ROW(
              EXCLUDED.source_tier,
              EXCLUDED.source_provider,
              EXCLUDED.chain,
              EXCLUDED.token_address,
              EXCLUDED.exchange,
              EXCLUDED.instrument,
              EXCLUDED.pricefeed_id,
              EXCLUDED.price_usd,
              EXCLUDED.liquidity_usd,
              EXCLUDED.volume_24h_usd,
              EXCLUDED.open_interest_usd,
              EXCLUDED.market_cap_usd,
              EXCLUDED.holders,
              EXCLUDED.raw_payload_json,
              EXCLUDED.payload_hash,
              EXCLUDED.created_at_ms
            )
          )
          RETURNING target_type, target_id
        ),
        mapped AS (
          SELECT
            'Asset'::text AS target_type_key,
            registry_assets.asset_id AS identity_id
          FROM changed_current
          CROSS JOIN LATERAL (
            SELECT assets.asset_id
            FROM registry_assets AS assets
            WHERE changed_current.target_id = assets.chain_id || ':' || assets.address
              AND assets.status IN ('candidate', 'canonical')
            ORDER BY assets.updated_at_ms DESC, assets.asset_id
            LIMIT 1
          ) AS registry_assets
          WHERE changed_current.target_type = 'chain_token'
          UNION ALL
          SELECT
            'CexToken'::text AS target_type_key,
            price_feeds.subject_id AS identity_id
          FROM changed_current
          CROSS JOIN LATERAL (
            SELECT feeds.subject_id
            FROM price_feeds AS feeds
            WHERE changed_current.target_id = feeds.provider || ':' || feeds.native_market_id
              AND feeds.subject_type = 'CexToken'
              AND feeds.provider = 'binance'
              AND feeds.feed_type = 'cex_swap'
              AND feeds.quote_symbol = 'USDT'
              AND feeds.status = 'canonical'
            ORDER BY feeds.updated_at_ms DESC, feeds.subject_id
            LIMIT 1
          ) AS price_feeds
          WHERE changed_current.target_type = 'cex_symbol'
        )
        INSERT INTO token_radar_dirty_targets(
          target_type_key,
          identity_id,
          dirty_reason,
          market_dirty,
          repair_dirty,
          payload_hash,
          due_at_ms,
          leased_until_ms,
          lease_owner,
          attempt_count,
          last_error,
          first_dirty_at_ms,
          updated_at_ms
        )
        SELECT
          mapped.target_type_key,
          mapped.identity_id,
          'market_tick_current_changed',
          true,
          false,
          encode(
            sha256(
              convert_to(
                mapped.target_type_key || ':' || mapped.identity_id || ':' || 'market_tick_current_changed',
                'UTF8'
              )
            ),
            'hex'
          ),
          migration_clock.now_ms,
          NULL,
          NULL,
          0,
          NULL,
          migration_clock.now_ms,
          migration_clock.now_ms
        FROM mapped
        CROSS JOIN migration_clock
        ON CONFLICT(target_type_key, identity_id) DO UPDATE SET
          dirty_reason = CASE
            WHEN token_radar_dirty_targets.dirty_reason = EXCLUDED.dirty_reason
            THEN token_radar_dirty_targets.dirty_reason
            ELSE 'mixed'
          END,
          market_dirty = true,
          payload_hash = EXCLUDED.payload_hash,
          due_at_ms = LEAST(token_radar_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
          leased_until_ms = NULL,
          lease_owner = NULL,
          attempt_count = CASE
            WHEN token_radar_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
            THEN 0
            ELSE token_radar_dirty_targets.attempt_count
          END,
          last_error = NULL,
          updated_at_ms = EXCLUDED.updated_at_ms
        """
    )


def _reset_macro_module_views() -> None:
    op.execute("DELETE FROM macro_view_snapshots")
    op.execute(
        """
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        )
        INSERT INTO macro_projection_dirty_targets(
          projection_name,
          projection_version,
          target_kind,
          target_id,
          payload_hash,
          dirty_reason,
          source_watermark_ms,
          priority,
          due_at_ms,
          leased_until_ms,
          lease_owner,
          attempt_count,
          last_error,
          created_at_ms,
          updated_at_ms
        )
        SELECT
          'macro_view',
          'macro_regime_v4',
          'current',
          'current',
          'migration:20260722_0186:module_views_only',
          'migration_module_views_only_rebuild',
          migration_clock.now_ms,
          0,
          migration_clock.now_ms,
          NULL,
          NULL,
          0,
          NULL,
          migration_clock.now_ms,
          migration_clock.now_ms
        FROM migration_clock
        ON CONFLICT(projection_name, projection_version, target_kind, target_id)
        DO UPDATE SET
          payload_hash = EXCLUDED.payload_hash,
          dirty_reason = EXCLUDED.dirty_reason,
          source_watermark_ms = GREATEST(
            macro_projection_dirty_targets.source_watermark_ms,
            EXCLUDED.source_watermark_ms
          ),
          priority = LEAST(macro_projection_dirty_targets.priority, EXCLUDED.priority),
          due_at_ms = LEAST(macro_projection_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
          leased_until_ms = NULL,
          lease_owner = NULL,
          attempt_count = 0,
          last_error = NULL,
          updated_at_ms = EXCLUDED.updated_at_ms
        """
    )
