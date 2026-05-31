from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"

PROJECTION_RUNTIME_GLOBS = ("domains/news_intel/runtime/*projection_worker.py",)

ALLOWED_PROJECTION_REPOSITORY_CALLS = {
    "claim_due",
    "enqueue_targets",
    "list_news_item_ids_for_sources",
    "list_source_quality_inputs_for_targets",
    "load_items_for_page_projection",
    "mark_done",
    "mark_error",
    "replace_page_rows",
    "replace_page_rows_for_items",
    "replace_source_quality_rows",
}

BANNED_PROJECTION_DISCOVERY_CALLS = {
    "list_events_missing_story",
    "list_events_for_page_projection",
    "list_expected_events_for_calendar_projection",
    "list_inactive_expected_event_ids_for_calendar_projection",
    "list_items_missing_story",
    "list_items_for_page_projection",
    "list_source_quality_inputs",
    "page_projection_source_summary",
}

CLAIM_MARK_METHODS = {"claim_due", "mark_done", "mark_error"}
NEWS_PROJECTION_WORKERS = {
    SRC / "domains/news_intel/runtime/news_page_projection_worker.py",
    SRC / "domains/news_intel/runtime/news_source_quality_projection_worker.py",
}
AGENT_BRIEF_WORKERS = {
    SRC / "domains/news_intel/runtime/news_item_brief_worker.py",
}
BANNED_AGENT_BRIEF_DISCOVERY_CALLS = {
    "list_items_for_brief",
    "list_events_for_brief",
}


@pytest.mark.architecture
def test_projection_workers_only_call_target_scoped_repository_methods() -> None:
    violations: list[str] = []
    for path in _projection_worker_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            method_name = _call_method_name(call)
            if method_name is None:
                continue
            if method_name in BANNED_PROJECTION_DISCOVERY_CALLS or _looks_like_projection_scan(method_name):
                violations.append(f"{_rel(path)} calls broad projection discovery method {method_name}")
                continue
            if _is_repos_call(call) and method_name not in ALLOWED_PROJECTION_REPOSITORY_CALLS:
                violations.append(f"{_rel(path)} calls non-allowlisted repository method {method_name}")

    assert violations == []


@pytest.mark.architecture
def test_dirty_target_claim_and_completion_are_projection_worker_owned() -> None:
    violations: list[str] = []
    for path in sorted((SRC / "domains").rglob("runtime/*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            method_name = _call_method_name(call)
            if method_name not in CLAIM_MARK_METHODS:
                continue
            chain = _attribute_chain(call.func)
            if "news_projection_dirty_targets" in chain and path not in NEWS_PROJECTION_WORKERS | AGENT_BRIEF_WORKERS:
                violations.append(f"{_rel(path)} calls news dirty target {method_name}")

    assert violations == []


@pytest.mark.architecture
def test_agent_brief_workers_claim_dirty_targets_instead_of_scanning_candidates() -> None:
    violations: list[str] = []
    for path in sorted(AGENT_BRIEF_WORKERS):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [_call_method_name(call) for call in ast.walk(tree) if isinstance(call, ast.Call)]
        banned = sorted(str(name) for name in calls if name in BANNED_AGENT_BRIEF_DISCOVERY_CALLS)
        if banned:
            violations.append(f"{_rel(path)} calls broad agent brief discovery methods: {', '.join(banned)}")
        if "claim_due" not in calls:
            violations.append(f"{_rel(path)} does not claim dirty targets")

    assert violations == []


def _projection_worker_paths() -> list[Path]:
    paths: list[Path] = []
    for pattern in PROJECTION_RUNTIME_GLOBS:
        paths.extend(SRC.glob(pattern))
    return sorted(set(paths))


def _call_method_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _is_repos_call(call: ast.Call) -> bool:
    return "repos" in _attribute_chain(call.func)


def _attribute_chain(node: ast.AST) -> tuple[str, ...]:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return tuple(reversed(parts))


def _looks_like_projection_scan(method_name: str) -> bool:
    return bool(re.match(r"list_.*_(?:for_.*_projection|missing_.*)$", method_name))


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()
