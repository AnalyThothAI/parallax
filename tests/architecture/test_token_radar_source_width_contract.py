from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_source_edge_populate_is_windowless_narrow_event_edge() -> None:
    query = _text(
        "src/gmgn_twitter_intel/domains/token_intel/queries/"
        "token_radar_rank_source_query.py"
    )
    populate = query.rsplit("_POPULATE_RANK_SOURCE_EDGES_FOR_EVENT_IDS_SQL", 1)[1]

    assert "requested_event_ids" in populate
    forbidden = (
        "market_tick_current",
        "latest_price_",
        "latest_market_",
        "event_price_",
        "account_profiles",
        "social_event_extractions",
        "asset_identity_current",
        "registry_assets",
        "cex_tokens",
        "price_feeds",
        "enriched_events",
        "market_ticks",
        "row_number() OVER",
        "to_jsonb(ranked_source)",
        "sha256(",
    )
    offenders = [token for token in forbidden if token in populate]
    assert offenders == []


def test_rank_source_table_is_not_window_or_payload_coupled() -> None:
    migration = _text(
        "src/gmgn_twitter_intel/platform/db/alembic/versions/"
        "20260529_0126_token_radar_venue_source_width_hard_cut.py"
    )
    create_table = migration.split("CREATE TABLE token_radar_rank_source_events", 1)[1].split(
        "CREATE INDEX idx_token_radar_rank_source_events_target_time", 1
    )[0]

    assert "source_kind" in create_table
    assert "source_id" in create_table
    assert '"window"' not in create_table
    assert "scope" not in create_table
    assert "source_payload_json" not in create_table
    assert "factor_snapshot_json" not in create_table
    assert len([line for line in create_table.splitlines() if line.strip() and "--" not in line]) <= 32


def test_source_dirty_is_event_edge_queue_not_target_union() -> None:
    projection = _text(
        "src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py"
    )
    source_dirty_repo = _text(
        "src/gmgn_twitter_intel/domains/token_intel/repositories/"
        "token_radar_source_dirty_event_repository.py"
    )
    target_dirty_repo = _text(
        "src/gmgn_twitter_intel/domains/token_intel/repositories/"
        "token_radar_dirty_target_repository.py"
    )

    assert "token_radar_source_dirty_events" in source_dirty_repo
    assert "source_event_id" in source_dirty_repo
    assert "source_event_ids_json = (" not in target_dirty_repo
    assert "jsonb_agg" not in target_dirty_repo
    assert "populate_edges_for_requests(" not in projection
    assert "populate_edges_for_event_ids(" in projection
