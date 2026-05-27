from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"
TOKEN_RADAR_PROJECTION = SRC / "domains/token_intel/services/token_radar_projection.py"

BANNED_RUNTIME_TOKENS = (
    "payload_hash changed during selected-row hydration",
    "_rank_and_hydrate_selected_rows",
    "_hydrate_ranked_rows",
    "_patch_hydrated_rank_row",
    "load_target_feature_payloads_for_ranked_keys",
    "rebuild_rank_inputs_full",
    "list_rank_input_rebuild_keys",
    "stale_rank_input_count",
    "rank_input_readiness_for_work_items",
    "latest_snapshot_audit_rows",
    "token_radar_projection_coverage",
    "token_radar_target_projection_coverage",
    "token_radar_rank_history",
    "token_radar_snapshot_audit",
    "token_radar_postgres_hard_reset",
    "runtime_worker_dirty_targets",
    "reset-token-radar-postgres-hard-cut",
    "enqueue-runtime-worker-dirty-targets",
    "side_effect_status",
    ":claimed:",
)

ONLINE_PATHS = (
    SRC / "app/surfaces/api/routes_radar.py",
    SRC / "domains/token_intel/read_models/asset_flow_service.py",
    SRC / "domains/pulse_lab/runtime/pulse_candidate_worker.py",
    SRC / "domains/pulse_lab/queries/pulse_policy_evaluator.py",
    SRC / "domains/notifications/services/notification_rules.py",
    SRC / "domains/narrative_intel/repositories/narrative_repository.py",
    SRC / "domains/asset_market/repositories/registry_repository.py",
)

FORBIDDEN_ONLINE_TABLES = (
    "token_radar_target_features",
    "token_radar_rank_history",
    "token_radar_snapshot_audit",
    "token_radar_rank_source_events",
)


