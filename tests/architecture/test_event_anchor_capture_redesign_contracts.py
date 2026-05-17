from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LATEST_MIGRATION = (
    ROOT / "src/gmgn_twitter_intel/platform/db/alembic/versions/20260515_0046_event_anchor_capture_redesign.py"
)
ALEMBIC_VERSIONS = ROOT / "src/gmgn_twitter_intel/platform/db/alembic/versions"
GENERATED_DOCS = ROOT / "docs/generated"
SUPERPOWERS_DOCS = ROOT / "docs/superpowers"

SCANNED_SUFFIXES = {".html", ".md", ".py", ".sql", ".toml", ".ts", ".tsx", ".yaml", ".yml"}
SKIPPED_DIRS = {
    ".codex",
    ".codex-merge-backup-20260513-frontend-hard-cut",
    ".git",
    ".mypy_cache",
    ".playwright-mcp",
    ".pytest_cache",
    ".ruff_cache",
    ".superpowers",
    ".venv",
    ".worktrees",
    "__pycache__",
    "node_modules",
}
BANNED_RUNTIME_STRINGS = (
    "".join(("Anchor", "Price", "Worker")),
    "_".join(("anchor", "price")),
    "_".join(("price", "observations")),
    "_".join(("market", "observation", "written")),
    "_".join(("message", "anchor")),
    " ".join(("message", "anchor")),
    " ".join(("anchor", "price")),
    "_".join(("should", "persist", "live", "observation")),
)


@pytest.mark.architecture
def test_old_price_observation_runtime_is_removed() -> None:
    offenders: list[str] = []
    for path in _scanned_project_files():
        rel_path = path.relative_to(ROOT).as_posix()
        if _allows_historical_anchor_references(path):
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
    assert f"DROP TABLE IF EXISTS {_legacy_price_table()} CASCADE" in migration
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


def _allows_historical_anchor_references(path: Path) -> bool:
    return path == Path(__file__).resolve() or any(
        path.is_relative_to(allowed_root) for allowed_root in (ALEMBIC_VERSIONS, GENERATED_DOCS, SUPERPOWERS_DOCS)
    )


def _legacy_price_table() -> str:
    return "_".join(("price", "observations"))
