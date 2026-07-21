"""Hard-cut redundant control planes and compact current read models."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "20260721_0185"
down_revision = "20260721_0184"
branch_labels = None
depends_on = None

_BACKFILL_BATCH_SIZE = 1_000
_RETENTION_30_DAYS_MS = 30 * 24 * 60 * 60 * 1_000
_RETENTION_180_DAYS_MS = 180 * 24 * 60 * 60 * 1_000


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")

    _archive_retired_queue_evidence()
    _merge_token_radar_source_queue()
    _add_news_source_config_identity()
    _hard_cut_news_projection_lanes()
    _compact_macro_storage()
    _add_retention_indexes()
    _apply_attempt_ledger_retention()
    _drop_redundant_tables()


def downgrade() -> None:
    raise RuntimeError("20260721_0185 is an irreversible hard cut; restore a pre-migration backup to downgrade")


def _archive_retired_queue_evidence() -> None:
    op.execute(
        """
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        )
        UPDATE worker_queue_terminal_events
        SET operator_action = 'archive',
            operator_reason = 'queue_retired_by_0185',
            operator_action_at_ms = migration_clock.now_ms
        FROM migration_clock
        WHERE operator_action IS NULL
          AND (
            source_table IN (
              'token_radar_source_dirty_events',
              'narrative_admission_dirty_targets'
            )
            OR worker_name IN (
              'narrative_admission',
              'macro_daily_brief',
              'cex_oi_radar_board',
              'news_item_brief',
              'news_source_quality'
            )
            OR (
              source_table = 'news_projection_dirty_targets'
              AND source_row_json ->> 'projection_name' IN ('brief_input', 'source_quality')
            )
          )
        """
    )


def _merge_token_radar_source_queue() -> None:
    op.execute(
        """
        WITH grouped AS (
          SELECT
            target_type_key,
            identity_id,
            CASE
              WHEN count(DISTINCT dirty_reason) = 1 THEN min(dirty_reason)
              ELSE 'mixed'
            END AS dirty_reason,
            'source-queue-hard-cut-0185:' || md5(
              target_type_key || ':' || identity_id || ':'
              || max(updated_at_ms)::text || ':' || count(*)::text
            ) AS payload_hash,
            min(due_at_ms)::bigint AS due_at_ms,
            min(first_dirty_at_ms)::bigint AS first_dirty_at_ms,
            max(updated_at_ms)::bigint AS updated_at_ms
          FROM token_radar_source_dirty_events
          GROUP BY target_type_key, identity_id
        )
        INSERT INTO token_radar_dirty_targets(
          target_type_key,
          identity_id,
          dirty_reason,
          payload_hash,
          due_at_ms,
          leased_until_ms,
          lease_owner,
          attempt_count,
          last_error,
          first_dirty_at_ms,
          updated_at_ms,
          market_dirty,
          repair_dirty
        )
        SELECT
          target_type_key,
          identity_id,
          dirty_reason,
          payload_hash,
          due_at_ms,
          NULL,
          NULL,
          0,
          NULL,
          first_dirty_at_ms,
          updated_at_ms,
          false,
          false
        FROM grouped
        ON CONFLICT(target_type_key, identity_id) DO UPDATE SET
          dirty_reason = CASE
            WHEN token_radar_dirty_targets.dirty_reason = excluded.dirty_reason
              THEN token_radar_dirty_targets.dirty_reason
            ELSE 'mixed'
          END,
          payload_hash = excluded.payload_hash,
          due_at_ms = LEAST(token_radar_dirty_targets.due_at_ms, excluded.due_at_ms),
          leased_until_ms = NULL,
          lease_owner = NULL,
          attempt_count = 0,
          last_error = NULL,
          first_dirty_at_ms = LEAST(
            token_radar_dirty_targets.first_dirty_at_ms,
            excluded.first_dirty_at_ms
          ),
          updated_at_ms = GREATEST(token_radar_dirty_targets.updated_at_ms, excluded.updated_at_ms),
          market_dirty = token_radar_dirty_targets.market_dirty OR excluded.market_dirty,
          repair_dirty = token_radar_dirty_targets.repair_dirty OR excluded.repair_dirty
        """
    )
    op.execute("DROP TABLE token_radar_source_dirty_events")


def _add_news_source_config_identity() -> None:
    op.execute("ALTER TABLE news_sources ADD COLUMN config_payload_hash TEXT")
    op.execute("ALTER TABLE news_sources ADD COLUMN terminal_config_payload_hash TEXT")
    _backfill_news_source_config_hashes()
    op.execute("ALTER TABLE news_sources ALTER COLUMN config_payload_hash SET NOT NULL")
    op.execute(
        """
        ALTER TABLE news_sources
        ADD CONSTRAINT news_sources_config_payload_hash_check
        CHECK (config_payload_hash ~ '^sha256:[0-9a-f]{64}$')
        """
    )
    op.execute(
        """
        ALTER TABLE news_sources
        ADD CONSTRAINT news_sources_terminal_config_payload_hash_check
        CHECK (
          terminal_config_payload_hash IS NULL
          OR terminal_config_payload_hash ~ '^sha256:[0-9a-f]{64}$'
        )
        """
    )


def _backfill_news_source_config_hashes() -> None:
    bind = op.get_bind()
    select_rows = sa.text(
        """
        SELECT
          source_id,
          provider_type,
          feed_url,
          source_domain,
          source_name,
          source_role,
          trust_tier,
          managed_by_config,
          enabled,
          refresh_interval_seconds,
          coverage_tags_json,
          asset_universe_json,
          authority_scope_json,
          fetch_policy_json,
          cost_policy_json
        FROM news_sources
        WHERE config_payload_hash IS NULL
        ORDER BY source_id
        LIMIT :limit
        """
    )
    update_hash = sa.text(
        """
        UPDATE news_sources
        SET config_payload_hash = :config_payload_hash
        WHERE source_id = :source_id
        """
    )
    while True:
        rows = bind.execute(select_rows, {"limit": _BACKFILL_BATCH_SIZE}).mappings().all()
        if not rows:
            break
        for row in rows:
            payload = {
                "source_id": str(row["source_id"]),
                "provider_type": str(row["provider_type"]),
                "feed_url": str(row["feed_url"]),
                "source_domain": str(row["source_domain"]),
                "source_name": str(row["source_name"]),
                "source_role": str(row["source_role"]),
                "trust_tier": str(row["trust_tier"]),
                "managed_by_config": bool(row["managed_by_config"]),
                "enabled": bool(row["enabled"]),
                "refresh_interval_seconds": int(row["refresh_interval_seconds"]),
                "coverage_tags_json": _string_list(row["coverage_tags_json"]),
                "asset_universe_json": _string_list(row["asset_universe_json"]),
                "authority_scope_json": _mapping_or_empty(row["authority_scope_json"]),
                "fetch_policy_json": _mapping_or_empty(row["fetch_policy_json"]),
                "cost_policy_json": _mapping_or_empty(row["cost_policy_json"]),
            }
            bind.execute(
                update_hash,
                {
                    "source_id": row["source_id"],
                    "config_payload_hash": _stable_payload_hash(payload),
                },
            )


def _hard_cut_news_projection_lanes() -> None:
    op.execute(
        """
        DELETE FROM news_projection_dirty_targets
        WHERE projection_name IN ('brief_input', 'source_quality')
        """
    )
    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
        DROP CONSTRAINT news_projection_dirty_targets_projection_name_check
        """
    )
    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
        DROP CONSTRAINT news_projection_dirty_targets_check
        """
    )
    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
        ADD CONSTRAINT news_projection_dirty_targets_projection_name_check
        CHECK (projection_name IN ('page', 'story_brief'))
        """
    )
    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
        ADD CONSTRAINT news_projection_dirty_targets_check
        CHECK (
          (projection_name = 'page' AND target_kind = 'news_item' AND "window" = '')
          OR (projection_name = 'story_brief' AND target_kind = 'story' AND "window" = '')
        )
        """
    )


def _compact_macro_storage() -> None:
    op.execute("ALTER TABLE macro_sync_runs DROP CONSTRAINT macro_sync_runs_import_run_id_fkey")
    op.execute("ALTER TABLE macro_sync_runs DROP COLUMN import_run_id")
    op.execute("ALTER TABLE macro_sync_runs ALTER COLUMN requested_start DROP NOT NULL")
    op.execute("ALTER TABLE macro_sync_runs ALTER COLUMN requested_end DROP NOT NULL")
    op.execute("DROP TABLE macro_import_runs")

    op.execute("ALTER TABLE macro_observation_series_rows ADD COLUMN event_metadata_json JSONB")
    op.execute(
        """
        UPDATE macro_observation_series_rows
        SET event_metadata_json = '{}'::jsonb
        WHERE concept_key NOT LIKE 'event:%'
        """
    )
    _backfill_macro_event_metadata()
    op.execute("ALTER TABLE macro_observation_series_rows ALTER COLUMN event_metadata_json SET NOT NULL")
    op.execute("DROP INDEX idx_macro_observation_series_rows_payload_hash")
    op.execute("DROP INDEX idx_macro_observation_series_rows_history_order")
    op.execute(
        """
        ALTER TABLE macro_observation_series_rows
          DROP COLUMN series_rank,
          DROP COLUMN source_priority,
          DROP COLUMN source_ts,
          DROP COLUMN raw_payload_json,
          DROP COLUMN ingested_at_ms,
          DROP COLUMN projected_at_ms,
          DROP COLUMN payload_hash
        """
    )

    op.execute("ALTER TABLE macro_view_snapshots ADD COLUMN assets_brief_json JSONB")
    op.execute("ALTER TABLE macro_view_snapshots ADD COLUMN module_views_json JSONB")
    op.execute(
        """
        UPDATE macro_view_snapshots AS snapshots
        SET assets_brief_json = COALESCE(
          (
            SELECT briefs.payload_json
              - 'brief_key'
              - 'projection_version'
              - 'brief_date'
              - 'computed_at_ms'
            FROM macro_daily_briefs AS briefs
            WHERE briefs.projection_version = snapshots.projection_version
              AND briefs.brief_key = 'assets_today'
            ORDER BY briefs.computed_at_ms DESC
            LIMIT 1
          ),
          '{}'::jsonb
        )
        """
    )
    op.execute("ALTER TABLE macro_view_snapshots ALTER COLUMN assets_brief_json SET NOT NULL")
    op.execute("UPDATE macro_view_snapshots SET module_views_json = '{}'::jsonb")
    op.execute("ALTER TABLE macro_view_snapshots ALTER COLUMN module_views_json SET NOT NULL")
    op.execute(
        """
        ALTER TABLE macro_view_snapshots
        ADD CONSTRAINT macro_view_snapshots_assets_brief_object_check
        CHECK (jsonb_typeof(assets_brief_json) = 'object')
        """
    )
    op.execute(
        """
        ALTER TABLE macro_view_snapshots
        ADD CONSTRAINT macro_view_snapshots_module_views_object_check
        CHECK (jsonb_typeof(module_views_json) = 'object')
        """
    )
    _backfill_macro_view_snapshot_hashes()
    _enqueue_macro_module_view_rebuild()
    op.execute("DROP TABLE macro_daily_briefs")


def _backfill_macro_event_metadata() -> None:
    bind = op.get_bind()
    select_rows = sa.text(
        """
        SELECT ctid::text AS row_ctid, concept_key, raw_payload_json
        FROM macro_observation_series_rows
        WHERE event_metadata_json IS NULL
        ORDER BY projection_version, concept_key, observed_at
        LIMIT :limit
        """
    )
    update_row = sa.text(
        """
        UPDATE macro_observation_series_rows
        SET event_metadata_json = CAST(:event_metadata_json AS jsonb)
        WHERE ctid = CAST(:row_ctid AS tid)
        """
    )
    while True:
        rows = bind.execute(select_rows, {"limit": _BACKFILL_BATCH_SIZE}).mappings().all()
        if not rows:
            break
        for row in rows:
            metadata = _macro_event_metadata(
                concept_key=str(row["concept_key"]),
                raw_payload=row["raw_payload_json"],
            )
            bind.execute(
                update_row,
                {
                    "row_ctid": row["row_ctid"],
                    "event_metadata_json": json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                },
            )


def _backfill_macro_view_snapshot_hashes() -> None:
    bind = op.get_bind()
    rows = (
        bind.execute(
            sa.text(
                """
            SELECT
              projection_version,
              asof_date,
              status,
              regime,
              overall_score,
              panels_json,
              indicators_json,
              triggers_json,
              data_gaps_json,
              source_coverage_json,
              features_json,
              chain_json,
              scenario_json,
              scorecard_json,
              assets_brief_json,
              module_views_json
            FROM macro_view_snapshots
            ORDER BY projection_version
            """
            )
        )
        .mappings()
        .all()
    )
    update_hash = sa.text(
        """
        UPDATE macro_view_snapshots
        SET payload_hash = :payload_hash
        WHERE projection_version = :projection_version
        """
    )
    for row in rows:
        payload = {key: row[key] for key in row}
        bind.execute(
            update_hash,
            {
                "projection_version": row["projection_version"],
                "payload_hash": _stable_payload_hash(payload),
            },
        )


def _enqueue_macro_module_view_rebuild() -> None:
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
          'migration:20260721_0185:route_ready_modules',
          'migration_route_ready_module_rebuild',
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
          attempt_count = CASE
            WHEN macro_projection_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
            THEN 0
            ELSE macro_projection_dirty_targets.attempt_count
          END,
          last_error = NULL,
          updated_at_ms = EXCLUDED.updated_at_ms
        """
    )


