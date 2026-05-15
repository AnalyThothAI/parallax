from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"
DOCS_WORKERS = ROOT / "docs" / "WORKERS.md"

EXPECTED_WORKERS = {
    "collector": "gmgn_twitter_intel.domains.ingestion.runtime.collector_service.CollectorService",
    "anchor_price": "gmgn_twitter_intel.domains.asset_market.runtime.anchor_price_worker.AnchorPriceWorker",
    "live_price_gateway": "gmgn_twitter_intel.domains.asset_market.runtime.live_price_gateway.LivePriceGateway",
    "resolution_refresh": (
        "gmgn_twitter_intel.domains.asset_market.runtime.resolution_refresh_worker.ResolutionRefreshWorker"
    ),
    "asset_profile_refresh": (
        "gmgn_twitter_intel.domains.asset_market.runtime.asset_profile_refresh_worker.AssetProfileRefreshWorker"
    ),
    "token_radar_projection": (
        "gmgn_twitter_intel.domains.token_intel.runtime.token_radar_projection_worker.TokenRadarProjectionWorker"
    ),
    "pulse_candidate": "gmgn_twitter_intel.domains.pulse_lab.runtime.pulse_candidate_worker.PulseCandidateWorker",
    "enrichment": "gmgn_twitter_intel.domains.social_enrichment.runtime.enrichment_worker.EnrichmentWorker",
    "handle_summary": "gmgn_twitter_intel.domains.watchlist_intel.runtime.handle_summary_worker.HandleSummaryWorker",
    "harness_ops": "gmgn_twitter_intel.domains.closed_loop_harness.runtime.harness_ops_worker.HarnessOpsWorker",
    "notification_rule": "gmgn_twitter_intel.domains.notifications.runtime.notification_worker.NotificationWorker",
    "notification_delivery": (
        "gmgn_twitter_intel.domains.notifications.runtime.notification_delivery.NotificationDeliveryWorker"
    ),
}

OLD_READYZ_WORKER_KEYS = {
    "collector",
    "anchor_price",
    "live_price_gateway",
    "resolution_refresh",
    "asset_profile_refresh",
    "token_radar_projection",
    "pulse_candidate",
    "enrichment",
    "handle_summary",
    "harness_ops",
    "notification_rule",
    "notification_delivery",
}

OLD_RUNTIME_SETTINGS = {
    "enrichment_poll_interval_seconds",
    "enrichment_batch_size",
    "pulse_agent_batch_size",
    "pulse_agent_interval_seconds",
    "watchlist_handle_summary_poll_interval_seconds",
    "notification_worker_interval_seconds",
    "notification_delivery_interval_seconds",
    "anchor_price_interval_seconds",
    "resolution_refresh_interval_seconds",
    "asset_profile_refresh_interval_seconds",
    "cex_sync_interval_seconds",
    "dex_sync_interval_seconds",
    "dex_price_hot_stale_seconds",
    "dex_price_warm_stale_seconds",
    "dex_price_refresh_limit",
}

DB_SESSION_HELPERS = {"worker_session", "_repository_session"}
EXTERNAL_IO_TOKENS = {
    "adapter",
    "client",
    "hub",
    "market",
    "publisher",
    "wake",
    "wake_bus",
    "wake_waiter",
}
GLOBAL_SETTER_NAMES = {
    "basicConfig",
    "set_default_openai_api",
    "set_default_openai_client",
    "set_default_openai_key",
    "set_tracer_provider",
    "set_tracing_export_api_key",
}
PROCESS_GLOBAL_SETTER_ALLOWLIST = {
    SRC / "app/runtime/bootstrap.py",
    SRC / "app/runtime/llm_gateway.py",
}
TOKEN_RADAR_WRITE_OWNER_ALLOWLIST = {
    SRC / "domains/token_intel/services/token_radar_projection.py",
    SRC / "domains/token_intel/runtime/token_radar_projection_worker.py",
    SRC / "domains/token_intel/repositories/token_radar_repository.py",
}


@pytest.mark.architecture
@pytest.mark.parametrize(("worker_key", "qualified_name"), EXPECTED_WORKERS.items())
def test_all_long_running_workers_inherit_worker_base(worker_key: str, qualified_name: str) -> None:
    worker_class = _import_qualified_name(qualified_name)

    assert issubclass(worker_class, WorkerBase), f"{worker_key} must inherit WorkerBase"


