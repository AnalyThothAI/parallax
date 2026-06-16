from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from parallax.app.runtime.queue_health import queue_health_adapter_specs
from parallax.app.runtime.worker_manifest import (
    WorkerRuntimeConstraint,
    all_worker_manifests,
    worker_queue_health_tables,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"


@dataclass(frozen=True)
class RuntimeWorkerHardCutContract:
    path: Path
    banned_calls: tuple[str, ...]
    control_claim_markers: tuple[str, ...]
    payload_loader_markers: tuple[str, ...] = (
        "load_",
        "payload",
        "rows_for_claim",
        "rows_for_targets",
        "targets_for_claim",
    )
    notes_keys: tuple[str, ...] = (
        "claimed",
        "queue_depth",
        "source_rows_scanned",
        "targets_loaded",
        "rows_written",
    )


RUNTIME_WORKER_CONTRACTS: tuple[RuntimeWorkerHardCutContract, ...] = (
    RuntimeWorkerHardCutContract(
        path=SRC / "domains/pulse_lab/runtime/pulse_candidate_worker.py",
        banned_calls=("latest_current_rows",),
        control_claim_markers=("pulse_trigger_dirty_targets.claim_due",),
    ),
    RuntimeWorkerHardCutContract(
        path=SRC / "domains/narrative_intel/runtime/narrative_admission_worker.py",
        banned_calls=("admitted_radar_rows", "admissions_for_window_scope", "delete_admissions_outside_frontier"),
        control_claim_markers=("narrative_admission_dirty_targets.claim_due",),
    ),
    RuntimeWorkerHardCutContract(
        path=SRC / "domains/asset_market/runtime/token_profile_current_worker.py",
        banned_calls=("recent_profile_targets",),
        control_claim_markers=("token_profile_current_dirty_targets.claim_due",),
    ),
    RuntimeWorkerHardCutContract(
        path=SRC / "domains/asset_market/runtime/token_image_mirror_worker.py",
        banned_calls=("candidate_sources",),
        control_claim_markers=("token_image_source_dirty_targets.claim_due",),
    ),
    RuntimeWorkerHardCutContract(
        path=SRC / "domains/asset_market/runtime/asset_profile_refresh_worker.py",
        banned_calls=("select_due_asset_profile_rows",),
        control_claim_markers=("asset_profile_refresh_targets.claim_due",),
    ),
    RuntimeWorkerHardCutContract(
        path=SRC / "domains/asset_market/runtime/token_capture_tier_worker.py",
        banned_calls=("active_live_market_targets", "demote_absent_hot_rows"),
        control_claim_markers=("token_capture_tier_dirty_targets.claim_due",),
    ),
    RuntimeWorkerHardCutContract(
        path=SRC / "domains/asset_market/runtime/live_price_gateway.py",
        banned_calls=("active_live_market_targets",),
        control_claim_markers=("token_capture_tiers.live_target_rows",),
        payload_loader_markers=(),
    ),
    RuntimeWorkerHardCutContract(
        path=SRC / "domains/macro_intel/runtime/macro_view_projection_worker.py",
        banned_calls=("refresh_observation_series_rows",),
        control_claim_markers=("claim_macro_projection_dirty_targets",),
        payload_loader_markers=("refresh_observation_series_rows_for_concepts", "observations_for_concepts"),
    ),
)
ENFORCED_RUNTIME_WORKER_CONTRACTS = RUNTIME_WORKER_CONTRACTS

BROAD_DISCOVERY_CALLS = frozenset(call for contract in RUNTIME_WORKER_CONTRACTS for call in contract.banned_calls)

CONTROL_PLANE_TABLES = frozenset(
    {
        "pulse_trigger_dirty_targets",
        "narrative_admission_dirty_targets",
        "token_profile_current_dirty_targets",
        "token_image_source_dirty_targets",
        "asset_profile_refresh_targets",
        "token_capture_tier_dirty_targets",
    }
)

BUSINESS_OUTPUT_TABLES = frozenset(
    {
        "pulse_candidates",
        "pulse_agent_runs",
        "pulse_agent_run_steps",
        "narrative_admissions",
        "token_profile_current",
        "token_image_assets",
        "asset_profiles",
        "token_capture_tier",
        "market_ticks",
        "watchlist_handle_signal_events",
        "watchlist_handle_signal_stats",
        "watchlist_handle_summaries",
    }
)

BOUNDED_SCHEDULER_COUNTER_PATHS = (SRC / "domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py",)

REMOVED_RUNTIME_REPAIR_PATHS = {
    SRC / "app/runtime/runtime_worker_dirty_targets.py",
}
REMOVED_RUNTIME_REPAIR_COMMAND = "enqueue-runtime-worker-dirty-targets"
TOKEN_RADAR_REPOSITORY_PATH = SRC / "domains/token_intel/repositories/token_radar_repository.py"
TOKEN_RADAR_PROJECTION_SERVICE_PATH = SRC / "domains/token_intel/services/token_radar_projection.py"
TOKEN_RADAR_PROJECTION_WORKER_PATH = SRC / "domains/token_intel/runtime/token_radar_projection_worker.py"
TOKEN_INTENT_REBUILD_PATH = SRC / "domains/token_intel/runtime/token_intent_rebuild.py"
TOKEN_RESOLUTION_REFRESH_SERVICE_PATH = SRC / "domains/token_intel/services/token_resolution_refresh.py"
TOKEN_INTENT_RESOLVER_SERVICE_PATH = SRC / "domains/token_intel/services/token_intent_resolver.py"
TOKEN_EVIDENCE_REPOSITORY_PATH = SRC / "domains/token_intel/repositories/token_evidence_repository.py"
TOKEN_INTENT_REPOSITORY_PATH = SRC / "domains/token_intel/repositories/token_intent_repository.py"
TOKEN_INTENT_LOOKUP_REPOSITORY_PATH = SRC / "domains/token_intel/repositories/token_intent_lookup_repository.py"
INTENT_RESOLUTION_REPOSITORY_PATH = SRC / "domains/token_intel/repositories/intent_resolution_repository.py"
PROJECTION_REPOSITORY_PATH = SRC / "domains/token_intel/repositories/projection_repository.py"
TOKEN_RADAR_RANK_SOURCE_REPOSITORY_PATH = SRC / "domains/token_intel/repositories/token_radar_rank_source_repository.py"
TOKEN_RADAR_RANK_SOURCE_QUERY_PATH = SRC / "domains/token_intel/queries/token_radar_rank_source_query.py"
TOKEN_FACTOR_EVALUATION_REPOSITORY_PATH = SRC / "domains/token_intel/repositories/token_factor_evaluation_repository.py"
SIGNAL_REPOSITORY_PATH = SRC / "domains/token_intel/repositories/signal_repository.py"
EVIDENCE_REPOSITORY_PATH = SRC / "domains/evidence/repositories/evidence_repository.py"
ENTITY_REPOSITORY_PATH = SRC / "domains/evidence/repositories/entity_repository.py"
EVENT_ANCHOR_WORKER_PATH = SRC / "domains/asset_market/runtime/event_anchor_backfill_worker.py"
EVENT_ANCHOR_JOB_REPOSITORY_PATH = SRC / "domains/asset_market/repositories/event_anchor_backfill_job_repository.py"
DISCOVERY_REPOSITORY_PATH = SRC / "domains/asset_market/repositories/discovery_repository.py"
RESOLUTION_REFRESH_WORKER_PATH = SRC / "domains/asset_market/runtime/resolution_refresh_worker.py"
TOKEN_CAPTURE_TIER_WORKER_PATH = SRC / "domains/asset_market/runtime/token_capture_tier_worker.py"
TOKEN_CAPTURE_TIER_REPOSITORY_PATH = SRC / "domains/asset_market/repositories/token_capture_tier_repository.py"
TOKEN_CAPTURE_TIER_DIRTY_TARGET_REPOSITORY_PATH = (
    SRC / "domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py"
)
MARKET_TICK_CURRENT_DIRTY_TARGET_REPOSITORY_PATH = (
    SRC / "domains/asset_market/repositories/market_tick_current_dirty_target_repository.py"
)
MARKET_TICK_CURRENT_REPOSITORY_PATH = SRC / "domains/asset_market/repositories/market_tick_current_repository.py"
MARKET_TICK_REPOSITORY_PATH = SRC / "domains/asset_market/repositories/market_tick_repository.py"
TOKEN_PROFILE_CURRENT_DIRTY_TARGET_REPOSITORY_PATH = (
    SRC / "domains/asset_market/repositories/token_profile_current_dirty_target_repository.py"
)
TOKEN_PROFILE_CURRENT_REPOSITORY_PATH = SRC / "domains/asset_market/repositories/token_profile_current_repository.py"
TOKEN_IMAGE_SOURCE_DIRTY_TARGET_REPOSITORY_PATH = (
    SRC / "domains/asset_market/repositories/token_image_source_dirty_target_repository.py"
)
TOKEN_IMAGE_SOURCE_ADMISSION_SERVICE_PATH = SRC / "domains/asset_market/services/token_image_source_admission.py"
TOKEN_IMAGE_ASSET_REPOSITORY_PATH = SRC / "domains/asset_market/repositories/token_image_asset_repository.py"
IDENTITY_EVIDENCE_REPOSITORY_PATH = SRC / "domains/asset_market/repositories/identity_evidence_repository.py"
REGISTRY_REPOSITORY_PATH = SRC / "domains/asset_market/repositories/registry_repository.py"
ASSET_PROFILE_REFRESH_TARGET_REPOSITORY_PATH = (
    SRC / "domains/asset_market/repositories/asset_profile_refresh_target_repository.py"
)
ASSET_PROFILE_REPOSITORY_PATH = SRC / "domains/asset_market/repositories/asset_profile_repository.py"
ASSET_PROFILE_REFRESH_SERVICE_PATH = SRC / "domains/asset_market/services/asset_profile_refresh.py"
CEX_TOKEN_PROFILE_REPOSITORY_PATH = SRC / "domains/asset_market/repositories/cex_token_profile_repository.py"
NARRATIVE_ADMISSION_DIRTY_TARGET_REPOSITORY_PATH = (
    SRC / "domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py"
)
NARRATIVE_REPOSITORY_PATH = SRC / "domains/narrative_intel/repositories/narrative_repository.py"
MACRO_REPOSITORY_PATH = SRC / "domains/macro_intel/repositories/macro_intel_repository.py"
MACRO_SYNC_SERVICE_PATH = SRC / "domains/macro_intel/services/macro_sync_service.py"
PULSE_CANDIDATE_JOB_SERVICE_PATH = SRC / "domains/pulse_lab/services/pulse_candidate_job_service.py"
PULSE_DECISION_RUNTIME_SERVICE_PATH = SRC / "domains/pulse_lab/services/pulse_decision_runtime.py"
PULSE_JOBS_REPOSITORY_PATH = SRC / "domains/pulse_lab/repositories/pulse_jobs_repository.py"
MACRO_ROUTE_PATH = SRC / "app/surfaces/api/routes_macro.py"
QUEUE_TERMINAL_PATH = SRC / "platform/db/queue_terminal.py"
POSTGRES_CLIENT_PATH = SRC / "platform/db/postgres_client.py"
QUEUE_OPS_PATH = SRC / "app/surfaces/cli/commands/queue_ops.py"
BOOTSTRAP_PATH = SRC / "app/runtime/bootstrap.py"
INGEST_SERVICE_PATH = SRC / "domains/evidence/services/ingest_service.py"


@pytest.mark.architecture
def test_every_registered_worker_has_runtime_constraint_classification() -> None:
    manifests = all_worker_manifests()

    assert manifests
    assert all(isinstance(manifest.runtime_constraint, WorkerRuntimeConstraint) for manifest in manifests)


@pytest.mark.architecture
def test_queue_health_adapter_registry_covers_manifest_queue_tables_exactly_once() -> None:
    manifest_table_users: dict[str, set[str]] = {}
    for worker_name, tables in worker_queue_health_tables().items():
        for table in tables:
            manifest_table_users.setdefault(table, set()).add(worker_name)
    specs = queue_health_adapter_specs()

    missing_specs = sorted(set(manifest_table_users) - set(specs))
    unused_specs = sorted(set(specs) - set(manifest_table_users))
    duplicate_specs = sorted(table for table, spec in specs.items() if spec.table != table)

    assert missing_specs == []
    assert unused_specs == []
    assert duplicate_specs == []
    assert {spec.kind for spec in specs.values()} <= {"status_queue", "dirty_target", "terminal_projection"}


@pytest.mark.architecture
def test_queue_health_uses_formal_api_pool_connection_contract_without_missing_connection_fallback() -> None:
    queue_health_source = (SRC / "app/runtime/queue_health.py").read_text(encoding="utf-8")
    app_status_source = (SRC / "app/runtime/app.py").read_text(encoding="utf-8")
    fill_source = queue_health_source.split("def fill_worker_queue_healths", 1)[1].split(
        "\n\ndef fetch_queue_table_health",
        1,
    )[0]
    forbidden_tokens = (
        'getattr(runtime, "db", None)',
        'getattr(db, "api_pool", None)',
        'getattr(api_pool, "connection", None)',
        "if not callable(connection):",
        'error_code="missing_connection"',
        '"missing_connection"',
    )
    violations = [token for token in forbidden_tokens if token in fill_source or token in queue_health_source]

    assert violations == []
    assert "connection_context = runtime.db.api_pool.connection()" in fill_source
    assert "with connection_context as conn:" in fill_source
    assert '"missing_connection":' not in app_status_source


@pytest.mark.architecture
def test_token_radar_rank_path_has_no_old_wide_feature_loader() -> None:
    token_intel_text = "\n".join(path.read_text() for path in (SRC / "domains/token_intel").rglob("*.py"))
    repository_text = TOKEN_RADAR_REPOSITORY_PATH.read_text()

    assert "list_target_features_for_rank_set" not in token_intel_text
    assert re.search(r"SELECT\s+\*\s+FROM\s+token_radar_target_features", token_intel_text, re.IGNORECASE) is None
    for forbidden in (
        "wide_rank_path",
        "legacy_rank_path",
        "rank_set_fallback",
        "use_wide_rank",
        "TOKEN_RADAR_WIDE_RANK",
    ):
        assert forbidden not in repository_text


@pytest.mark.architecture
def test_token_radar_runtime_has_no_single_target_source_query() -> None:
    runtime_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (TOKEN_RADAR_PROJECTION_SERVICE_PATH, TOKEN_RADAR_PROJECTION_WORKER_PATH)
    )

    for forbidden in (
        "TokenRadarTargetFeatureQuery",
        "WITH source_intents AS MATERIALIZED",
        "source_rows(",
    ):
        assert forbidden not in runtime_text