def _runtime_files() -> list[Path]:
    roots = (SRC / "app", SRC / "domains")
    return sorted(path for root in roots for path in root.rglob("*.py"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class_method(tree: ast.AST, class_name: str, method_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                return item
    raise AssertionError(f"{class_name}.{method_name} was not found")


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _expr_uses_any_name(node: ast.AST, names: set[str]) -> bool:
    return any(isinstance(child, ast.Name) and child.id in names for child in ast.walk(node))


def _keyword_value(node: ast.Call, keyword_name: str) -> ast.expr | None:
    for keyword in node.keywords:
        if keyword.arg == keyword_name:
            return keyword.value
    return None


def _is_generation_id_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "generation_id"


def _generation_id_writes(node: ast.AST) -> list[tuple[ast.AST, ast.expr | None]]:
    writes: list[tuple[ast.AST, ast.expr | None]] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Assign) and any(_is_generation_id_name(target) for target in child.targets):
            writes.append((child, child.value))
            continue
        if isinstance(child, (ast.AnnAssign, ast.AugAssign)) and _is_generation_id_name(child.target):
            writes.append((child, child.value))
    return writes


def test_legacy_token_radar_publication_paths_are_removed() -> None:
    violations: list[str] = []
    for path in _runtime_files():
        text = path.read_text(encoding="utf-8")
        violations.extend(
            f"{path.relative_to(ROOT)} contains {token}" for token in BANNED_RUNTIME_TOKENS if token in text
        )
    assert violations == []


def test_token_radar_runtime_repair_and_hard_reset_modules_are_removed() -> None:
    removed_paths = (
        SRC / "app/runtime/runtime_worker_dirty_targets.py",
        SRC / "app/runtime/token_radar_postgres_hard_reset.py",
    )

    assert [str(path.relative_to(ROOT)) for path in removed_paths if path.exists()] == []


def test_online_token_radar_paths_do_not_read_private_or_cold_tables() -> None:
    violations: list[str] = []
    for path in ONLINE_PATHS:
        text = path.read_text(encoding="utf-8")
        violations.extend(
            f"{path.relative_to(ROOT)} reads {table}" for table in FORBIDDEN_ONLINE_TABLES if table in text
        )
    assert violations == []


def test_token_radar_dirty_projection_does_not_enqueue_recent_resolved_targets() -> None:
    tree = _parse(TOKEN_RADAR_PROJECTION)
    rebuild_dirty_targets = _class_method(tree, "TokenRadarProjection", "rebuild_dirty_targets")
    violations = [
        f"{TOKEN_RADAR_PROJECTION.relative_to(ROOT)}:{node.lineno} calls enqueue_recent_resolved_targets"
        for node in ast.walk(rebuild_dirty_targets)
        if isinstance(node, ast.Call) and _call_name(node) == "enqueue_recent_resolved_targets"
    ]

    assert violations == []


def test_token_radar_rank_input_queries_require_latest_event_cutoff() -> None:
    violations: list[str] = []
    for path in _runtime_files():
        tree = _parse(path)
        violations.extend(
            (
                f"{path.relative_to(ROOT)}:{node.lineno} calls list_rank_inputs_for_rank_set "
                "without min_latest_event_received_at_ms"
            )
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and _call_name(node) == "list_rank_inputs_for_rank_set"
            and _keyword_value(node, "min_latest_event_received_at_ms") is None
        )

    assert violations == []


def test_token_radar_successful_publication_generation_ids_are_content_stable() -> None:
    tree = _parse(TOKEN_RADAR_PROJECTION)
    refresh_rank_set = _class_method(tree, "TokenRadarProjection", "refresh_rank_set")
    generation_writes = _generation_id_writes(refresh_rank_set)
    successful_generation_calls = [
        _call_name(value)
        for _node, value in generation_writes
        if isinstance(value, ast.Call)
    ]
    timestamp_names = {"computed_at_ms", "published_at_ms", "now_ms"}
    stable_generation_names = {
        "generation_id"
        for _node, value in generation_writes
        if isinstance(value, ast.Call) and _call_name(value) == "stable_generation_id"
    }
    non_stable_generation_assignments = [
        f"{TOKEN_RADAR_PROJECTION.relative_to(ROOT)}:{node.lineno} assigns generation_id outside stable_generation_id"
        for node, value in generation_writes
        if not (isinstance(value, ast.Call) and _call_name(value) == "stable_generation_id")
    ]
    publish_generation_args = [
        (node, _keyword_value(node, "generation_id"))
        for node in ast.walk(refresh_rank_set)
        if isinstance(node, ast.Call) and _call_name(node) == "publish_current_generation"
    ]
    unstable_publish_args = [
        f"{TOKEN_RADAR_PROJECTION.relative_to(ROOT)}:{node.lineno} publishes a non-stable generation_id"
        for node, generation_arg in publish_generation_args
        if not (isinstance(generation_arg, ast.Name) and generation_arg.id in stable_generation_names)
    ]
    timestamp_publish_args = [
        f"{TOKEN_RADAR_PROJECTION.relative_to(ROOT)}:{node.lineno} publishes timestamp-derived generation_id"
        for node, generation_arg in publish_generation_args
        if generation_arg is not None and _expr_uses_any_name(generation_arg, timestamp_names)
    ]
    failed_generation_args = [
        (node, _keyword_value(node, "generation_id"))
        for node in ast.walk(refresh_rank_set)
        if isinstance(node, ast.Call) and _call_name(node) == "mark_publication_failed"
    ]
    unexpected_failed_generation_args = [
        f"{TOKEN_RADAR_PROJECTION.relative_to(ROOT)}:{node.lineno} failed attempt id is not scoped to attempt_id"
        for node, generation_arg in failed_generation_args
        if not (isinstance(generation_arg, ast.Name) and generation_arg.id == "attempt_id")
    ]
    timestamp_derived_assignments = [
        f"{TOKEN_RADAR_PROJECTION.relative_to(ROOT)}:{node.lineno} assigns successful generation_id from timestamp"
        for node, value in generation_writes
        if value is not None and _expr_uses_any_name(value, timestamp_names)
    ]
    timestamp_generation_helpers = [
        f"{TOKEN_RADAR_PROJECTION.relative_to(ROOT)}:{node.lineno} defines timestamp-derived _generation_id helper"
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_generation_id"
    ]

    assert "stable_generation_id" in successful_generation_calls
    assert len(generation_writes) == 1
    assert stable_generation_names == {"generation_id"}
    assert non_stable_generation_assignments == []
    assert len(publish_generation_args) == 1
    assert unstable_publish_args == []
    assert timestamp_publish_args == []
    assert len(failed_generation_args) == 1
    assert unexpected_failed_generation_args == []
    assert timestamp_derived_assignments == []
    assert timestamp_generation_helpers == []