def _apply_attempt_ledger_retention() -> None:
    op.execute(
        f"""
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        )
        DELETE FROM worker_queue_terminal_events
        USING migration_clock
        WHERE operator_action IS NOT NULL
          AND COALESCE(operator_action_at_ms, terminalized_at_ms)
              < migration_clock.now_ms - {_RETENTION_30_DAYS_MS}
        """
    )
    op.execute(
        f"""
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        )
        DELETE FROM news_fetch_runs
        USING migration_clock
        WHERE status = 'success'
          AND finished_at_ms > 0
          AND finished_at_ms < migration_clock.now_ms - {_RETENTION_30_DAYS_MS}
        """
    )
    op.execute(
        f"""
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        )
        DELETE FROM news_story_agent_runs AS runs
        USING migration_clock
        WHERE runs.finished_at_ms < migration_clock.now_ms - {_RETENTION_180_DAYS_MS}
          AND NOT EXISTS (
            SELECT 1
            FROM news_story_agent_briefs AS briefs
            WHERE briefs.agent_run_id = runs.run_id
          )
        """
    )


def _add_retention_indexes() -> None:
    op.execute(
        """
        CREATE INDEX idx_notifications_retention
          ON notifications(last_seen_at_ms ASC, notification_id ASC)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_news_fetch_runs_success_retention
          ON news_fetch_runs(finished_at_ms ASC, fetch_run_id ASC)
          WHERE status = 'success'
        """
    )
    op.execute(
        """
        CREATE INDEX idx_news_story_agent_runs_retention
          ON news_story_agent_runs(finished_at_ms ASC, run_id ASC)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_news_story_agent_briefs_agent_run
          ON news_story_agent_briefs(agent_run_id)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_worker_queue_terminal_resolved_retention
          ON worker_queue_terminal_events(
            (COALESCE(operator_action_at_ms, terminalized_at_ms)) ASC,
            terminal_id ASC
          )
          WHERE operator_action IS NOT NULL
        """
    )


