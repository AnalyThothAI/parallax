from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"
TOKEN_RADAR_PROJECTION = SRC / "domains/token_intel/services/token_radar_projection.py"
TOKEN_RADAR_PROJECTION_WORKER = SRC / "domains/token_intel/runtime/token_radar_projection_worker.py"
TOKEN_RADAR_REPOSITORY = SRC / "domains/token_intel/repositories/token_radar_repository.py"
TOKEN_RADAR_RANK_SOURCE_QUERY = SRC / "domains/token_intel/queries/token_radar_rank_source_query.py"
TOKEN_CAPTURE_TIER_DIRTY_REPOSITORY = (
    SRC / "domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py"
)
ASSET_FLOW_SERVICE = SRC / "domains/token_intel/read_models/asset_flow_service.py"
ASSET_REGISTRY_REPOSITORY = SRC / "domains/asset_market/repositories/registry_repository.py"
PULSE_POLICY_EVALUATOR = SRC / "domains/pulse_lab/queries/pulse_policy_evaluator.py"
NARRATIVE_REPOSITORY = SRC / "domains/narrative_intel/repositories/narrative_repository.py"

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


def test_token_radar_projection_requires_valid_windows_without_window_ms_fallbacks() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    forbidden = (
        "WINDOW_MS.get(window",
        'default=WINDOW_MS["24h"]',
        'WINDOW_MS["1h"]',
    )
    required = (
        "class TokenRadarProjectionWindowError",
        "def _window_ms(",
        "return WINDOW_MS[window]",
        "raise TokenRadarProjectionWindowError(window)",
        "token_radar_projection_work_item_window_required",
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []


def test_asset_flow_read_limit_rejects_runtime_int_repairs() -> None:
    source = ASSET_FLOW_SERVICE.read_text(encoding="utf-8")

    assert "max(0, int(limit))" not in source
    assert "targets[:limit]" not in source
    assert "attention[:limit]" not in source
    assert "asset_flow_limit_required" in source


def _runtime_files() -> list[Path]:
    roots = (SRC / "app", SRC / "domains")
    return sorted(path for root in roots for path in root.rglob("*.py"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _function_source(path: Path, function_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == function_name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"{function_name} was not found")


def _class_method(tree: ast.AST, class_name: str, method_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef) and item.name == method_name:
                return item
    raise AssertionError(f"{class_name}.{method_name} was not found")


def _class_method_source(path: Path, class_name: str, method_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    return (
        ast.get_source_segment(source, _class_method(ast.parse(source, filename=str(path)), class_name, method_name))
        or ""
    )


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
        if isinstance(child, ast.AnnAssign | ast.AugAssign) and _is_generation_id_name(child.target):
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


def test_pulse_policy_evaluator_reads_radar_rows_with_single_window_scope_keyset_sql() -> None:
    source = _function_source(PULSE_POLICY_EVALUATOR, "fetch_radar_rows")
    forbidden = (
        "for window in EVALUATED_WINDOWS",
        "for scope in EVALUATED_SCOPES",
        'token_radar_current_rows."window" = %s',
        "token_radar_current_rows.scope = %s",
    )
    required = (
        '"window" = ANY(%s)',
        "scope = ANY(%s)",
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []


def test_token_radar_product_read_paths_do_not_gate_serving_rows_by_generation_id() -> None:
    forbidden_by_path = {
        TOKEN_RADAR_REPOSITORY: {
            "state.current_generation_id = current_rows.generation_id",
            "state.current_generation_id = token_radar_current_rows.generation_id",
            "def current_rows_for_generation",
        },
        ASSET_REGISTRY_REPOSITORY: {
            "current_generation_id",
            "rows.generation_id = latest_sets.current_generation_id",
        },
        ASSET_FLOW_SERVICE: {
            "current_generation =",
            "current_rows_for_generation(",
            "projection_generation_mismatch",
        },
        PULSE_POLICY_EVALUATOR: {
            "state.current_generation_id = current_rows.generation_id",
            "state.current_generation_id = token_radar_current_rows.generation_id",
        },
        NARRATIVE_REPOSITORY: {
            "latest.current_generation_id = token_radar_current_rows.generation_id",
            "token_radar_current_rows.generation_id = latest.current_generation_id",
        },
    }
    violations = [
        f"{path.relative_to(ROOT)} contains {token}"
        for path, forbidden_tokens in forbidden_by_path.items()
        for token in forbidden_tokens
        if token in path.read_text(encoding="utf-8")
    ]

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


def test_token_radar_rank_publication_does_not_run_retention_prune() -> None:
    tree = _parse(TOKEN_RADAR_PROJECTION)
    refresh_rank_set = _class_method(tree, "TokenRadarProjection", "refresh_rank_set")
    forbidden_calls = {"prune_target_features", "prune_edges"}
    forbidden_result_keys = {"pruned_features", "pruned_edges"}
    prune_calls = [
        f"{TOKEN_RADAR_PROJECTION.relative_to(ROOT)}:{node.lineno} calls {_call_name(node)}"
        for node in ast.walk(refresh_rank_set)
        if isinstance(node, ast.Call) and _call_name(node) in forbidden_calls
    ]
    prune_result_keys = [
        f"{TOKEN_RADAR_PROJECTION.relative_to(ROOT)}:{node.lineno} returns {node.value!r}"
        for node in ast.walk(refresh_rank_set)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        if node.value in forbidden_result_keys
    ]

    assert prune_calls == []
    assert prune_result_keys == []


def test_token_radar_private_cache_retention_is_bounded_worker_lane_not_publish_path() -> None:
    projection_source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    repository_source = TOKEN_RADAR_REPOSITORY.read_text(encoding="utf-8")
    rank_source_query = TOKEN_RADAR_RANK_SOURCE_QUERY.read_text(encoding="utf-8")
    prune_private_cache = _class_method_source(TOKEN_RADAR_PROJECTION, "TokenRadarProjection", "prune_private_cache")

    assert "def prune_private_cache(" in projection_source
    assert "prune_target_features(" in prune_private_cache
    assert "prune_edges(" in prune_private_cache
    assert "limit=remaining" in prune_private_cache
    assert "limit=remaining_budget" in prune_private_cache
    assert "max(1, int(limit))" not in prune_private_cache
    assert "max(1, int(retention_ms))" not in prune_private_cache
    assert "max(0, int(limit))" not in repository_source
    assert "token_radar_private_cache_limit_required" in projection_source
    assert "token_radar_private_cache_retention_ms_required" in projection_source
    assert "token_radar_prune_target_features_limit_required" in repository_source
    assert "token_radar_latest_current_rows_limit_required" in repository_source
    assert "LIMIT %s" in repository_source
    assert "LIMIT %s" in rank_source_query


def test_token_radar_rank_publication_requires_connection_transaction_without_optional_probe() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    transaction_helper = _function_source(TOKEN_RADAR_PROJECTION, "_transaction_context")
    forbidden = (
        'getattr(conn, "transaction", None)',
        "return nullcontext()",
        "if transaction is None:",
    )

    assert "token_radar_projection_requires_transactional_connection" in transaction_helper
    assert "if not callable(transaction):" in transaction_helper
    assert [token for token in forbidden if token in source] == []


def test_token_radar_dirty_projection_processing_uses_one_explicit_transaction() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(TOKEN_RADAR_PROJECTION))
    rebuild_dirty_targets = _class_method(tree, "TokenRadarProjection", "rebuild_dirty_targets")
    transactional_body = _class_method(tree, "TokenRadarProjection", "_rebuild_dirty_targets_in_transaction")
    finish_successful_claims = _class_method(tree, "TokenRadarProjection", "_finish_successful_claims")
    rebuild_source = ast.get_source_segment(source, rebuild_dirty_targets) or ""
    processing_source = ast.get_source_segment(source, transactional_body) or ""
    finish_source = ast.get_source_segment(source, finish_successful_claims) or ""

    assert "with _transaction_context(self.repos.conn):" in rebuild_source
    assert "self._rebuild_dirty_targets_in_transaction(" in rebuild_source
    assert "refresh_rank_set(" in processing_source
    assert "commit=True" not in processing_source
    assert "commit=True" not in finish_source
    assert "commit=False" in processing_source
    assert "commit=False" in finish_source


def test_token_radar_projection_service_requires_worker_supplied_work_width_policy() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(TOKEN_RADAR_PROJECTION))
    rebuild = _class_method(tree, "TokenRadarProjection", "rebuild")
    refresh_rank_set = _class_method(tree, "TokenRadarProjection", "refresh_rank_set")
    rebuild_dirty_targets = _class_method(tree, "TokenRadarProjection", "rebuild_dirty_targets")
    dirty_transaction = _class_method(tree, "TokenRadarProjection", "_rebuild_dirty_targets_in_transaction")
    worker_source = TOKEN_RADAR_PROJECTION_WORKER.read_text(encoding="utf-8")

    def required_kwonly(method: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
        for index, arg in enumerate(method.args.kwonlyargs):
            if arg.arg == name:
                return method.args.kw_defaults[index] is None
        return False

    for method, names in (
        (rebuild, ("limit",)),
        (refresh_rank_set, ("limit",)),
        (rebuild_dirty_targets, ("limit", "rank_limit", "lease_owner")),
        (dirty_transaction, ("limit", "rank_limit", "lease_owner")),
    ):
        assert [name for name in names if not required_kwonly(method, name)] == []

    forbidden_defaults = (
        "limit: int = 100",
        "rank_limit: int = 100",
        'lease_owner: str = "token_radar_projection"',
    )
    assert [token for token in forbidden_defaults if token in source] == []
    assert '"limit": self.limit' in worker_source
    assert '"rank_limit": self.limit' in worker_source
    assert '"lease_owner": self.name' in worker_source


def test_token_radar_successful_publication_generation_ids_are_content_stable() -> None:
    tree = _parse(TOKEN_RADAR_PROJECTION)
    refresh_rank_set = _class_method(tree, "TokenRadarProjection", "refresh_rank_set")
    generation_writes = _generation_id_writes(refresh_rank_set)
    successful_generation_calls = [
        _call_name(value) for _node, value in generation_writes if isinstance(value, ast.Call)
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


def test_token_radar_repository_requires_formal_current_identity_without_target_or_intent_fallback() -> None:
    source = TOKEN_RADAR_REPOSITORY.read_text(encoding="utf-8")
    forbidden = (
        'row.get("target_type_key") or row.get("target_type")',
        'row.get("identity_id") or row.get("target_id")',
        'row.get("identity_id") or row.get("target_id") or row.get("intent_id")',
    )
    required = (
        "_current_row_identity_key(row)",
        "token_radar_current_identity_required",
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []


def test_token_radar_projection_builds_formal_identity_before_publication_without_intent_fallback() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    identity_source = _function_source(TOKEN_RADAR_PROJECTION, "_projection_identity_key")
    forbidden = (
        'else str(row.get("intent_id"))',
        'str(target_id or latest.get("intent_id"))',
        "_display_symbol(dict(row))",
        'f"symbol:{symbol.upper()}"',
        'row.get("lookup_keys_json") or []',
    )
    required = (
        "_projection_identity_key(latest)",
        '"LookupKey"',
        '_required_resolution_list(row, "lookup_keys_json")',
        "token_radar_projection_identity_required",
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in forbidden if token in identity_source] == []
    assert [token for token in required if token not in source] == []


def test_token_radar_projection_requires_formal_resolution_json_without_defaults() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    project_group = _function_source(TOKEN_RADAR_PROJECTION, "_project_group")
    resolution_discovery = _function_source(TOKEN_RADAR_PROJECTION, "_resolution_discovery")
    forbidden = (
        'str(latest.get("resolution_status") or "NIL")',
        'latest.get("reason_codes_json") or []',
        'latest.get("candidate_ids_json") or []',
        'latest.get("lookup_keys_json") or []',
        'row.get("lookup_keys_json") or []',
    )
    required = (
        '_required_resolution_text(latest, "resolution_status")',
        '_required_resolution_list(latest, "reason_codes_json")',
        '_required_resolution_list(latest, "candidate_ids_json")',
        '_required_resolution_list(latest, "lookup_keys_json")',
        "token_radar_projection_resolution_required",
        "token_radar_projection_resolution_invalid",
    )

    assert [token for token in forbidden if token in project_group + resolution_discovery] == []
    assert [token for token in required if token not in source] == []


def test_token_radar_projection_requires_formal_high_confidence_target_identity() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    project_group = _function_source(TOKEN_RADAR_PROJECTION, "_project_group")
    has_resolved_target = _function_source(TOKEN_RADAR_PROJECTION, "_has_resolved_target")
    forbidden = (
        'not bool(row.get("target_id"))',
        'str(row.get("resolution_status") or "")',
        'row.get("target_type") == "Asset"',
    )
    required = (
        "_has_resolved_target(latest, resolution_status=resolution_status)",
        '_required_resolved_target_text(row, "target_type")',
        '_required_resolved_target_text(row, "target_id")',
        "token_radar_projection_resolved_target_required",
        "token_radar_projection_resolved_target_invalid",
    )

    assert [token for token in forbidden if token in has_resolved_target] == []
    assert [token for token in required if token not in source] == []
    assert "_has_resolved_target(latest)" not in project_group


def test_token_radar_projection_requires_formal_asset_identity_for_resolved_asset_target() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    project_group = _function_source(TOKEN_RADAR_PROJECTION, "_project_group")
    target_source = _function_source(TOKEN_RADAR_PROJECTION, "_target")
    forbidden = (
        '"reason_codes": row.get("asset_identity_reason_codes") or []',
        '"conflict_count": row.get("asset_identity_conflict_count") or 0',
        'str(row.get("resolution_status") or "NIL")',
    )
    required = (
        "_target(latest, resolved=resolved)",
        '_required_asset_identity_text(row, "asset_identity_confidence")',
        '_required_asset_identity_list(row, "asset_identity_reason_codes")',
        '_required_asset_identity_int(row, "asset_identity_conflict_count")',
        "token_radar_projection_asset_identity_required",
        "token_radar_projection_asset_identity_invalid",
    )

    assert [token for token in forbidden if token in target_source] == []
    assert [token for token in required if token not in source] == []
    assert "_target(latest)" not in project_group


def test_token_radar_projection_downstream_current_key_requires_formal_identity_without_fallback() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    current_key_source = source.split("def _current_key", 1)[1].split("\ndef _pulse_trigger_target", 1)[0]
    forbidden = (
        'row.get("target_type_key") or row.get("target_type")',
        'row.get("identity_id") or row.get("target_id")',
        'row.get("identity_id") or row.get("target_id") or row.get("intent_id")',
    )
    required = (
        '_required_projection_row_text(row, "target_type_key")',
        '_required_projection_row_text(row, "identity_id")',
        "token_radar_current_identity_required",
    )

    assert [token for token in forbidden if token in current_key_source] == []
    assert [token for token in required if token not in source] == []


def test_token_radar_target_feature_current_row_requires_formal_identity_without_empty_defaults() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    row_from_target_feature = _function_source(TOKEN_RADAR_PROJECTION, "_row_from_target_feature")
    forbidden = (
        'str(row.get("target_type_key") or "")',
        'str(row.get("identity_id") or "")',
    )
    required = (
        '_required_projection_row_text(row, "target_type_key")',
        '_required_projection_row_text(row, "identity_id")',
        "token_radar_current_identity_required",
    )

    assert [token for token in forbidden if token in row_from_target_feature] == []
    assert [token for token in required if token not in source] == []


def test_token_radar_target_feature_current_row_requires_formal_dimensions_without_defaults() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    row_from_target_feature = _function_source(TOKEN_RADAR_PROJECTION, "_row_from_target_feature")
    forbidden = (
        '_json_ready(row.get("factor_snapshot_json")) or {}',
        'str(row.get("projection_version") or "")',
        'str(row.get("window") or "")',
        'str(row.get("scope") or "")',
        'str(row.get("lane") or "")',
        'str(row.get("lane") or "attention")',
        'int(row.get("latest_event_received_at_ms") or 0)',
    )
    required = (
        '_required_target_feature_current_row_text(row, "projection_version")',
        '_required_target_feature_current_row_text(row, "window")',
        '_required_target_feature_current_row_text(row, "scope")',
        '_required_target_feature_current_row_text(row, "lane")',
        '_required_target_feature_current_row_mapping(row, "factor_snapshot_json")',
        '_required_target_feature_current_row_int(row, "latest_event_received_at_ms")',
        "token_radar_target_feature_current_row_required",
        "token_radar_target_feature_current_row_invalid",
    )

    assert [token for token in forbidden if token in row_from_target_feature] == []
    assert [token for token in required if token not in source] == []


def test_token_radar_rank_set_selection_requires_formal_rank_input_fields_without_silent_skip() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    rank_current_rows = _class_method_source(TOKEN_RADAR_PROJECTION, "TokenRadarProjection", "_rank_current_rows")
    select_top_ranked = _function_source(TOKEN_RADAR_PROJECTION, "_select_top_ranked_by_lane")
    forbidden = (
        'int(row.get("latest_event_received_at_ms") or 0)',
        'str(row.get("lane") or "") == lane',
    )
    required = (
        "_rank_input_latest_event_received_at_ms(row)",
        "_rank_input_lane(row)",
        "token_radar_rank_input_required",
        "token_radar_rank_input_invalid",
    )

    assert [token for token in forbidden if token in rank_current_rows + select_top_ranked] == []
    assert [token for token in required if token not in source] == []


def test_token_radar_compact_rank_inputs_require_formal_score_decision_fields_without_defaults() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    rank_compact_inputs = _class_method_source(TOKEN_RADAR_PROJECTION, "TokenRadarProjection", "rank_compact_inputs")
    compact_rank_key = _function_source(TOKEN_RADAR_PROJECTION, "_compact_rank_key")
    decision_from_score_and_gates = _function_source(TOKEN_RADAR_PROJECTION, "_decision_from_score_and_gates")
    forbidden = (
        '_display_score_from_value(row.get("raw_composite_score"))',
        '{"max_decision": row.get("gates_max_decision")}',
        'decision = row.get("recommended_decision") or "discard"',
        'rank_score = _float_or_none(row.get("rank_score")) or 0.0',
        'str(gates.get("max_decision") or "discard")',
    )
    required = (
        '_rank_input_display_score(row, "raw_composite_score")',
        '_rank_input_decision(row, "gates_max_decision")',
        '_rank_input_decision(row, "recommended_decision")',
        '_rank_input_number(row, "rank_score")',
        '_rank_input_decision(gates, "max_decision")',
        "token_radar_rank_input_required",
        "token_radar_rank_input_invalid",
    )

    checked_source = rank_compact_inputs + compact_rank_key + decision_from_score_and_gates
    assert [token for token in forbidden if token in checked_source] == []
    assert [token for token in required if token not in source] == []


def test_token_radar_projection_does_not_keep_retired_rank_key_or_raw_score_fallback_helpers() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    forbidden = (
        "def _rank_key(",
        "def _display_score_from_value(",
        "def _factor_snapshot_for_ranking(",
        "def _raw_composite_score(",
        'composite.get("raw_alpha_score")',
        "return (3, 0.0, 0, 0, 0)",
    )
    required = (
        "def _compact_rank_key(",
        '_rank_input_display_score(row, "raw_composite_score")',
        "def _factor_snapshot_or_raise(",
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []


def test_token_radar_target_feature_current_row_requires_last_scored_time_without_runtime_clock() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    row_from_target_feature = _function_source(TOKEN_RADAR_PROJECTION, "_row_from_target_feature")
    forbidden = (
        'row.get("last_scored_at_ms") or row.get("updated_at_ms") or _now_ms()',
        "_now_ms()",
    )
    required = (
        '_required_target_feature_current_row_int(row, "last_scored_at_ms")',
        "token_radar_target_feature_current_row_required",
        "token_radar_target_feature_current_row_invalid",
    )

    assert [token for token in forbidden if token in row_from_target_feature] == []
    assert [token for token in required if token not in source] == []


def test_token_radar_patch_ranked_current_row_requires_formal_ranked_metadata_without_defaults() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    patch_ranked = _function_source(TOKEN_RADAR_PROJECTION, "_patch_ranked_current_row")
    forbidden = (
        'ranked.get("normalization_status") or "no_signal"',
        'ranked.get("cohort_status") or "not_ranked"',
        'int(ranked.get("cohort_size") or 0)',
        'factor_ranks = _dict(ranked.get("factor_ranks"))',
        'patched["rank"] = int(ranked.get("rank") or 0)',
        'patched["source_max_received_at_ms"] = int(ranked.get("latest_event_received_at_ms") or 0)',
    )
    required = (
        '_ranked_row_status(ranked, "normalization_status"',
        '_ranked_row_status(ranked, "cohort_status"',
        '_ranked_row_non_negative_int(ranked, "cohort_size")',
        '_ranked_row_mapping(ranked, "cohort_metadata")',
        '_ranked_row_mapping(ranked, "factor_ranks")',
        '_ranked_row_positive_int(ranked, "rank")',
        '_ranked_row_non_negative_int(ranked, "latest_event_received_at_ms")',
        "token_radar_ranked_row_required",
        "token_radar_ranked_row_invalid",
    )

    assert [token for token in forbidden if token in patch_ranked] == []
    assert [token for token in required if token not in source] == []


def test_token_radar_patch_ranked_current_row_requires_formal_normalization_metadata_without_defaults() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    patch_ranked = _function_source(TOKEN_RADAR_PROJECTION, "_patch_ranked_current_row")
    forbidden = (
        'ranked.get("cohort_in_cohort") is True',
        '"alpha_rank": ranked.get("alpha_rank")',
        "round(float(rank) * 100.0)",
    )
    required = (
        '_ranked_row_bool(ranked, "cohort_in_cohort")',
        "_ranked_alpha_rank(ranked, normalization_status)",
        "_ranked_factor_ranks(ranked)",
        "token_radar_ranked_row_invalid:alpha_rank",
        "token_radar_ranked_row_invalid:factor_ranks",
        "token_radar_ranked_row_invalid:{column}",
    )

    assert [token for token in forbidden if token in patch_ranked] == []
    assert [token for token in required if token not in source] == []


def test_token_radar_target_feature_writer_requires_formal_payload_fields_without_defaults() -> None:
    source = TOKEN_RADAR_REPOSITORY.read_text(encoding="utf-8")
    target_feature_payload = _function_source(TOKEN_RADAR_REPOSITORY, "_target_feature_payload")
    forbidden = (
        'row.get("factor_snapshot_json") or {}',
        'str(row.get("lane") or "attention")',
        'int(row.get("source_max_received_at_ms") or computed_at_ms)',
        'list(row.get("source_event_ids_json") or [])',
        'int(row.get("created_at_ms") or computed_at_ms)',
        '"rank_score": _rank_score(factor_snapshot) or 0.0',
        '"raw_composite_score": _composite_score(composite if isinstance(composite, dict) else {})',
        '(composite.get("recommended_decision") if isinstance(composite, dict) else None) or "discard"',
        'str((gates.get("max_decision") if isinstance(gates, dict) else None) or "discard")',
    )
    required = (
        '_required_target_feature_payload_mapping(row, "factor_snapshot_json")',
        "_required_target_feature_payload_lane(row)",
        '_required_target_feature_payload_int(row, "source_max_received_at_ms")',
        "source_event_ids = _required_target_feature_payload_string_list(",
        '_required_target_feature_payload_int(row, "created_at_ms")',
        '_required_target_feature_payload_mapping(factor_snapshot, "composite")',
        '_required_target_feature_payload_mapping(factor_snapshot, "gates")',
        '_required_target_feature_payload_number(composite, "rank_score")',
        '_required_target_feature_payload_decision(composite, "recommended_decision")',
        '_required_target_feature_payload_decision(gates, "max_decision")',
        "token_radar_target_feature_payload_required",
        "token_radar_target_feature_payload_invalid",
    )

    assert [token for token in forbidden if token in target_feature_payload] == []
    assert [token for token in required if token not in source] == []


def test_token_radar_repository_write_counts_require_real_cursor_rowcount_without_defaults() -> None:
    source = TOKEN_RADAR_REPOSITORY.read_text(encoding="utf-8")
    forbidden = (
        'getattr(cursor, "rowcount"',
        'getattr(cursor, "rowcount", 1)',
        'getattr(cursor, "rowcount", 0)',
        "count = int(rowcount)",
    )
    required = (
        "def _cursor_rowcount(cursor: Any) -> int:",
        "rowcount: object = cursor.rowcount",
        "isinstance(rowcount, bool) or not isinstance(rowcount, int)",
        "token_radar_repository_rowcount_required",
        "token_radar_repository_rowcount_invalid",
        "rows_written += _cursor_rowcount(cursor)",
        "return _cursor_rowcount(cursor)",
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []


def test_token_radar_first_seen_write_count_uses_cursor_rowcount_without_candidate_count() -> None:
    source = TOKEN_RADAR_REPOSITORY.read_text(encoding="utf-8")
    first_seen_source = source.split("def upsert_first_seen_batch", 1)[1].split(
        "\n    def mark_publication_failed",
        1,
    )[0]

    forbidden = (
        "return len(records)",
        "return len(rows)",
    )
    required = (
        "cursor = self.conn.execute(",
        "return _cursor_rowcount(cursor)",
    )

    assert [token for token in forbidden if token in first_seen_source] == []
    assert [token for token in required if token not in first_seen_source] == []


def test_token_radar_downstream_fanout_uses_formal_current_identity_without_alias_override() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    fanout_source = "\n".join(
        (
            source.split("def _pulse_trigger_target", 1)[1].split("\ndef _pulse_trigger_reason", 1)[0],
            source.split("def _capture_tier_rank_payload", 1)[1].split("\ndef _capture_tier_fields_from_target", 1)[0],
            source.split("def _capture_tier_target_key", 1)[1].split("\ndef _rank_subject", 1)[0],
        )
    )
    forbidden = (
        'row.get("target_type") or row.get("target_type_key")',
        'row.get("target_id") or row.get("identity_id")',
        'str(row.get("target_type") or "").strip()',
        'str(row.get("target_id") or "").strip()',
        'int(row.get("source_max_received_at_ms") or computed_at_ms)',
    )
    required = (
        "_current_row_resolved_target(row)",
        '_required_projection_row_text(row, "target_type_key")',
        '_required_projection_row_text(row, "identity_id")',
        "_downstream_source_watermark_ms(row)",
        "token_radar_downstream_source_watermark_required",
    )

    assert [token for token in forbidden if token in fanout_source] == []
    assert [token for token in required if token not in source] == []


def test_token_capture_tier_rank_set_hash_requires_formal_current_identity_without_alias_fallback() -> None:
    source = TOKEN_CAPTURE_TIER_DIRTY_REPOSITORY.read_text(encoding="utf-8")
    rank_hash_source = source.split("def _rank_row_payload", 1)[1].split("\ndef _rank_subject", 1)[0]
    forbidden = (
        'row.get("target_type") or row.get("target_type_key")',
        'row.get("target_id") or row.get("identity_id")',
    )
    required = (
        '_required_rank_row_text(row, "target_type_key")',
        '_required_rank_row_text(row, "identity_id")',
        "token_capture_tier_rank_set_identity_required",
    )

    assert [token for token in forbidden if token in rank_hash_source] == []
    assert [token for token in required if token not in source] == []


def test_token_radar_capture_tier_fanout_requires_formal_source_watermark_without_runtime_fallback() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    enqueue_source = _function_source(TOKEN_RADAR_PROJECTION, "_enqueue_token_capture_tier_for_rank_changes")
    watermark_source = source.split("def _rank_set_source_watermark_ms", 1)[1].split(
        "\ndef _capture_tier_relevant_row",
        1,
    )[0]
    forbidden = (
        'int(row.get("source_max_received_at_ms") or 0)',
        "default=int(computed_at_ms)",
        "source_watermark_ms = max(",
    )

    assert "_rank_set_source_watermark_ms(rows=tier_rows, exited_rows=tier_exited_rows)" in enqueue_source
    assert "_downstream_source_watermark_ms(row)" in watermark_source
    assert "token_radar_downstream_source_watermark_required" in source
    assert [token for token in forbidden if token in enqueue_source] == []


def test_token_radar_rank_input_venue_uses_formal_identity_without_alias_override() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    venue_source = source.split("def token_radar_venue_for_rank_input", 1)[1].split(
        "\ndef _factor_snapshot_subject_chain",
        1,
    )[0]
    forbidden = (
        'row.get("target_type") or row.get("target_type_key")',
        'row.get("target_type_key") or row.get("target_type")',
    )
    required = (
        'row.get("target_type_key")',
        'row.get("target_type")',
    )

    assert [token for token in forbidden if token in venue_source] == []
    assert [token for token in required if token not in venue_source] == []


def test_token_radar_projection_source_targets_require_formal_identity_without_alias_fallback() -> None:
    source = TOKEN_RADAR_PROJECTION.read_text(encoding="utf-8")
    source_request_targets = _function_source(TOKEN_RADAR_PROJECTION, "_source_requests_for_targets")
    project_source_request = _class_method_source(
        TOKEN_RADAR_PROJECTION,
        "TokenRadarProjection",
        "_project_source_request",
    )
    combined = source_request_targets + project_source_request
    forbidden = (
        'target.get("target_type_key") or target.get("target_type")',
        'target.get("identity_id") or target.get("target_id")',
        "if not target_type_key or not identity_id:",
    )
    required = (
        '_required_target_identity_text(target, "target_type_key")',
        '_required_target_identity_text(target, "identity_id")',
        "token_radar_projection_target_identity_required",
    )

    assert [token for token in forbidden if token in combined] == []
    assert [token for token in required if token not in source] == []
