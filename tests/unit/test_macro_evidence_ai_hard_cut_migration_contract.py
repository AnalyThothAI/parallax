from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "src/parallax/platform/db/alembic/versions/20260723_0191_macro_evidence_ai_hard_cut.py"


def test_macro_evidence_ai_hard_cut_extends_the_real_linear_head() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    module = ast.parse(source)
    assignments = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"revision", "down_revision"}
    }

    assert assignments == {
        "revision": "20260723_0191",
        "down_revision": "20260722_0190",
    }


def test_macro_evidence_ai_hard_cut_is_fail_closed_and_irreversible() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    upper = source.upper()

    assert "SET LOCAL LOCK_TIMEOUT = '5S'" in upper
    assert "SET LOCAL STATEMENT_TIMEOUT = '30MIN'" in upper
    assert "IF EXISTS" not in upper
    assert "CASCADE" not in upper
    assert "RESTORE THE PRE-MIGRATION BACKUP" in upper
    assert "COMPAT" not in upper


def test_macro_evidence_ai_hard_cut_uses_exact_dependency_order() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert source.index("DROP TABLE news_story_agent_briefs") < source.index("DROP TABLE news_story_agent_runs")
    assert source.index("DROP INDEX idx_news_page_rows_direction_time") < source.index("DROP COLUMN agent_brief_json")
    assert source.index("DELETE FROM token_radar_target_features") < source.index(
        "DROP COLUMN semantic_catalyst_raw_score"
    )
    assert source.index("DROP TABLE macro_view_snapshots") < source.index("CREATE TABLE macro_view_snapshots")


def test_macro_evidence_ai_hard_cut_creates_only_the_six_page_snapshot_contract() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    create_table = source.split("CREATE TABLE macro_view_snapshots (", maxsplit=1)[1].split(
        ')\n        """', maxsplit=1
    )[0]

    for column in (
        "snapshot_key",
        "projection_version",
        "overview_json",
        "cross_asset_json",
        "rates_inflation_json",
        "growth_labor_json",
        "liquidity_funding_json",
        "credit_json",
    ):
        expected_type = "JSONB" if column.endswith("_json") else "TEXT"
        assert f"{column} {expected_type}" in create_table
    assert "CHECK (snapshot_key = 'current')" in create_table
    assert "'macro_evidence'" in source
    for retired in (
        "regime",
        "overall_score",
        "scenario_json",
        "scorecard_json",
        "module_views_json",
    ):
        assert retired not in create_table
