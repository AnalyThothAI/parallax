from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RUNTIME_FILES = (
    "src/parallax/app/runtime/worker_manifest.py",
    "src/parallax/app/runtime/queue_health.py",
    "src/parallax/app/runtime/worker_factories/__init__.py",
    "src/parallax/platform/config/settings.py",
    "docs/WORKERS.md",
)

FORBIDDEN = (
    "equity_event_page_projection",
    "equity_event_story_projection",
    "equity_event_brief",
    "equity_event_projection_dirty_targets",
)


def test_deleted_equity_runtime_contract_is_not_in_manifest_or_health() -> None:
    offenders: list[str] = []
    for relpath in RUNTIME_FILES:
        text = (ROOT / relpath).read_text(encoding="utf-8")
        offenders.extend(f"{relpath} contains {token}" for token in FORBIDDEN if token in text)
    assert offenders == []
