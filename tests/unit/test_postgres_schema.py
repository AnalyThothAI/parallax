from __future__ import annotations

import ast
from pathlib import Path

from alembic.script import ScriptDirectory

from parallax.platform.db.postgres_migrations import alembic_config

VERSIONS = Path("src/parallax/platform/db/alembic/versions")
HARD_CUT = VERSIONS / "20260721_0185_backend_kiss_hard_cut.py"
RUNTIME_HARD_CUT = VERSIONS / "20260722_0186_runtime_projection_hard_cut.py"
NEWS_FETCH_RUN_FK_INDEX = VERSIONS / "20260722_0187_news_fetch_run_fk_index.py"


def _assignment(path: Path, name: str) -> str | None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing {name}: {path}")


def test_alembic_graph_has_one_current_head_and_unique_revisions() -> None:
    migration_files = sorted(VERSIONS.glob("*.py"))
    revisions = [_assignment(path, "revision") for path in migration_files]
    script = ScriptDirectory.from_config(alembic_config())

    assert None not in revisions
    assert len(revisions) == len(set(revisions))
    assert script.get_heads() == ["20260722_0187"]


def test_backend_kiss_hard_cut_is_fail_closed_and_irreversible() -> None:
    text = HARD_CUT.read_text(encoding="utf-8")
    downgrade = text.split("def downgrade() -> None:", maxsplit=1)[1]

    assert 'revision = "20260721_0185"' in text
    assert 'down_revision = "20260721_0184"' in text
    assert "SET LOCAL lock_timeout = '5s'" in text
    assert "SET LOCAL statement_timeout = '30min'" in text
    assert "IF EXISTS" not in text
    assert "CASCADE" not in text
    assert "RuntimeError" in downgrade


def test_runtime_projection_hard_cut_is_fail_closed_and_irreversible() -> None:
    text = RUNTIME_HARD_CUT.read_text(encoding="utf-8")
    downgrade = text.split("def downgrade() -> None:", maxsplit=1)[1]

    assert 'revision = "20260722_0186"' in text
    assert 'down_revision = "20260721_0185"' in text
    assert "SET LOCAL lock_timeout = '5s'" in text
    assert "SET LOCAL statement_timeout = '30min'" in text
    assert "IF EXISTS" not in text
    assert "CASCADE" not in text
    assert "RuntimeError" in downgrade
    for retired_table in (
        "market_tick_current_dirty_targets",
        "token_capture_tier_dirty_targets",
        "token_capture_tier",
    ):
        assert f"DROP TABLE {retired_table}" in text
    assert text.index("_reconcile_market_tick_current_backlog()") < text.index(
        'op.execute("DROP TABLE market_tick_current_dirty_targets")'
    )
    assert "ORDER BY ticks.observed_at_ms DESC, ticks.received_at_ms DESC, ticks.tick_id DESC" in text
    assert "source_row_json ->> 'target_type'" in text
    assert "source_table = 'market_tick_current_dirty_targets'" in text
    assert "operator_reason = 'queue_retired_by_0186'" in text
    assert "INSERT INTO market_tick_current" in text
    assert "INSERT INTO token_radar_dirty_targets" in text
    assert "ON registry_assets(chain_id, address)" in text
    assert "ON price_feeds(provider, feed_type, chain_id, address)" in text
    assert "ck_registry_assets_evm_address_canonical" in text
    assert "ck_price_feeds_evm_address_canonical" in text
    for cex_route_filter in (
        "feeds.provider = 'binance'",
        "feeds.feed_type = 'cex_swap'",
        "feeds.quote_symbol = 'USDT'",
        "feeds.status = 'canonical'",
    ):
        assert cex_route_filter in text


def test_news_fetch_run_fk_index_is_canonical_and_reversible() -> None:
    text = NEWS_FETCH_RUN_FK_INDEX.read_text(encoding="utf-8")

    assert 'revision = "20260722_0187"' in text
    assert 'down_revision = "20260722_0186"' in text
    assert "CREATE INDEX idx_news_provider_items_fetch_run_id" in text
    assert "ON news_provider_items(fetch_run_id)" in text
    assert "DROP INDEX idx_news_provider_items_fetch_run_id" in text
    assert "IF EXISTS" not in text
    assert "CONCURRENTLY" not in text


def test_backend_kiss_hard_cut_removes_only_the_audited_control_planes() -> None:
    text = HARD_CUT.read_text(encoding="utf-8")
    retired_tables = {
        "projection_runs",
        "projection_offsets",
        "narrative_admissions",
        "narrative_admission_dirty_targets",
        "macro_daily_briefs",
        "macro_import_runs",
        "cex_oi_radar_publication_state",
        "cex_oi_radar_rows",
        "cex_detail_snapshots",
        "account_profiles",
        "account_token_call_stats",
        "account_quality_snapshots",
        "news_item_agent_briefs",
        "news_item_agent_runs",
        "news_source_quality_rows",
        "token_radar_source_dirty_events",
    }

    for table in retired_tables:
        assert table in text
    assert 'op.execute(f"DROP TABLE {table_name}")' in text
    for material_fact in (
        "events",
        "token_intents",
        "token_intent_resolutions",
        "market_ticks",
        "enriched_events",
        "account_token_alerts",
    ):
        assert f"DROP TABLE {material_fact}" not in text


