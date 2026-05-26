from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from gmgn_twitter_intel.app.runtime.worker_manifest import worker_class_by_name

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"


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
        path=SRC / "domains/narrative_intel/runtime/mention_semantics_worker.py",
        banned_calls=(
            "_enqueue_missing_from_admissions_sync",
            "_missing_source_rows_for_semantics",
            "due_admissions_for_semantics",
            "missing_source_rows_for_mention_semantics",
        ),
        control_claim_markers=("claim_due_mention_semantics",),
    ),
    RuntimeWorkerHardCutContract(
        path=SRC / "domains/narrative_intel/runtime/token_discussion_digest_worker.py",
        banned_calls=("due_digest_targets",),
        control_claim_markers=("discussion_digest_dirty_targets.claim_due",),
    ),
    RuntimeWorkerHardCutContract(
        path=SRC / "domains/asset_market/runtime/token_profile_current_worker.py",
        banned_calls=("recent_profile_targets",),
        control_claim_markers=("token_profile_current_dirty_targets.claim_due",),
    ),
    RuntimeWorkerHardCutContract(
        path=SRC / "domains/asset_market/runtime/token_image_mirror_worker.py",
        banned_calls=("candidate_sources",),
        control_claim_markers=("token_image_source_dirty_targets.claim_due", "token_image_assets.claim_due_sources"),
    ),
    RuntimeWorkerHardCutContract(
        path=SRC / "domains/asset_market/runtime/asset_profile_refresh_worker.py",
        banned_calls=("select_due_asset_profile_rows",),
        control_claim_markers=("asset_profile_refresh_targets.claim_due",),
    ),
    RuntimeWorkerHardCutContract(
        path=SRC / "domains/asset_market/runtime/token_capture_tier_worker.py",
        banned_calls=("active_live_market_targets", "demote_absent_hot_rows"),
        control_claim_markers=(
            "token_capture_tier_dirty_targets.claim_due",
            "live_market_target_set_dirty_targets.claim_due",
        ),
    ),
    RuntimeWorkerHardCutContract(
        path=SRC / "domains/asset_market/runtime/live_price_gateway.py",
        banned_calls=("active_live_market_targets",),
        control_claim_markers=("token_capture_tiers.live_target_rows",),
        payload_loader_markers=(),
    ),
    RuntimeWorkerHardCutContract(
        path=SRC / "domains/watchlist_intel/runtime/handle_summary_worker.py",
        banned_calls=("handles_missing_summary_jobs", "reconcile_missing_jobs_once"),
        control_claim_markers=("claim_next_summary_job",),
    ),
)
ENFORCED_RUNTIME_WORKER_CONTRACTS = (
    RUNTIME_WORKER_CONTRACTS[0],
    RUNTIME_WORKER_CONTRACTS[1],
    RUNTIME_WORKER_CONTRACTS[2],
    RUNTIME_WORKER_CONTRACTS[3],
    RUNTIME_WORKER_CONTRACTS[4],
    RUNTIME_WORKER_CONTRACTS[5],
    RUNTIME_WORKER_CONTRACTS[6],
    RUNTIME_WORKER_CONTRACTS[7],
    RUNTIME_WORKER_CONTRACTS[8],
    RUNTIME_WORKER_CONTRACTS[9],
)

WORKER_CLASSIFICATION: dict[str, str] = {
    "collector": "bounded_provider_scheduler",
    "token_capture_tier": "dirty_target_consumer",
    "market_tick_stream": "bounded_provider_scheduler",
    "market_tick_poll": "bounded_provider_scheduler",
    "market_tick_current_projection": "dirty_target_consumer",
    "event_anchor_backfill": "leased_job_consumer",
    "live_price_gateway": "target_scoped_expansion",
    "resolution_refresh": "target_scoped_expansion",
    "asset_profile_refresh": "dirty_target_consumer",
    "token_image_mirror": "dirty_target_consumer",
    "token_profile_current": "dirty_target_consumer",
    "token_radar_projection": "dirty_target_consumer",
    "narrative_admission": "dirty_target_consumer",
    "mention_semantics": "leased_job_consumer",
    "token_discussion_digest": "dirty_target_consumer",
    "news_fetch": "bounded_provider_scheduler",
    "news_item_process": "target_scoped_expansion",
    "news_story_projection": "dirty_target_consumer",
    "news_item_brief": "dirty_target_consumer",
    "news_page_projection": "dirty_target_consumer",
    "news_source_quality_projection": "dirty_target_consumer",
    "equity_event_source_reconcile": "bounded_provider_scheduler",
    "equity_event_fetch": "bounded_provider_scheduler",
    "equity_event_process": "target_scoped_expansion",
    "equity_event_story_projection": "dirty_target_consumer",
    "equity_event_brief": "dirty_target_consumer",
    "equity_event_page_projection": "dirty_target_consumer",
    "cex_oi_radar_board": "bounded_provider_scheduler",
    "macro_view_projection": "bounded_provider_scheduler",
    "pulse_candidate": "dirty_target_consumer",
    "enrichment": "leased_job_consumer",
    "handle_summary": "leased_job_consumer",
    "notification_rule": "target_scoped_expansion",
    "notification_delivery": "leased_job_consumer",
}
VALID_WORKER_CLASSIFICATIONS = frozenset(
    {
        "dirty_target_consumer",
        "leased_job_consumer",
        "bounded_provider_scheduler",
        "target_scoped_expansion",
        "candidate_for_hard_cut",
    }
)

