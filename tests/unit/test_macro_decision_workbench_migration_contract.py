from __future__ import annotations

import ast
from pathlib import Path

from parallax.platform.db.postgres_migrations import latest_migration_version

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "src/parallax/platform/db/alembic/versions/20260723_0192_macro_decision_workbench_hard_cut.py"


def test_macro_decision_workbench_hard_cut_is_the_linear_head() -> None:
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
        "revision": "20260723_0192",
        "down_revision": "20260723_0191",
    }
    assert latest_migration_version() == "20260723_0192"


def test_macro_decision_workbench_hard_cut_rebuilds_only_derived_state() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    upper = source.upper()

    assert "SET LOCAL LOCK_TIMEOUT = '5S'" in upper
    assert "SET LOCAL STATEMENT_TIMEOUT = '10MIN'" in upper
    assert "LOCK TABLE" in upper
    assert "DELETE FROM MACRO_PROJECTION_DIRTY_TARGETS" in upper
    assert "DELETE FROM MACRO_OBSERVATION_SERIES_ROWS" in upper
    assert "DELETE FROM MACRO_OBSERVATION_SERIES_PUBLICATION_STATE" in upper
    assert "DELETE FROM MACRO_VIEW_SNAPSHOTS" in upper
    assert "DELETE FROM MACRO_OBSERVATIONS" not in upper
    assert "'MACRO_DECISION_V2'" in upper
    assert "IF EXISTS" not in upper
    assert "CASCADE" not in upper
    assert "RESTORE THE PRE-MIGRATION BACKUP" in upper