@pytest.mark.architecture
def test_worker_registry_matches_workers_yaml_schema() -> None:
    from gmgn_twitter_intel.app.runtime import bootstrap
    from gmgn_twitter_intel.app.runtime.worker_registry import CANONICAL_WORKER_CLASSES, CANONICAL_WORKER_NAMES
    from gmgn_twitter_intel.app.runtime.worker_scheduler import _START_PRIORITY
    from gmgn_twitter_intel.platform.config.settings import WorkersSettings

    expected_keys = set(EXPECTED_WORKERS)
    settings_keys = set(WorkersSettings.model_fields) - {"defaults"}
    docs_keys = _worker_inventory_keys()

    assert CANONICAL_WORKER_CLASSES == EXPECTED_WORKERS
    assert set(CANONICAL_WORKER_NAMES) == expected_keys
    assert set(bootstrap.CANONICAL_WORKER_NAMES) == expected_keys
    assert set(_START_PRIORITY) == expected_keys
    assert settings_keys == expected_keys
    assert docs_keys == expected_keys


@pytest.mark.architecture
def test_no_external_io_inside_db_session() -> None:
    violations: list[str] = []
    for path in _worker_runtime_paths():
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.With, ast.AsyncWith)) and _opens_db_session(node):
                for inner in _descendants_excluding_nested_sessions(node):
                    if isinstance(inner, ast.Await):
                        violations.append(f"{_rel(path)}:{inner.lineno} await inside DB worker session")
                    if isinstance(inner, ast.Call) and _is_external_io_call(inner):
                        violations.append(f"{_rel(path)}:{inner.lineno} external IO call `{_call_path(inner.func)}`")

    assert violations == []


@pytest.mark.architecture
def test_workers_do_not_call_repository_session_or_raw_pool() -> None:
    violations: list[str] = []
    for path in _worker_runtime_paths():
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "repository_session":
                violations.append(f"{_rel(path)}:{node.lineno} calls repository_session() directly")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "connection":
                violations.append(f"{_rel(path)}:{node.lineno} opens a raw pool connection")

    assert violations == []


@pytest.mark.architecture
def test_process_global_setters_only_in_bootstrap() -> None:
    violations: list[str] = []
    for path in _runtime_provider_openai_paths():
        if path in PROCESS_GLOBAL_SETTER_ALLOWLIST:
            continue
        violations.extend(
            f"{_rel(path)}:{node.lineno} calls process-global setter `{_call_path(node.func)}`"
            for node in ast.walk(_parse(path))
            if isinstance(node, ast.Call) and _call_leaf(node.func) in GLOBAL_SETTER_NAMES
        )

    assert violations == []


@pytest.mark.architecture
def test_no_old_readyz_worker_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    from gmgn_twitter_intel.app.runtime import app as app_module
    from gmgn_twitter_intel.app.surfaces.api.schemas import StatusData

    top_level_schema_keys = set(StatusData.model_fields)
    runtime = SimpleNamespace(
        collector=SimpleNamespace(
            status=SimpleNamespace(
                to_dict=lambda: {
                    "started_at_ms": 1_700_000_000_000,
                    "frames_received": 0,
                    "twitter_events": 0,
                    "matched_twitter_events": 0,
                    "events_published": 0,
                    "duplicate_twitter_events": 0,
                    "duplicate_matched_twitter_events": 0,
                    "parse_errors": 0,
                    "snapshot_gate_outcomes": {"debounced_complete": 1},
                }
            ),
            upstream_client=None,
        ),
        db=SimpleNamespace(),
        providers=SimpleNamespace(asset_market=SimpleNamespace(stream_dex_market=None)),
        scheduler=SimpleNamespace(
            status_payload=lambda: {"collector": {"enabled": False, "running": False}},
            unhealthy_reasons=lambda: [],
        ),
        settings=SimpleNamespace(handles=("toly",)),
    )
    monkeypatch.setattr(app_module, "_db_status", lambda _runtime: {"ok": True})
    payload, status_code = app_module._readiness_payload(runtime)

    assert top_level_schema_keys.isdisjoint(OLD_READYZ_WORKER_KEYS)
    assert "workers" in top_level_schema_keys
    assert status_code == 200
    assert set(payload).isdisjoint(OLD_READYZ_WORKER_KEYS)
    collector = payload["workers"]["collector"]
    assert collector["enabled"] is False
    assert collector["running"] is False
    assert collector["details"]["frames_received"] == 0
    assert collector["details"]["matched_twitter_events"] == 0
    assert collector["details"]["snapshot_gate_outcomes"] == {"debounced_complete": 1}
    assert payload["snapshot_gate"] == {"debounced_complete": 1}