def test_source_queue_rows_and_terminal_evidence_are_preserved_before_drop() -> None:
    text = HARD_CUT.read_text(encoding="utf-8")

    merge_at = text.index("INSERT INTO token_radar_dirty_targets")
    archive_at = text.index("UPDATE worker_queue_terminal_events")
    drop_at = text.index('op.execute("DROP TABLE token_radar_source_dirty_events")')

    assert archive_at < drop_at
    assert merge_at < drop_at
    assert "operator_action = 'archive'" in text
    assert "queue_retired_by_0185" in text
    assert "market_dirty = token_radar_dirty_targets.market_dirty OR excluded.market_dirty" in text
    assert "repair_dirty = token_radar_dirty_targets.repair_dirty OR excluded.repair_dirty" in text


def test_news_terminal_state_is_bound_to_the_current_source_config() -> None:
    text = HARD_CUT.read_text(encoding="utf-8")

    assert "ALTER TABLE news_sources ADD COLUMN config_payload_hash TEXT" in text
    assert "ALTER TABLE news_sources ADD COLUMN terminal_config_payload_hash TEXT" in text
    assert "ALTER TABLE news_sources ALTER COLUMN config_payload_hash SET NOT NULL" in text
    assert "news_sources_config_payload_hash_check" in text
    assert "news_sources_terminal_config_payload_hash_check" in text
    assert "CHECK (projection_name IN ('page', 'story_brief'))" in text


def test_macro_hard_cut_preserves_event_metadata_and_rebuilds_module_views_once() -> None:
    text = HARD_CUT.read_text(encoding="utf-8")
    runtime_text = RUNTIME_HARD_CUT.read_text(encoding="utf-8")

    assert "ALTER TABLE macro_observation_series_rows ADD COLUMN event_metadata_json JSONB" in text
    assert "ALTER TABLE macro_observation_series_rows ALTER COLUMN event_metadata_json SET NOT NULL" in text
    assert "ALTER TABLE macro_view_snapshots ADD COLUMN assets_brief_json JSONB" in text
    assert "ALTER TABLE macro_view_snapshots ALTER COLUMN assets_brief_json SET NOT NULL" in text
    assert "ALTER TABLE macro_view_snapshots ADD COLUMN module_views_json JSONB" in text
    assert "ALTER TABLE macro_view_snapshots ALTER COLUMN module_views_json SET NOT NULL" in text
    assert "macro_view_snapshots_assets_brief_object_check" in text
    assert "macro_view_snapshots_module_views_object_check" in text
    assert "migration_route_ready_module_rebuild" in text
    assert "ALTER TABLE macro_view_snapshots DROP COLUMN assets_brief_json" in runtime_text
    assert "migration:20260722_0186:module_views_only" in runtime_text
    assert "migration_module_views_only_rebuild" in runtime_text
    assert "DELETE FROM macro_view_snapshots" in runtime_text
    assert runtime_text.index("_reset_macro_module_views()") < runtime_text.index(
        "ALTER TABLE macro_view_snapshots DROP COLUMN assets_brief_json"
    )
    for redundant_column in (
        "series_rank",
        "source_priority",
        "source_ts",
        "raw_payload_json",
        "ingested_at_ms",
        "projected_at_ms",
        "payload_hash",
    ):
        assert f"DROP COLUMN {redundant_column}" in text
    assert text.index("_backfill_macro_event_metadata()") < text.index("DROP COLUMN raw_payload_json")
    assert text.index("_enqueue_macro_module_view_rebuild()") < text.index("DROP TABLE macro_daily_briefs")


def test_attempt_ledgers_have_explicit_bounded_retention() -> None:
    text = HARD_CUT.read_text(encoding="utf-8")

    assert "DELETE FROM worker_queue_terminal_events" in text
    assert "DELETE FROM news_fetch_runs" in text
    assert "DELETE FROM news_story_agent_runs AS runs" in text
    assert "NOT EXISTS" in text
    assert "FROM news_story_agent_briefs AS briefs" in text
    for index_name in (
        "idx_notifications_retention",
        "idx_news_fetch_runs_success_retention",
        "idx_news_story_agent_runs_retention",
        "idx_news_story_agent_briefs_agent_run",
        "idx_worker_queue_terminal_resolved_retention",
    ):
        assert f"CREATE INDEX {index_name}" in text
