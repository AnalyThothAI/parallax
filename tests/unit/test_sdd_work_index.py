from __future__ import annotations

from pathlib import Path

from scripts.regen_sdd_work_index import render_index
from scripts.validate_sdd_artifacts import scan_sdd_features, validate_sdd_root

ROOT = Path(__file__).resolve().parents[2]


def test_work_index_is_an_active_work_board_only() -> None:
    features = scan_sdd_features(ROOT)
    text = render_index(features, validate_sdd_root(ROOT))

    active = [feature for feature in features if feature.state == "active"]
    completed = [feature for feature in features if feature.state == "completed"]
    assert f"Active features: {len(active)}." in text
    assert all(feature.slug in text for feature in active)
    assert all(feature.slug not in text for feature in completed)
    assert "Factory lane" not in text
    assert "Subagent report" not in text
    assert "Dispatch" not in text
