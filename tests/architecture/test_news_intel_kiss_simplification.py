from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"

ALLOWED_DIRTY_STRING_FILES = {
    "src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py",
    "src/parallax/domains/news_intel/runtime/news_projection_work.py",
    "src/parallax/app/runtime/projection_dirty_targets.py",
}

RAW_PROJECTION_STRINGS = {"brief_input", "page", "source_quality"}


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def test_news_fetch_has_no_agent_brief_admission_dependency() -> None:
    source = _read("src/parallax/domains/news_intel/runtime/news_fetch_worker.py")
    tree = ast.parse(source)
    imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "parallax.domains.news_intel.services.news_item_agent_policy"
    ]
    assert imports == []
    assert "brief_input" not in source
    assert "news_item_agent_brief_eligibility" not in source
    assert "NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS" not in source


def test_fetch_process_brief_constructors_do_not_accept_source_quality_windows() -> None:
    paths = [
        "src/parallax/domains/news_intel/runtime/news_fetch_worker.py",
        "src/parallax/domains/news_intel/runtime/news_item_process_worker.py",
        "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py",
        "src/parallax/app/runtime/worker_factories/news_intel.py",
    ]
    offenders = [path for path in paths if "source_quality_windows" in _read(path)]
    assert offenders == []


def test_news_runtime_workers_do_not_use_raw_dirty_projection_strings() -> None:
    offenders: list[str] = []
    for path in (SRC / "domains/news_intel/runtime").glob("news_*worker.py"):
        rel = _rel(path)
        if rel in ALLOWED_DIRTY_STRING_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in RAW_PROJECTION_STRINGS:
                offenders.append(f"{rel}:{node.lineno}:{node.value}")
    assert offenders == []


def test_news_item_brief_stage_adapter_has_hard_cut_name() -> None:
    old_path = SRC / "domains/news_intel/services/news_item_brief_runtime.py"
    new_path = SRC / "domains/news_intel/services/news_item_brief_stage.py"
    assert not old_path.exists()
    assert new_path.exists()


def test_news_has_single_item_brief_llm_lane() -> None:
    lane_names: set[str] = set()
    for path in SRC.rglob("*.py"):
        if "alembic" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
                continue
            if not node.value.value.startswith("news."):
                continue
            if any(isinstance(target, ast.Name) and target.id.endswith("_LANE") for target in node.targets):
                lane_names.add(node.value.value)
    assert sorted(lane_names) == ["news.item_brief"]