def _drop_redundant_tables() -> None:
    for table_name in (
        "news_item_agent_briefs",
        "news_item_agent_runs",
        "news_source_quality_rows",
        "narrative_admission_dirty_targets",
        "narrative_admissions",
        "cex_oi_radar_rows",
        "cex_oi_radar_publication_state",
        "cex_detail_snapshots",
        "account_quality_snapshots",
        "account_token_call_stats",
        "account_profiles",
        "projection_offsets",
        "projection_runs",
    ):
        op.execute(f"DROP TABLE {table_name}")


def _macro_event_metadata(*, concept_key: str, raw_payload: object) -> dict[str, Any]:
    if not concept_key.startswith("event:") or not isinstance(raw_payload, Mapping):
        return {}
    provenance = raw_payload.get("provenance")
    first_provenance = (
        provenance[0]
        if isinstance(provenance, Sequence)
        and not isinstance(provenance, str | bytes | bytearray)
        and provenance
        and isinstance(provenance[0], Mapping)
        else {}
    )
    metadata: dict[str, Any] = {}
    raw_value = raw_payload.get("value")
    text_value = _first_non_empty_text(
        raw_value if isinstance(raw_value, str) else None,
        first_provenance.get("document_title"),
    )
    source_url = _first_non_empty_text(
        first_provenance.get("source_url"),
        raw_payload.get("source_url"),
        raw_payload.get("url"),
    )
    event_code = _first_non_empty_text(raw_payload.get("series_key"))
    if text_value is not None:
        metadata["text_value"] = text_value
    if source_url is not None:
        metadata["source_url"] = source_url
    if event_code is not None:
        metadata["event_code"] = event_code
    for field_name in (
        "document_type",
        "speaker",
        "event_time",
        "event_time_et",
        "reference_period",
        "cusip",
        "announcement_date",
        "settlement_date",
    ):
        value = _first_non_empty_text(first_provenance.get(field_name), raw_payload.get(field_name))
        if value is not None:
            metadata[field_name] = value
    if bool(first_provenance.get("reopening") or raw_payload.get("reopening")):
        metadata["reopening"] = True
    return metadata


def _stable_payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _json_ready(dict(payload)),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(inner) for key, inner in value.items()}
    if isinstance(value, tuple | list):
        return [_json_ready(inner) for inner in value]
    if isinstance(value, Decimal):
        return str(value.normalize())
    if isinstance(value, date | datetime | time):
        return value.isoformat()
    return value


def _mapping_or_empty(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [str(item) for item in value]


def _first_non_empty_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None
