from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_token_radar_api_accepts_server_side_venue() -> None:
    route = _text("src/gmgn_twitter_intel/app/surfaces/api/routes_radar.py")
    service = _text("src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py")
    repo = _text("src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py")

    assert "venue:" in route
    assert "_venue(" in route
    assert "venue=parsed_venue" in route
    assert "venue: str" in service
    assert "venue=venue" in service
    assert "current_rows.venue = %s" in repo


def test_token_radar_current_identity_includes_venue() -> None:
    manifest = _text("src/gmgn_twitter_intel/app/runtime/worker_manifest.py")
    migration = _text(
        "src/gmgn_twitter_intel/platform/db/alembic/versions/"
        "20260529_0126_token_radar_venue_source_width_hard_cut.py"
    )

    assert '"token_radar_current_rows"' in manifest
    assert '"venue"' in manifest
    assert "ADD COLUMN IF NOT EXISTS venue TEXT" in migration
    assert 'PRIMARY KEY(projection_version, "window", scope, venue)' in migration


def test_token_radar_prevenue_current_uniques_are_hard_dropped() -> None:
    migration = _text(
        "src/gmgn_twitter_intel/platform/db/alembic/versions/"
        "20260529_0127_token_radar_drop_prevenue_current_uniques.py"
    )

    assert "pg_get_constraintdef(oid)" in migration
    assert 'UNIQUE (projection_version, "window", scope, lane, rank)' in migration
    assert 'UNIQUE (projection_version, "window", scope, lane, target_type_key, identity_id)' in migration
    assert "DELETE FROM token_radar_current_rows" in migration
    assert "DELETE FROM token_radar_publication_state" in migration


def test_frontend_does_not_treat_client_filter_as_leaderboard_truth() -> None:
    hook = _text("web/src/features/live/api/useTokenRadarQuery.ts")
    query_keys = _text("web/src/shared/query/queryKeys.ts")
    table = _text("web/src/features/live/ui/TokenRadarTable.tsx")
    live_feature = _text("web/src/features/live/ui/LiveRadar.tsx")
    venue_lib = _text("web/src/lib/venue.ts")

    assert "venue" in hook
    assert "params: { window, limit, scope, venue }" in hook
    assert "venue: TokenRadarVenueFilter" in query_keys
    assert '["token-radar", window, scope, venue, limit]' in query_keys
    assert "items.filter((item) => tokenRadarVenueMatches(item, venueFilter))" not in table
    assert "tokenRadarVenueMatches(" not in table
    assert "tokenRadarVenueMatches(" not in live_feature
    assert "tokenRadarVenueMatches(" not in venue_lib
