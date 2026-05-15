from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LATEST_MIGRATION = (
    ROOT
    / "src/gmgn_twitter_intel/platform/db/alembic/versions/20260515_0046_event_anchor_capture_redesign.py"
)

SCANNED_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".toml", ".sql"}
SKIPPED_DIRS = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache"}
BANNED_RUNTIME_STRINGS = (
    "AnchorPriceWorker",
    "anchor_price",
    "price_observations",
    "market_observation_written",
    "message_anchor",
    "decision_latest",
    "should_persist_live_observation",
)
ALLOWED_HISTORICAL_PATHS = {
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260513_0036_token_radar_kappa_cqrs_hard_cut.py",
    "docs/superpowers/specs/active/2026-05-15-event-anchor-capture-redesign-cn.md",
    "docs/superpowers/plans/active/2026-05-15-event-anchor-capture-redesign-plan-cn.md",
    "tests/architecture/test_event_anchor_capture_redesign_contracts.py",
}


@pytest.mark.architecture
def test_old_price_observation_runtime_is_removed() -> None:
    offenders: list[str] = []
    for path in _scanned_project_files():
        rel_path = path.relative_to(ROOT).as_posix()
        if rel_path in ALLOWED_HISTORICAL_PATHS:
            continue

        text = path.read_text(encoding="utf-8")
        offenders.extend(f"{rel_path}: contains {banned}" for banned in BANNED_RUNTIME_STRINGS if banned in text)

    assert offenders == []


@pytest.mark.architecture
def test_market_tick_tables_are_append_only_in_latest_migration() -> None:
    migration = LATEST_MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS market_ticks" in migration
    assert "CREATE TABLE IF NOT EXISTS enriched_events" in migration
    assert "BEFORE UPDATE ON market_ticks" in migration
    assert "BEFORE UPDATE ON enriched_events" in migration
    assert "DROP TABLE IF EXISTS price_observations CASCADE" in migration
    assert "UPDATE market_ticks" not in migration
    assert "UPDATE enriched_events" not in migration


def _scanned_project_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and path.suffix in SCANNED_SUFFIXES
        and not SKIPPED_DIRS.intersection(path.relative_to(ROOT).parts)
    )