BROAD_DISCOVERY_CALLS = frozenset(
    call for contract in RUNTIME_WORKER_CONTRACTS for call in contract.banned_calls
)

CONTROL_PLANE_TABLES = frozenset(
    {
        "pulse_trigger_dirty_targets",
        "narrative_admission_dirty_targets",
        "discussion_digest_dirty_targets",
        "token_profile_current_dirty_targets",
        "token_image_source_dirty_targets",
        "asset_profile_refresh_targets",
        "token_capture_tier_dirty_targets",
        "live_market_target_set_dirty_targets",
        "watchlist_handle_summary_jobs",
    }
)

BUSINESS_OUTPUT_TABLES = frozenset(
    {
        "pulse_candidates",
        "pulse_agent_runs",
        "pulse_agent_run_steps",
        "narrative_admissions",
        "token_mention_semantics",
        "token_discussion_digests",
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

BOUNDED_SCHEDULER_COUNTER_PATHS = (
    SRC / "domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py",
    SRC / "domains/macro_intel/runtime/macro_view_projection_worker.py",
)

REPAIR_HANDLER_PATHS = {
    SRC / "app/runtime/runtime_worker_dirty_targets.py",
}
REPAIR_HANDLER_COMMAND = "enqueue-runtime-worker-dirty-targets"


@pytest.mark.architecture
def test_every_registered_worker_has_runtime_constraint_classification() -> None:
    manifest_workers = set(worker_class_by_name())
    missing = sorted(manifest_workers - set(WORKER_CLASSIFICATION))
    extra = sorted(set(WORKER_CLASSIFICATION) - manifest_workers)
    invalid = {
        worker: classification
        for worker, classification in WORKER_CLASSIFICATION.items()
        if classification not in VALID_WORKER_CLASSIFICATIONS
    }

    assert missing == []
    assert extra == []
    assert invalid == {}


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
    missing = [
        key
        for key in ("source_rows_scanned", "targets_loaded", "rows_written")
        if key not in keys
    ]

    assert missing == [], f"{_rel(path)} is missing compact worker cost counters: {missing}"


@pytest.mark.architecture
def test_runtime_worker_dirty_target_repair_is_enqueue_only_when_present() -> None:
    repair_paths = sorted(path for path in REPAIR_HANDLER_PATHS if path.exists())
    if not repair_paths:
        pytest.skip("enqueue-runtime-worker-dirty-targets repair handler has not landed yet")

    violations: list[str] = []
    for path in repair_paths:
        text = path.read_text(encoding="utf-8")
        tree = _parse(path)
        if REPAIR_HANDLER_COMMAND not in text:
            violations.append(f"{_rel(path)} does not expose {REPAIR_HANDLER_COMMAND}")
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            call_path = _call_path(call.func)
            call_leaf = _call_leaf(call.func)
            if call_leaf == "run_once":
                violations.append(f"{_rel(path)}:{call.lineno} calls worker run_once()")
            if _looks_like_provider_or_agent_call(call_path):
                violations.append(f"{_rel(path)}:{call.lineno} calls provider/agent path `{call_path}`")
        violations.extend(
            f"{_rel(path)} writes business/read-model table {table}"
            for table in BUSINESS_OUTPUT_TABLES
            if _write_pattern(table).search(text)
        )
        if not any(table in text for table in CONTROL_PLANE_TABLES):
            violations.append(f"{_rel(path)} does not enqueue a known runtime control-plane table")

    assert violations == []


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
    return path in REPAIR_HANDLER_PATHS or bool(re.search(r"/services/[^/]*repair[^/]*\.py$", f"/{rel}"))


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