@pytest.mark.architecture
def test_macro_request_path_has_no_observation_dedupe_window() -> None:
    route_text = MACRO_ROUTE_PATH.read_text(encoding="utf-8")
    repository_tree = _parse(MACRO_REPOSITORY_PATH)
    request_method_text = "\n".join(
        _function_source(MACRO_REPOSITORY_PATH, node)
        for node in ast.walk(repository_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {"latest_observations", "observations_for_concepts", "concept_history_counts"}
    )

    for forbidden in (
        "WITH deduped AS",
        "row_number() OVER",
        "PARTITION BY concept_key, observed_at",
        "FROM macro_observations",
    ):
        assert forbidden not in route_text
        assert forbidden not in request_method_text


@pytest.mark.architecture
def test_macro_cli_has_no_direct_projection_writer() -> None:
    cli_text = (SRC / "app/surfaces/cli/commands/macro.py").read_text(encoding="utf-8")
    parser_text = (SRC / "app/surfaces/cli/parser.py").read_text(encoding="utf-8")

    for forbidden in (
        "project-once",
        "build_macro_view_snapshot",
        "_project_once",
        "insert_snapshot",
    ):
        assert forbidden not in cli_text
        assert forbidden not in parser_text
    assert 'macro_sync.add_argument("--project"' not in parser_text


@pytest.mark.architecture
def test_event_anchor_runtime_has_no_ready_fact_reconciliation_scan() -> None:
    worker_text = EVENT_ANCHOR_WORKER_PATH.read_text(encoding="utf-8")
    repository_text = EVENT_ANCHOR_JOB_REPOSITORY_PATH.read_text(encoding="utf-8")

    assert "mark_ready_jobs_done" not in worker_text
    assert "ready_jobs_reconciled" not in worker_text
    assert "mark_ready_jobs_done" not in repository_text
    assert "JOIN enriched_events anchors" not in repository_text


@pytest.mark.architecture
def test_event_anchor_stale_cleanup_requires_worker_session_unit_of_work_without_manual_commit() -> None:
    worker_text = EVENT_ANCHOR_WORKER_PATH.read_text(encoding="utf-8")
    worker_tree = _parse(EVENT_ANCHOR_WORKER_PATH)
    stale_cleanup = "\n".join(
        _function_source(EVENT_ANCHOR_WORKER_PATH, node)
        for node in ast.walk(worker_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_expire_stale_jobs"
    )

    forbidden = (
        "_commit_if_supported",
        'getattr(conn, "commit", None)',
        'getattr(repos, "commit", None)',
        "commit()",
    )

    assert "with self._transaction_session() as repos:" in stale_cleanup
    assert all(token not in worker_text for token in forbidden)


@pytest.mark.architecture
def test_event_anchor_repository_terminal_paths_require_connection_transaction_without_nullcontext() -> None:
    repository_text = EVENT_ANCHOR_JOB_REPOSITORY_PATH.read_text(encoding="utf-8")
    repository_tree = _parse(EVENT_ANCHOR_JOB_REPOSITORY_PATH)
    transaction_helper = "\n".join(
        _function_source(EVENT_ANCHOR_JOB_REPOSITORY_PATH, node)
        for node in ast.walk(repository_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_transaction"
    )

    forbidden = (
        "nullcontext",
        "return nullcontext()",
        'getattr(conn, "transaction", None)',
        "if callable(transaction):",
        "if transaction is None:",
    )

    assert "raise RuntimeError" in transaction_helper
    assert "event_anchor_repository_transaction_required" in transaction_helper
    assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_live_price_gateway_publish_uses_async_hub_contract_without_isawaitable_fallback() -> None:
    source = (SRC / "domains/asset_market/runtime/live_price_gateway.py").read_text(encoding="utf-8")
    publish_source = source.split("async def _publish", maxsplit=1)[1].split(
        "\n\ndef _market_target_from_row",
        maxsplit=1,
    )[0]
    forbidden_tokens = (
        "import inspect",
        "inspect.isawaitable",
        "isawaitable(",
        "await result",
        "result = self.on_live_market_update(payload)",
    )

    assert [token for token in forbidden_tokens if token in source] == []
    assert "await self.on_live_market_update(payload)" in publish_source


@pytest.mark.architecture
def test_queue_terminal_operator_resolution_requires_transaction_without_nullcontext() -> None:
    queue_terminal_text = QUEUE_TERMINAL_PATH.read_text(encoding="utf-8")
    queue_terminal_tree = _parse(QUEUE_TERMINAL_PATH)
    transaction_helper = "\n".join(
        _function_source(QUEUE_TERMINAL_PATH, node)
        for node in ast.walk(queue_terminal_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_transaction"
    )
    resolve_source = "\n".join(
        _function_source(QUEUE_TERMINAL_PATH, node)
        for node in ast.walk(queue_terminal_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "resolve_terminal_event"
    )
    terminalize_source = "\n".join(
        _function_source(QUEUE_TERMINAL_PATH, node)
        for node in ast.walk(queue_terminal_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "terminalize_source_row"
    )

    forbidden = (
        "nullcontext",
        "return nullcontext()",
        'hasattr(conn, "transaction")',
        'getattr(conn, "transaction", None)',
        "conn.commit()",
        '_optional_int(normalized_row.get("attempt_count")) or 0',
        'unresolved.get("terminal_generation") or 1',
        '(row or {}).get("terminal_generation") or 1',
        "str(max(1, int(terminal_generation)))",
    )

    assert "raise RuntimeError" in transaction_helper
    assert "queue_terminal_transaction_required" in transaction_helper
    assert "queue_terminal_attempt_contract_required" in queue_terminal_text
    assert "queue_terminal_generation_contract_required" in queue_terminal_text
    assert "with _transaction(conn):" in resolve_source
    assert "with _transaction(conn):" in terminalize_source
    assert "conn.commit()" not in resolve_source
    assert all(token not in queue_terminal_text for token in forbidden)


@pytest.mark.architecture
def test_queue_terminal_returning_writes_require_cursor_rowcount_match() -> None:
    queue_terminal_text = QUEUE_TERMINAL_PATH.read_text(encoding="utf-8")
    queue_terminal_tree = _parse(QUEUE_TERMINAL_PATH)
    functions = {
        node.name: _function_source(QUEUE_TERMINAL_PATH, node)
        for node in ast.walk(queue_terminal_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name
        in {
            "terminalize_source_row",
            "resolve_terminal_event",
            "_cursor_rowcount",
            "_single_returning_rowcount",
        }
    }
    terminalize_source = functions["terminalize_source_row"]
    resolve_source = functions["resolve_terminal_event"]
    rowcount_source = functions["_cursor_rowcount"]
    returning_source = functions["_single_returning_rowcount"]
    forbidden = (
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
        "cursor.rowcount or 0",
    )

    assert "def _cursor_rowcount(cursor: Any) -> int:" in queue_terminal_text
    assert "rowcount: object = cursor.rowcount" in rowcount_source
    assert "queue_terminal_rowcount_required" in rowcount_source
    assert "queue_terminal_rowcount_invalid" in rowcount_source
    assert "def _single_returning_rowcount(cursor: Any, row: Any | None) -> int:" in queue_terminal_text
    assert "count = _cursor_rowcount(cursor)" in returning_source
    assert "count > 1" in returning_source
    assert "count != int(row is not None)" in returning_source
    assert "queue_terminal_rowcount_invalid" in returning_source
    assert "_single_returning_rowcount(cursor, row)" in terminalize_source
    assert "_single_returning_rowcount(cursor, row)" in resolve_source
    assert all(token not in queue_terminal_text for token in forbidden)


@pytest.mark.architecture
def test_terminal_ledger_callers_do_not_default_attempt_count_before_platform_contract() -> None:
    paths = (
        EVENT_ANCHOR_JOB_REPOSITORY_PATH,
        DISCOVERY_REPOSITORY_PATH,
        SRC / "domains/pulse_lab/repositories/pulse_jobs_repository.py",
    )
    banned = 'attempt_count=int(row.get("attempt_count") or 0)'

    violations = [str(path.relative_to(ROOT)) for path in paths if banned in path.read_text(encoding="utf-8")]

    assert violations == []


@pytest.mark.architecture
def test_postgres_health_check_uses_formal_commit_rollback_contract_without_optional_probe() -> None:
    tree = _parse(POSTGRES_CLIENT_PATH)
    health_source = "\n".join(
        _function_source(POSTGRES_CLIENT_PATH, node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "postgres_health_check"
    )
    forbidden_tokens = (
        'hasattr(conn, "commit")',
        'hasattr(conn, "rollback")',
        'getattr(conn, "commit"',
        'getattr(conn, "rollback"',
    )
    violations = [token for token in forbidden_tokens if token in health_source]

    assert violations == []
    assert "conn.commit()" in health_source
    assert "conn.rollback()" in health_source


@pytest.mark.architecture
def test_postgres_require_transaction_uses_formal_transaction_status_without_optional_info_fallback() -> None:
    tree = _parse(POSTGRES_CLIENT_PATH)
    guard_source = "\n".join(
        _function_source(POSTGRES_CLIENT_PATH, node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "require_transaction"
    )
    forbidden_tokens = (
        'getattr(conn, "info", None)',
        "if info is None",
        "except Exception",
        "return\n",
    )
    violations = [token for token in forbidden_tokens if token in guard_source]

    assert violations == []
    assert "conn.info.transaction_status" in guard_source
    assert "requires_transaction_status_contract" in guard_source
    assert "requires_explicit_transaction" in guard_source


@pytest.mark.architecture
def test_queue_ops_retry_transitions_require_repository_contracts_without_optional_probes() -> None:
    queue_ops_text = QUEUE_OPS_PATH.read_text(encoding="utf-8")

    forbidden = (
        'getattr(repos, "signals", None)',
        'getattr(signals, "conn", None)',
        'getattr(repos, "discovery", None)',
        'getattr(discovery, "enqueue_lookup_keys", None)',
        'getattr(repos, "event_anchor_jobs", None)',
        'getattr(repo, "retry_terminal_job_from_snapshot", None)',
        'getattr(repos, "pulse_jobs", None)',
    )

    assert "signals_connection_required" in queue_ops_text
    assert "discovery_repository_required" in queue_ops_text
    assert "event_anchor_job_repository_required" in queue_ops_text
    assert "pulse_jobs_repository_required" in queue_ops_text
    assert all(token not in queue_ops_text for token in forbidden)


@pytest.mark.architecture
def test_discovery_repository_terminal_paths_require_connection_transaction_without_nullcontext() -> None:
    repository_text = DISCOVERY_REPOSITORY_PATH.read_text(encoding="utf-8")
    repository_tree = _parse(DISCOVERY_REPOSITORY_PATH)
    transaction_helper = "\n".join(
        _function_source(DISCOVERY_REPOSITORY_PATH, node)
        for node in ast.walk(repository_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_transaction"
    )
    terminalize_source = "\n".join(
        _function_source(DISCOVERY_REPOSITORY_PATH, node)
        for node in ast.walk(repository_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "terminalize_lookup_claims"
    )

    forbidden = (
        "nullcontext",
        "return nullcontext()",
        "if callable(transaction):",
        'getattr(self.conn, "transaction", None)',
        "self.conn.commit()",
    )

    assert "def _run_repository_write" in repository_text
    assert "raise RuntimeError" in transaction_helper
    assert "discovery_repository_transaction_required" in transaction_helper
    assert repository_text.count("_run_repository_write(self.conn, commit,") == 7
    assert "with _transaction(self.conn):" in terminalize_source
    assert "self.conn.commit()" not in terminalize_source
    assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_token_capture_tier_projection_requires_session_transaction_without_manual_commit() -> None:
    worker_text = TOKEN_CAPTURE_TIER_WORKER_PATH.read_text(encoding="utf-8")
    worker_tree = _parse(TOKEN_CAPTURE_TIER_WORKER_PATH)
    project_once_source = "\n".join(
        _function_source(TOKEN_CAPTURE_TIER_WORKER_PATH, node)
        for node in ast.walk(worker_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "project_once"
    )
    worker_project_source = "\n".join(
        _function_source(TOKEN_CAPTURE_TIER_WORKER_PATH, node)
        for node in ast.walk(worker_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_project_once"
    )

    forbidden = (
        "_commit_if_supported",
        "commit: bool",
        "commit=True",
        'getattr(conn, "commit", None)',
        'getattr(repos, "commit", None)',
        "commit()",
    )

    assert 'repos.require_transaction(operation="token_capture_tier_projection")' in project_once_source
    assert "with repos.transaction():" in worker_project_source
    assert worker_project_source.index("with repos.transaction():") < worker_project_source.index("claim_due(")
    assert all(token not in worker_text for token in forbidden)


@pytest.mark.architecture
def test_resolution_refresh_worker_requires_session_transaction_without_manual_commit() -> None:
    worker_text = RESOLUTION_REFRESH_WORKER_PATH.read_text(encoding="utf-8")
    worker_tree = _parse(RESOLUTION_REFRESH_WORKER_PATH)
    refresh_once_source = "\n".join(
        _function_source(RESOLUTION_REFRESH_WORKER_PATH, node)
        for node in ast.walk(worker_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_run_refresh_once"
    )
    finish_claims_source = "\n".join(
        _function_source(RESOLUTION_REFRESH_WORKER_PATH, node)
        for node in ast.walk(worker_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_finish_lookup_claims"
    )

    forbidden = (
        "repos.conn.commit()",
        "repos.conn.transaction()",
        "_commit_if_supported",
        'getattr(repos, "transaction", None)',
        'getattr(repos.conn, "transaction", None)',
        'getattr(repos.conn, "commit", None)',
    )

    transaction_marker = "_session_transaction(repos)"
    assert transaction_marker in refresh_once_source
    assert transaction_marker in finish_claims_source
    assert refresh_once_source.index(transaction_marker) < refresh_once_source.index("start_lookup(")
    assert all(token not in worker_text for token in forbidden)


@pytest.mark.architecture
def test_token_intent_reprocess_and_rebuild_require_session_transaction_without_manual_commit() -> None:
    rebuild_text = TOKEN_INTENT_REBUILD_PATH.read_text(encoding="utf-8")
    rebuild_tree = _parse(TOKEN_INTENT_REBUILD_PATH)
    rebuild_recent_source = "\n".join(
        _function_source(TOKEN_INTENT_REBUILD_PATH, node)
        for node in ast.walk(rebuild_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "rebuild_recent_token_intents"
    )
    rebuild_event_source = "\n".join(
        _function_source(TOKEN_INTENT_REBUILD_PATH, node)
        for node in ast.walk(rebuild_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "rebuild_event_token_intents"
    )
    rebuild_inner_source = "\n".join(
        _function_source(TOKEN_INTENT_REBUILD_PATH, node)
        for node in ast.walk(rebuild_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_rebuild_event_token_intents"
    )
    refresh_text = TOKEN_RESOLUTION_REFRESH_SERVICE_PATH.read_text(encoding="utf-8")
    refresh_tree = _parse(TOKEN_RESOLUTION_REFRESH_SERVICE_PATH)
    reprocess_source = "\n".join(
        _function_source(TOKEN_RESOLUTION_REFRESH_SERVICE_PATH, node)
        for node in ast.walk(refresh_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "reprocess_recent_token_intents"
    )
    reprocess_inner_source = "\n".join(
        _function_source(TOKEN_RESOLUTION_REFRESH_SERVICE_PATH, node)
        for node in ast.walk(refresh_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_reprocess_recent_token_intents"
    )
    resolver_text = TOKEN_INTENT_RESOLVER_SERVICE_PATH.read_text(encoding="utf-8")

    forbidden = (
        "repos.conn.commit()",
        "repos.conn.transaction()",
        "commit: bool",
        "self.resolutions.conn.commit()",
        "_commit_if_supported",
        'getattr(repos, "transaction", None)',
        'getattr(repos.conn, "transaction", None)',
        'getattr(repos.conn, "commit", None)',
    )

    assert "with repos.transaction():" in rebuild_recent_source
    assert "with repos.transaction():" in rebuild_event_source
    assert 'repos.require_transaction(operation="token_intent_rebuild")' in rebuild_inner_source
    assert "with repos.transaction():" in reprocess_source
    assert 'repos.require_transaction(operation="token_resolution_refresh")' in reprocess_inner_source
    assert all(token not in rebuild_text for token in forbidden)
    assert all(token not in refresh_text for token in forbidden)
    assert all(token not in resolver_text for token in forbidden)


@pytest.mark.architecture
def test_token_resolution_refresh_batches_evidence_reads_for_reprocess_intents() -> None:
    service_source = TOKEN_RESOLUTION_REFRESH_SERVICE_PATH.read_text(encoding="utf-8")
    repository_source = TOKEN_EVIDENCE_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden_service_tokens = (
        "repos.token_evidence.evidence_for_intent(str(intent",
        "evidence_for_intent(str(intent",
    )
    required_service_tokens = (
        "evidence_by_intent = repos.token_evidence.evidence_for_intents(",
        'evidence_by_intent.get(str(intent["intent_id"]), [])',
    )
    required_repository_tokens = (
        "def evidence_for_intents(self, intent_ids: list[str]) -> dict[str, list[dict[str, Any]]]:",
        "WITH input_intents AS",
        "WITH ORDINALITY",
        "JOIN token_intent_evidence",
        "ORDER BY distinct_intents.ordinality ASC",
    )

    assert [token for token in forbidden_service_tokens if token in service_source] == []
    assert [token for token in required_service_tokens if token not in service_source] == []
    assert [token for token in required_repository_tokens if token not in repository_source] == []


@pytest.mark.architecture
def test_token_fact_repositories_use_connection_transaction_without_manual_commit_fallback() -> None:
    repository_contracts = (
        (TOKEN_EVIDENCE_REPOSITORY_PATH, "token_evidence_repository_transaction_required", 2),
        (TOKEN_INTENT_REPOSITORY_PATH, "token_intent_repository_transaction_required", 2),
        (TOKEN_INTENT_LOOKUP_REPOSITORY_PATH, "token_intent_lookup_repository_transaction_required", 1),
        (INTENT_RESOLUTION_REPOSITORY_PATH, "intent_resolution_repository_transaction_required", 1),
    )
    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )
    for path, error_marker, helper_calls in repository_contracts:
        repository_text = path.read_text(encoding="utf-8")
        assert "def _run_repository_write" in repository_text
        assert error_marker in repository_text
        assert repository_text.count("_run_repository_write(self.conn, commit,") == helper_calls
        assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_token_fact_repositories_require_real_cursor_rowcount_for_fact_writes() -> None:
    evidence_text = TOKEN_EVIDENCE_REPOSITORY_PATH.read_text(encoding="utf-8")
    intent_text = TOKEN_INTENT_REPOSITORY_PATH.read_text(encoding="utf-8")
    lookup_text = TOKEN_INTENT_LOOKUP_REPOSITORY_PATH.read_text(encoding="utf-8")
    resolution_text = INTENT_RESOLUTION_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        'getattr(cursor, "rowcount"',
        "cursor.rowcount or 0",
        'return self.get(payload["evidence_id"]) or {}',
        'return self.get(payload["intent_id"]) or {}',
        "return self.get(resolution_id) or {}",
    )
    required_by_source = (
        (
            evidence_text,
            (
                "def _cursor_rowcount(cursor: Any) -> int:",
                "rowcount: object = cursor.rowcount",
                "token_evidence_repository_rowcount_required",
                "token_evidence_repository_rowcount_invalid",
                "RETURNING *",
                "return _required_returning_row(cursor, row)",
                "_cursor_rowcount(cursor)",
            ),
        ),
        (
            intent_text,
            (
                "def _cursor_rowcount(cursor: Any) -> int:",
                "rowcount: object = cursor.rowcount",
                "token_intent_repository_rowcount_required",
                "token_intent_repository_rowcount_invalid",
                "RETURNING *",
                "intent_row = _required_returning_row(cursor, row)",
                "_optional_single_rowcount(cursor)",
            ),
        ),
        (
            lookup_text,
            (
                "def _cursor_rowcount(cursor: Any) -> int:",
                "rowcount: object = cursor.rowcount",
                "token_intent_lookup_repository_rowcount_required",
                "token_intent_lookup_repository_rowcount_invalid",
                "_cursor_rowcount(delete_cursor)",
                "_required_single_rowcount(cursor)",
            ),
        ),
        (
            resolution_text,
            (
                "def _cursor_rowcount(cursor: Any) -> int:",
                "rowcount: object = cursor.rowcount",
                "intent_resolution_repository_rowcount_required",
                "intent_resolution_repository_rowcount_invalid",
                "RETURNING *",
                "_required_single_rowcount(cursor)",
                "return _required_returning_row(cursor, row)",
            ),
        ),
    )

    for source, required_tokens in required_by_source:
        assert [token for token in forbidden if token in source] == []
        assert [token for token in required_tokens if token not in source] == []


@pytest.mark.architecture
def test_token_radar_repository_uses_connection_transaction_without_manual_commit_fallback() -> None:
    repository_text = TOKEN_RADAR_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "token_radar_repository_transaction_required" in repository_text
    assert repository_text.count("with _transaction(self.conn):") == 6
    assert "SELECT pg_advisory_xact_lock" in repository_text
    assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_evidence_ingest_repositories_use_connection_transaction_without_manual_commit_fallback() -> None:
    repository_contracts = (
        (EVIDENCE_REPOSITORY_PATH, "evidence_repository_transaction_required", 1),
        (ENTITY_REPOSITORY_PATH, "entity_repository_transaction_required", 1),
    )
    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )
    for path, error_marker, helper_calls in repository_contracts:
        repository_text = path.read_text(encoding="utf-8")
        assert "def _run_repository_write" in repository_text
        assert error_marker in repository_text
        assert repository_text.count("_run_repository_write(self.conn, commit,") == helper_calls
        assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_evidence_fact_write_counts_require_real_cursor_rowcount() -> None:
    evidence_text = EVIDENCE_REPOSITORY_PATH.read_text(encoding="utf-8")
    entity_text = ENTITY_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden_evidence = (
        "cursor.rowcount == 1",
        "cursor.rowcount != 0",
        "bool(cursor.rowcount == 1)",
        "bool(cursor.rowcount != 0)",
        'getattr(cursor, "rowcount", 0)',
    )
    forbidden_entity = (
        "cursor.rowcount == 1",
        "int(cursor.rowcount == 1)",
        'getattr(cursor, "rowcount", 0)',
    )
    required_evidence = (
        "def _single_rowcount(cursor: Any) -> int:",
        "rowcount: object = cursor.rowcount",
        "evidence_repository_rowcount_required",
        "evidence_repository_rowcount_invalid",
        "return _single_rowcount(cursor) == 1",
    )
    required_entity = (
        "def _single_rowcount(cursor: Any) -> int:",
        "rowcount: object = cursor.rowcount",
        "entity_repository_rowcount_required",
        "entity_repository_rowcount_invalid",
        "inserted += _single_rowcount(cursor)",
    )

    assert [token for token in forbidden_evidence if token in evidence_text] == []
    assert [token for token in forbidden_entity if token in entity_text] == []
    assert [token for token in required_evidence if token not in evidence_text] == []
    assert [token for token in required_entity if token not in entity_text] == []


@pytest.mark.architecture
def test_projection_repository_uses_connection_transaction_without_manual_commit_fallback() -> None:
    repository_text = PROJECTION_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "def _run_repository_write" in repository_text
    assert "projection_repository_transaction_required" in repository_text
    assert repository_text.count("_run_repository_write(self.conn, commit,") == 6
    assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_projection_repository_diagnostic_reads_require_explicit_limits_without_defaults() -> None:
    repository_text = PROJECTION_REPOSITORY_PATH.read_text(encoding="utf-8")

    assert "def list_runs(self, *, limit: int," in repository_text
    assert "def list_dirty_ranges(self, *, limit: int," in repository_text
    assert "limit: int = 20" not in repository_text
    assert "limit: int = 50" not in repository_text


@pytest.mark.architecture
def test_projection_repository_stale_run_accounting_requires_real_cursor_rowcount() -> None:
    repository_text = PROJECTION_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        'getattr(result, "rowcount", 0)',
        'int(getattr(result, "rowcount", 0) or 0)',
    )
    required = (
        "def _cursor_rowcount(cursor: Any) -> int:",
        "rowcount = cursor.rowcount",
        "projection_repository_rowcount_required",
        "projection_repository_rowcount_invalid",
        "return _cursor_rowcount(result)",
    )

    assert [token for token in forbidden if token in repository_text] == []
    assert [token for token in required if token not in repository_text] == []


@pytest.mark.architecture
def test_projection_repository_claim_dirty_ranges_requires_returning_rowcount_match() -> None:
    repository_text = PROJECTION_REPOSITORY_PATH.read_text(encoding="utf-8")
    repository_tree = _parse(PROJECTION_REPOSITORY_PATH)
    claim_source = "\n".join(
        _function_source(PROJECTION_REPOSITORY_PATH, node)
        for node in ast.walk(repository_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "claim_dirty_ranges"
    )
    forbidden = (
        ").fetchall()",
        "len(rows)",
    )
    required = (
        "def _returned_rowcount(cursor: Any, rows: list[Any]) -> int:",
        "projection_repository_rowcount_required",
        "projection_repository_rowcount_invalid",
        "cursor = self.conn.execute(",
        "rows = cursor.fetchall()",
        "_returned_rowcount(cursor, rows)",
    )

    assert [token for token in forbidden if token in claim_source] == []
    assert [token for token in required if token not in repository_text + claim_source] == []


@pytest.mark.architecture
def test_projection_repository_required_control_writes_require_rowcount_and_returning_evidence() -> None:
    repository_text = PROJECTION_REPOSITORY_PATH.read_text(encoding="utf-8")
    repository_tree = _parse(PROJECTION_REPOSITORY_PATH)
    functions = {
        node.name: _function_source(PROJECTION_REPOSITORY_PATH, node)
        for node in ast.walk(repository_tree)
        if isinstance(node, ast.FunctionDef)
    }
    required_helpers = (
        "def _required_single_rowcount(cursor: Any) -> int:",
        "def _required_returning_row(cursor: Any, row: Any) -> dict[str, Any]:",
        "projection_repository_rowcount_required",
        "projection_repository_rowcount_invalid",
    )
    required_by_function = {
        "advance_offset": (
            "cursor = self.conn.execute(",
            "_required_single_rowcount(cursor)",
        ),
        "start_run": (
            "cursor = self.conn.execute(",
            "RETURNING *",
            "row = cursor.fetchone()",
            "return _required_returning_row(cursor, row)",
        ),
        "finish_run": (
            "cursor = self.conn.execute(",
            "_required_single_rowcount(cursor)",
        ),
        "enqueue_dirty_range": (
            "cursor = self.conn.execute(",
            "_required_single_rowcount(cursor)",
        ),
    }
    forbidden_start_run = (
        "return self.run_by_id(resolved_run_id) or {}",
        "run_by_id(resolved_run_id) or {}",
    )

    assert [token for token in required_helpers if token not in repository_text] == []
    for function_name, required in required_by_function.items():
        source = functions[function_name]
        assert [token for token in required if token not in source] == []
    assert [token for token in forbidden_start_run if token in functions["start_run"]] == []


@pytest.mark.architecture
def test_token_radar_rank_source_repository_owns_write_transactions_without_query_commit_fallback() -> None:
    repository_text = TOKEN_RADAR_RANK_SOURCE_REPOSITORY_PATH.read_text(encoding="utf-8")
    query_text = TOKEN_RADAR_RANK_SOURCE_QUERY_PATH.read_text(encoding="utf-8")

    repository_forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )
    query_forbidden = (
        "self.conn.commit()",
        "commit: bool",
        "commit=True",
        "if commit:",
    )

    assert "def _run_repository_write" in repository_text
    assert "token_radar_rank_source_repository_transaction_required" in repository_text
    assert repository_text.count("_run_repository_write(self.conn, commit,") == 3
    assert all(token not in repository_text for token in repository_forbidden)
    assert all(token not in query_text for token in query_forbidden)


@pytest.mark.architecture
def test_token_factor_evaluation_repository_uses_connection_transaction_without_manual_commit_fallback() -> None:
    repository_text = TOKEN_FACTOR_EVALUATION_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "def _run_repository_write" in repository_text
    assert "token_factor_evaluation_repository_transaction_required" in repository_text
    assert repository_text.count("_run_repository_write(self.conn, commit,") == 2
    assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_signal_repository_alert_writes_use_connection_transaction_without_manual_commit_fallback() -> None:
    repository_text = SIGNAL_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        'getattr(cursor, "rowcount"',
        "if cursor.rowcount == 0:",
        "return nullcontext()",
    )
    required = (
        "def _single_row_write_count(cursor: Any) -> int:",
        "rowcount = cursor.rowcount",
        "signal_repository_rowcount_required",
        "signal_repository_rowcount_invalid",
        "inserted = _single_row_write_count(cursor)",
        "if inserted == 0:",
    )

    assert "def _run_repository_write" in repository_text
    assert "signal_repository_transaction_required" in repository_text
    assert repository_text.count("_run_repository_write(self.conn, commit,") == 1
    assert all(token not in repository_text for token in forbidden)
    assert all(token in repository_text for token in required)


def test_asset_market_sync_services_require_connection_transaction_without_manual_commit() -> None:
    service_contracts = (
        (
            SRC / "domains/asset_market/services/asset_market_sync.py",
            "asset_market_sync_transaction_required",
            "with _transaction(registry.conn):",
        ),
        (
            SRC / "domains/asset_market/services/cex_token_profile_sync.py",
            "cex_token_profile_sync_transaction_required",
            "with _transaction(cex_token_profiles.conn):",
        ),
        (
            SRC / "domains/asset_market/services/us_equity_symbol_sync.py",
            "us_equity_symbol_sync_transaction_required",
            "with _transaction(registry.conn):",
        ),
    )

    forbidden = (
        ".conn.commit()",
        "nullcontext",
        'getattr(conn, "transaction", None)',
        'getattr(registry.conn, "transaction", None)',
        'getattr(cex_token_profiles.conn, "transaction", None)',
        'getattr(registry, "binance_usdt_perp_sync_plan_counts", None)',
        '"cex_tokens_to_insert": len(set(base_symbols))',
        '"pricefeeds_to_insert": len(set(native_market_ids))',
    )
    for path, error_marker, transaction_marker in service_contracts:
        source = path.read_text()
        assert [token for token in forbidden if token in source] == []
        assert error_marker in source
        assert transaction_marker in source

    route_sync_source = (SRC / "domains/asset_market/services/asset_market_sync.py").read_text()
    assert "registry.binance_usdt_perp_sync_plan_counts(" in route_sync_source


@pytest.mark.architecture
def test_cex_token_profile_sync_requires_formal_mapping_profiles_without_object_fallback() -> None:
    service_text = (SRC / "domains/asset_market/services/cex_token_profile_sync.py").read_text(encoding="utf-8")

    forbidden = (
        "getattr(profile,",
        'profile.get("provider") or BINANCE_CEX_PROFILE_PROVIDER',
        'profile["symbol"] or base_symbol',
        'raw_payload") if isinstance(profile, dict) else',
        "return dict(raw) if isinstance(raw, dict) else {}",
    )

    assert "cex_token_profile_sync_profile_mapping_required" in service_text
    assert "cex_token_profile_sync_raw_payload_required" in service_text
    assert "cex_token_profile_sync_raw_payload_invalid" in service_text
    assert "_formal_profile(profile)" in service_text
    assert [token for token in forbidden if token in service_text] == []


@pytest.mark.architecture
def test_registry_us_equity_deactivate_returning_counts_require_cursor_rowcount_match() -> None:
    repository_text = REGISTRY_REPOSITORY_PATH.read_text(encoding="utf-8")
    repository_tree = _parse(REGISTRY_REPOSITORY_PATH)
    functions = {
        node.name: _function_source(REGISTRY_REPOSITORY_PATH, node)
        for node in ast.walk(repository_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"deactivate_missing_us_equity_symbols", "_cursor_rowcount", "_returned_rowcount"}
    }
    deactivate_source = functions["deactivate_missing_us_equity_symbols"]
    helper_source = functions["_returned_rowcount"]
    rowcount_source = functions["_cursor_rowcount"]
    forbidden = (
        "return len(row)",
        "return len(rows)",
        "deactivated_count = len(row)",
        "deactivated_count = len(rows)",
    )

    assert [token for token in forbidden if token in deactivate_source] == []
    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "rowcount: object = cursor.rowcount" in rowcount_source
    assert "registry_repository_rowcount_required" in rowcount_source
    assert "registry_repository_rowcount_invalid" in rowcount_source
    assert "def _returned_rowcount(cursor: Any, rows: list[Any]) -> int:" in repository_text
    assert "count = _cursor_rowcount(cursor)" in helper_source
    assert "if count != len(rows):" in helper_source
    assert "registry_repository_rowcount_invalid" in helper_source
    assert "cursor = self.conn.execute" in deactivate_source
    assert "rows = cursor.fetchall()" in deactivate_source
    assert "return _returned_rowcount(cursor, rows)" in deactivate_source


@pytest.mark.architecture
def test_registry_repository_upserts_require_returning_rowcount_without_fallback_readback() -> None:
    repository_text = REGISTRY_REPOSITORY_PATH.read_text(encoding="utf-8")
    repository_tree = _parse(REGISTRY_REPOSITORY_PATH)
    functions = {
        node.name: _function_source(REGISTRY_REPOSITORY_PATH, node)
        for node in ast.walk(repository_tree)
        if isinstance(node, ast.FunctionDef)
    }
    required_helpers = (
        "def _required_returning_row(cursor: Any, row: Any) -> dict[str, Any]:",
        "count = _cursor_rowcount(cursor)",
        "if count != 1:",
        "if row is None:",
        "registry_repository_rowcount_required",
        "registry_repository_rowcount_invalid",
    )
    upsert_names = ("upsert_cex_token", "upsert_chain_asset", "upsert_pricefeed", "upsert_us_equity_symbol")
    forbidden_upsert_tokens = (
        "return self._row_by_id(",
        "return dict(row) if row else {}",
        ") or {}",
    )

    assert "def _row_by_id(" not in repository_text
    assert [token for token in required_helpers if token not in repository_text] == []
    for name in upsert_names:
        source = functions[name]
        assert [token for token in forbidden_upsert_tokens if token in source] == []
        assert "cursor = self.conn.execute(" in source
        assert "row = cursor.fetchone()" in source
        assert "return _required_returning_row(cursor, row)" in source
    for name in ("upsert_cex_token", "upsert_pricefeed", "upsert_us_equity_symbol"):
        assert "RETURNING *" in functions[name]


def test_ops_execute_commands_require_transaction_without_manual_commit_fallback() -> None:
    source = (SRC / "app/surfaces/cli/commands/ops.py").read_text()

    forbidden = (
        "commit=True",
        "repos.conn.commit()",
        "repository.conn.commit()",
        ".conn.commit()",
        "nullcontext",
        'getattr(conn, "transaction", None)',
    )

    assert [token for token in forbidden if token in source] == []
    assert "ops_command_transaction_required" in source
    assert "with _transaction(repos.conn):" in source
    assert "with _transaction(repository.conn):" in source


def test_ops_capture_tier_rank_set_requires_valid_window_without_24h_fallback() -> None:
    source = (SRC / "app/surfaces/cli/commands/ops.py").read_text()
    function_source = source.split("def _enqueue_token_capture_tier_rank_set", 1)[1].split(
        "\n\ndef _ops_window_ms",
        1,
    )[0]
    helper_source = source.split("def _ops_window_ms", 1)[1].split(
        "\n\ndef _rebuild_news_canonical_items",
        1,
    )[0]

    assert "WINDOW_MS.get(parsed_window" not in function_source
    assert 'WINDOW_MS["24h"]' not in function_source
    assert "_ops_window_ms(parsed_window)" in function_source
    assert "return WINDOW_MS[window]" in helper_source
    assert "raise ValueError" in helper_source


def test_ops_one_shot_worker_lifecycle_uses_formal_db_and_lock_contracts() -> None:
    source = (SRC / "app/surfaces/cli/commands/ops.py").read_text()
    db_close_source = source.split("def _close_db_bundle", 1)[1].split(
        "\ndef _release_advisory_lock_connection",
        1,
    )[0]
    lock_release_source = source.split("def _release_advisory_lock_connection", 1)[1].split(
        "\ndef _effective_worker_advisory_lock_key",
        1,
    )[0]
    lock_key_source = source.split("def _effective_worker_advisory_lock_key", 1)[1].split(
        "\ndef _close_asset_market_providers",
        1,
    )[0]

    db_close_forbidden = (
        'for name in ("api_pool", "worker_pool", "lock_pool", "tool_pool", "wake_pool")',
        "getattr(db, name, None)",
        'getattr(pool, "close", None)',
    )
    lock_release_forbidden = (
        'getattr(connection, "release", None)',
        'getattr(connection, "close", None)',
        "release or close",
        "releaser is not None",
    )
    lock_key_forbidden = (
        'getattr(worker, "_advisory_lock_key", None)',
        'getattr(worker, "SINGLE_WRITER_KEY", None)',
        "if callable(resolve)",
        "worker.__class__.__name__",
    )

    assert [token for token in db_close_forbidden if token in db_close_source] == []
    assert [token for token in lock_release_forbidden if token in lock_release_source] == []
    assert [token for token in lock_key_forbidden if token in lock_key_source] == []
    assert "ops_db_bundle_aclose_required" in db_close_source
    assert "asyncio.run(aclose())" in db_close_source
    assert "ops_advisory_lock_release_required" in lock_release_source
    assert "release = connection.release" in lock_release_source
    assert "release()" in lock_release_source
    assert "ops_worker_advisory_lock_key_required" in lock_key_source
    assert "resolve = worker._advisory_lock_key" in lock_key_source
    assert "key = resolve()" in lock_key_source


def test_ops_one_shot_worker_settings_overrides_use_formal_model_copy_contract() -> None:
    source = (SRC / "app/surfaces/cli/commands/ops.py").read_text()
    helper_source = source.split("def _worker_settings_with_overrides", 1)[1].split(
        "\n\ndef _close_db_bundle",
        1,
    )[0]
    forbidden = (
        "from types import SimpleNamespace",
        'getattr(config, "model_dump", None)',
        "model_dump",
        "dict(vars(config))",
        "vars(config)",
        "__dict__",
        "SimpleNamespace(**",
        "return SimpleNamespace",
        "-> SimpleNamespace",
    )

    assert [token for token in forbidden if token in source] == []
    assert "model_copy = config.model_copy" in helper_source
    assert 'raise RuntimeError("ops_worker_settings_model_copy_required")' in helper_source
    assert "if not callable(model_copy):" in helper_source
    assert "return model_copy(update=overrides)" in helper_source


def test_ops_market_tick_current_rebuild_uses_formal_worker_settings_contract() -> None:
    source = (SRC / "app/surfaces/cli/commands/ops.py").read_text()
    rebuild_source = source.split("def _run_market_tick_current_rebuild", 1)[1].split(
        "\n\ndef _market_tick_current_projection_lock_key",
        1,
    )[0]
    lock_key_source = source.split("def _market_tick_current_projection_lock_key", 1)[1].split(
        "\n\ndef _enqueue_token_radar_dirty_targets",
        1,
    )[0]
    forbidden_tokens = (
        'getattr(getattr(settings, "workers", SimpleNamespace())',
        "worker_settings or SimpleNamespace()",
        'getattr(worker_settings, "statement_timeout_seconds", None)',
        'getattr(self.settings, "advisory_lock_key", None)',
        "class _LockProbe",
    )
    combined = f"{rebuild_source}\n{lock_key_source}"
    violations = [token for token in forbidden_tokens if token in combined]

    assert violations == []
    assert "worker_settings = settings.workers.market_tick_current_projection" in rebuild_source
    assert "statement_timeout_seconds=worker_settings.statement_timeout_seconds" in rebuild_source
    assert "return int(settings.workers.market_tick_current_projection.advisory_lock_key)" in lock_key_source


def test_ops_asset_market_provider_cleanup_uses_bundle_aclose_without_provider_field_probe() -> None:
    source = (SRC / "app/surfaces/cli/commands/ops.py").read_text()
    cleanup_source = source.split("def _close_asset_market_providers", 1)[1].split(
        "\ndef _audit_token_intent",
        1,
    )[0]

    forbidden = (
        "for name in (",
        '"cex_market"',
        '"dex_discovery_market"',
        '"dex_quote_market"',
        '"dex_candle_market"',
        '"stream_dex_market"',
        "dex_profile_sources",
        "getattr(asset_market",
        'getattr(provider, "close", None)',
        "close = getattr",
        "if close:",
    )

    assert [token for token in forbidden if token in cleanup_source] == []
    assert "ops_asset_market_providers_aclose_required" in cleanup_source
    assert "aclose = asset_market.aclose" in cleanup_source
    assert "asyncio.run(aclose())" in cleanup_source


@pytest.mark.architecture
def test_token_capture_tier_dirty_repository_uses_connection_transaction_without_manual_commit_fallback() -> None:
    repository_text = TOKEN_CAPTURE_TIER_DIRTY_TARGET_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "def _run_repository_write" in repository_text
    assert "token_capture_tier_dirty_target_transaction_required" in repository_text
    assert repository_text.count("_run_repository_write(self.conn, commit,") == 3
    assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_token_capture_tier_dirty_write_counts_require_real_cursor_rowcount() -> None:
    repository_text = TOKEN_CAPTURE_TIER_DIRTY_TARGET_REPOSITORY_PATH.read_text(encoding="utf-8")
    tree = _parse(TOKEN_CAPTURE_TIER_DIRTY_TARGET_REPOSITORY_PATH)
    write_sources = "\n".join(
        _function_source(TOKEN_CAPTURE_TIER_DIRTY_TARGET_REPOSITORY_PATH, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in {"enqueue_rank_set", "mark_done"}
    )
    forbidden = (
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
    )

    assert [token for token in forbidden if token in write_sources] == []
    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "token_capture_tier_dirty_target_rowcount_required" in repository_text
    assert "token_capture_tier_dirty_target_rowcount_invalid" in repository_text
    assert "changed = _cursor_rowcount(cursor)" in write_sources
    assert "return _cursor_rowcount(cursor)" in write_sources


@pytest.mark.architecture
def test_token_capture_tier_repository_demote_counts_require_real_cursor_rowcount() -> None:
    repository_text = TOKEN_CAPTURE_TIER_REPOSITORY_PATH.read_text(encoding="utf-8")
    tree = _parse(TOKEN_CAPTURE_TIER_REPOSITORY_PATH)
    demote_source = "\n".join(
        _function_source(TOKEN_CAPTURE_TIER_REPOSITORY_PATH, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "demote_hot_rows_outside_rank_set"
    )
    forbidden = (
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
    )

    assert [token for token in forbidden if token in demote_source] == []
    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "token_capture_tier_repository_rowcount_required" in repository_text
    assert "token_capture_tier_repository_rowcount_invalid" in repository_text
    assert "return _cursor_rowcount(cursor)" in demote_source


@pytest.mark.architecture
def test_token_capture_tier_upsert_changed_requires_cursor_rowcount_match() -> None:
    repository_text = TOKEN_CAPTURE_TIER_REPOSITORY_PATH.read_text(encoding="utf-8")
    tree = _parse(TOKEN_CAPTURE_TIER_REPOSITORY_PATH)
    functions = {
        node.name: _function_source(TOKEN_CAPTURE_TIER_REPOSITORY_PATH, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"upsert_tier", "_cursor_rowcount", "_single_returning_changed"}
    }
    upsert_source = functions["upsert_tier"]
    rowcount_source = functions["_cursor_rowcount"]
    changed_source = functions["_single_returning_changed"]
    forbidden = (
        "return row is not None",
        'return bool(row and row["changed"])',
        "return bool(row and row['changed'])",
        "dict(row or {})",
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
    )

    assert [token for token in forbidden if token in upsert_source] == []
    assert "cursor = self._conn.execute" in upsert_source
    assert "row = cursor.fetchone()" in upsert_source
    assert "return _single_returning_changed(cursor, row)" in upsert_source
    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "rowcount: object = cursor.rowcount" in rowcount_source
    assert "token_capture_tier_repository_rowcount_required" in rowcount_source
    assert "token_capture_tier_repository_rowcount_invalid" in rowcount_source
    assert "def _single_returning_changed(cursor: Any, row: Any | None) -> bool:" in repository_text
    assert "if count not in (0, 1):" in changed_source
    assert "if count != (1 if row is not None else 0):" in changed_source
    assert 'return row is not None and bool(row.get("changed", True))' in changed_source


@pytest.mark.architecture
def test_market_tick_current_dirty_repository_uses_connection_transaction_without_manual_commit_fallback() -> None:
    repository_text = MARKET_TICK_CURRENT_DIRTY_TARGET_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "def _run_repository_write" in repository_text
    assert "market_tick_current_dirty_target_transaction_required" in repository_text
    assert repository_text.count("_run_repository_write(self.conn, commit,") == 4
    assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_market_tick_current_dirty_completion_keys_require_claim_attempt_contract() -> None:
    repository_text = MARKET_TICK_CURRENT_DIRTY_TARGET_REPOSITORY_PATH.read_text(encoding="utf-8")
    forbidden = (
        'int(claim.get("attempt_count") or 0)',
        'claim.get("attempt_count") or 0',
    )

    assert all(token not in repository_text for token in forbidden)
    assert 'claim["attempt_count"]' in repository_text


@pytest.mark.architecture
def test_market_tick_current_dirty_completion_counts_require_real_cursor_rowcount() -> None:
    repository_text = MARKET_TICK_CURRENT_DIRTY_TARGET_REPOSITORY_PATH.read_text(encoding="utf-8")
    tree = _parse(MARKET_TICK_CURRENT_DIRTY_TARGET_REPOSITORY_PATH)
    completion_sources = "\n".join(
        _function_source(MARKET_TICK_CURRENT_DIRTY_TARGET_REPOSITORY_PATH, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in {"mark_done", "mark_error"}
    )
    forbidden = (
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
    )

    assert [token for token in forbidden if token in completion_sources] == []
    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "market_tick_current_dirty_target_rowcount_required" in repository_text
    assert "market_tick_current_dirty_target_rowcount_invalid" in repository_text
    assert completion_sources.count("return _cursor_rowcount(cursor)") == 2


@pytest.mark.architecture
def test_market_tick_current_dirty_enqueue_counts_require_real_cursor_rowcount_without_candidate_count() -> None:
    tree = _parse(MARKET_TICK_CURRENT_DIRTY_TARGET_REPOSITORY_PATH)
    enqueue_source = "\n".join(
        _function_source(MARKET_TICK_CURRENT_DIRTY_TARGET_REPOSITORY_PATH, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "enqueue_targets"
    )
    forbidden = (
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
        "return len(records)",
    )

    assert [token for token in forbidden if token in enqueue_source] == []
    assert "cursor = self.conn.execute" in enqueue_source
    assert "return _cursor_rowcount(cursor)" in enqueue_source


@pytest.mark.architecture
def test_market_tick_current_upsert_changed_requires_cursor_rowcount_match() -> None:
    repository_text = MARKET_TICK_CURRENT_REPOSITORY_PATH.read_text(encoding="utf-8")
    tree = _parse(MARKET_TICK_CURRENT_REPOSITORY_PATH)
    functions = {
        node.name: _function_source(MARKET_TICK_CURRENT_REPOSITORY_PATH, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"upsert_current_from_tick", "_cursor_rowcount", "_single_returning_changed"}
    }
    upsert_source = functions["upsert_current_from_tick"]
    rowcount_source = functions["_cursor_rowcount"]
    changed_source = functions["_single_returning_changed"]
    forbidden = (
        'return bool(row and row["changed"])',
        "return bool(row and row['changed'])",
        "return row is not None",
        'return bool(dict(row or {}).get("changed", False))',
        "dict(row or {})",
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
    )

    assert [token for token in forbidden if token in upsert_source] == []
    assert "cursor = self.conn.execute" in upsert_source
    assert "row = cursor.fetchone()" in upsert_source
    assert "return _single_returning_changed(cursor, row)" in upsert_source
    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "rowcount: object = cursor.rowcount" in rowcount_source
    assert "market_tick_current_repository_rowcount_required" in rowcount_source
    assert "market_tick_current_repository_rowcount_invalid" in rowcount_source
    assert "def _single_returning_changed(cursor: Any, row: Any | None) -> bool:" in repository_text
    assert "if count not in (0, 1):" in changed_source
    assert "if count != (1 if row is not None else 0):" in changed_source
    assert 'return row is not None and bool(row.get("changed", True))' in changed_source


@pytest.mark.architecture
def test_market_tick_fact_insert_returning_requires_cursor_rowcount_match() -> None:
    repository_text = MARKET_TICK_REPOSITORY_PATH.read_text(encoding="utf-8")
    tree = _parse(MARKET_TICK_REPOSITORY_PATH)
    functions = {
        node.name: _function_source(MARKET_TICK_REPOSITORY_PATH, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_insert_tick_returning_id", "_cursor_rowcount", "_optional_returning_id"}
    }
    insert_source = functions["_insert_tick_returning_id"]
    rowcount_source = functions["_cursor_rowcount"]
    optional_source = functions["_optional_returning_id"]
    forbidden = (
        ").fetchone()",
        "if row is None:\n            return None",
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
        "cursor.rowcount or 0",
    )

    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "market_tick_repository_rowcount_required" in rowcount_source
    assert "market_tick_repository_rowcount_invalid" in rowcount_source
    assert "def _optional_returning_id(" in repository_text
    assert [token for token in forbidden if token in insert_source] == []
    assert "cursor = self._conn.execute" in insert_source
    assert "row = cursor.fetchone()" in insert_source
    assert "_optional_returning_id(cursor, row)" in insert_source
    assert "if count not in (0, 1):" in optional_source
    assert "if count != (1 if row is not None else 0):" in optional_source


@pytest.mark.architecture
def test_asset_profile_image_refresh_dirty_completion_keys_require_claim_attempt_contract() -> None:
    repositories = {
        "token_profile_current": TOKEN_PROFILE_CURRENT_DIRTY_TARGET_REPOSITORY_PATH,
        "token_image_source": TOKEN_IMAGE_SOURCE_DIRTY_TARGET_REPOSITORY_PATH,
        "asset_profile_refresh": ASSET_PROFILE_REFRESH_TARGET_REPOSITORY_PATH,
    }
    forbidden = (
        'int(claim.get("attempt_count") or 0)',
        'claim.get("attempt_count") or 0',
    )

    violations = {
        name: [token for token in forbidden if token in path.read_text(encoding="utf-8")]
        for name, path in repositories.items()
    }

    assert violations == {name: [] for name in repositories}
    for path in repositories.values():
        assert 'claim["attempt_count"]' in path.read_text(encoding="utf-8")


@pytest.mark.architecture
def test_token_profile_current_dirty_repository_uses_connection_transaction_without_manual_commit_fallback() -> None:
    repository_text = TOKEN_PROFILE_CURRENT_DIRTY_TARGET_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "def _run_repository_write" in repository_text
    assert "token_profile_current_dirty_target_transaction_required" in repository_text
    assert repository_text.count("_run_repository_write(self.conn, commit,") == 4
    assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_token_profile_current_dirty_completion_counts_require_real_cursor_rowcount() -> None:
    repository_text = TOKEN_PROFILE_CURRENT_DIRTY_TARGET_REPOSITORY_PATH.read_text(encoding="utf-8")
    tree = _parse(TOKEN_PROFILE_CURRENT_DIRTY_TARGET_REPOSITORY_PATH)
    completion_sources = "\n".join(
        _function_source(TOKEN_PROFILE_CURRENT_DIRTY_TARGET_REPOSITORY_PATH, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in {"mark_done", "mark_error"}
    )
    forbidden = (
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
    )

    assert [token for token in forbidden if token in completion_sources] == []
    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "token_profile_current_dirty_target_rowcount_required" in repository_text
    assert "token_profile_current_dirty_target_rowcount_invalid" in repository_text
    assert completion_sources.count("return _cursor_rowcount(cursor)") == 2


@pytest.mark.architecture
def test_token_profile_current_repository_uses_connection_transaction_without_manual_commit_fallback() -> None:
    repository_text = TOKEN_PROFILE_CURRENT_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "def _transaction(conn: Any)" in repository_text
    assert "token_profile_current_repository_transaction_required" in repository_text
    assert repository_text.count("_transaction(self.conn)") == 1
    assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_token_profile_current_upsert_changed_requires_cursor_rowcount_match() -> None:
    repository_text = TOKEN_PROFILE_CURRENT_REPOSITORY_PATH.read_text(encoding="utf-8")
    repository_tree = _parse(TOKEN_PROFILE_CURRENT_REPOSITORY_PATH)
    functions = {
        node.name: _function_source(TOKEN_PROFILE_CURRENT_REPOSITORY_PATH, node)
        for node in ast.walk(repository_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"upsert_current", "_cursor_rowcount", "_single_returning_changed"}
    }
    upsert_source = functions["upsert_current"]
    forbidden = (
        'getattr(returned, "fetchone", None)',
        "changed_row = fetchone() if fetchone is not None else None",
        "return changed_row is not None",
        "return changed_row is not None and bool(changed_row.get",
    )

    assert [token for token in forbidden if token in upsert_source] == []
    assert "cursor = self.conn.execute" in upsert_source
    assert "row = cursor.fetchone()" in upsert_source
    assert "return _single_returning_changed(cursor, row)" in upsert_source
    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "token_profile_current_repository_rowcount_required" in repository_text
    assert "token_profile_current_repository_rowcount_invalid" in repository_text
    assert "def _single_returning_changed(cursor: Any, row: Any | None) -> bool:" in repository_text
    assert "if count not in (0, 1):" in functions["_single_returning_changed"]


@pytest.mark.architecture
def test_token_profile_current_repository_requires_formal_json_payload_fields_without_aliases() -> None:
    repository_text = TOKEN_PROFILE_CURRENT_REPOSITORY_PATH.read_text(encoding="utf-8")
    upsert_source = _function_source_by_name(TOKEN_PROFILE_CURRENT_REPOSITORY_PATH, "upsert_current")
    forbidden = (
        'row.get("quality_flags_json", row.get("quality_flags", []))',
        'row.get("source_payload_json", row.get("source_payload", {}))',
        'row.get("quality_flags"',
        'row.get("source_payload"',
    )

    assert "def _required_json_list(row: dict[str, Any], field: str) -> Any:" in repository_text
    assert "def _required_json_mapping(row: dict[str, Any], field: str) -> Any:" in repository_text
    assert "token_profile_current_repository_required:" in repository_text
    assert "token_profile_current_repository_invalid:" in repository_text
    assert '_required_json_list(row, "quality_flags_json")' in upsert_source
    assert '_required_json_mapping(row, "source_payload_json")' in upsert_source
    assert [token for token in forbidden if token in upsert_source] == []


@pytest.mark.architecture
def test_token_image_source_dirty_repository_uses_connection_transaction_without_manual_commit_fallback() -> None:
    repository_text = TOKEN_IMAGE_SOURCE_DIRTY_TARGET_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "def _run_repository_write" in repository_text
    assert "token_image_source_dirty_target_transaction_required" in repository_text
    assert repository_text.count("_run_repository_write(self.conn, commit,") == 4
    assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_token_image_source_dirty_completion_counts_require_real_cursor_rowcount() -> None:
    repository_text = TOKEN_IMAGE_SOURCE_DIRTY_TARGET_REPOSITORY_PATH.read_text(encoding="utf-8")
    tree = _parse(TOKEN_IMAGE_SOURCE_DIRTY_TARGET_REPOSITORY_PATH)
    completion_sources = "\n".join(
        _function_source(TOKEN_IMAGE_SOURCE_DIRTY_TARGET_REPOSITORY_PATH, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in {"mark_done", "mark_error", "_delete_claims_returning"}
    )
    functions = {
        node.name: _function_source(TOKEN_IMAGE_SOURCE_DIRTY_TARGET_REPOSITORY_PATH, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in {"mark_done", "mark_error", "_delete_claims_returning"}
    }
    forbidden = (
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
    )

    assert [token for token in forbidden if token in completion_sources] == []
    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "token_image_source_dirty_target_rowcount_required" in repository_text
    assert "token_image_source_dirty_target_rowcount_invalid" in repository_text
    assert "return _cursor_rowcount(cursor)" in functions["mark_done"]
    assert "changed += _cursor_rowcount(cursor)" in functions["mark_error"]
    assert "rowcount = _cursor_rowcount(cursor)" in functions["_delete_claims_returning"]
    assert "if rowcount != len(rows):" in functions["_delete_claims_returning"]


@pytest.mark.architecture
def test_token_image_source_dirty_target_source_watermark_has_no_runtime_fallback() -> None:
    repository_text = TOKEN_IMAGE_SOURCE_DIRTY_TARGET_REPOSITORY_PATH.read_text(encoding="utf-8")
    admission_text = TOKEN_IMAGE_SOURCE_ADMISSION_SERVICE_PATH.read_text(encoding="utf-8")
    repository_target_source = _function_source_by_name(
        TOKEN_IMAGE_SOURCE_DIRTY_TARGET_REPOSITORY_PATH,
        "_target_records",
    )
    admission_watermark_source = _function_source_by_name(
        TOKEN_IMAGE_SOURCE_ADMISSION_SERVICE_PATH,
        "_source_watermark_ms",
    )
    forbidden = (
        'target.get("source_watermark_ms") or target.get("observed_at_ms")',
        'target.get("observed_at_ms") or now_ms',
        'target.get("source_watermark_ms") or now_ms',
        'row.get("updated_at_ms")',
        "return 0",
    )

    assert "token_image_source_dirty_target_source_watermark_required" in repository_text
    assert "token_image_source_admission_source_watermark_required" in admission_text
    assert [token for token in forbidden if token in repository_target_source] == []
    assert [token for token in forbidden if token in admission_watermark_source] == []


@pytest.mark.architecture
def test_token_image_asset_repository_uses_connection_transaction_without_manual_commit_fallback() -> None:
    repository_text = TOKEN_IMAGE_ASSET_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "def _transaction(conn: Any)" in repository_text
    assert "token_image_asset_repository_transaction_required" in repository_text
    assert repository_text.count("_transaction(self.conn)") == 4
    assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_token_image_asset_lifecycle_writes_require_real_cursor_rowcount() -> None:
    repository_text = TOKEN_IMAGE_ASSET_REPOSITORY_PATH.read_text(encoding="utf-8")
    repository_tree = _parse(TOKEN_IMAGE_ASSET_REPOSITORY_PATH)
    functions = {
        node.name: _function_source(TOKEN_IMAGE_ASSET_REPOSITORY_PATH, node)
        for node in ast.walk(repository_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"upsert_pending_sources", "mark_ready", "mark_error", "mark_unsupported"}
    }
    mutation_source = "\n".join(functions.values())
    forbidden = (
        "if row is not None:\n                affected += 1",
        "affected += 1",
        "return int(rowcount)",
        'getattr(cursor, "rowcount", 0)',
    )

    assert [token for token in forbidden if token in mutation_source] == []
    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "token_image_asset_repository_rowcount_required" in repository_text
    assert "token_image_asset_repository_rowcount_invalid" in repository_text
    assert "def _single_rowcount(cursor: Any) -> int:" in repository_text
    assert "def _single_returning_rowcount(cursor: Any, row: Any | None) -> int:" in repository_text
    assert "_single_returning_rowcount(cursor, row)" in functions["upsert_pending_sources"]
    assert "_single_returning_rowcount(cursor, row)" in functions["mark_ready"]
    assert "_single_rowcount(cursor)" in functions["mark_error"]
    assert "_single_rowcount(cursor)" in functions["mark_unsupported"]


@pytest.mark.architecture
def test_identity_evidence_repository_uses_connection_transaction_without_manual_commit_fallback() -> None:
    repository_text = IDENTITY_EVIDENCE_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "def _transaction(conn: Any)" in repository_text
    assert "identity_evidence_repository_transaction_required" in repository_text
    assert repository_text.count("_transaction(self.conn)") == 3
    assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_asset_identity_current_changed_requires_cursor_rowcount_match() -> None:
    repository_text = IDENTITY_EVIDENCE_REPOSITORY_PATH.read_text(encoding="utf-8")
    tree = _parse(IDENTITY_EVIDENCE_REPOSITORY_PATH)
    functions = {
        node.name: _function_source(IDENTITY_EVIDENCE_REPOSITORY_PATH, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_upsert_current_identity", "_cursor_rowcount", "_single_returning_changed"}
    }
    upsert_source = functions["_upsert_current_identity"]
    rowcount_source = functions["_cursor_rowcount"]
    changed_source = functions["_single_returning_changed"]
    forbidden = (
        'getattr(returned, "fetchone", None)',
        "fetchone = getattr",
        "row = fetchone() if",
        "return row is not None",
        'return bool(row and row["changed"])',
        "return bool(row and row['changed'])",
        "dict(row or {})",
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
    )

    assert [token for token in forbidden if token in upsert_source] == []
    assert "cursor = self.conn.execute" in upsert_source
    assert "row = cursor.fetchone()" in upsert_source
    assert "return _single_returning_changed(cursor, row)" in upsert_source
    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "rowcount: object = cursor.rowcount" in rowcount_source
    assert "identity_evidence_repository_rowcount_required" in rowcount_source
    assert "identity_evidence_repository_rowcount_invalid" in rowcount_source
    assert "def _single_returning_changed(cursor: Any, row: Any | None) -> bool:" in repository_text
    assert "if count not in (0, 1):" in changed_source
    assert "if count != (1 if row is not None else 0):" in changed_source
    assert 'return row is not None and bool(row.get("changed", True))' in changed_source


@pytest.mark.architecture
def test_registry_repository_uses_connection_transaction_without_manual_commit_fallback() -> None:
    repository_text = REGISTRY_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "def _transaction(conn: Any)" in repository_text
    assert "registry_repository_transaction_required" in repository_text
    assert repository_text.count("_transaction(self.conn)") == 5
    assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_asset_profile_refresh_target_repository_uses_connection_transaction_without_manual_commit_fallback() -> None:
    repository_text = ASSET_PROFILE_REFRESH_TARGET_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "def _run_repository_write" in repository_text
    assert "asset_profile_refresh_target_transaction_required" in repository_text
    assert repository_text.count("_run_repository_write(self.conn, commit,") == 4
    assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_asset_profile_refresh_completion_counts_require_real_cursor_rowcount() -> None:
    repository_text = ASSET_PROFILE_REFRESH_TARGET_REPOSITORY_PATH.read_text(encoding="utf-8")
    tree = _parse(ASSET_PROFILE_REFRESH_TARGET_REPOSITORY_PATH)
    completion_sources = "\n".join(
        _function_source(ASSET_PROFILE_REFRESH_TARGET_REPOSITORY_PATH, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in {"reschedule", "mark_error"}
    )
    forbidden = (
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
    )

    assert [token for token in forbidden if token in completion_sources] == []
    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "asset_profile_refresh_target_rowcount_required" in repository_text
    assert "asset_profile_refresh_target_rowcount_invalid" in repository_text
    assert completion_sources.count("return _cursor_rowcount(cursor)") == 2


@pytest.mark.architecture
def test_asset_profile_repository_uses_connection_transaction_without_manual_commit_fallback() -> None:
    repository_text = ASSET_PROFILE_REPOSITORY_PATH.read_text(encoding="utf-8")
    service_tree = _parse(ASSET_PROFILE_REFRESH_SERVICE_PATH)
    service_write_sources = "\n".join(
        _function_source(ASSET_PROFILE_REFRESH_SERVICE_PATH, node)
        for node in ast.walk(service_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {"_write_ready_profile", "_write_missing_profile", "_write_error_profile"}
    )

    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "def _run_repository_write" in repository_text
    assert "asset_profile_repository_transaction_required" in repository_text
    assert repository_text.count("_run_repository_write(self.conn, commit,") == 2
    assert service_write_sources.count("commit=False") == 3
    assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_cex_token_profile_repository_uses_connection_transaction_without_manual_commit_fallback() -> None:
    repository_text = CEX_TOKEN_PROFILE_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "def _run_repository_write" in repository_text
    assert "cex_token_profile_repository_transaction_required" in repository_text
    assert repository_text.count("_run_repository_write(self.conn, commit,") == 1
    assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_cex_token_profile_repository_returning_write_requires_cursor_rowcount_match() -> None:
    repository_text = CEX_TOKEN_PROFILE_REPOSITORY_PATH.read_text(encoding="utf-8")
    tree = _parse(CEX_TOKEN_PROFILE_REPOSITORY_PATH)
    functions = {
        node.name: _function_source(CEX_TOKEN_PROFILE_REPOSITORY_PATH, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"upsert_ready_profile_if_token_exists", "_cursor_rowcount", "_optional_returning_row"}
    }
    source = functions["upsert_ready_profile_if_token_exists"]
    forbidden = (
        "row = self.conn.execute(",
        "return dict(row) if row else None",
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
        "cursor.rowcount or 0",
    )

    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "cex_token_profile_repository_rowcount_required" in functions["_cursor_rowcount"]
    assert "cex_token_profile_repository_rowcount_invalid" in functions["_cursor_rowcount"]
    assert "def _optional_returning_row(" in repository_text
    assert [token for token in forbidden if token in source] == []
    assert "_optional_returning_row(cursor, row)" in source
    assert "if count not in (0, 1):" in functions["_optional_returning_row"]
    assert "if count != (1 if row is not None else 0):" in functions["_optional_returning_row"]


@pytest.mark.architecture
def test_cex_token_profile_repository_requires_formal_raw_payload_without_empty_default() -> None:
    repository_text = CEX_TOKEN_PROFILE_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "raw_payload or {}",
        "raw_payload_json = Jsonb({})",
    )

    assert "def _required_raw_payload(value: Any) -> Any:" in repository_text
    assert "cex_token_profile_repository_raw_payload_required" in repository_text
    assert "cex_token_profile_repository_raw_payload_invalid" in repository_text
    assert "Jsonb(_required_raw_payload(raw_payload))" in repository_text
    assert [token for token in forbidden if token in repository_text] == []


@pytest.mark.architecture
def test_narrative_admission_dirty_repository_uses_connection_transaction_without_manual_commit_fallback() -> None:
    repository_text = NARRATIVE_ADMISSION_DIRTY_TARGET_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )

    assert "def _transaction(conn: Any)" in repository_text
    assert "narrative_admission_dirty_target_transaction_required" in repository_text
    assert repository_text.count("_transaction(self.conn)") == 5
    assert all(token not in repository_text for token in forbidden)


@pytest.mark.architecture
def test_discovery_and_narrative_dirty_completion_keys_require_claim_attempt_contract() -> None:
    repositories = {
        "discovery": DISCOVERY_REPOSITORY_PATH,
        "narrative_admission": NARRATIVE_ADMISSION_DIRTY_TARGET_REPOSITORY_PATH,
    }
    forbidden = (
        'int(claim.get("attempt_count") or 0)',
        'claim.get("attempt_count") or 0',
    )

    violations = {
        name: [token for token in forbidden if token in path.read_text(encoding="utf-8")]
        for name, path in repositories.items()
    }

    assert violations == {name: [] for name in repositories}
    for path in repositories.values():
        assert 'claim["attempt_count"]' in path.read_text(encoding="utf-8")


@pytest.mark.architecture
def test_narrative_admission_dirty_completion_counts_require_real_cursor_rowcount() -> None:
    repository_text = NARRATIVE_ADMISSION_DIRTY_TARGET_REPOSITORY_PATH.read_text(encoding="utf-8")
    forbidden = (
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
    )
    required = (
        "def _cursor_rowcount(cursor: Any) -> int:",
        "narrative_admission_dirty_target_rowcount_required",
        "narrative_admission_dirty_target_rowcount_invalid",
        "return _cursor_rowcount(cursor)",
    )

    assert [token for token in forbidden if token in repository_text] == []
    assert [token for token in required if token not in repository_text] == []


@pytest.mark.architecture
def test_event_anchor_and_resolution_refresh_workers_require_claim_attempt_contract_without_defaults() -> None:
    worker_paths = {
        "event_anchor_backfill": EVENT_ANCHOR_WORKER_PATH,
        "resolution_refresh": RESOLUTION_REFRESH_WORKER_PATH,
    }
    forbidden = (
        'int(row.get("attempt_count") or 0)',
        'row.get("attempt_count") or 0',
        'int(claim.get("attempt_count") or 0)',
        'claim.get("attempt_count") or 0',
    )

    violations = {
        name: [token for token in forbidden if token in path.read_text(encoding="utf-8")]
        for name, path in worker_paths.items()
    }

    assert violations == {name: [] for name in worker_paths}
    assert 'row["attempt_count"]' in EVENT_ANCHOR_WORKER_PATH.read_text(encoding="utf-8")
    assert 'claim["attempt_count"]' in RESOLUTION_REFRESH_WORKER_PATH.read_text(encoding="utf-8")


@pytest.mark.architecture
def test_dirty_completion_keys_require_claim_lease_owner_contract_without_defaults() -> None:
    paths = {
        "token_radar_projection": SRC / "domains/token_intel/services/token_radar_projection.py",
        "token_radar_dirty_target": SRC / "domains/token_intel/repositories/token_radar_dirty_target_repository.py",
        "token_radar_source_dirty": SRC
        / "domains/token_intel/repositories/token_radar_source_dirty_event_repository.py",
        "news_projection_dirty_target": SRC
        / "domains/news_intel/repositories/news_projection_dirty_target_repository.py",
        "market_tick_current_dirty": SRC
        / "domains/asset_market/repositories/market_tick_current_dirty_target_repository.py",
        "token_profile_current_dirty": SRC
        / "domains/asset_market/repositories/token_profile_current_dirty_target_repository.py",
        "token_image_source_dirty": SRC
        / "domains/asset_market/repositories/token_image_source_dirty_target_repository.py",
        "asset_profile_refresh": SRC / "domains/asset_market/repositories/asset_profile_refresh_target_repository.py",
        "discovery": SRC / "domains/asset_market/repositories/discovery_repository.py",
        "narrative_admission": SRC
        / "domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py",
        "pulse_trigger": SRC / "domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py",
        "event_anchor_backfill": SRC / "domains/asset_market/runtime/event_anchor_backfill_worker.py",
    }
    forbidden = (
        'str(claim.get("lease_owner") or "")',
        'str(key.get("lease_owner") or "")',
        'str(row.get("lease_owner") or "").strip()',
        '"lease_owner": str(claim.get("lease_owner") or "")',
        '"lease_owner": str(key.get("lease_owner") or "")',
    )

    violations = {
        name: [token for token in forbidden if token in path.read_text(encoding="utf-8")]
        for name, path in paths.items()
    }

    assert violations == {name: [] for name in paths}
    for name, path in paths.items():
        text = path.read_text(encoding="utf-8")
        expected_reader = 'row["lease_owner"]' if name == "event_anchor_backfill" else '["lease_owner"]'
        assert expected_reader in text


@pytest.mark.architecture
def test_dirty_completion_keys_require_claim_payload_hash_contract_without_defaults() -> None:
    paths = {
        "token_radar_projection": SRC / "domains/token_intel/services/token_radar_projection.py",
        "token_radar_dirty_target": SRC / "domains/token_intel/repositories/token_radar_dirty_target_repository.py",
        "token_radar_source_dirty": SRC
        / "domains/token_intel/repositories/token_radar_source_dirty_event_repository.py",
        "news_projection_dirty_target": SRC
        / "domains/news_intel/repositories/news_projection_dirty_target_repository.py",
        "market_tick_current_dirty": SRC
        / "domains/asset_market/repositories/market_tick_current_dirty_target_repository.py",
        "token_profile_current_dirty": SRC
        / "domains/asset_market/repositories/token_profile_current_dirty_target_repository.py",
        "token_image_source_dirty": SRC
        / "domains/asset_market/repositories/token_image_source_dirty_target_repository.py",
        "asset_profile_refresh": SRC / "domains/asset_market/repositories/asset_profile_refresh_target_repository.py",
        "discovery": SRC / "domains/asset_market/repositories/discovery_repository.py",
        "narrative_admission": SRC
        / "domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py",
        "pulse_trigger": SRC / "domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py",
    }
    forbidden = (
        'payload_hash = str(claim.get("payload_hash") or "")',
        'payload_hash = str(key.get("payload_hash") or "")',
        '"payload_hash": str(claim.get("payload_hash") or "")',
    )

    violations = {
        name: [token for token in forbidden if token in path.read_text(encoding="utf-8")]
        for name, path in paths.items()
    }

    assert violations == {name: [] for name in paths}
    for path in paths.values():
        assert '["payload_hash"]' in path.read_text(encoding="utf-8")


@pytest.mark.architecture
def test_token_image_source_dirty_completion_requires_claim_source_url_hash_without_fallback() -> None:
    repository = SRC / "domains/asset_market/repositories/token_image_source_dirty_target_repository.py"
    source = repository.read_text(encoding="utf-8")
    forbidden = (
        'claim.get("source_url_hash") or _source_url_hash',
        'claim.get("source_url") or ""',
    )

    assert [token for token in forbidden if token in source] == []
    assert 'claim["source_url_hash"]' in source


@pytest.mark.architecture
def test_discovery_terminalization_requires_deleted_source_payload_hash_without_default() -> None:
    source = DISCOVERY_REPOSITORY_PATH.read_text(encoding="utf-8")
    forbidden = (
        'payload_hash=str(row.get("payload_hash") or "")',
        'row.get("payload_hash") or ""',
    )

    assert [token for token in forbidden if token in source] == []
    assert "_terminal_source_payload_hash(row)" in source


@pytest.mark.architecture
def test_pulse_candidate_exit_suppression_requires_claim_payload_hash_without_default() -> None:
    worker = SRC / "domains/pulse_lab/runtime/pulse_candidate_worker.py"
    source = worker.read_text(encoding="utf-8")
    forbidden = (
        'str(claim.get("payload_hash") or "")',
        'claim.get("payload_hash") or ""',
    )

    assert [token for token in forbidden if token in source] == []
    assert 'claim["payload_hash"]' in source


@pytest.mark.architecture
def test_token_radar_downstream_rank_change_payload_hash_requires_row_contract_without_defaults() -> None:
    projection = SRC / "domains/token_intel/services/token_radar_projection.py"
    source = projection.read_text(encoding="utf-8")
    forbidden = (
        'str(previous.get("payload_hash") or "") == str(row.get("payload_hash") or "")',
        'previous.get("payload_hash") or ""',
        'row.get("payload_hash") or ""',
    )

    assert [token for token in forbidden if token in source] == []
    assert "_rank_change_payload_hash(previous)" in source
    assert "_rank_change_payload_hash(row)" in source


@pytest.mark.architecture
def test_token_radar_dirty_claim_completion_identity_requires_formal_fields_without_alias_fallback() -> None:
    projection = SRC / "domains/token_intel/services/token_radar_projection.py"
    dirty_targets = SRC / "domains/token_intel/repositories/token_radar_dirty_target_repository.py"
    source_dirty = SRC / "domains/token_intel/repositories/token_radar_source_dirty_event_repository.py"
    projection_source = projection.read_text(encoding="utf-8")
    dirty_target_source = dirty_targets.read_text(encoding="utf-8")
    source_dirty_source = source_dirty.read_text(encoding="utf-8")
    projection_forbidden = (
        'claim.get("target_type_key") or claim.get("target_type")',
        'claim.get("identity_id") or claim.get("target_id")',
        'claim.get("projection_version") or PROJECTION_VERSION',
        'claim.get("source_event_id") or claim.get("event_id")',
    )
    source_dirty_forbidden = (
        'key.get("projection_version") or TOKEN_RADAR_PROJECTION_VERSION',
        'key.get("source_event_id") or key.get("event_id")',
        'key.get("target_type_key") or key.get("target_type")',
        'key.get("identity_id") or key.get("target_id")',
    )

    assert [token for token in projection_forbidden if token in projection_source] == []
    assert "target_type_key, identity_id = _target_key(key)" not in dirty_target_source
    assert "_completion_target_key(key)" in dirty_target_source
    assert [token for token in source_dirty_forbidden if token in source_dirty_source] == []
    assert "_source_completion_key(key)" in source_dirty_source


@pytest.mark.architecture
def test_pulse_job_and_macro_sync_attempt_contracts_require_claim_fields_without_defaults() -> None:
    source_paths = {
        "pulse_candidate_job_service": PULSE_CANDIDATE_JOB_SERVICE_PATH,
        "pulse_decision_runtime": PULSE_DECISION_RUNTIME_SERVICE_PATH,
        "pulse_jobs_repository": PULSE_JOBS_REPOSITORY_PATH,
        "macro_sync_service": MACRO_SYNC_SERVICE_PATH,
    }
    forbidden = (
        'str(job.get("attempt_count") or 0)',
        'int(job.get("attempt_count") or 0)',
        'job.get("attempt_count") or 0',
        'int(job.get("max_attempts") or 3)',
        'job.get("max_attempts") or 3',
        'int(window.get("attempt_count") or 0)',
        'window.get("attempt_count") or 0',
        'int(window.get("max_attempts") or 1)',
        'window.get("max_attempts") or 1',
    )

    violations = {
        name: [token for token in forbidden if token in path.read_text(encoding="utf-8")]
        for name, path in source_paths.items()
    }

    assert violations == {name: [] for name in source_paths}
    for path in (
        PULSE_CANDIDATE_JOB_SERVICE_PATH,
        PULSE_DECISION_RUNTIME_SERVICE_PATH,
        PULSE_JOBS_REPOSITORY_PATH,
    ):
        assert 'job["attempt_count"]' in path.read_text(encoding="utf-8")
    assert 'window["attempt_count"]' in MACRO_SYNC_SERVICE_PATH.read_text(encoding="utf-8")


@pytest.mark.architecture
def test_narrative_repository_admission_writes_require_connection_transaction_without_manual_commit_fallback() -> None:
    repository_text = NARRATIVE_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "_commit_if_available",
        "self.conn.commit()",
        'getattr(conn, "commit", None)',
        'getattr(self.conn, "transaction", None)',
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
        'getattr(admissions, "rowcount", 0)',
        'int(getattr(admissions, "rowcount", 0) or 0)',
        "return nullcontext()",
    )
    required = (
        "def _cursor_rowcount(cursor: Any) -> int:",
        "narrative_repository_rowcount_required",
        "narrative_repository_rowcount_invalid",
        "upserted += _cursor_rowcount(cursor)",
        '"staled_admissions": _cursor_rowcount(admissions)',
    )

    assert "def _transaction(conn: Any)" in repository_text
    assert "narrative_admission_transaction_required" in repository_text
    assert repository_text.count("_transaction(self.conn)") == 2
    assert all(token not in repository_text for token in forbidden)
    assert all(token in repository_text for token in required)


@pytest.mark.architecture
@pytest.mark.parametrize(
    "contract",
    ENFORCED_RUNTIME_WORKER_CONTRACTS,
    ids=lambda contract: _rel(contract.path),
)
def test_converted_runtime_workers_do_not_call_broad_discovery_methods(
    contract: RuntimeWorkerHardCutContract,
) -> None:
    tree = _parse(contract.path)
    violations = [
        f"{_rel(contract.path)}:{node.lineno} calls broad discovery `{_call_path(node.func)}`"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_leaf(node.func) in contract.banned_calls
    ]

    assert violations == []


@pytest.mark.architecture
@pytest.mark.parametrize(
    "contract",
    ENFORCED_RUNTIME_WORKER_CONTRACTS,
    ids=lambda contract: _rel(contract.path),
)
def test_converted_runtime_workers_are_claim_first_consumers(contract: RuntimeWorkerHardCutContract) -> None:
    call_sites = _runtime_entrypoint_call_sites(contract.path)
    claim_sites = [
        site for site in call_sites if _is_control_claim_call(site.call_path, contract.control_claim_markers)
    ]
    payload_sites = [
        site
        for site in call_sites
        if any(marker in site.call_path for marker in contract.payload_loader_markers)
        and not _is_control_claim_call(site.call_path, contract.control_claim_markers)
    ]
    broad_sites = [site for site in call_sites if site.call_leaf in contract.banned_calls]

    assert claim_sites, (
        f"{_rel(contract.path)} must claim the planned dirty/control rows before loading payloads; "
        f"expected one of {contract.control_claim_markers}"
    )
    if payload_sites:
        first_claim = min(site.lineno for site in claim_sites)
        first_payload = min(site.lineno for site in payload_sites)
        assert first_claim < first_payload, (
            f"{_rel(contract.path)} loads payloads at line {first_payload} before claiming at line {first_claim}"
        )
    assert broad_sites == []


@pytest.mark.architecture
@pytest.mark.parametrize(
    "contract",
    ENFORCED_RUNTIME_WORKER_CONTRACTS,
    ids=lambda contract: _rel(contract.path),
)
def test_converted_runtime_workers_expose_idle_cost_notes(contract: RuntimeWorkerHardCutContract) -> None:
    keys = _runtime_entrypoint_dict_keys(contract.path)
    missing = [key for key in contract.notes_keys if key not in keys]

    assert missing == [], f"{_rel(contract.path)} is missing WorkerResult notes keys: {missing}"


@pytest.mark.architecture
def test_broad_discovery_calls_are_repair_only_outside_runtime_workers() -> None:
    violations: list[str] = []
    runtime_roots = sorted({contract.path.parent for contract in RUNTIME_WORKER_CONTRACTS})
    for runtime_root in runtime_roots:
        for path in runtime_root.glob("*.py"):
            if path in {contract.path for contract in RUNTIME_WORKER_CONTRACTS}:
                continue
            tree = _parse(path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = _call_leaf(node.func)
                if name not in BROAD_DISCOVERY_CALLS:
                    continue
                if _is_allowed_repair_path(path):
                    continue
                violations.append(f"{_rel(path)}:{node.lineno} contains broad discovery `{name}` outside repair")
    for path in (SRC / "app" / "runtime").rglob("*.py"):
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_leaf(node.func)
            if name not in BROAD_DISCOVERY_CALLS:
                continue
            if _is_allowed_repair_path(path):
                continue
            violations.append(f"{_rel(path)}:{node.lineno} contains broad discovery `{name}` outside repair")

    assert violations == []


@pytest.mark.architecture
@pytest.mark.parametrize("path", BOUNDED_SCHEDULER_COUNTER_PATHS, ids=lambda path: path.name)
def test_bounded_scheduler_tail_workers_expose_compact_cost_counters(path: Path) -> None:
    keys = _runtime_entrypoint_dict_keys(path)
    missing = [key for key in ("source_rows_scanned", "targets_loaded", "rows_written") if key not in keys]

    assert missing == [], f"{_rel(path)} is missing compact worker cost counters: {missing}"


@pytest.mark.architecture
def test_runtime_worker_dirty_target_repair_surface_is_removed() -> None:
    lingering_paths = [str(path.relative_to(ROOT)) for path in REMOVED_RUNTIME_REPAIR_PATHS if path.exists()]
    runtime_text = "\n".join(path.read_text(encoding="utf-8") for path in (SRC / "app").rglob("*.py"))

    assert lingering_paths == []
    assert REMOVED_RUNTIME_REPAIR_COMMAND not in runtime_text


@pytest.mark.architecture
def test_token_profile_current_requires_repository_session_source_query_contract() -> None:
    worker_text = (SRC / "domains/asset_market/runtime/token_profile_current_worker.py").read_text(encoding="utf-8")
    session_text = (SRC / "app/runtime/repository_session.py").read_text(encoding="utf-8")

    for forbidden in (
        "TokenProfileSourceQuery(repos.conn)",
        'getattr(repos, "source_query", None)',
        "getattr(repos, 'source_query', None)",
        "or TokenProfileSourceQuery(",
    ):
        assert forbidden not in worker_text
    assert "repos.source_query" in worker_text
    assert "source_query: TokenProfileSourceQuery" in session_text
    assert "source_query=TokenProfileSourceQuery(conn)" in session_text


@pytest.mark.architecture
def test_ingest_service_requires_formal_repository_session_contracts_without_constructor_fallbacks() -> None:
    bootstrap_text = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    ingest_text = INGEST_SERVICE_PATH.read_text(encoding="utf-8")

    forbidden_bootstrap_tokens = (
        'getattr(repos, "token_evidence", None)',
        'getattr(repos, "token_intents", None)',
        'getattr(repos, "intent_resolutions", None)',
        'getattr(repos, "market_ticks", None)',
        'getattr(repos, "enriched_events", None)',
        'getattr(repos, "event_anchor_jobs", None)',
        'getattr(repos, "token_radar_dirty_targets", None)',
        "token_radar_dirty_targets=",
    )
    forbidden_ingest_tokens = (
        "registry or RegistryRepository(evidence.conn)",
        "identity_evidence or IdentityEvidenceRepository(evidence.conn)",
        "token_intent_lookup or TokenIntentLookupRepository(evidence.conn)",
        "token_evidence or TokenEvidenceRepository(evidence.conn)",
        "token_intents or TokenIntentRepository(evidence.conn)",
        "intent_resolutions or IntentResolutionRepository(evidence.conn)",
        "discovery or DiscoveryRepository(evidence.conn)",
        "market_ticks or MarketTickRepository(evidence.conn)",
        "market_tick_current_dirty_targets or MarketTickCurrentDirtyTargetRepository(evidence.conn)",
        "enriched_events or EnrichedEventRepository(evidence.conn)",
        "event_anchor_jobs or EventAnchorBackfillJobRepository(evidence.conn)",
        "token_radar_source_dirty_events or TokenRadarSourceDirtyEventRepository(",
        "token_radar_dirty_targets",
    )

    assert "discovery=repos.discovery" in bootstrap_text
    assert "token_radar_source_dirty_events=repos.token_radar_source_dirty_events" in bootstrap_text
    assert all(token not in bootstrap_text for token in forbidden_bootstrap_tokens)
    assert all(token not in ingest_text for token in forbidden_ingest_tokens)


@pytest.mark.architecture
def test_repair_service_broad_scans_enqueue_control_rows_only() -> None:
    repair_paths = sorted(
        path
        for path in SRC.rglob("*.py")
        if _is_allowed_repair_path(path)
        and any(call in path.read_text(encoding="utf-8") for call in BROAD_DISCOVERY_CALLS)
    )
    violations: list[str] = []
    for path in repair_paths:
        text = path.read_text(encoding="utf-8")
        if not any(table in text for table in CONTROL_PLANE_TABLES):
            violations.append(f"{_rel(path)} contains broad discovery but no known control-plane enqueue")
        violations.extend(
            f"{_rel(path)} writes business/read-model table {table}"
            for table in BUSINESS_OUTPUT_TABLES
            if _write_pattern(table).search(text)
        )

    assert violations == []


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _function_source(path: Path, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    end_lineno = node.end_lineno or node.lineno
    return "\n".join(lines[node.lineno - 1 : end_lineno])


def _function_source_by_name(path: Path, name: str) -> str:
    for node in ast.walk(_parse(path)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return _function_source(path, node)
    raise AssertionError(f"{path} has no function {name}")


@dataclass(frozen=True)
class CallSite:
    lineno: int
    call_path: str
    call_leaf: str


def _call_sites(path: Path) -> list[CallSite]:
    return sorted(
        (
            CallSite(lineno=node.lineno, call_path=_call_path(node.func), call_leaf=_call_leaf(node.func))
            for node in ast.walk(_parse(path))
            if isinstance(node, ast.Call)
        ),
        key=lambda site: site.lineno,
    )


RUNTIME_ENTRYPOINT_NAMES = frozenset(
    {
        "run_once",
        "run_once_sync",
        "run_once_async",
        "_process_dirty_targets_sync",
        "_project_once",
        "_active_targets",
        "_run_cycle",
        "scan_triggers_once",
        "_claim_due_rows_sync",
        "_due_targets_sync",
        "rebuild_once",
        "_rebuild_once",
        "_mirror_once",
        "_refresh_source_once",
        "refresh_once",
        "process_once",
        "process_due_jobs_once_async",
        "_claim_next_job_sync",
        "rebuild_token_profile_current_once",
    }
)


def _runtime_entrypoint_call_sites(path: Path) -> list[CallSite]:
    sites: list[CallSite] = []
    for node in ast.walk(_parse(path)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name not in RUNTIME_ENTRYPOINT_NAMES:
            continue
        sites.extend(
            CallSite(
                lineno=child.lineno,
                call_path=_call_path(child.func),
                call_leaf=_call_leaf(child.func),
            )
            for child in ast.walk(node)
            if isinstance(child, ast.Call)
        )
    return sorted(sites, key=lambda site: site.lineno)


def _runtime_entrypoint_dict_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for node in ast.walk(_parse(path)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name not in RUNTIME_ENTRYPOINT_NAMES:
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Dict):
                continue
            for key in child.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
    return keys


def _is_control_claim_call(call_path: str, markers: tuple[str, ...]) -> bool:
    if not any(marker in call_path for marker in markers):
        return False
    leaf = call_path.rsplit(".", 1)[-1]
    return leaf in {"claim_due", "live_target_rows"} or leaf.startswith("claim_") or ".claim_due" in call_path


def _is_allowed_repair_path(path: Path) -> bool:
    rel = path.relative_to(SRC).as_posix()
    return bool(re.search(r"/services/[^/]*repair[^/]*\.py$", f"/{rel}"))


def _looks_like_provider_or_agent_call(call_path: str) -> bool:
    lowered = call_path.lower()
    if "pending_agent_job_count" in lowered:
        return False
    if "agent" in lowered:
        return True
    provider_tokens = ("provider", "client", "gateway", "adapter")
    return any(token in lowered for token in provider_tokens)


def _write_pattern(table_name: str) -> re.Pattern[str]:
    return re.compile(rf"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+{re.escape(table_name)}\b", re.IGNORECASE)


def _call_leaf(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _call_path(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_path(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _call_path(node.func)
    return ""


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def test_macro_asset_correlation_builder_requires_explicit_window_without_60d_default() -> None:
    service_source = (SRC / "domains/macro_intel/services/macro_asset_correlation.py").read_text(encoding="utf-8")
    route_source = (SRC / "app/surfaces/api/routes_macro.py").read_text(encoding="utf-8")

    assert 'window: str = "60d"' not in service_source
    assert "window: str," in service_source
    assert 'request.query_params.get("window") or "60d"' in route_source
    assert "window=window" in route_source


def test_dirty_claim_window_scope_dimensions_are_formal_worker_contracts() -> None:
    pulse_source = (SRC / "domains/pulse_lab/runtime/pulse_candidate_worker.py").read_text(encoding="utf-8")
    narrative_source = (SRC / "domains/narrative_intel/runtime/narrative_admission_worker.py").read_text(
        encoding="utf-8"
    )

    assert "_required_configured_claim_dimension(" in pulse_source
    assert 'field="window"' in pulse_source
    assert 'field="scope"' in pulse_source
    assert 'error_prefix="pulse_trigger_dirty_target"' in pulse_source
    assert "narrative_admission_dirty_target_invalid_window" in narrative_source
    assert '_required_claim_member(claim, "window", self.windows)' in narrative_source
    assert '_required_claim_member(claim, "scope", self.scopes)' in narrative_source
    assert ".get(window, 86_400_000)" not in narrative_source
    assert 'watched_only=scope == "matched"' not in pulse_source
    assert 'watched_only=scope == "matched"' not in narrative_source
    assert "PULSE_SCOPE_WATCHED_ONLY[scope]" in pulse_source
    assert "NARRATIVE_SCOPE_WATCHED_ONLY[scope]" in narrative_source
    assert "NARRATIVE_WINDOW_MS_BY_KEY[window]" in narrative_source


@pytest.mark.architecture
def test_discovery_repository_lookup_write_counts_require_real_cursor_rowcount() -> None:
    repository_text = DISCOVERY_REPOSITORY_PATH.read_text(encoding="utf-8")
    repository_tree = _parse(DISCOVERY_REPOSITORY_PATH)
    write_sources = "\n".join(
        _function_source(DISCOVERY_REPOSITORY_PATH, node)
        for node in ast.walk(repository_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"enqueue_lookup_keys", "mark_lookup_done", "reschedule_lookup_claims"}
    )
    forbidden = (
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
    )

    assert [token for token in forbidden if token in write_sources] == []
    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "discovery_repository_rowcount_required" in repository_text
    assert "discovery_repository_rowcount_invalid" in repository_text
    assert write_sources.count("return _cursor_rowcount(cursor)") == 3


@pytest.mark.architecture
def test_discovery_terminal_returning_counts_require_cursor_rowcount_match() -> None:
    repository_text = DISCOVERY_REPOSITORY_PATH.read_text(encoding="utf-8")
    repository_tree = _parse(DISCOVERY_REPOSITORY_PATH)
    functions = {
        node.name: _function_source(DISCOVERY_REPOSITORY_PATH, node)
        for node in ast.walk(repository_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"terminalize_lookup_claims", "_delete_lookup_claims_returning", "_returned_rowcount"}
    }
    terminalize_source = functions["terminalize_lookup_claims"]
    delete_source = functions["_delete_lookup_claims_returning"]
    helper_source = functions["_returned_rowcount"]
    forbidden = (
        "len(deleted_rows) != len(records)",
        '"deleted": len(deleted_rows)',
        "deleted_count = len(deleted_rows)",
    )

    assert [token for token in forbidden if token in terminalize_source + delete_source] == []
    assert "def _returned_rowcount(cursor: Any, rows: list[Any]) -> int:" in repository_text
    assert "count = _cursor_rowcount(cursor)" in helper_source
    assert "if count != len(rows):" in helper_source
    assert "discovery_repository_rowcount_invalid" in helper_source
    assert "cursor = self.conn.execute" in delete_source
    assert "rows = cursor.fetchall()" in delete_source
    assert "deleted_count = _returned_rowcount(cursor, rows)" in delete_source
    assert "return [dict(row) for row in rows], deleted_count" in delete_source
    assert "deleted_rows, deleted_count = self._delete_lookup_claims_returning(records)" in terminalize_source
    assert '"deleted": deleted_count' in terminalize_source


@pytest.mark.architecture
def test_discovery_repository_claim_due_requires_returning_rowcount_match() -> None:
    repository_text = DISCOVERY_REPOSITORY_PATH.read_text(encoding="utf-8")
    claim_source = _function_source_by_name(DISCOVERY_REPOSITORY_PATH, "claim_due_lookup_keys")
    forbidden = (
        ").fetchall()",
        "return len(rows)",
        "cursor.rowcount or 0",
        'getattr(cursor, "rowcount", 0)',
    )

    assert [token for token in forbidden if token in claim_source] == []
    assert "def _returned_rowcount(cursor: Any, rows: list[Any]) -> int:" in repository_text
    assert "cursor = self.conn.execute" in claim_source
    assert "rows = cursor.fetchall()" in claim_source
    assert "_returned_rowcount(cursor, rows)" in claim_source
    assert "return [dict(row) for row in rows]" in claim_source
    assert claim_source.index("_returned_rowcount(cursor, rows)") < claim_source.index(
        "return [dict(row) for row in rows]"
    )


@pytest.mark.architecture
def test_discovery_repository_result_writes_require_rowcount_without_readback_fallback() -> None:
    repository_text = DISCOVERY_REPOSITORY_PATH.read_text(encoding="utf-8")
    start_source = _function_source_by_name(DISCOVERY_REPOSITORY_PATH, "start_lookup")
    finish_source = _function_source_by_name(DISCOVERY_REPOSITORY_PATH, "finish_lookup")
    fail_source = _function_source_by_name(DISCOVERY_REPOSITORY_PATH, "fail_lookup")
    result_write_sources = start_source + finish_source + fail_source
    forbidden = (
        "return self.result(provider=provider, lookup_key=lookup_key) or {}",
        "cursor.rowcount or 0",
        'getattr(cursor, "rowcount", 0)',
    )

    assert [token for token in forbidden if token in result_write_sources] == []
    assert "def _required_single_rowcount(cursor: Any) -> int:" in repository_text
    assert "def _required_returning_row(cursor: Any, row: Any) -> dict[str, Any]:" in repository_text
    assert "RETURNING *" in start_source
    assert "_required_returning_row(cursor, row)" in start_source
    assert "_required_single_rowcount(cursor)" in finish_source
    assert "RETURNING *" in fail_source
    assert "_required_returning_row(cursor, row)" in fail_source


@pytest.mark.architecture
def test_enriched_event_repository_lifecycle_write_counts_require_real_cursor_rowcount() -> None:
    repository_path = SRC / "domains/asset_market/repositories/enriched_event_repository.py"
    repository_text = repository_path.read_text(encoding="utf-8")
    repository_tree = _parse(repository_path)
    lifecycle_sources = "\n".join(
        _function_source(repository_path, node)
        for node in ast.walk(repository_tree)
        if isinstance(node, ast.FunctionDef) and node.name in {"attach_backfill_capture", "mark_backfill_terminal"}
    )
    forbidden = (
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
    )

    assert [token for token in forbidden if token in lifecycle_sources] == []
    assert "def _single_row_mutation_applied(cursor: Any) -> bool:" in repository_text
    assert "enriched_event_repository_rowcount_required" in repository_text
    assert "enriched_event_repository_rowcount_invalid" in repository_text
    assert lifecycle_sources.count("return _single_row_mutation_applied(cursor)") == 2


@pytest.mark.architecture
def test_event_anchor_job_returning_writes_require_cursor_rowcount_match() -> None:
    repository_text = EVENT_ANCHOR_JOB_REPOSITORY_PATH.read_text(encoding="utf-8")
    repository_tree = _parse(EVENT_ANCHOR_JOB_REPOSITORY_PATH)
    functions = {
        node.name: _function_source(EVENT_ANCHOR_JOB_REPOSITORY_PATH, node)
        for node in ast.walk(repository_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name
        in {
            "claim_due",
            "mark_done",
            "mark_terminal",
            "retry_terminal_job_from_snapshot",
            "reconcile_ready_historical_jobs",
            "_terminalize_expired_jobs",
            "_reschedule_stale_running_jobs",
            "_fail_exhausted_stale_running_jobs",
            "reschedule",
            "_returned_rowcount",
            "_single_returning_rowcount",
            "_returning_rows",
        }
    }
    returning_function_names = (
        "claim_due",
        "mark_done",
        "mark_terminal",
        "retry_terminal_job_from_snapshot",
        "reconcile_ready_historical_jobs",
        "_terminalize_expired_jobs",
        "_reschedule_stale_running_jobs",
        "_fail_exhausted_stale_running_jobs",
        "reschedule",
    )
    returning_sources = "\n".join(functions[name] for name in returning_function_names)
    forbidden = (
        "return row is not None",
        "if row is None:\n                return False",
        '"updated_count": len(updated_rows)',
    )

    assert [token for token in forbidden if token in returning_sources] == []
    assert "def _cursor_rowcount(cursor: Any) -> int:" in repository_text
    assert "event_anchor_job_repository_rowcount_required" in repository_text
    assert "event_anchor_job_repository_rowcount_invalid" in repository_text
    assert "def _returned_rowcount(cursor: Any, rows: list[Any]) -> int:" in repository_text
    assert "def _single_returning_rowcount(cursor: Any, row: Any | None) -> int:" in repository_text
    assert "def _returning_rows(cursor: Any) -> list[dict[str, Any]]:" in repository_text
    assert returning_sources.count("_single_returning_rowcount(cursor, row)") == 4
    assert returning_sources.count("_returning_rows(cursor)") == 5
    assert "if count != len(rows):" in functions["_returned_rowcount"]