@pytest.mark.architecture
def test_no_old_worker_runtime_settings() -> None:
    from gmgn_twitter_intel.platform.config.settings import (
        CollectorConfig,
        LlmConfig,
        NotificationsConfig,
        OkxProviderConfig,
        Settings,
        WorkersSettings,
    )

    checked_models = (CollectorConfig, LlmConfig, NotificationsConfig, OkxProviderConfig, Settings)
    violations = {
        f"{model.__name__}.{field_name}"
        for model in checked_models
        for field_name in model.model_fields
        if field_name in OLD_RUNTIME_SETTINGS
    }
    worker_fields = set(WorkersSettings.model_fields) - {"defaults"}

    assert violations == set()
    assert worker_fields == set(EXPECTED_WORKERS)


@pytest.mark.architecture
def test_wake_bus_is_emit_only() -> None:
    from gmgn_twitter_intel.app.runtime import wake_bus

    text = (SRC / "app/runtime/wake_bus.py").read_text(encoding="utf-8")

    assert not hasattr(wake_bus, "WakeListener")
    assert "LISTEN" not in text


@pytest.mark.architecture
def test_read_model_single_writers() -> None:
    write_pattern = re.compile(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+token_radar_rows\b", re.IGNORECASE)
    violations = [
        f"{_rel(path)} writes token_radar_rows"
        for path in SRC.rglob("*.py")
        if path not in TOKEN_RADAR_WRITE_OWNER_ALLOWLIST
        and "alembic/versions" not in path.as_posix()
        and write_pattern.search(path.read_text())
    ]

    assert violations == []


def _import_qualified_name(qualified_name: str) -> Any:
    module_name, _, attr_name = qualified_name.rpartition(".")
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def _worker_inventory_keys() -> set[str]:
    marker = re.search(r"<!--\s*worker-inventory-keys:\s*(.*?)\s*-->", DOCS_WORKERS.read_text(), re.DOTALL)
    if marker is None:
        return set()
    return {key.strip() for key in marker.group(1).replace("\n", " ").split(",") if key.strip()}


def _worker_runtime_paths() -> list[Path]:
    return sorted(Path(_module_file(qualified_name)) for qualified_name in EXPECTED_WORKERS.values())


def _runtime_provider_openai_paths() -> list[Path]:
    return sorted(
        path
        for path in SRC.rglob("*.py")
        if "/runtime/" in path.as_posix() or "/providers" in path.as_posix() or "/openai_" in path.as_posix()
    )


def _module_file(qualified_name: str) -> str:
    module_name, _, _ = qualified_name.rpartition(".")
    module = importlib.import_module(module_name)
    module_file = getattr(module, "__file__", None)
    assert module_file is not None
    return module_file


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(), filename=str(path))


def _opens_db_session(node: ast.With | ast.AsyncWith) -> bool:
    return any(_is_db_session_context(item.context_expr) for item in node.items)


def _is_db_session_context(expr: ast.expr) -> bool:
    call = expr if isinstance(expr, ast.Call) else None
    return call is not None and _call_leaf(call.func) in DB_SESSION_HELPERS


def _descendants_excluding_nested_sessions(node: ast.With | ast.AsyncWith) -> list[ast.AST]:
    descendants: list[ast.AST] = []
    for statement in node.body:
        for child in ast.walk(statement):
            if child is statement:
                descendants.append(child)
                continue
            if isinstance(child, (ast.With, ast.AsyncWith)) and _opens_db_session(child):
                continue
            descendants.append(child)
    return descendants


def _is_external_io_call(node: ast.Call) -> bool:
    tokens = _call_path(node.func).split(".")
    if not tokens or tokens[0] == "repos":
        return False
    if tokens[0] == "self":
        return any(marker in token for token in tokens[1:] for marker in EXTERNAL_IO_TOKENS)
    return tokens[0] in EXTERNAL_IO_TOKENS


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
