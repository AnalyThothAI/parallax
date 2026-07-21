from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


DIRTY_QUEUE_ATTEMPT_RESET_CONTRACTS = (
    (
        "src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py",
        "asset_profile_refresh_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash",
    ),
    (
        "src/parallax/domains/asset_market/repositories/discovery_repository.py",
        "token_discovery_dirty_lookup_keys.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash",
    ),
    (
        "src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py",
        "market_tick_current_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash",
    ),
    (
        "src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py",
        "token_capture_tier_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash",
    ),
    (
        "src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py",
        "token_image_source_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash",
    ),
    (
        "src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py",
        "token_profile_current_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash",
    ),
    (
        "src/parallax/domains/macro_intel/repositories/macro_intel_repository.py",
        "macro_projection_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash",
    ),
    (
        "src/parallax/domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py",
        "{table}.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash",
    ),
    (
        "src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py",
        "news_projection_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash",
    ),
    (
        "src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py",
        "token_radar_dirty_targets.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash",
    ),
    (
        "src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py",
        "token_radar_source_dirty_events.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash",
    ),
)


def test_dirty_queue_new_payload_resets_attempt_budget() -> None:
    for relative_path, reset_condition in DIRTY_QUEUE_ATTEMPT_RESET_CONTRACTS:
        source = (ROOT / relative_path).read_text()

        assert "attempt_count = CASE" in source, relative_path
        assert reset_condition in source, relative_path
        assert "THEN 0" in source, relative_path
