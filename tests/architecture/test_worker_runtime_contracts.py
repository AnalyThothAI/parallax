from __future__ import annotations

import ast
import importlib
import inspect
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_manifest import (
    WorkerKind,
    all_worker_manifests,
    worker_start_priority,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"
DOCS_WORKERS = ROOT / "docs" / "WORKERS.md"
DOCS_CONTRACTS = ROOT / "docs" / "CONTRACTS.md"
DOCS_ARCHITECTURE = ROOT / "docs" / "ARCHITECTURE.md"
API_SCHEMAS = SRC / "app" / "surfaces" / "api" / "schemas.py"
API_DEPENDENCIES = SRC / "app" / "surfaces" / "api" / "dependencies.py"
APP_RUNTIME_APP = SRC / "app" / "runtime" / "app.py"
APP_RUNTIME_BOOTSTRAP = SRC / "app" / "runtime" / "bootstrap.py"
APP_RUNTIME_DB_POOL_BUNDLE = SRC / "app" / "runtime" / "db_pool_bundle.py"
OPS_DIAGNOSTICS = SRC / "app" / "runtime" / "ops_diagnostics.py"
CLI_OPS = SRC / "app" / "surfaces" / "cli" / "commands" / "ops.py"
WORKER_SCHEDULER = SRC / "app" / "runtime" / "worker_scheduler.py"
OKX_PROVIDER_WIRING = SRC / "app" / "runtime" / "provider_wiring" / "okx.py"
ASSET_MARKET_PROVIDER_WIRING = SRC / "app" / "runtime" / "provider_wiring" / "asset_market.py"
CEX_MARKET_INTEL_PROVIDER_WIRING = SRC / "app" / "runtime" / "provider_wiring" / "cex_market_intel.py"
PROVIDER_WIRING_TYPES = SRC / "app" / "runtime" / "provider_wiring" / "types.py"
ASSET_MARKET_PROVIDERS = SRC / "domains" / "asset_market" / "providers.py"
INGESTION_PROVIDERS = SRC / "domains" / "ingestion" / "providers.py"
COLLECTOR_SERVICE = SRC / "domains" / "ingestion" / "runtime" / "collector_service.py"
GMGN_DIRECT_WS = SRC / "integrations" / "gmgn" / "direct_ws.py"
MARKET_TICK_STREAM_WORKER = SRC / "domains" / "asset_market" / "runtime" / "market_tick_stream_worker.py"
MARKET_TICK_POLL_WORKER = SRC / "domains" / "asset_market" / "runtime" / "market_tick_poll_worker.py"
MARKET_TICK_CURRENT_PROJECTION_WORKER = (
    SRC / "domains" / "asset_market" / "runtime" / "market_tick_current_projection_worker.py"
)
TOKEN_CAPTURE_TIER_WORKER = SRC / "domains" / "asset_market" / "runtime" / "token_capture_tier_worker.py"
TOKEN_RADAR_PROJECTION_WORKER = SRC / "domains" / "token_intel" / "runtime" / "token_radar_projection_worker.py"
LIVE_PRICE_GATEWAY = SRC / "domains" / "asset_market" / "runtime" / "live_price_gateway.py"
TOKEN_PROFILE_CURRENT_WORKER = SRC / "domains" / "asset_market" / "runtime" / "token_profile_current_worker.py"
TOKEN_IMAGE_MIRROR_WORKER = SRC / "domains" / "asset_market" / "runtime" / "token_image_mirror_worker.py"
TOKEN_IMAGE_MIRROR_SERVICE = SRC / "domains" / "asset_market" / "services" / "token_image_mirror.py"
ASSET_PROFILE_REFRESH_WORKER = SRC / "domains" / "asset_market" / "runtime" / "asset_profile_refresh_worker.py"
EVENT_ANCHOR_BACKFILL_WORKER = SRC / "domains" / "asset_market" / "runtime" / "event_anchor_backfill_worker.py"
INGEST_SERVICE = SRC / "domains" / "evidence" / "services" / "ingest_service.py"
RESOLUTION_REFRESH_WORKER = SRC / "domains" / "asset_market" / "runtime" / "resolution_refresh_worker.py"
NEWS_PAGE_PROJECTION_WORKER = SRC / "domains" / "news_intel" / "runtime" / "news_page_projection_worker.py"
NEWS_ITEM_PROCESS_WORKER = SRC / "domains" / "news_intel" / "runtime" / "news_item_process_worker.py"
NEWS_ITEM_BRIEF_WORKER = SRC / "domains" / "news_intel" / "runtime" / "news_item_brief_worker.py"
NEWS_REPOSITORY = SRC / "domains" / "news_intel" / "repositories" / "news_repository.py"
NEWS_SOURCE_QUALITY_PROJECTION_WORKER = (
    SRC / "domains" / "news_intel" / "runtime" / "news_source_quality_projection_worker.py"
)
NEWS_FETCH_WORKER = SRC / "domains" / "news_intel" / "runtime" / "news_fetch_worker.py"
MACRO_SYNC_WORKER = SRC / "domains" / "macro_intel" / "runtime" / "macro_sync_worker.py"
MACRO_SYNC_SERVICE = SRC / "domains" / "macro_intel" / "services" / "macro_sync_service.py"
MACRO_VIEW_PROJECTION_WORKER = SRC / "domains" / "macro_intel" / "runtime" / "macro_view_projection_worker.py"
MACRO_DAILY_BRIEF_PROJECTION_WORKER = (
    SRC / "domains" / "macro_intel" / "runtime" / "macro_daily_brief_projection_worker.py"
)
NARRATIVE_ARCHITECTURE = SRC / "domains" / "narrative_intel" / "ARCHITECTURE.md"
NARRATIVE_REPOSITORY = SRC / "domains" / "narrative_intel" / "repositories" / "narrative_repository.py"
NARRATIVE_READ_MODEL = SRC / "domains" / "narrative_intel" / "read_models" / "narrative_read_model.py"
NARRATIVE_ADMISSION_WORKER = SRC / "domains" / "narrative_intel" / "runtime" / "narrative_admission_worker.py"
NARRATIVE_ADMISSION_SERVICE = SRC / "domains" / "narrative_intel" / "services" / "narrative_admission.py"
API_ROUTES = SRC / "app" / "surfaces" / "api"
WORKER_FACTORIES = SRC / "app" / "runtime" / "worker_factories"
CEX_OI_RADAR_REPOSITORY = SRC / "domains" / "cex_market_intel" / "repositories" / "cex_oi_radar_repository.py"
CEX_OI_RADAR_BOARD_WORKER = SRC / "domains" / "cex_market_intel" / "runtime" / "cex_oi_radar_board_worker.py"
CEX_BINANCE_OI_RADAR_BUILDER = SRC / "domains" / "cex_market_intel" / "services" / "binance_oi_radar_builder.py"
CEX_COINGLASS_DETAIL_ENRICHER = SRC / "domains" / "cex_market_intel" / "services" / "coinglass_detail_enricher.py"
NEWS_INTEL_CANONICAL_DEDUP_MIGRATION = (
    SRC / "platform/db/alembic/versions/20260528_0117_news_intel_canonical_dedup_hard_cut.py"
)
NEWS_REALTIME_POSTGRES_HOTPATH_MIGRATION = (
    SRC / "platform/db/alembic/versions/20260528_0118_news_realtime_postgres_hotpath_hard_cut.py"
)
ZERO_HARD_TIMEOUT_ALLOWLIST = {"collector"}


MANIFEST_WORKER_CLASSES = {manifest.name: manifest.worker_class for manifest in all_worker_manifests()}

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

SINGLE_WRITER_READ_MODELS: dict[str, set[Path]] = {
    "token_radar_current_rows": TOKEN_RADAR_WRITE_OWNER_ALLOWLIST,
    "token_radar_publication_state": TOKEN_RADAR_WRITE_OWNER_ALLOWLIST,
    "token_radar_target_first_seen": TOKEN_RADAR_WRITE_OWNER_ALLOWLIST,
    "token_profile_current": {
        SRC / "domains/asset_market/repositories/token_profile_current_repository.py",
        SRC / "domains/asset_market/runtime/token_profile_current_worker.py",
        SRC / "platform/db/alembic/versions/20260517_0052_token_profile_current.py",
        SRC / "platform/db/alembic/versions/20260521_0079_token_profile_local_logo_hard_cut.py",
    },
    "market_tick_current": {
        SRC / "domains/asset_market/repositories/market_tick_current_repository.py",
        SRC / "domains/asset_market/runtime/market_tick_current_projection_worker.py",
        SRC / "platform/db/alembic/versions/20260523_0090_token_radar_postgres_hard_cut.py",
    },
    "token_image_assets": {
        SRC / "domains/asset_market/repositories/token_image_asset_repository.py",
        SRC / "platform/db/alembic/versions/20260521_0078_token_image_assets.py",
    },
    "token_capture_tier": {
        SRC / "domains/asset_market/repositories/token_capture_tier_repository.py",
    },
    "narrative_admissions": {
        SRC / "domains/narrative_intel/repositories/narrative_repository.py",
        SRC / "domains/narrative_intel/runtime/narrative_admission_worker.py",
        SRC / "platform/db/alembic/versions/20260518_0063_narrative_intel_read_models.py",
        SRC / "platform/db/alembic/versions/20260519_0064_narrative_admission_source_sets.py",
    },
    "news_page_rows": {
        SRC / "domains/news_intel/repositories/news_repository.py",
        SRC / "domains/news_intel/runtime/news_page_projection_worker.py",
        SRC / "platform/db/alembic/versions/20260519_0064_news_intel_kappa_cqrs.py",
    },
    "news_item_agent_runs": {
        SRC / "domains/news_intel/repositories/news_repository.py",
        SRC / "domains/news_intel/runtime/news_item_brief_worker.py",
        SRC / "platform/db/alembic/versions/20260520_0068_news_item_agent_brief.py",
    },
    "news_item_agent_briefs": {
        SRC / "domains/news_intel/repositories/news_repository.py",
        SRC / "domains/news_intel/runtime/news_item_brief_worker.py",
        SRC / "platform/db/alembic/versions/20260520_0068_news_item_agent_brief.py",
    },
    "news_source_quality_rows": {
        SRC / "domains/news_intel/repositories/news_repository.py",
        SRC / "domains/news_intel/runtime/news_source_quality_projection_worker.py",
        SRC / "platform/db/alembic/versions/20260522_0082_news_source_quality_rows.py",
    },
    "cex_oi_radar_rows": {
        CEX_OI_RADAR_REPOSITORY,
        CEX_OI_RADAR_BOARD_WORKER,
        SRC / "platform/db/alembic/versions/20260521_0073_cex_oi_radar_board.py",
        SRC / "platform/db/alembic/versions/20260527_0115_next_runtime_lifecycle_hard_cut.py",
    },
    "macro_view_snapshots": {
        SRC / "domains/macro_intel/repositories/macro_intel_repository.py",
        SRC / "domains/macro_intel/runtime/macro_view_projection_worker.py",
        SRC / "platform/db/alembic/versions/20260521_0076_macro_views.py",
    },
    "macro_observation_series_rows": {
        SRC / "domains/macro_intel/repositories/macro_intel_repository.py",
        SRC / "domains/macro_intel/runtime/macro_view_projection_worker.py",
        SRC / "platform/db/alembic/versions/20260521_0076_macro_views.py",
    },
}

CONTROL_PLANE_TABLES: dict[str, set[Path]] = {
    "narrative_admission_dirty_targets": {
        SRC / "domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py",
        SRC / "platform/db/alembic/versions/20260525_0098_runtime_worker_dirty_targets.py",
        SRC / "platform/db/alembic/versions/20260713_0183_backend_kappa_cqrs_hard_cut.py",
    },
    "token_profile_current_dirty_targets": {
        SRC / "domains/asset_market/repositories/token_profile_current_dirty_target_repository.py",
        SRC / "platform/db/alembic/versions/20260525_0098_runtime_worker_dirty_targets.py",
        SRC / "platform/db/alembic/versions/20260531_0136_okx_symbol_candidate_profile_icons.py",
        SRC / "platform/db/alembic/versions/20260713_0183_backend_kappa_cqrs_hard_cut.py",
    },
    "token_image_source_dirty_targets": {
        SRC / "domains/asset_market/repositories/token_image_source_dirty_target_repository.py",
        SRC / "platform/db/alembic/versions/20260525_0098_runtime_worker_dirty_targets.py",
    },
    "asset_profile_refresh_targets": {
        SRC / "domains/asset_market/repositories/asset_profile_refresh_target_repository.py",
        SRC / "platform/db/alembic/versions/20260525_0098_runtime_worker_dirty_targets.py",
    },
    "token_capture_tier_dirty_targets": {
        SRC / "domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py",
        SRC / "platform/db/alembic/versions/20260525_0098_runtime_worker_dirty_targets.py",
    },
    "news_projection_dirty_targets": {
        SRC / "domains/news_intel/repositories/news_repository.py",
        SRC / "domains/news_intel/repositories/news_projection_dirty_target_repository.py",
        SRC / "platform/db/alembic/versions/20260524_0094_projection_dirty_targets_hard_cut.py",
        SRC / "platform/db/alembic/versions/20260525_0097_agent_brief_dirty_targets.py",
        NEWS_INTEL_CANONICAL_DEDUP_MIGRATION,
        NEWS_REALTIME_POSTGRES_HOTPATH_MIGRATION,
        SRC / "platform/db/alembic/versions/20260529_0123_news_public_url_hard_identity.py",
        SRC / "platform/db/alembic/versions/20260531_0131_news_story_projection_hard_cut.py",
        SRC / "platform/db/alembic/versions/20260531_0132_news_rebuild_brief_backlog_hard_cut.py",
        SRC / "platform/db/alembic/versions/20260531_0137_news_dirty_projection_hard_cut.py",
        SRC / "platform/db/alembic/versions/20260601_0139_news_item_brief_lightweight_contract.py",
        SRC / "platform/db/alembic/versions/20260601_0140_news_item_brief_requeue_nonready.py",
        SRC / "platform/db/alembic/versions/20260609_0167_news_story_identity_v2.py",
        SRC / "platform/db/alembic/versions/20260609_0168_news_story_identity_v2_remaining_opennews.py",
        SRC / "platform/db/alembic/versions/20260609_0170_news_agent_admission_retired_policy_reprocess.py",
        SRC / "platform/db/alembic/versions/20260609_0171_news_page_rows_require_story_identity.py",
        SRC / "platform/db/alembic/versions/20260609_0172_news_page_rows_require_agent_eligible.py",
        SRC / "platform/db/alembic/versions/20260609_0173_news_page_rows_serving_invariants.py",
        SRC / "platform/db/alembic/versions/20260609_0175_news_agent_provider_rating_gate.py",
        SRC / "platform/db/alembic/versions/20260609_0176_news_provider_rating_gate_finalize.py",
        SRC / "platform/db/alembic/versions/20260612_0177_news_brief_duplicate_cost_hard_cut.py",
    },
    "market_tick_current_dirty_targets": {
        SRC / "domains/asset_market/repositories/market_tick_current_dirty_target_repository.py",
        SRC / "platform/db/alembic/versions/20260524_0095_market_tick_current_dirty_targets.py",
    },
    "token_discovery_dirty_lookup_keys": {
        SRC / "domains/asset_market/repositories/discovery_repository.py",
        SRC / "platform/db/alembic/versions/20260525_0096_token_discovery_dirty_lookup_keys.py",
    },
}

LEGACY_ASSET_TABLES = ("assets", "asset_aliases", "asset_venues", "asset_market_snapshots")
EXPECTED_WORKER_FACTORY_FILES = {
    "__init__.py",
    "asset_market.py",
    "cex_market_intel.py",
    "ingestion.py",
    "macro_intel.py",
    "narrative_intel.py",
    "news_intel.py",
    "notifications.py",
    "token_intel.py",
}
BOOTSTRAP_RUNTIME_WORKER_IMPORT_ALLOWLIST = {
    "parallax.domains.ingestion.runtime.collector_service",
}


@pytest.mark.architecture
@pytest.mark.parametrize(("worker_key", "qualified_name"), MANIFEST_WORKER_CLASSES.items())
def test_all_long_running_workers_inherit_worker_base(worker_key: str, qualified_name: str) -> None:
    worker_class = _import_qualified_name(qualified_name)

    assert issubclass(worker_class, WorkerBase), f"{worker_key} must inherit WorkerBase"


@pytest.mark.architecture
def test_long_running_workers_do_not_override_worker_base_run_without_allowlist() -> None:
    violations: list[str] = []
    for worker_key, qualified_name in MANIFEST_WORKER_CLASSES.items():
        worker_class = _import_qualified_name(qualified_name)
        if "run" in worker_class.__dict__:
            violations.append(f"{worker_key} overrides run()")

    assert violations == []


@pytest.mark.architecture
def test_worker_queue_depth_overrides_are_status_payload_compatible() -> None:
    violations: list[str] = []
    for worker_key, qualified_name in MANIFEST_WORKER_CLASSES.items():
        worker_class = _import_qualified_name(qualified_name)
        override = worker_class.__dict__.get("_queue_depth")
        if override is None:
            continue
        signature = inspect.signature(override)
        try:
            signature.bind(object())
        except TypeError as exc:
            violations.append(
                f"{worker_key}._queue_depth must be callable by WorkerBase.status_payload() "
                f"with no required arguments: {exc}"
            )

    assert violations == []


@pytest.mark.architecture
def test_worker_scheduler_status_payload_contract_is_not_optional_or_swallowed() -> None:
    source = WORKER_SCHEDULER.read_text(encoding="utf-8")
    helper = source.split("def _worker_status_payload", 1)[1].split("\ndef _worker_hard_timed_out", 1)[0]
    forbidden_tokens = (
        'getattr(worker, "status_payload", None)',
        "if not callable(status_payload)",
        "payload = status_payload()",
        "except Exception:",
        "return {}",
        "payload if isinstance(payload, dict) else {}",
    )
    violations = [token for token in forbidden_tokens if token in helper]

    assert violations == []
    assert "payload = worker.status_payload()" in helper
    assert "worker_status_payload_must_be_dict" in helper


@pytest.mark.architecture
def test_worker_scheduler_unhealthy_reasons_use_status_payload_not_worker_attributes() -> None:
    source = WORKER_SCHEDULER.read_text(encoding="utf-8")
    unhealthy_source = source.split("def unhealthy_reasons", 1)[1].split("\n    def _ordered_worker_names", 1)[0]
    reason_source = source.split("def _worker_unavailable_reason", 1)[1].split("\ndef _worker_status_payload", 1)[0]

    forbidden_tokens = (
        'getattr(worker, "unavailable_reason", None)',
        'getattr(worker, "last_error", None)',
        'getattr(worker, "active_run_once_hard_timed_out_at_ms", None)',
    )
    combined = f"{unhealthy_source}\n{reason_source}"
    violations = [token for token in forbidden_tokens if token in combined]

    assert violations == []
    assert "payload = _worker_status_payload(worker)" in unhealthy_source
    assert "_worker_failure_reason(name, payload, effective_status)" in unhealthy_source
    assert "_worker_unavailable_reason(payload)" in unhealthy_source


@pytest.mark.architecture
def test_worker_scheduler_closes_db_pool_bundle_contract_without_pool_fallback() -> None:
    source = WORKER_SCHEDULER.read_text(encoding="utf-8")
    stop_source = source.split("async def stop", 1)[1].split("\n    def status_payload", 1)[0]
    forbidden_tokens = (
        'getattr(self.db, "aclose", None)',
        'for attr in ("api_pool", "worker_pool", "lock_pool", "tool_pool", "wake_pool")',
        "getattr(self.db, attr, None)",
        "def _close_resource",
        "await _maybe_await(",
        "def _maybe_await",
        "inspect.isawaitable",
        "import inspect",
    )
    violations = [token for token in forbidden_tokens if token in source]

    assert violations == []
    assert "await worker.stop()" in stop_source
    assert "await worker.aclose()" in stop_source
    assert "await self.db.aclose()" in stop_source


@pytest.mark.architecture
def test_worker_scheduler_stop_timeout_is_formal_nonnegative_contract_without_runtime_repair() -> None:
    source = WORKER_SCHEDULER.read_text(encoding="utf-8")
    init_source = source.split("def __init__", 1)[1].split("\n    async def start", 1)[0]
    helper_source = source.split("def _nonnegative_timeout_seconds", 1)[1].split(
        "\n\ndef worker_effective_status",
        1,
    )[0]
    forbidden_tokens = (
        "max(0.0, float(stop_timeout_seconds))",
        "float(stop_timeout_seconds)",
    )

    assert [token for token in forbidden_tokens if token in init_source] == []
    assert "self.stop_timeout_seconds = _nonnegative_timeout_seconds(stop_timeout_seconds)" in init_source
    assert "worker_scheduler_stop_timeout_seconds_required" in helper_source
    assert "isinstance(value, bool) or not isinstance(value, int | float)" in helper_source
    assert "value < 0" in helper_source


@pytest.mark.architecture
def test_bootstrap_failure_closes_db_pool_bundle_contract_without_pool_fallback() -> None:
    source = APP_RUNTIME_BOOTSTRAP.read_text(encoding="utf-8")
    bootstrap_source = source.split("def bootstrap", 1)[1].split("\ndef _assemble_runtime", 1)[0]
    failure_source = bootstrap_source.split("except Exception as exc:", 1)[1]
    failure_forbidden_tokens = (
        "_close_db_pools(",
        'getattr(db, "lock_pool", None)',
        "db.api_pool",
        "db.worker_pool",
        "db.tool_pool",
        "db.wake_pool",
    )
    violations = [token for token in failure_forbidden_tokens if token in failure_source]
    if "def _close_db_pools" in source:
        violations.append("def _close_db_pools")

    assert violations == []
    assert "_close_db_bundle_sync(db)" in failure_source
    assert "_await_sync(db.aclose())" in source


@pytest.mark.architecture
def test_db_pool_bundle_create_partial_cleanup_uses_formal_pool_close_contract() -> None:
    source = APP_RUNTIME_DB_POOL_BUNDLE.read_text(encoding="utf-8")
    create_source = source.split("def create(cls", 1)[1].split("\n    @contextmanager", 1)[0]
    partial_cleanup_source = source.split("def _close_partial_pools", 1)[1].split(
        "\n\nasync def _close_pool",
        1,
    )[0]
    combined = "\n".join((create_source, partial_cleanup_source))

    forbidden_tokens = (
        'getattr(pool, "close", None)',
        "close = getattr",
        "if close:",
        "if close is not None",
        "if not close",
    )
    violations = [token for token in forbidden_tokens if token in combined]

    assert violations == []
    assert "_close_partial_pools(" in create_source
    assert "cast(_SyncClosePool, pool).close()" in partial_cleanup_source
    assert "partial db pool cleanup failed" in partial_cleanup_source


@pytest.mark.architecture
def test_db_pool_bundle_discard_connection_uses_formal_connection_close_without_pool_fallback() -> None:
    source = APP_RUNTIME_DB_POOL_BUNDLE.read_text(encoding="utf-8")
    discard_source = source.split("def _discard_connection", 1)[1].split(
        "\n\n\ndef _close_partial_pools",
        1,
    )[0]

    forbidden_tokens = (
        "close_returns",
        'getattr(pool, "close_returns", None)',
        'getattr(conn, "close", None)',
        "discard = getattr",
        "close = getattr",
        "if discard:",
        "if close:",
    )
    violations = [token for token in forbidden_tokens if token in discard_source]

    assert violations == []
    assert "conn.close()" in discard_source
    assert "pool.putconn(conn)" in discard_source


@pytest.mark.architecture
def test_db_pool_bundle_pool_close_is_sync_contract_without_awaitable_fallback() -> None:
    source = APP_RUNTIME_DB_POOL_BUNDLE.read_text(encoding="utf-8")
    close_pool_source = source.split("async def _close_pool", 1)[1]

    forbidden_tokens = (
        "import inspect",
        "inspect.isawaitable",
        "await result",
        "await pool.close()",
    )
    violations = [token for token in forbidden_tokens if token in source]

    assert violations == []
    assert "result = pool.close()" in close_pool_source
    assert "db_pool_close_must_be_sync" in close_pool_source


@pytest.mark.architecture
def test_bootstrap_provider_cleanup_uses_formal_roots_without_object_graph_scan() -> None:
    bootstrap_source = APP_RUNTIME_BOOTSTRAP.read_text(encoding="utf-8")
    provider_types_source = PROVIDER_WIRING_TYPES.read_text(encoding="utf-8")
    runtime_cleanup_source = bootstrap_source.split("async def _cleanup_runtime_providers", 1)[1].split(
        "\ndef _cleanup_provider_roots_sync",
        1,
    )[0]
    sync_cleanup_source = bootstrap_source.split("def _cleanup_provider_roots_sync", 1)[1].split(
        "\ndef _close_db_bundle_sync",
        1,
    )[0]
    wired_providers_aclose = provider_types_source.split("class WiredProviders", 1)[1].split(
        "\n\n__all__",
        1,
    )[0]

    forbidden_tokens = (
        "_provider_cleanup_targets",
        "_object_values_for_cleanup",
        "_has_close_method",
        "fields(",
        "is_dataclass",
        "inspect.isclass",
        "inspect.ismodule",
        "inspect.isroutine",
        'getattr(provider, "aclose", None)',
        'getattr(provider, "close", None)',
    )
    violations = [token for token in forbidden_tokens if token in bootstrap_source]

    assert violations == []
    assert "await runtime.providers.aclose()" in runtime_cleanup_source
    assert "await runtime.agent_execution_gateway.aclose()" in runtime_cleanup_source
    assert "await runtime.llm_gateway.aclose()" in runtime_cleanup_source
    assert "_await_sync(providers.aclose())" in sync_cleanup_source
    assert "_await_sync(agent_execution_gateway.aclose())" in sync_cleanup_source
    assert "_await_sync(llm_gateway.aclose())" in sync_cleanup_source
    assert "async def aclose(self) -> None" in wired_providers_aclose
    assert "self.agent_execution_gateway" not in wired_providers_aclose


@pytest.mark.architecture
def test_stream_provider_connection_state_is_formal_runtime_contract() -> None:
    asset_provider_source = ASSET_MARKET_PROVIDERS.read_text(encoding="utf-8")
    dex_stream_protocol = asset_provider_source.split("class DexMarketStreamProvider", 1)[1].split(
        "\n\n__all__",
        1,
    )[0]
    assert "def connection_state_payload(self) -> dict[str, Any]" in dex_stream_protocol

    ingestion_provider_source = INGESTION_PROVIDERS.read_text(encoding="utf-8")
    upstream_protocol = ingestion_provider_source.split("class UpstreamClientProtocol", 1)[1].split(
        "\n\n__all__",
        1,
    )[0]
    assert "def connection_state_payload(self) -> dict[str, Any]" in upstream_protocol

    stream_worker_source = MARKET_TICK_STREAM_WORKER.read_text(encoding="utf-8")
    stream_helper_source = stream_worker_source.split("def _provider_connection_state_payload", 1)[1].split(
        "\n\ndef _provider_failure_category",
        1,
    )[0]
    readiness_helper_source = (
        APP_RUNTIME_APP.read_text(encoding="utf-8")
        .split(
            "def _provider_state_payload",
            1,
        )[1]
        .split("\n\ndef _now_ms", 1)[0]
    )
    diagnostics_helper_source = (
        OPS_DIAGNOSTICS.read_text(encoding="utf-8")
        .split(
            "def _provider_connection_payload",
            1,
        )[1]
        .split("\n\ndef _provider_status", 1)[0]
    )
    okx_adapter_source = (
        OKX_PROVIDER_WIRING.read_text(encoding="utf-8")
        .split(
            "def connection_state_payload(self) -> dict[str, Any]:",
            1,
        )[1]
        .split("\n\n\ndef wire_okx_provider_bundle", 1)[0]
    )

    helper_sources = {
        "market_tick_stream_worker": stream_helper_source,
        "app_readiness": readiness_helper_source,
        "ops_diagnostics": diagnostics_helper_source,
        "okx_adapter": okx_adapter_source,
    }
    forbidden_tokens = (
        'getattr(provider, "connection_state_payload", None)',
        'getattr(self._provider, "connection_state_payload", None)',
        "if not callable(payload)",
        "if payload is None",
    )
    violations = [
        f"{source_name} contains {token}"
        for source_name, source in helper_sources.items()
        for token in forbidden_tokens
        if token in source
    ]

    assert violations == []
    assert "provider.connection_state_payload()" in stream_helper_source
    assert "provider.connection_state_payload()" in readiness_helper_source
    assert "provider.connection_state_payload()" in diagnostics_helper_source
    assert "self._provider.connection_state_payload()" in okx_adapter_source


@pytest.mark.architecture
def test_readyz_does_not_keep_dead_notification_summary_fallback() -> None:
    source = APP_RUNTIME_APP.read_text(encoding="utf-8")
    forbidden_tokens = (
        "def _notification_summary",
        'repos.notifications.summary(subscriber_key="local")',
        "except Exception:\n        return {}",
    )
    violations = [token for token in forbidden_tokens if token in source]

    assert violations == []


@pytest.mark.architecture
def test_status_provider_roots_use_formal_runtime_provider_bundle_contract() -> None:
    app_source = APP_RUNTIME_APP.read_text(encoding="utf-8")
    stream_root_source = app_source.split("def _stream_dex_market", 1)[1].split(
        "\n\ndef _agent_execution_status",
        1,
    )[0]
    readiness_payload_source = app_source.split("def _readiness_payload", 1)[1].split(
        "\n\ndef _stream_dex_market",
        1,
    )[0]
    diagnostics_source = OPS_DIAGNOSTICS.read_text(encoding="utf-8")
    diagnostics_provider_source = diagnostics_source.split("def _asset_market_provider_health", 1)[1].split(
        "\n\ndef _connection_provider_payload",
        1,
    )[0]

    helper_sources = {
        "api_stream_root": stream_root_source,
        "api_readiness": readiness_payload_source,
        "ops_diagnostics_providers": diagnostics_provider_source,
    }
    forbidden_tokens = (
        'getattr(runtime, "providers", None)',
        'getattr(providers, "asset_market", None)',
        'getattr(getattr(runtime, "providers", None), "asset_market", None)',
        'getattr(runtime.collector, "upstream_client", None)',
        'getattr(asset_market, "provider_health", ())',
    )
    violations = [
        f"{source_name} contains {token}"
        for source_name, source in helper_sources.items()
        for token in forbidden_tokens
        if token in source
    ]

    assert violations == []
    assert "runtime.providers.asset_market.stream_dex_market" in stream_root_source
    assert "runtime.collector.upstream_client" in readiness_payload_source
    assert "runtime.providers.asset_market" in diagnostics_provider_source
    assert "health_items = runtime.providers.asset_market.provider_health" in diagnostics_provider_source


@pytest.mark.architecture
def test_ops_diagnostics_collector_section_uses_formal_collector_status_contract() -> None:
    diagnostics_source = OPS_DIAGNOSTICS.read_text(encoding="utf-8")
    collector_source = diagnostics_source.split("def _collector_payload", 1)[1].split(
        "\n\ndef _providers_payload",
        1,
    )[0]
    forbidden_tokens = (
        'getattr(runtime, "collector", None)',
        'getattr(collector, "status", None)',
        'getattr(status_object, "to_dict", None)',
        'getattr(collector, "upstream_client", None)',
        "if callable(to_dict)",
        "else {}",
        "details if isinstance(details, dict) else {}",
    )
    violations = [token for token in forbidden_tokens if token in collector_source]

    assert violations == []
    assert "details = runtime.collector.status.to_dict()" in collector_source
    assert "provider = runtime.collector.upstream_client" in collector_source
    assert "collector_status_payload_must_be_dict" in collector_source


@pytest.mark.architecture
def test_ops_diagnostics_asset_market_provider_health_items_use_explicit_contract_without_reflection() -> None:
    diagnostics_source = OPS_DIAGNOSTICS.read_text(encoding="utf-8")
    provider_health_source = diagnostics_source.split("def _provider_health_payload", 1)[1].split(
        "\n\ndef _error_type",
        1,
    )[0]
    forbidden_tokens = (
        "def _object_payload",
        "vars(",
        "__dict__",
        "is_dataclass",
    )
    violations = [token for token in forbidden_tokens if token in diagnostics_source]

    assert violations == []
    assert "isinstance(value, ProviderHealth)" in provider_health_source
    assert "isinstance(value, Mapping)" in provider_health_source
    assert "asset_market_provider_health_item_contract_required" in provider_health_source


@pytest.mark.architecture
def test_ops_diagnostics_config_uses_formal_runtime_settings_contract_without_optional_probe() -> None:
    diagnostics_source = OPS_DIAGNOSTICS.read_text(encoding="utf-8")
    watchlist_source = diagnostics_source.split("def _watchlist_domain", 1)[1].split(
        "\n\ndef _notifications_domain",
        1,
    )[0]
    config_source = diagnostics_source.split("def _config_payload", 1)[1].split(
        "\n\ndef _suggested_checks",
        1,
    )[0]
    forbidden_tokens = (
        'getattr(runtime, "settings", None)',
        'getattr(getattr(runtime, "settings", None), "handles", ())',
        'getattr(settings, "app_home", "")',
        'getattr(settings, "handles", ())',
        'getattr(settings, "upstream_channels", ())',
        'getattr(settings, "gmgn_configured", False)',
        'getattr(settings, "okx_dex_configured", False)',
        'getattr(settings, "llm_configured", False)',
        'getattr(settings, "news_intel_enabled", False)',
        'getattr(settings, "notification_rules", None)',
    )
    combined = f"{watchlist_source}\n{config_source}"
    violations = [token for token in forbidden_tokens if token in combined]

    assert violations == []
    assert "configured_handles = tuple(runtime.settings.handles or ())" in watchlist_source
    assert "settings = runtime.settings" in config_source
    assert "app_home = Path(str(settings.app_home)).expanduser()" in config_source
    assert 'handles_count": len(tuple(settings.handles or ()))' in config_source
    assert 'upstream_channels": list(settings.upstream_channels or ())' in config_source


@pytest.mark.architecture
def test_ops_diagnostics_queues_use_formal_api_pool_connection_contract() -> None:
    diagnostics_source = OPS_DIAGNOSTICS.read_text(encoding="utf-8")
    queue_source = diagnostics_source.split("def _queues_payload", 1)[1].split(
        "\n\ndef _queue_summary",
        1,
    )[0]
    forbidden_tokens = (
        'getattr(runtime, "db", None)',
        'getattr(db, "api_pool", None)',
        'getattr(api_pool, "connection", None)',
        "if not callable(connection):",
        "return []",
    )
    violations = [token for token in forbidden_tokens if token in queue_source]

    assert violations == []
    assert "with runtime.db.api_pool.connection() as conn:" in queue_source


@pytest.mark.architecture
def test_market_tick_stream_worker_iterator_cleanup_uses_formal_aclose_contract() -> None:
    source = MARKET_TICK_STREAM_WORKER.read_text(encoding="utf-8")
    stream_source = source.split("async def _stream_and_persist_ticks", 1)[1].split(
        "\n    def _persist_ticks",
        1,
    )[0]

    forbidden_tokens = (
        'getattr(iterator, "aclose", None)',
        "close = getattr(iterator",
        "if close is not None",
        "if close:",
        "if not close",
    )
    violations = [token for token in forbidden_tokens if token in stream_source]

    assert violations == []
    assert "class _AsyncCloseIterator(Protocol)" in source
    assert "await cast(_AsyncCloseIterator, iterator).aclose()" in stream_source


@pytest.mark.architecture
def test_market_tick_stream_worker_constructor_uses_formal_runtime_contract_without_synthetic_defaults() -> None:
    source = MARKET_TICK_STREAM_WORKER.read_text(encoding="utf-8")
    init_source = source.split("def __init__", 1)[1].split("\n    async def run_once", 1)[0]
    settings_source = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    settings_class = settings_source.split("class MarketTickStreamWorkerSettings", 1)[1].split(
        "\n\nclass MarketTickPollWorkerSettings",
        1,
    )[0]
    factory_source = (WORKER_FACTORIES / "asset_market.py").read_text(encoding="utf-8")
    stream_factory_source = factory_source.split(
        'constructed["market_tick_stream"] = MarketTickStreamWorker(',
        1,
    )[1].split(
        "\n            )",
        1,
    )[0]
    forbidden_source_tokens = (
        "from types import SimpleNamespace",
        "DEFAULT_SUBSCRIPTION_LIMIT",
        "DEFAULT_STREAM_CYCLE_SECONDS",
        "def _settings",
        "def _stream_cycle_seconds",
        "SimpleNamespace(",
        "SimpleNamespace(**",
        'getattr(settings, "__dict__", {})',
        'getattr(settings, "stream_cycle_seconds"',
    )
    forbidden_init_tokens = (
        "resolved_settings",
        "wake_bus",
        "db: Any | None",
        "pool_bundle or db",
        "wake_emitter or",
        "subscription_limit:",
        "interval_seconds:",
        "stream_cycle_seconds:",
        "settings: Any | None",
        "telemetry or object()",
        'getattr(settings, "',
        'getattr(resolved_settings, "',
        "max(0, int(settings.subscription_limit))",
        "max(0.001, float(settings.stream_cycle_seconds))",
    )
    forbidden_factory_tokens = (
        "subscription_limit=workers.market_tick_stream.subscription_limit",
        "wake_bus=",
        "db=",
    )
    violations = (
        [f"worker-source:{token}" for token in forbidden_source_tokens if token in source]
        + [f"worker-init:{token}" for token in forbidden_init_tokens if token in init_source]
        + [f"factory:{token}" for token in forbidden_factory_tokens if token in stream_factory_source]
    )

    assert violations == []
    assert "market_tick_stream_settings_required" in init_source
    assert "market_tick_stream_db_required" in init_source
    assert "market_tick_stream_provider_required" in init_source
    assert "market_tick_stream_subscription_limit_required" in init_source
    assert "market_tick_stream_cycle_seconds_required" in init_source
    assert "def _required_positive_int(value: Any, *, error_code: str) -> int:" in source
    assert "def _required_min_float(value: Any, *, minimum: float, error_code: str) -> float:" in source
    assert "isinstance(value, bool)" in source
    assert "settings=workers.market_tick_stream" in stream_factory_source
    assert "pool_bundle=ctx.db" in stream_factory_source
    assert "stream_dex_market=stream_dex_market" in stream_factory_source
    assert "wake_emitter=ctx.wake_bus" in stream_factory_source
    assert "stream_cycle_seconds: float = Field(default=30.0, ge=0.001)" in settings_class
    assert "rows[: max(0, int(limit))]" not in source


@pytest.mark.architecture
def test_okx_dex_ws_provider_uses_formal_subscription_and_circuit_limits() -> None:
    source = (SRC / "integrations/okx/dex_ws_client.py").read_text(encoding="utf-8")
    provider_init = source.split("class OkxDexWebSocketMarketProvider", 1)[1].split(
        "\n    def connection_state_payload",
        1,
    )[0]
    subscription_args_source = source.split("def _subscription_args", 1)[1].split(
        "\n\ndef _arg_key",
        1,
    )[0]
    forbidden = (
        "self.subscription_limit = max(1, int(subscription_limit))",
        "max(1, int(OKX_DEX_WS_CIRCUIT_FAILURES))",
        "len(args) >= max(1, int(limit))",
    )

    assert [token for token in forbidden if token in source] == []
    assert "okx_dex_ws_subscription_limit_required" in provider_init
    assert "okx_dex_ws_subscription_limit_required" in subscription_args_source
    assert "_circuit_failure_limit()" in source
    assert "okx_dex_ws_circuit_failures_required" in source
    assert "def _required_positive_int(value: Any, *, error_code: str) -> int:" in source


@pytest.mark.architecture
def test_market_tick_poll_worker_constructor_uses_formal_runtime_contract_without_synthetic_defaults() -> None:
    source = MARKET_TICK_POLL_WORKER.read_text(encoding="utf-8")
    init_source = source.split("def __init__", 1)[1].split("\n    async def run_once", 1)[0]
    factory_source = (WORKER_FACTORIES / "asset_market.py").read_text(encoding="utf-8")
    poll_factory_source = factory_source.split('constructed["market_tick_poll"] = MarketTickPollWorker(', 1)[1].split(
        "\n            )",
        1,
    )[0]
    forbidden_source_tokens = (
        "from types import SimpleNamespace",
        "DEFAULT_BATCH_SIZE",
        "def _settings",
        "model_dump",
        "vars(",
        "SimpleNamespace(",
        "SimpleNamespace(**",
    )
    forbidden_init_tokens = (
        "resolved_settings",
        "dex_quote_market:",
        "cex_market:",
        "dex_quote_market=",
        "cex_market=",
        "self.dex_quote_market = dex_quote_market",
        "self.cex_market = cex_market",
        "wake_bus",
        "db: Any | None",
        "pool_bundle or db",
        "providers or",
        "wake_emitter or",
        'getattr(settings, "',
        'getattr(resolved_settings, "',
        'getattr(settings, "__dict__", {})',
        "interval_seconds:",
        "batch_size:",
        "max(1, int(settings.batch_size))",
        "max(1, int(settings.concurrency))",
    )
    forbidden_provider_tokens = (
        'getattr(self.providers, "dex_quote_market", None)',
        'getattr(self.providers, "cex_market", None)',
    )
    forbidden_factory_tokens = (
        "batch_size=workers.market_tick_poll.batch_size",
        "dex_quote_market=",
        "cex_market=",
        "wake_bus=",
        "db=",
    )
    violations = (
        [f"worker-source:{token}" for token in forbidden_source_tokens if token in source]
        + [f"worker-init:{token}" for token in forbidden_init_tokens if token in init_source]
        + [f"worker-provider:{token}" for token in forbidden_provider_tokens if token in source]
        + [f"factory:{token}" for token in forbidden_factory_tokens if token in poll_factory_source]
    )

    assert violations == []
    assert "if settings is None:" in init_source
    assert "market_tick_poll_settings_required" in init_source
    assert "if providers is None:" in init_source
    assert "market_tick_poll_providers_required" in init_source
    assert "if pool_bundle is None:" in init_source
    assert "market_tick_poll_db_required" in init_source
    assert "market_tick_poll_batch_size_required" in init_source
    assert "market_tick_poll_concurrency_required" in init_source
    assert "def _required_positive_int(value: Any, *, error_code: str) -> int:" in source
    assert "isinstance(value, bool)" in source
    assert "self.dex_quote_market = providers.dex_quote_market" in init_source
    assert "self.cex_market = providers.cex_market" in init_source
    assert "settings=workers.market_tick_poll" in poll_factory_source
    assert "providers=asset_market" in poll_factory_source
    assert "pool_bundle=ctx.db" in poll_factory_source
    assert "wake_emitter=ctx.wake_bus" in poll_factory_source


@pytest.mark.architecture
def test_live_price_gateway_constructor_uses_formal_settings_contract_without_synthetic_defaults() -> None:
    source = LIVE_PRICE_GATEWAY.read_text(encoding="utf-8")
    init_source = source.split("def __init__", 1)[1].split("\n    async def run_once", 1)[0]
    settings_source = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    settings_class = settings_source.split("class LivePriceGatewayWorkerSettings", 1)[1].split(
        "\n\nclass ResolutionRefreshWorkerSettings",
        1,
    )[0]
    factory_source = (WORKER_FACTORIES / "asset_market.py").read_text(encoding="utf-8")
    live_factory_source = factory_source.split(
        'constructed["live_price_gateway"] = LivePriceGateway(',
        1,
    )[1].split(
        "\n        )",
        1,
    )[0]
    forbidden_source_tokens = (
        "from types import SimpleNamespace",
        "DEFAULT_LIVE_TARGET_LIMIT",
        "DEFAULT_LIVE_TARGET_TTL_SECONDS",
        "SimpleNamespace(",
        "del providers",
    )
    forbidden_init_tokens = (
        "providers:",
        "interval_seconds:",
        "settings: Any | None",
        'getattr(settings, "',
        "max(0, int(settings.target_limit))",
        "max(0.0, float(settings.target_ttl_seconds))",
    )
    forbidden_factory_tokens = (
        "providers=asset_market",
        "interval_seconds=workers.live_price_gateway.interval_seconds",
    )
    violations = (
        [f"worker-source:{token}" for token in forbidden_source_tokens if token in source]
        + [f"worker-init:{token}" for token in forbidden_init_tokens if token in init_source]
        + [f"factory:{token}" for token in forbidden_factory_tokens if token in live_factory_source]
    )

    assert violations == []
    assert "live_price_gateway_settings_required" in init_source
    assert "live_price_gateway_db_required" in init_source
    assert "live_price_gateway_target_limit_required" in init_source
    assert "live_price_gateway_target_ttl_seconds_required" in init_source
    assert "def _required_nonnegative_int(value: Any, *, error_code: str) -> int:" in source
    assert "def _required_nonnegative_float(value: Any, *, error_code: str) -> float:" in source
    assert "isinstance(value, bool)" in source
    assert "settings=workers.live_price_gateway" in live_factory_source
    assert "pool_bundle=ctx.db" in live_factory_source
    assert "target_limit: int = Field(default=100, ge=0)" in settings_class
    assert "target_ttl_seconds: float = Field(default=300.0, ge=0)" in settings_class


@pytest.mark.architecture
def test_news_fetch_worker_uses_formal_settings_news_settings_and_wake_contract() -> None:
    source = NEWS_FETCH_WORKER.read_text(encoding="utf-8")
    init_source = source.split("def __init__", 1)[1].split("\n    async def on_close", 1)[0]
    claim_source = source.split("def run_once", 1)[1].split("\n    def _fetch_source", 1)[0]
    repository_source = NEWS_REPOSITORY.read_text(encoding="utf-8")
    claim_due_sources = repository_source.split("def claim_due_sources", 1)[1].split(
        "\n\n    @_news_repository_write\n    def start_fetch_run",
        1,
    )[0]
    settings_source = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    settings_class = settings_source.split("class NewsFetchWorkerSettings", 1)[1].split(
        "\n\nclass NewsItemProcessWorkerSettings",
        1,
    )[0]
    factory_source = (WORKER_FACTORIES / "news_intel.py").read_text(encoding="utf-8")
    fetch_factory_source = factory_source.split(
        'constructed["news_fetch"] = NewsFetchWorker(',
        1,
    )[1].split(
        '        else:\n            constructed["news_fetch"] = unavailable_worker',
        1,
    )[0]
    forbidden_source_tokens = (
        'getattr(self.settings, "statement_timeout_seconds"',
        'getattr(self.settings, "batch_size"',
        "getattr(self.news_settings",
        '"batch_size", 10',
        'getattr(self.settings, "lease_ms"',
        '"lease_ms", 60_000',
        "wake_bus",
    )
    forbidden_repository_tokens = (
        "_DEFAULT_SOURCE_CLAIM_LEASE_MS",
        "claim_lease_ms: int =",
    )
    forbidden_init_tokens = (
        "**kwargs",
        "super().__init__(**kwargs)",
        "settings: Any | None",
        "feed_client: NewsSourceProvider | None",
    )
    forbidden_factory_tokens = ("wake_bus=ctx.wake_bus",)
    violations = (
        [f"worker-source:{token}" for token in forbidden_source_tokens if token in source]
        + [
            f"repository:{token}"
            for token in forbidden_repository_tokens
            if token in repository_source or token in claim_due_sources
        ]
        + [f"worker-init:{token}" for token in forbidden_init_tokens if token in init_source]
        + [f"factory:{token}" for token in forbidden_factory_tokens if token in fetch_factory_source]
    )

    assert violations == []
    assert "news_fetch_settings_required" in init_source
    assert "news_fetch_db_required" in init_source
    assert "news_fetch_news_settings_required" in init_source
    assert "news_fetch_feed_client_required" in init_source
    assert "self.wake_emitter = wake_emitter" in init_source
    assert "configured_sources = tuple(self.news_settings.sources or ())" in source
    assert "statement_timeout_seconds=self.settings.statement_timeout_seconds" in source
    assert "claim_lease_ms=self._lease_ms()" in claim_source
    assert 'positive_worker_setting_int(self.settings, "batch_size", worker_name=self.name)' in source
    assert 'positive_worker_setting_int(self.settings, "lease_ms", worker_name=self.name)' in source
    assert "self.wake_emitter.notify_news_item_written" in source
    assert "_notify_news_page_dirty(\n            self.wake_emitter," in source
    assert "wake_emitter=ctx.wake_bus" in fetch_factory_source
    assert "batch_size: int = Field(default=5, ge=1)" in settings_class
    assert "lease_ms: int = Field(default=60_000, ge=1)" in settings_class
    assert "statement_timeout_seconds: float = Field(default=30.0, ge=0)" in settings_class


@pytest.mark.architecture
def test_news_page_projection_worker_uses_formal_settings_contract_without_runtime_defaults() -> None:
    source = NEWS_PAGE_PROJECTION_WORKER.read_text(encoding="utf-8")
    init_source = source.split("def __init__", 1)[1].split("\n    async def run_once", 1)[0]
    settings_source = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    settings_class = settings_source.split("class NewsPageProjectionWorkerSettings", 1)[1].split(
        "\n\nclass NewsSourceQualityProjectionWorkerSettings",
        1,
    )[0]
    factory_source = (WORKER_FACTORIES / "news_intel.py").read_text(encoding="utf-8")
    page_factory_source = factory_source.split(
        'constructed["news_page_projection"] = NewsPageProjectionWorker(',
        1,
    )[1].split(
        "    if workers.news_source_quality_projection.enabled:",
        1,
    )[0]
    forbidden_source_tokens = (
        'getattr(self.settings, "statement_timeout_seconds"',
        'getattr(self.settings, "batch_size"',
        'getattr(self.settings, "lease_ms"',
        'getattr(self.settings, "retry_ms"',
        '"batch_size", 100',
        '"lease_ms", 120_000',
        '"retry_ms", 30_000',
    )
    forbidden_init_tokens = (
        "**kwargs",
        "wake_bus",
        "super().__init__(**kwargs)",
        "settings: Any | None",
    )
    forbidden_factory_tokens = ("wake_bus=ctx.wake_bus",)
    violations = (
        [f"worker-source:{token}" for token in forbidden_source_tokens if token in source]
        + [f"worker-init:{token}" for token in forbidden_init_tokens if token in init_source]
        + [f"factory:{token}" for token in forbidden_factory_tokens if token in page_factory_source]
    )

    assert violations == []
    assert "news_page_projection_settings_required" in init_source
    assert "news_page_projection_db_required" in init_source
    assert "statement_timeout_seconds=self.settings.statement_timeout_seconds" in source
    assert 'positive_worker_setting_int(self.settings, "batch_size", worker_name=self.name)' in source
    assert 'positive_worker_setting_int(self.settings, "lease_ms", worker_name=self.name)' in source
    assert 'positive_worker_setting_int(self.settings, "retry_ms", worker_name=self.name)' in source
    assert 'positive_worker_setting_int(self.settings, "max_attempts", worker_name=self.name)' in source
    assert "wake_bus=ctx.wake_bus" not in page_factory_source
    assert "batch_size: int = Field(default=100, ge=1)" in settings_class
    assert "lease_ms: int = Field(default=120_000, ge=1)" in settings_class
    assert "retry_ms: int = Field(default=30_000, ge=1)" in settings_class
    assert "statement_timeout_seconds: float = Field(default=30.0, ge=0)" in settings_class


@pytest.mark.architecture
def test_news_item_process_worker_uses_formal_settings_and_wake_contract_without_runtime_defaults() -> None:
    source = NEWS_ITEM_PROCESS_WORKER.read_text(encoding="utf-8")
    init_source = source.split("def __init__", 1)[1].split("\n    async def run_once", 1)[0]
    settings_source = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    settings_class = settings_source.split("class NewsItemProcessWorkerSettings", 1)[1].split(
        "\n\nclass NewsItemBriefWorkerSettings",
        1,
    )[0]
    factory_source = (WORKER_FACTORIES / "news_intel.py").read_text(encoding="utf-8")
    item_process_factory_source = factory_source.split(
        'constructed["news_item_process"] = NewsItemProcessWorker(',
        1,
    )[1].split(
        "    brief_provider = news_providers.brief_provider",
        1,
    )[0]
    forbidden_source_tokens = (
        'getattr(self.settings, "statement_timeout_seconds"',
        'getattr(self.settings, "batch_size"',
        'getattr(self.settings, "lease_ms"',
        'getattr(self.settings, "max_attempts"',
        'getattr(self.settings, "retry_delay_ms"',
        '"batch_size", 10',
        '"lease_ms", 120_000',
        '"max_attempts", 3',
        '"retry_delay_ms", 60_000',
    )
    forbidden_init_tokens = (
        "**kwargs",
        "wake_bus",
        "super().__init__(**kwargs)",
        "settings: Any | None",
    )
    forbidden_factory_tokens = ("wake_bus=ctx.wake_bus",)
    violations = (
        [f"worker-source:{token}" for token in forbidden_source_tokens if token in source]
        + [f"worker-init:{token}" for token in forbidden_init_tokens if token in init_source]
        + [f"factory:{token}" for token in forbidden_factory_tokens if token in item_process_factory_source]
    )

    assert violations == []
    assert "news_item_process_settings_required" in init_source
    assert "news_item_process_db_required" in init_source
    assert "self.wake_emitter = wake_emitter" in init_source
    assert "self.wake_emitter.notify_news_item_processed" in source
    assert "statement_timeout_seconds=self.settings.statement_timeout_seconds" in source
    assert 'positive_worker_setting_int(self.settings, "batch_size", worker_name=self.name)' in source
    assert 'positive_worker_setting_int(self.settings, "lease_ms", worker_name=self.name)' in source
    assert 'positive_worker_setting_int(self.settings, "max_attempts", worker_name=self.name)' in source
    assert 'positive_worker_setting_int(self.settings, "retry_delay_ms", worker_name=self.name)' in source
    assert "wake_emitter=ctx.wake_bus" in item_process_factory_source
    assert "batch_size: int = Field(default=10, ge=1)" in settings_class
    assert "lease_ms: int = Field(default=120_000, ge=1)" in settings_class
    assert "max_attempts: int = Field(default=3, ge=1)" in settings_class
    assert "retry_delay_ms: int = Field(default=60_000, ge=1)" in settings_class
    assert "statement_timeout_seconds: float = Field(default=30.0, ge=0)" in settings_class


@pytest.mark.architecture
def test_news_item_brief_worker_uses_formal_settings_and_wake_contract_without_runtime_defaults() -> None:
    source = NEWS_ITEM_BRIEF_WORKER.read_text(encoding="utf-8")
    init_source = source.split("def __init__", 1)[1].split("\n    async def run_once", 1)[0]
    settings_source = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    settings_class = settings_source.split("class NewsItemBriefWorkerSettings", 1)[1].split(
        "\n\nclass NewsPageProjectionWorkerSettings",
        1,
    )[0]
    factory_source = (WORKER_FACTORIES / "news_intel.py").read_text(encoding="utf-8")
    item_brief_factory_source = factory_source.split(
        "constructed[worker_name] = NewsItemBriefWorker(",
        1,
    )[1].split(
        "        else:\n            constructed[worker_name] = unavailable_worker",
        1,
    )[0]
    forbidden_source_tokens = (
        'getattr(self.settings, "statement_timeout_seconds"',
        'getattr(self.settings, "batch_size"',
        'getattr(self.settings, "lease_ms"',
        'getattr(self.settings, "retry_ms"',
        'getattr(self.settings, "backpressure_cooldown_ms"',
        '"batch_size", 5',
        '"lease_ms", 120_000',
        '"retry_ms", self._backpressure_cooldown_ms()',
        '"backpressure_cooldown_ms", 60_000',
        "max(1, int(queue_depth))",
        "limit=max(1, int(limit))",
        "missing_provider",
        "notify_news_item_brief_updated",
        "news_item_brief_updated",
    )
    forbidden_init_tokens = (
        "**kwargs",
        "wake_bus",
        "wake_emitter",
        "super().__init__(**kwargs)",
        "settings: Any | None",
        "provider: Any | None",
    )
    forbidden_factory_tokens = ("wake_bus=ctx.wake_bus", "wake_emitter=ctx.wake_bus")
    violations = (
        [f"worker-source:{token}" for token in forbidden_source_tokens if token in source]
        + [f"worker-init:{token}" for token in forbidden_init_tokens if token in init_source]
        + [f"factory:{token}" for token in forbidden_factory_tokens if token in item_brief_factory_source]
    )

    assert violations == []
    assert "news_item_brief_settings_required" in init_source
    assert "news_item_brief_db_required" in init_source
    assert "news_item_brief_provider_required" in init_source
    assert "self.wake_emitter = wake_emitter" not in init_source
    assert "notify_news_item_brief_updated" not in source
    assert "statement_timeout_seconds=self.settings.statement_timeout_seconds" in source
    assert 'positive_worker_setting_int(self.settings, "batch_size", worker_name=self.name)' in source
    assert 'positive_worker_setting_int(self.settings, "lease_ms", worker_name=self.name)' in source
    assert 'positive_worker_setting_int(self.settings, "retry_ms", worker_name=self.name)' in source
    assert 'positive_worker_setting_int(self.settings, "max_attempts", worker_name=self.name)' in source
    assert 'positive_worker_setting_int(self.settings, "backpressure_cooldown_ms", worker_name=self.name)' in source
    assert "required_nonnegative_int(" in source
    assert 'required_positive_int(limit, error_code="news_item_brief_claim_limit_required")' in source
    assert "news_item_brief_queue_depth_required" in source
    assert "wake_emitter=ctx.wake_bus" not in item_brief_factory_source
    assert "batch_size: int = Field(default=5, ge=1)" in settings_class
    assert "lease_ms: int = Field(default=120_000, ge=1)" in settings_class
    assert "retry_ms: int = Field(default=60_000, ge=1)" in settings_class
    assert "backpressure_cooldown_ms: int = Field(default=60_000, ge=1)" in settings_class
    assert "statement_timeout_seconds: float = Field(default=30.0, ge=0)" in settings_class


@pytest.mark.architecture
def test_news_source_quality_projection_worker_uses_formal_settings_and_wake_contract() -> None:
    source = NEWS_SOURCE_QUALITY_PROJECTION_WORKER.read_text(encoding="utf-8")
    init_source = source.split("def __init__", 1)[1].split("\n    async def run_once", 1)[0]
    settings_source = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    settings_class = settings_source.split("class NewsSourceQualityProjectionWorkerSettings", 1)[1].split(
        "\n\nclass WorkersSettings",
        1,
    )[0]
    factory_source = (WORKER_FACTORIES / "news_intel.py").read_text(encoding="utf-8")
    source_quality_factory_source = factory_source.split(
        'constructed["news_source_quality_projection"] = NewsSourceQualityProjectionWorker(',
        1,
    )[1].split(
        "    return constructed",
        1,
    )[0]
    forbidden_source_tokens = (
        'getattr(self.settings, "statement_timeout_seconds"',
        'getattr(self.settings, "windows"',
        'getattr(self.settings, "batch_size"',
        'getattr(self.settings, "lease_ms"',
        'getattr(self.settings, "retry_ms"',
        '"batch_size", 100',
        '"lease_ms", 120_000',
        '"retry_ms", 30_000',
        '("24h", "7d")',
    )
    forbidden_init_tokens = (
        "**kwargs",
        "wake_bus",
        "super().__init__(**kwargs)",
        "settings: Any | None",
    )
    forbidden_factory_tokens = ("wake_bus=ctx.wake_bus",)
    violations = (
        [f"worker-source:{token}" for token in forbidden_source_tokens if token in source]
        + [f"worker-init:{token}" for token in forbidden_init_tokens if token in init_source]
        + [f"factory:{token}" for token in forbidden_factory_tokens if token in source_quality_factory_source]
    )

    assert violations == []
    assert "news_source_quality_projection_settings_required" in init_source
    assert "news_source_quality_projection_db_required" in init_source
    assert "self.wake_emitter = wake_emitter" in init_source
    assert "statement_timeout_seconds=self.settings.statement_timeout_seconds" in source
    assert "return tuple(str(window).strip().lower() for window in self.settings.windows)" in source
    assert 'positive_worker_setting_int(self.settings, "batch_size", worker_name=self.name)' in source
    assert 'positive_worker_setting_int(self.settings, "lease_ms", worker_name=self.name)' in source
    assert 'positive_worker_setting_int(self.settings, "retry_ms", worker_name=self.name)' in source
    assert 'positive_worker_setting_int(self.settings, "max_attempts", worker_name=self.name)' in source
    assert "_notify_news_page_dirty(\n            self.wake_emitter," in source
    assert "wake_emitter=ctx.wake_bus" in source_quality_factory_source
    assert "batch_size: int = Field(default=100, ge=1)" in settings_class
    assert "lease_ms: int = Field(default=120_000, ge=1)" in settings_class
    assert "retry_ms: int = Field(default=30_000, ge=1)" in settings_class
    assert "statement_timeout_seconds: float = Field(default=30.0, ge=0)" in settings_class
    assert 'windows: tuple[str, ...] = ("24h", "7d")' in settings_class


@pytest.mark.architecture
def test_token_radar_projection_worker_uses_formal_settings_and_wake_contract_without_runtime_defaults() -> None:
    source = TOKEN_RADAR_PROJECTION_WORKER.read_text(encoding="utf-8")
    projection_service_source = (SRC / "domains" / "token_intel" / "services" / "token_radar_projection.py").read_text(
        encoding="utf-8"
    )
    init_source = source.split("def __init__", 1)[1].split("\n    async def run_once", 1)[0]
    settings_source = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    settings_class = settings_source.split("class TokenRadarProjectionWorkerSettings", 1)[1].split(
        "\n\nclass CexOiRadarBoardWorkerSettings",
        1,
    )[0]
    per_worker_settings = settings_source.split("class PerWorkerSettings", 1)[1].split(
        "\n\nclass WorkerDefaults",
        1,
    )[0]
    factory_source = (WORKER_FACTORIES / "token_intel.py").read_text(encoding="utf-8")
    factory_block = factory_source.split(
        "worker_name: TokenRadarProjectionWorker(",
        1,
    )[1].split(
        "    }\n",
        1,
    )[0]
    ops_source = CLI_OPS.read_text(encoding="utf-8")
    forbidden_source_tokens = (
        "DEFAULT_WINDOWS",
        "DEFAULT_SCOPES",
        "DEFAULT_HOT_WINDOWS",
        "TOKEN_RADAR_VENUES",
        'getattr(settings, "windows"',
        'getattr(settings, "scopes"',
        'getattr(settings, "venues"',
        'getattr(settings, "hot_windows"',
        'getattr(settings, "batch_size"',
        'getattr(settings, "cold_interval_seconds"',
        'getattr(settings, "private_cache_retention_enabled"',
        'getattr(settings, "private_cache_retention_ms"',
        'getattr(self.settings, "statement_timeout_seconds"',
        '"batch_size", 100',
        '"cold_interval_seconds", 60.0',
        '"statement_timeout_seconds", None',
        "self.limit = max(1, int(settings.batch_size))",
        "self.lease_ms = max(1, int(settings.lease_ms))",
        "self.retry_ms = max(1, int(settings.retry_ms))",
        "self.max_attempts = max(1, int(settings.max_attempts))",
        "self.private_cache_retention_enabled = bool(settings.private_cache_retention_enabled)",
        "self.private_cache_retention_ms = max(1, int(settings.private_cache_retention_ms))",
        "self.cold_interval_ms = int(float(settings.cold_interval_seconds) * 1000)",
        "self.limit = max(1, int(limit))",
        "return computed_at_ms - int(since_ms) >= max(0, int(interval_ms))",
        "self.wake_bus",
        "wake_bus:",
        "wake_bus=",
        "_dirty_target_lease_ms",
    )
    forbidden_service_tokens = (
        "DIRTY_TARGET_LEASE_MS",
        "DIRTY_TARGET_RETRY_MS",
    )
    forbidden_init_tokens = (
        "**kwargs",
        "super().__init__(**kwargs)",
        "settings: Any | None",
    )
    forbidden_factory_tokens = ("wake_bus=ctx.wake_bus",)
    violations = (
        [f"worker-source:{token}" for token in forbidden_source_tokens if token in source]
        + [f"projection-service:{token}" for token in forbidden_service_tokens if token in projection_service_source]
        + [f"worker-init:{token}" for token in forbidden_init_tokens if token in init_source]
        + [f"factory:{token}" for token in forbidden_factory_tokens if token in factory_block]
    )

    assert violations == []
    assert "token_radar_projection_settings_required" in init_source
    assert "token_radar_projection_db_required" in init_source
    assert "self.wake_emitter = wake_emitter" in init_source
    assert "self.windows = tuple(str(window).strip().lower() for window in settings.windows)" in source
    assert "self.scopes = tuple(str(scope).strip().lower() for scope in settings.scopes)" in source
    assert "self.venues = tuple(str(venue).strip().lower() for venue in settings.venues)" in source
    assert "hot_windows = tuple(str(window).strip().lower() for window in settings.hot_windows)" in source
    assert "token_radar_projection_batch_size_required" in source
    assert "token_radar_projection_lease_ms_required" in source
    assert "token_radar_projection_retry_ms_required" in source
    assert "token_radar_projection_max_attempts_required" in source
    assert "token_radar_projection_private_cache_retention_enabled_required" in source
    assert "token_radar_projection_private_cache_retention_ms_required" in source
    assert "token_radar_projection_cold_interval_seconds_required" in source
    assert "token_radar_projection_limit_required" in source
    assert "token_radar_projection_interval_ms_required" in source
    assert "def _required_positive_int(value: Any, *, error_code: str) -> int:" in source
    assert "def _required_nonnegative_int(value: Any, *, error_code: str) -> int:" in source
    assert "def _required_bool(value: Any, *, error_code: str) -> bool:" in source
    assert "def _required_nonnegative_seconds_ms(value: Any, *, error_code: str) -> int:" in source
    assert "isinstance(value, bool)" in source
    assert "lease_ms=self.lease_ms" in source
    assert '"retry_ms": self.retry_ms' in source
    assert "projection.prune_private_cache(" in source
    assert '"retention_ms": self.private_cache_retention_ms' in source
    assert "statement_timeout_seconds=self.settings.statement_timeout_seconds" in source
    assert "self.wake_emitter.notify_token_radar_updated" in source
    assert "wake_emitter=ctx.wake_bus" in factory_block
    assert "wake_bus=db.wake_emitter()" not in ops_source
    assert "wake_emitter=db.wake_emitter()" in ops_source
    assert "batch_size: int = Field(default=100, ge=1)" in settings_class
    assert "statement_timeout_seconds: float = Field(default=120.0, ge=0)" in settings_class
    assert 'windows: tuple[str, ...] = ("5m", "1h", "4h", "24h")' in settings_class
    assert 'scopes: tuple[str, ...] = ("all", "matched")' in settings_class
    assert 'hot_windows: tuple[str, ...] = ("5m",)' in settings_class
    assert "cold_interval_seconds: float = Field(default=60.0, ge=0)" in settings_class
    assert "lease_ms: int = Field(default=120_000, ge=1)" in per_worker_settings
    assert "retry_ms: int = Field(default=30_000, ge=1)" in settings_class
    assert "private_cache_retention_enabled: bool = True" in settings_class
    assert "private_cache_retention_ms: int = Field(default=172_800_000, ge=1)" in settings_class


@pytest.mark.architecture
def test_narrative_admission_worker_uses_formal_settings_contract_without_runtime_defaults() -> None:
    source = NARRATIVE_ADMISSION_WORKER.read_text(encoding="utf-8")
    service_source = NARRATIVE_ADMISSION_SERVICE.read_text(encoding="utf-8")
    init_source = source.split("def __init__", 1)[1].split("\n    async def run_once", 1)[0]
    settings_source = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    settings_class = settings_source.split("class NarrativeAdmissionWorkerSettings", 1)[1].split(
        "\n\nclass NotificationRuleWorkerSettings",
        1,
    )[0]
    factory_source = (WORKER_FACTORIES / "narrative_intel.py").read_text(encoding="utf-8")
    factory_block = factory_source.split(
        '"narrative_admission": NarrativeAdmissionWorker(',
        1,
    )[1].split(
        "        )\n",
        1,
    )[0]
    forbidden_source_tokens = (
        'getattr(settings, "hot_rank_limit"',
        'getattr(settings, "min_rank_score"',
        'getattr(self.settings, "admission_limit"',
        'getattr(self.settings, "source_limit"',
        'getattr(self.settings, "max_attempts"',
        'getattr(self.settings, "lease_seconds"',
        'getattr(self.settings, "error_retry_seconds"',
        'getattr(self.settings, "statement_timeout_seconds"',
        '"admission_limit", 200',
        '"source_limit", 2000',
        '"max_attempts", 3',
        '"lease_seconds", 60',
        '"error_retry_seconds", 60',
        '"statement_timeout_seconds", None',
        "admission_limit = max(1, int(self.settings.admission_limit))",
        "source_limit = max(1, int(self.settings.source_limit))",
        "lease_ms = max(1, int(self.settings.lease_ms))",
        "retry_ms = max(1, int(self.settings.retry_ms))",
        "wake_bus",
        "wake_emitter",
    )
    forbidden_init_tokens = (
        "**kwargs",
        "super().__init__(**kwargs)",
        "settings: Any | None",
    )
    forbidden_factory_tokens = (
        "wake_bus=ctx.wake_bus",
        "wake_emitter=ctx.wake_bus",
    )
    forbidden_service_tokens = (
        "hot_rank_limit: int =",
        "min_rank_score: int =",
        "self.hot_rank_limit = max(1, int(hot_rank_limit))",
        "self.min_rank_score = max(0, int(min_rank_score))",
        "carry_ttl_ms",
    )
    violations = (
        [f"worker-source:{token}" for token in forbidden_source_tokens if token in source]
        + [f"worker-init:{token}" for token in forbidden_init_tokens if token in init_source]
        + [f"factory:{token}" for token in forbidden_factory_tokens if token in factory_block]
        + [f"service:{token}" for token in forbidden_service_tokens if token in service_source]
    )

    assert violations == []
    assert "narrative_admission_settings_required" in init_source
    assert "narrative_admission_db_required" in init_source
    assert "hot_rank_limit=int(settings.hot_rank_limit)" in source
    assert "min_rank_score=int(settings.min_rank_score)" in source
    assert "hot_rank_limit: int," in service_source
    assert "min_rank_score: int," in service_source
    assert "self.admission_limit = _positive_worker_setting_int(" in source
    assert 'settings,\n            "admission_limit",' in source
    assert 'error_code="narrative_admission_admission_limit_required"' in source
    assert "self.source_limit = _positive_worker_setting_int(" in source
    assert 'settings,\n            "source_limit",' in source
    assert 'error_code="narrative_admission_source_limit_required"' in source
    assert "self.lease_ms = _positive_worker_setting_int(" in source
    assert 'settings,\n            "lease_ms",' in source
    assert 'error_code="narrative_admission_lease_ms_required"' in source
    assert "self.retry_ms = _positive_worker_setting_int(" in source
    assert 'settings,\n            "retry_ms",' in source
    assert 'error_code="narrative_admission_retry_ms_required"' in source
    assert "self.max_attempts = _positive_worker_setting_int(" in source
    assert 'settings,\n            "max_attempts",' in source
    assert 'error_code="narrative_admission_max_attempts_required"' in source
    assert "max_attempts=self.max_attempts" in source
    assert "worker_name=self.name" in source
    assert "narrative_admission_hot_rank_limit_required" in service_source
    assert "narrative_admission_min_rank_score_required" in service_source
    assert "statement_timeout_seconds=self.settings.statement_timeout_seconds" in source
    assert "wake_waiter=ctx.db.wake_listener" in factory_block
    assert "lease_ms: int = Field(default=60_000, ge=1)" in settings_class
    assert "retry_ms: int = Field(default=60_000, ge=1)" in settings_class
    assert "max_attempts: int = Field(default=3, ge=1)" in settings_class
    assert "statement_timeout_seconds: float = Field(default=30.0, ge=0)" in settings_class
    assert "admission_limit: int = Field(default=200, ge=1)" in settings_class
    assert "source_limit: int = Field(default=2000, ge=1)" in settings_class


@pytest.mark.architecture
def test_macro_sync_worker_and_service_use_formal_settings_wake_contract_without_runtime_defaults() -> None:
    worker_source = MACRO_SYNC_WORKER.read_text(encoding="utf-8")
    init_source = worker_source.split("def __init__", 1)[1].split("\n    async def run_once", 1)[0]
    service_source = MACRO_SYNC_SERVICE.read_text(encoding="utf-8")
    settings_source = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    settings_class = settings_source.split("class MacroSyncWorkerSettings", 1)[1].split(
        "\n\nclass NarrativeAdmissionWorkerSettings",
        1,
    )[0]
    factory_source = (WORKER_FACTORIES / "macro_intel.py").read_text(encoding="utf-8")
    macro_factory_source = factory_source.split(
        "constructed[worker_name] = MacroSyncWorker(",
        1,
    )[1].split(
        "    elif workers.macro_sync.enabled:",
        1,
    )[0]
    forbidden_worker_tokens = (
        "**kwargs",
        "super().__init__(**kwargs)",
        "wake_bus",
        'getattr(self.settings, "batch_size"',
        '"batch_size", 1',
        "configured = max(1, int(self.settings.batch_size))",
    )
    forbidden_service_tokens = (
        "def _sync_settings",
        "getattr(sync_settings",
        "self.wake_bus",
        "wake_bus:",
        "wake_bus=",
        '"source_name", "macrodata-cli"',
        '"bundle_name", "macro-core"',
        "self.sync_settings.bundle_name",
        '"bootstrap_lookback_days", 1095',
        '"max_window_days", 31',
        '"steady_overlap_days", 7',
        '"interval_seconds", 900.0',
        '"max_bootstrap_windows_per_cycle", 1',
        '"max_attempts", 8',
        '"lease_ms", 300_000',
        '"retry_delay_ms", 900_000',
        '"statement_timeout_seconds", None',
        "bootstrap_lookback_days=int(self.sync_settings.bootstrap_lookback_days)",
        "max_window_days=int(self.sync_settings.max_window_days)",
        "steady_overlap_days=int(self.sync_settings.steady_overlap_days)",
        "steady_interval_seconds=float(self.sync_settings.interval_seconds)",
        "max_bootstrap_windows_per_cycle=int(self.sync_settings.max_bootstrap_windows_per_cycle)",
        "max_attempts=int(self.sync_settings.max_attempts)",
    )
    forbidden_factory_tokens = ("wake_bus=ctx.wake_bus",)
    violations = (
        [f"worker:{token}" for token in forbidden_worker_tokens if token in worker_source]
        + [f"service:{token}" for token in forbidden_service_tokens if token in service_source]
        + [f"factory:{token}" for token in forbidden_factory_tokens if token in macro_factory_source]
    )

    assert violations == []
    assert "macro_sync_settings_required" in init_source
    assert "macro_sync_db_required" in init_source
    assert "macro_sync_settings_root_required" in init_source
    assert "self.wake_emitter = wake_emitter" in init_source
    assert "macro_sync_batch_size_required" in worker_source
    assert "def _required_positive_int(value: Any, *, error_code: str) -> int:" in worker_source
    assert "isinstance(value, bool)" in worker_source
    assert "self.sync_settings = _require_macro_sync_worker_settings(settings)" in service_source
    assert "source_name=str(self.sync_settings.source_name)" in service_source
    assert "for bundle_name in _macro_sync_bundle_names(self.sync_settings):" in service_source
    assert "bootstrap_lookback_days=self.sync_settings.bootstrap_lookback_days" in service_source
    assert "steady_interval_seconds=self.sync_settings.interval_seconds" in service_source
    scheduler_source = (SRC / "domains/macro_intel/services/macro_sync_scheduler.py").read_text(encoding="utf-8")
    assert "max(1, int(bootstrap_lookback_days))" not in scheduler_source
    assert "max(1, int(max_bootstrap_windows_per_cycle))" not in scheduler_source
    assert "max(1, int(steady_overlap_days))" not in scheduler_source
    assert "max(1, int(max_window_days))" not in scheduler_source
    assert "macro_sync_bootstrap_lookback_days_required" in scheduler_source
    assert "macro_sync_max_window_days_required" in scheduler_source
    assert "macro_sync_max_bootstrap_windows_per_cycle_required" in scheduler_source
    assert "lease_ms=int(self.sync_settings.lease_ms)" in service_source
    assert "retry_delay_ms=int(self.sync_settings.retry_delay_ms)" in service_source
    assert "statement_timeout_seconds=self.sync_settings.statement_timeout_seconds" in service_source
    assert "wake_emitter=ctx.wake_bus" in macro_factory_source
    assert "batch_size: int = Field(default=3, ge=1)" in settings_class
    assert "bundle_names: tuple[str, ...] = (" in settings_class
    assert "statement_timeout_seconds: float = Field(default=30.0, ge=0)" in settings_class
    assert "lease_ms: int = Field(default=300_000, ge=1)" in settings_class
    assert "retry_delay_ms: int = Field(default=900_000, ge=1)" in settings_class


@pytest.mark.architecture
def test_macro_view_projection_worker_uses_formal_settings_and_wake_contract_without_runtime_defaults() -> None:
    source = MACRO_VIEW_PROJECTION_WORKER.read_text(encoding="utf-8")
    init_source = source.split("def __init__", 1)[1].split("\n    async def run_once", 1)[0]
    settings_source = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    settings_class = settings_source.split("class MacroViewProjectionWorkerSettings", 1)[1].split(
        "\n\nclass MacroDailyBriefProjectionWorkerSettings",
        1,
    )[0]
    factory_source = (WORKER_FACTORIES / "macro_intel.py").read_text(encoding="utf-8")
    macro_factory_source = factory_source.split(
        "constructed[worker_name] = MacroViewProjectionWorker(",
        1,
    )[1].split(
        "    if workers.macro_daily_brief_projection.enabled:",
        1,
    )[0]
    forbidden_source_tokens = (
        "MACRO_VIEW_HISTORY_LIMIT_PER_SERIES",
        "MACRO_VIEW_HISTORY_LOOKBACK_DAYS",
        'getattr(self.settings, "statement_timeout_seconds"',
        'getattr(self.settings, "batch_size"',
        'getattr(self.settings, "lookback_days"',
        'getattr(self.settings, "limit_per_series"',
        'getattr(self.settings, "lease_ms"',
        'getattr(self.settings, "retry_ms"',
        '"lease_ms", 300_000',
        '"retry_ms", 300_000',
        "limit=1,",
        "return max(1, int(self.settings.batch_size))",
        "return max(1, int(self.settings.lookback_days))",
        "return max(1, int(self.settings.limit_per_series))",
        "return max(1, int(self.settings.lease_ms))",
        "return max(1, int(self.settings.retry_ms))",
    )
    forbidden_init_tokens = (
        "**kwargs",
        "wake_bus",
        "super().__init__(**kwargs)",
        "settings: Any | None",
    )
    forbidden_factory_tokens = ("wake_bus=ctx.wake_bus",)
    violations = (
        [f"worker-source:{token}" for token in forbidden_source_tokens if token in source]
        + [f"worker-init:{token}" for token in forbidden_init_tokens if token in init_source]
        + [f"factory:{token}" for token in forbidden_factory_tokens if token in macro_factory_source]
    )

    assert violations == []
    assert "macro_view_projection_settings_required" in init_source
    assert "macro_view_projection_db_required" in init_source
    assert "self.wake_emitter = wake_emitter" in init_source
    assert "limit=self._batch_size()" in source
    assert "self.wake_emitter.notify_macro_view_snapshot_updated" in source
    assert "statement_timeout_seconds=self.settings.statement_timeout_seconds" in source
    assert "macro_view_projection_batch_size_required" in source
    assert "macro_view_projection_lookback_days_required" in source
    assert "macro_view_projection_limit_per_series_required" in source
    assert "macro_view_projection_lease_ms_required" in source
    assert "macro_view_projection_retry_ms_required" in source
    assert "macro_view_projection_max_attempts_required" in source
    assert "def _required_positive_int(value: Any, *, error_code: str) -> int:" in source
    assert "def _required_min_int(value: Any, *, minimum: int, error_code: str) -> int:" in source
    assert "isinstance(value, bool)" in source
    assert "wake_emitter=ctx.wake_bus" in macro_factory_source
    assert "batch_size: int = Field(default=250, ge=1)" in settings_class
    assert "lease_ms: int = Field(default=300_000, ge=1)" in settings_class
    assert "retry_ms: int = Field(default=300_000, ge=1)" in settings_class
    assert "max_attempts: int = Field(default=3, ge=1)" in settings_class
    assert "lookback_days: int = Field(default=1095, ge=1095)" in settings_class
    assert "limit_per_series: int = Field(default=800, ge=800)" in settings_class
    assert "statement_timeout_seconds: float = Field(default=30.0, ge=0)" in settings_class


@pytest.mark.architecture
def test_macro_daily_brief_projection_worker_uses_formal_settings_contract_without_runtime_defaults() -> None:
    source = MACRO_DAILY_BRIEF_PROJECTION_WORKER.read_text(encoding="utf-8")
    init_source = source.split("def __init__", 1)[1].split("\n    async def run_once", 1)[0]
    settings_source = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    settings_class = settings_source.split("class MacroDailyBriefProjectionWorkerSettings", 1)[1].split(
        "\n\nclass MacroSyncWorkerSettings",
        1,
    )[0]
    factory_source = (WORKER_FACTORIES / "macro_intel.py").read_text(encoding="utf-8")
    factory_block = factory_source.split(
        "constructed[worker_name] = MacroDailyBriefProjectionWorker(",
        1,
    )[1].split("    return constructed", 1)[0]
    forbidden_tokens = (
        "**kwargs",
        "super().__init__(**kwargs)",
        'getattr(self.settings, "statement_timeout_seconds"',
        '"statement_timeout_seconds", None',
        "wake_bus",
    )
    violations = [token for token in forbidden_tokens if token in source]

    assert violations == []
    assert "macro_daily_brief_projection_settings_required" in init_source
    assert "macro_daily_brief_projection_db_required" in init_source
    assert "statement_timeout_seconds=self.settings.statement_timeout_seconds" in source
    assert "settings=workers.macro_daily_brief_projection" in factory_block
    assert "wake_waiter=ctx.db.wake_listener" in factory_block
    assert "statement_timeout_seconds: float = Field(default=30.0, ge=0)" in settings_class


@pytest.mark.architecture
def test_market_tick_current_projection_worker_uses_formal_settings_contract_without_runtime_defaults() -> None:
    source = MARKET_TICK_CURRENT_PROJECTION_WORKER.read_text(encoding="utf-8")
    forbidden_tokens = (
        "DEFAULT_RETRY_MS",
        'getattr(self.settings, "statement_timeout_seconds", None)',
        'getattr(self.settings, "batch_size"',
        'getattr(self.settings, "lease_ms"',
        'getattr(self.settings, "retry_ms"',
        '"lease_ms", 120_000',
        '"batch_size", 100',
        "limit=max(1, int(self.settings.batch_size))",
        "lease_ms=max(1, int(self.settings.lease_ms))",
        "retry_ms=max(1, int(self.settings.retry_ms))",
        "max_attempts=max(1, int(self.settings.max_attempts))",
    )
    violations = [token for token in forbidden_tokens if token in source]

    assert violations == []
    assert source.count("statement_timeout_seconds=self.settings.statement_timeout_seconds") == 3
    assert "market_tick_current_batch_size_required" in source
    assert "market_tick_current_lease_ms_required" in source
    assert "market_tick_current_retry_ms_required" in source
    assert "market_tick_current_max_attempts_required" in source
    assert "def _required_positive_int(value: Any, *, error_code: str) -> int:" in source
    assert "isinstance(value, bool)" in source


@pytest.mark.architecture
def test_token_capture_tier_worker_constructor_uses_formal_settings_contract_without_synthetic_defaults() -> None:
    source = TOKEN_CAPTURE_TIER_WORKER.read_text(encoding="utf-8")
    init_source = source.split("def __init__", 1)[1].split("\n    async def run_once", 1)[0]
    project_source = source.split("def project_once", 1)[1].split("\n\n@dataclass", 1)[0]
    factory_source = (WORKER_FACTORIES / "asset_market.py").read_text(encoding="utf-8")
    capture_factory_source = factory_source.split(
        'constructed["token_capture_tier"] = TokenCaptureTierWorker(',
        1,
    )[1].split(
        "\n            )",
        1,
    )[0]
    forbidden_source_tokens = (
        "from types import SimpleNamespace",
        "DEFAULT_BATCH_SIZE",
        "DEFAULT_WS_LIMIT",
        "DEFAULT_POLL_LIMIT",
        "DEFAULT_LEASE_MS",
        "def _settings",
        "model_dump",
        "vars(",
        "SimpleNamespace(",
        "SimpleNamespace(**",
        "__dict__",
    )
    forbidden_init_tokens = (
        "resolved_settings",
        "db: Any | None",
        "pool_bundle or db",
        "interval_seconds:",
        "batch_size:",
        "ws_limit:",
        "poll_limit:",
        'getattr(settings, "',
        'getattr(resolved_settings, "',
        'getattr(self.settings, "lease_ms"',
        "max(1, int(settings.batch_size))",
        "max(0, int(settings.ws_limit))",
        "max(0, int(settings.poll_limit))",
    )
    forbidden_factory_tokens = (
        "batch_size=workers.token_capture_tier.batch_size",
        "ws_limit=workers.token_capture_tier.ws_limit",
        "poll_limit=workers.token_capture_tier.poll_limit",
        "db=",
    )
    violations = (
        [f"worker-source:{token}" for token in forbidden_source_tokens if token in source]
        + [f"worker-init:{token}" for token in forbidden_init_tokens if token in init_source]
        + [f"factory:{token}" for token in forbidden_factory_tokens if token in capture_factory_source]
    )

    assert violations == []
    assert "if settings is None:" in init_source
    assert "token_capture_tier_settings_required" in init_source
    assert "if pool_bundle is None:" in init_source
    assert "token_capture_tier_db_required" in init_source
    assert "token_capture_tier_batch_size_required" in init_source
    assert "token_capture_tier_ws_limit_required" in init_source
    assert "token_capture_tier_poll_limit_required" in init_source
    assert "token_capture_tier_lease_ms_required" in source
    assert "token_capture_tier_project_batch_size_required" in project_source
    assert "token_capture_tier_project_ws_limit_required" in project_source
    assert "token_capture_tier_project_poll_limit_required" in project_source
    assert "def _required_positive_int(value: Any, *, error_code: str) -> int:" in source
    assert "def _required_nonnegative_int(value: Any, *, error_code: str) -> int:" in source
    assert "isinstance(value, bool)" in source
    assert "batch_size: int," in project_source
    assert "ws_limit: int," in project_source
    assert "poll_limit: int," in project_source
    assert "settings=workers.token_capture_tier" in capture_factory_source
    assert "pool_bundle=ctx.db" in capture_factory_source


@pytest.mark.architecture
def test_event_anchor_backfill_worker_constructor_uses_formal_runtime_contract_without_synthetic_defaults() -> None:
    source = EVENT_ANCHOR_BACKFILL_WORKER.read_text(encoding="utf-8")
    init_source = source.split("def __init__", 1)[1].split("\n    async def run_once", 1)[0]
    session_source = source.split("def _worker_session", 1)[1].split(
        "\n    @contextmanager\n    def _transaction_session",
        1,
    )[0]
    factory_source = (WORKER_FACTORIES / "asset_market.py").read_text(encoding="utf-8")
    backfill_factory_source = factory_source.split(
        'constructed["event_anchor_backfill"] = EventAnchorBackfillWorker(',
        1,
    )[1].split(
        "\n        )",
        1,
    )[0]
    forbidden_source_tokens = (
        "from types import SimpleNamespace",
        "DEFAULT_BATCH_SIZE",
        "DEFAULT_CONCURRENCY",
        "DEFAULT_MIN_AGE_MS",
        "DEFAULT_ACTIVE_WINDOW_MS",
        "DEFAULT_MAX_ANCHOR_LAG_MS",
        "DEFAULT_INTERVAL_SECONDS",
        "DEFAULT_LEASE_MS",
        "def _settings",
        "model_dump",
        "vars(",
        "SimpleNamespace(",
        "SimpleNamespace(**",
        "__dict__",
        'getattr(self.settings, "statement_timeout_seconds", None)',
    )
    forbidden_init_tokens = (
        "resolved_settings",
        "dex_quote_market",
        "cex_market",
        "wake_bus",
        "db: Any | None",
        "pool_bundle or db",
        "interval_seconds:",
        "batch_size:",
        "concurrency:",
        "min_age_ms:",
        "active_window_ms:",
        "max_anchor_lag_ms:",
        'getattr(settings, "',
        'getattr(resolved_settings, "',
        "max(1, int(settings.",
        "max(0, int(settings.",
    )
    forbidden_factory_tokens = (
        "batch_size=workers.event_anchor_backfill.batch_size",
        "concurrency=workers.event_anchor_backfill.concurrency",
        "min_age_ms=workers.event_anchor_backfill.min_age_ms",
        "active_window_ms=workers.event_anchor_backfill.active_window_ms",
        "max_anchor_lag_ms=workers.event_anchor_backfill.max_anchor_lag_ms",
        "db=",
        "wake_bus=",
        "dex_quote_market=",
        "cex_market=",
    )
    violations = (
        [f"worker-source:{token}" for token in forbidden_source_tokens if token in source]
        + [f"worker-init:{token}" for token in forbidden_init_tokens if token in init_source]
        + [f"factory:{token}" for token in forbidden_factory_tokens if token in backfill_factory_source]
    )

    assert violations == []
    assert "if settings is None:" in init_source
    assert "event_anchor_backfill_settings_required" in init_source
    assert "if pool_bundle is None:" in init_source
    assert "event_anchor_backfill_db_required" in init_source
    assert "if providers is None:" in init_source
    assert "event_anchor_backfill_providers_required" in init_source
    assert "event_anchor_backfill_batch_size_required" in init_source
    assert "event_anchor_backfill_concurrency_required" in init_source
    assert "event_anchor_backfill_max_attempts_required" in init_source
    assert "event_anchor_backfill_min_age_ms_required" in init_source
    assert "event_anchor_backfill_lease_ms_required" in init_source
    assert "event_anchor_backfill_active_window_ms_required" in init_source
    assert "event_anchor_backfill_max_anchor_lag_ms_required" in init_source
    assert "def _required_positive_int(value: Any, *, error_code: str) -> int:" in source
    assert "def _required_nonnegative_int(value: Any, *, error_code: str) -> int:" in source
    assert "isinstance(value, bool)" in source
    assert "statement_timeout_seconds=self.settings.statement_timeout_seconds" in session_source
    assert "settings=workers.event_anchor_backfill" in backfill_factory_source
    assert "pool_bundle=ctx.db" in backfill_factory_source
    assert "providers=asset_market" in backfill_factory_source
    assert "wake_emitter=ctx.wake_bus" in backfill_factory_source


@pytest.mark.architecture
def test_ingest_event_anchor_window_uses_formal_settings_without_service_defaults() -> None:
    ingest_source = INGEST_SERVICE.read_text(encoding="utf-8")
    bootstrap_source = APP_RUNTIME_BOOTSTRAP.read_text(encoding="utf-8")
    pooled_init_source = bootstrap_source.split("class _PooledIngestStore", 1)[1].split(
        "\n    def insert_raw_frame",
        1,
    )[0]
    ingest_helper_source = bootstrap_source.split("def _ingest_service_for_repos", 1)[1].split(
        "\n\n\ndef _prepared_value",
        1,
    )[0]
    prepared_value_source = bootstrap_source.split("def _prepared_value", 1)[1].split(
        "\n\n\ndef _now_ms",
        1,
    )[0]
    assemble_source = bootstrap_source.split("def _assemble_runtime", 1)[1].split(
        "\n\nclass _PooledIngestStore",
        1,
    )[0]
    forbidden_ingest_tokens = (
        "DEFAULT_EVENT_ANCHOR_ACTIVE_WINDOW_MS",
        "event_anchor_active_window_ms: int =",
        "max(1, int(event_anchor_active_window_ms))",
    )
    forbidden_bootstrap_tokens = (
        "event_anchor_active_window_ms: int = 300_000",
        "event_anchor_active_window_ms: int =",
        "max(1, int(event_anchor_active_window_ms))",
    )
    violations = [f"ingest:{token}" for token in forbidden_ingest_tokens if token in ingest_source] + [
        f"bootstrap:{token}"
        for token in forbidden_bootstrap_tokens
        if token in pooled_init_source or token in ingest_helper_source
    ]

    assert violations == []
    assert "event_anchor_active_window_ms: int," in ingest_source
    assert "event_anchor_active_window_ms: int," in pooled_init_source
    assert "event_anchor_active_window_ms: int," in ingest_helper_source
    assert "event_anchor_active_window_ms=workers.event_anchor_backfill.active_window_ms" in assemble_source
    assert "require_event_anchor_active_window_ms(event_anchor_active_window_ms)" in ingest_source
    assert "require_event_anchor_active_window_ms(event_anchor_active_window_ms)" in pooled_init_source
    assert "event_anchor_active_window_ms_required" in ingest_source
    assert "if isinstance(prepared, dict)" not in prepared_value_source
    assert "PreparedIngest" in prepared_value_source
    assert "prepared_ingest_contract_required" in prepared_value_source


@pytest.mark.architecture
def test_token_profile_current_worker_uses_formal_settings_contract_without_runtime_defaults() -> None:
    source = TOKEN_PROFILE_CURRENT_WORKER.read_text(encoding="utf-8")
    rebuild_source = source.split("def _rebuild_once", 1)[1].split("\n\n\ndef rebuild_token_profile_current_once", 1)[0]
    helper_signature = source.split("def rebuild_token_profile_current_once", 1)[1].split(") -> dict[str, Any]:", 1)[0]
    settings_source = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    settings_class = settings_source.split("class TokenProfileCurrentWorkerSettings", 1)[1].split(
        "\n\nclass TokenCaptureTierWorkerSettings",
        1,
    )[0]
    forbidden_tokens = (
        "DEFAULT_LEASE_MS",
        "DEFAULT_RETRY_MS",
        'getattr(self.settings, "statement_timeout_seconds", None)',
        'getattr(self.settings, "batch_size"',
        'getattr(self.settings, "lease_ms"',
        'getattr(self.settings, "retry_ms"',
        "limit: int =",
        "lease_owner: str =",
        "lease_ms: int =",
        "retry_ms: int =",
        "limit=max(1, int(self.settings.batch_size))",
        "lease_ms=max(1, int(self.settings.lease_ms))",
        "retry_ms=max(1, int(self.settings.retry_ms))",
    )
    violations = [token for token in forbidden_tokens if token in source]

    assert violations == []
    assert "statement_timeout_seconds=self.settings.statement_timeout_seconds" in rebuild_source
    assert "token_profile_current_batch_size_required" in rebuild_source
    assert "token_profile_current_lease_ms_required" in rebuild_source
    assert "token_profile_current_retry_ms_required" in rebuild_source
    assert "def _required_positive_int(value: Any, *, error_code: str) -> int:" in source
    assert "isinstance(value, bool)" in source
    assert "limit: int," in helper_signature
    assert "lease_owner: str," in helper_signature
    assert "lease_ms: int," in helper_signature
    assert "retry_ms: int," in helper_signature
    assert "retry_ms: int = Field(default=30_000, ge=1)" in settings_class


@pytest.mark.architecture
def test_token_image_mirror_worker_uses_formal_settings_contract_without_runtime_defaults() -> None:
    source = TOKEN_IMAGE_MIRROR_WORKER.read_text(encoding="utf-8")
    service_source = TOKEN_IMAGE_MIRROR_SERVICE.read_text(encoding="utf-8")
    settings_source = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    settings_class = settings_source.split("class TokenImageMirrorWorkerSettings", 1)[1].split(
        "\n\nclass TokenProfileCurrentWorkerSettings",
        1,
    )[0]
    forbidden_tokens = (
        "DEFAULT_LEASE_MS",
        "DEFAULT_RETRY_MS",
        'getattr(self.settings, "statement_timeout_seconds"',
        'getattr(self.settings, "batch_size"',
        'getattr(self.settings, "lease_ms"',
        'getattr(self.settings, "retry_ms"',
        'getattr(self.settings, "max_attempts"',
        'getattr(self.settings, "source_limit"',
        '"statement_timeout_seconds", 120.0',
        '"batch_size", 100',
        '"max_attempts", 3',
        "limit=max(1, int(self.settings.batch_size))",
        "lease_ms=max(1, int(self.settings.lease_ms))",
        "retry_ms=max(1, int(self.settings.retry_ms))",
        "max_attempts=int(self.settings.max_attempts)",
    )
    violations = [token for token in forbidden_tokens if token in source]

    assert violations == []
    assert source.count("statement_timeout_seconds=float(self.settings.statement_timeout_seconds)") == 6
    assert "token_image_mirror_batch_size_required" in source
    assert "token_image_mirror_lease_ms_required" in source
    assert "token_image_mirror_retry_ms_required" in source
    assert "token_image_mirror_max_attempts_required" in source
    assert "def _required_positive_int(value: Any, *, error_code: str) -> int:" in source
    assert "isinstance(value, bool)" in source
    repository_source = (SRC / "domains/asset_market/repositories/token_image_asset_repository.py").read_text(
        encoding="utf-8"
    )
    assert "token_image_asset_retry_ms_required" in repository_source
    assert "max(0, int(retry_ms))" not in repository_source
    service_forbidden_tokens = (
        "TOKEN_IMAGE_MIRROR_RETRY_MS",
        "retry_ms: int =",
    )
    service_violations = [token for token in service_forbidden_tokens if token in service_source]
    assert service_violations == []
    assert "retry_ms: int = Field(default=300_000, ge=1)" in settings_class
    assert "max_attempts: int = Field(default=3, ge=1)" in settings_class


@pytest.mark.architecture
def test_asset_profile_refresh_worker_uses_formal_settings_contract_without_runtime_defaults() -> None:
    source = ASSET_PROFILE_REFRESH_WORKER.read_text(encoding="utf-8")
    service_source = (SRC / "domains/asset_market/services/asset_profile_refresh.py").read_text(encoding="utf-8")
    repository_source = (SRC / "domains/asset_market/repositories/asset_profile_repository.py").read_text(
        encoding="utf-8"
    )
    settings_source = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    settings_class = settings_source.split("class AssetProfileRefreshWorkerSettings", 1)[1].split(
        "\n\nclass TokenImageMirrorWorkerSettings",
        1,
    )[0]
    forbidden_tokens = (
        "DEFAULT_LEASE_MS",
        "DEFAULT_PROVIDER_RETRY_MS",
        'getattr(self.settings, "statement_timeout_seconds"',
        'getattr(self.settings, "batch_size"',
        'getattr(self.settings, "lease_ms"',
        'getattr(self.settings, "provider_retry_ms"',
        '"batch_size", 50',
        "limit=max(1, int(self.settings.batch_size))",
        "lease_ms=max(1, int(self.settings.lease_ms))",
        "return max(1, int(self.settings.provider_retry_ms))",
        "ready_refresh_ms = max(1, int(self.settings.ready_refresh_ms))",
        "missing_refresh_ms = max(1, int(self.settings.missing_refresh_ms))",
        "error_refresh_ms = max(1, int(self.settings.error_refresh_ms))",
    )
    violations = [token for token in forbidden_tokens if token in source]
    policy_forbidden_tokens = (
        "READY_REFRESH_MS",
        "MISSING_REFRESH_MS",
        "ERROR_REFRESH_MS",
        "next_refresh_at_ms=int(now_ms) +",
        "due_at_ms=now_ms + READY_REFRESH_MS",
        "due_at_ms=now_ms + MISSING_REFRESH_MS",
        "due_at_ms=now_ms + ERROR_REFRESH_MS",
    )
    policy_violations = [
        token
        for token in policy_forbidden_tokens
        if token in source or token in service_source or token in repository_source
    ]

    assert violations == []
    assert policy_violations == []
    assert source.count("statement_timeout_seconds=self.settings.statement_timeout_seconds") == 4
    assert "asset_profile_refresh_batch_size_required" in source
    assert "asset_profile_refresh_lease_ms_required" in source
    assert "asset_profile_refresh_provider_retry_ms_required" in source
    assert "asset_profile_refresh_ready_refresh_ms_required" in source
    assert "asset_profile_refresh_missing_refresh_ms_required" in source
    assert "asset_profile_refresh_error_refresh_ms_required" in source
    assert "def _required_positive_int(value: Any, *, error_code: str) -> int:" in source
    assert "isinstance(value, bool)" in source
    assert "provider_retry_ms: int = Field(default=300_000, ge=1)" in settings_class
    assert "ready_refresh_ms: int = Field(default=21_600_000, ge=1)" in settings_class
    assert "missing_refresh_ms: int = Field(default=900_000, ge=1)" in settings_class
    assert "error_refresh_ms: int = Field(default=900_000, ge=1)" in settings_class


@pytest.mark.architecture
def test_resolution_refresh_worker_uses_formal_settings_and_wake_contract_without_runtime_defaults() -> None:
    source = RESOLUTION_REFRESH_WORKER.read_text(encoding="utf-8")
    init_source = source.split("def __init__", 1)[1].split("\n    async def run_once", 1)[0]
    run_source = source.split("def _run_refresh_once", 1)[1].split("\n\n\ndef _fetch_lookup_provider_result", 1)[0]
    factory_source = (WORKER_FACTORIES / "asset_market.py").read_text(encoding="utf-8")
    resolution_factory_source = factory_source.split(
        'constructed["resolution_refresh"] = ResolutionRefreshWorker(',
        1,
    )[1].split(
        "\n            )",
        1,
    )[0]
    forbidden_source_tokens = (
        "DEFAULT_DISCOVERY_LIMIT",
        "DEFAULT_REPROCESS_LIMIT",
        "RUNNING_LOOKUP_TIMEOUT_MS",
        "HOT_NOT_FOUND_RETRY_MS",
        'getattr(self.settings, "batch_size"',
        'getattr(self.settings, "reprocess_limit"',
        'getattr(self.settings, "lease_ms"',
        'getattr(self.settings, "hot_not_found_retry_ms"',
        'getattr(settings, "chain_ids"',
        'getattr(settings, "max_attempts"',
        'getattr(settings, "lease_ms"',
        'getattr(settings, "hot_not_found_retry_ms"',
        "getattr(candidate,",
        "limit=max(1, int(self.settings.batch_size))",
        "limit=max(1, int(self.settings.reprocess_limit))",
        "max(1, int(hot_not_found_retry_ms))",
        "max(1, int(max_attempts))",
        "ranked[: max(0, int(per_chain_limit))]",
        "max(0, int(error_count))",
        'int(lookup.get("error_count") or 0)',
    )
    forbidden_init_tokens = (
        "dex_quote_market",
        "wake_bus",
        "chain_ids:",
        "self.dex_quote_market",
        "configured_chain_ids",
        'getattr(settings, "',
        "max(1, int(settings.max_attempts))",
        "max(1, int(settings.lease_ms))",
        "max(1, int(settings.hot_not_found_retry_ms))",
    )
    forbidden_factory_tokens = (
        "dex_quote_market=dex_quote_market",
        "chain_ids=workers.resolution_refresh.chain_ids",
        "wake_bus=ctx.wake_bus",
    )
    violations = (
        [f"worker-source:{token}" for token in forbidden_source_tokens if token in source]
        + [f"worker-init:{token}" for token in forbidden_init_tokens if token in init_source]
        + [f"factory:{token}" for token in forbidden_factory_tokens if token in resolution_factory_source]
    )

    assert violations == []
    assert "resolution_refresh_settings_required" in init_source
    assert "resolution_refresh_provider_required" in init_source
    assert "isinstance(candidate, DexTokenCandidate)" in source
    assert "dex_token_candidate_contract_required" in source
    assert "settings.chain_ids" in init_source
    assert "resolution_refresh_max_attempts_required" in init_source
    assert "resolution_refresh_lease_ms_required" in init_source
    assert "resolution_refresh_hot_not_found_retry_ms_required" in init_source
    assert "self.wake_emitter = wake_emitter" in init_source
    assert "self.wake_emitter.notify_resolution_updated" in source
    assert "resolution_refresh_batch_size_required" in run_source
    assert "lease_ms=self.lease_ms" in run_source
    assert "running_timeout_ms=self.lease_ms" in run_source
    assert "hot_not_found_retry_ms=self.hot_not_found_retry_ms" in run_source
    assert "resolution_refresh_reprocess_limit_required" in run_source
    assert "resolution_refresh_symbol_candidate_per_chain_limit_required" in source
    assert "resolution_refresh_claim_attempt_count_required" in source
    assert "resolution_refresh_claim_error_count_required" in source
    assert "def _required_positive_int(value: Any, *, error_code: str) -> int:" in source
    assert "def _required_nonnegative_int(value: Any, *, error_code: str) -> int:" in source
    assert "isinstance(value, bool)" in source
    assert "dex_discovery_market=dex_discovery_market" in resolution_factory_source
    assert "wake_emitter=ctx.wake_bus" in resolution_factory_source


@pytest.mark.architecture
def test_token_resolution_reprocess_helpers_require_explicit_window_and_limits_without_defaults() -> None:
    service_source = (SRC / "domains/token_intel/services/token_resolution_refresh.py").read_text(encoding="utf-8")
    rebuild_source = (SRC / "domains/token_intel/runtime/token_intent_rebuild.py").read_text(encoding="utf-8")
    interfaces_source = (SRC / "domains/token_intel/interfaces.py").read_text(encoding="utf-8")
    forbidden_tokens = (
        "DEFAULT_REPROCESS_LIMIT",
        "DEFAULT_REPROCESS_WINDOW",
        "window: str =",
        "limit: int =",
        "reprocess_limit: int =",
        "projection_limit: int =",
        "WINDOW_MS.get(window",
    )
    violations = (
        [f"token_resolution_refresh:{token}" for token in forbidden_tokens if token in service_source]
        + [f"token_intent_rebuild:{token}" for token in forbidden_tokens if token in rebuild_source]
        + [
            f"interfaces:{token}"
            for token in ("DEFAULT_REPROCESS_LIMIT", "DEFAULT_REPROCESS_WINDOW")
            if token in interfaces_source
        ]
    )

    assert violations == []
    assert 'TOKEN_REPROCESS_WINDOW = "24h"' in service_source
    assert "window: str," in service_source
    assert "limit: int," in service_source
    assert "since_ms = int(now_ms) - WINDOW_MS[window]" in service_source
    assert "since_ms = int(now_ms) - WINDOW_MS[window]" in rebuild_source


@pytest.mark.architecture
def test_token_resolution_refresh_requires_formal_resolution_decision_without_reflection() -> None:
    service_source = (SRC / "domains/token_intel/services/token_resolution_refresh.py").read_text(encoding="utf-8")

    forbidden_tokens = (
        "getattr(decision,",
        "hasattr(decision",
        'decision.get("target_type"',
        'decision.get("target_id"',
        'decision.get("event_id"',
    )

    assert [token for token in forbidden_tokens if token in service_source] == []
    assert "TokenIntentResolutionDecision" in service_source
    assert "isinstance(decision, TokenIntentResolutionDecision)" in service_source
    assert "token_resolution_refresh_decision_contract_required" in service_source
    assert "target_type = decision.target_type" in service_source
    assert "target_id = decision.target_id" in service_source
    assert "event_id = decision.event_id" in service_source


@pytest.mark.architecture
def test_collector_upstream_client_close_contract_is_direct() -> None:
    ingestion_provider_source = INGESTION_PROVIDERS.read_text(encoding="utf-8")
    upstream_protocol = ingestion_provider_source.split("class UpstreamClientProtocol", 1)[1].split(
        "\n\n__all__",
        1,
    )[0]
    collector_source = COLLECTOR_SERVICE.read_text(encoding="utf-8")
    on_close_source = collector_source.split("async def on_close", 1)[1].split(
        "\n    async def _clear_pending_snapshots",
        1,
    )[0]

    forbidden_tokens = (
        'getattr(self.upstream_client, "aclose", None)',
        'getattr(self.upstream_client, "close", None)',
        'or getattr(self.upstream_client, "close", None)',
        "close = getattr",
        "result = close()",
        "inspect.isawaitable",
        "if close is None",
    )
    violations = [token for token in forbidden_tokens if token in on_close_source]

    assert violations == []
    assert "async def aclose(self) -> None" in upstream_protocol
    assert "aclose = self.upstream_client.aclose" in on_close_source
    assert "await aclose()" in on_close_source
    assert "collector_upstream_client_aclose_required" in on_close_source


@pytest.mark.architecture
def test_collector_snapshot_gate_timeout_uses_formal_worker_settings_contract() -> None:
    collector_source = COLLECTOR_SERVICE.read_text(encoding="utf-8")
    init_source = collector_source.split("def __init__", 1)[1].split("\n    async def run_once", 1)[0]
    forbidden_tokens = (
        'getattr(settings, "snapshot_timeout_seconds", 0.5)',
        'getattr(settings, "snapshot_timeout_seconds",',
    )
    violations = [token for token in forbidden_tokens if token in init_source]

    assert violations == []
    assert "settings.snapshot_timeout_seconds" in init_source


@pytest.mark.architecture
def test_direct_gmgn_ws_frame_handler_uses_async_collector_contract_without_isawaitable_fallback() -> None:
    source = GMGN_DIRECT_WS.read_text(encoding="utf-8")
    init_source = source.split("def __init__", 1)[1].split("\n    def connection_state_payload", 1)[0]
    receive_source = source.split("async def _receive_frames", 1)[1].split(
        "\n    async def _subscribe_all",
        1,
    )[0]

    forbidden_tokens = (
        "import inspect",
        "inspect.isawaitable",
        "result = self.on_frame(frame)",
        "await result",
        "Callable[[str], Any | Awaitable[Any]]",
    )
    violations = [token for token in forbidden_tokens if token in source]

    assert violations == []
    assert "on_frame: Callable[[str], Awaitable[None]]" in init_source
    assert "await self.on_frame(frame)" in receive_source


@pytest.mark.architecture
def test_worker_owned_provider_cleanup_uses_formal_lifecycle_contracts() -> None:
    news_source = NEWS_FETCH_WORKER.read_text(encoding="utf-8")
    news_on_close = news_source.split("async def on_close", 1)[1].split("\n    async def run_once", 1)[0]

    news_forbidden = (
        'getattr(self.feed_client, "close", None)',
        "isawaitable(",
        "if close is None",
        "await result",
    )
    violations = [f"news:{token}" for token in news_forbidden if token in news_on_close]

    assert violations == []
    assert "close = cast(Callable[[], object | None], self.feed_client.close)" in news_on_close
    assert "result = close()" in news_on_close
    assert "news_fetch_feed_client_close_must_be_sync" in news_on_close


@pytest.mark.architecture
def test_provider_wiring_cleanup_uses_formal_close_contracts_without_optional_probes() -> None:
    asset_source = ASSET_MARKET_PROVIDER_WIRING.read_text(encoding="utf-8")
    okx_source = OKX_PROVIDER_WIRING.read_text(encoding="utf-8")
    fallback_close_source = asset_source.split("def close(self) -> None:", 1)[1].split(
        "\n\n\ndef wire_asset_market",
        1,
    )[0]
    asset_partial_cleanup = asset_source.split("def _close_partial_providers", 1)[1].split(
        "\n\n\n__all__",
        1,
    )[0]
    serialized_close_source = okx_source.split("class SerializedDiscoveryProvider", 1)[1].split(
        "\n\n\nclass OkxDexWebSocketMarketProviderAdapter",
        1,
    )[0]
    okx_partial_cleanup = okx_source.split("def _close_partial_providers", 1)[1].split("\n\n\n__all__", 1)[0]
    okx_ws_adapter_close = okx_source.split("class OkxDexWebSocketMarketProviderAdapter", 1)[1].split(
        "def connection_state_payload",
        1,
    )[0]
    combined = "\n".join(
        (
            fallback_close_source,
            asset_partial_cleanup,
            serialized_close_source,
            okx_ws_adapter_close,
            okx_partial_cleanup,
        )
    )

    forbidden_tokens = (
        'getattr(provider, "close", None)',
        'getattr(self._provider, "close", None)',
        "if close is None",
        "if close:",
        "if not close",
        "_websocket",
    )
    violations = [token for token in forbidden_tokens if token in combined]

    assert violations == []
    assert "provider.close()" in fallback_close_source
    assert "self._provider.close()" in serialized_close_source
    assert "self._provider.connection_state_payload()" in okx_ws_adapter_close
    assert "cast(_SyncCloseProvider, provider).close()" in asset_partial_cleanup
    assert "cast(_SyncCloseProvider, provider).close()" in okx_partial_cleanup


@pytest.mark.architecture
def test_configured_asset_market_gmgn_provider_uses_formal_quote_and_profile_contracts() -> None:
    source = ASSET_MARKET_PROVIDER_WIRING.read_text(encoding="utf-8")

    forbidden_tokens = (
        "_has_token_quotes",
        "_has_token_profile",
        'getattr(value, "token_quotes", None)',
        'getattr(value, "token_profile", None)',
    )
    violations = [token for token in forbidden_tokens if token in source]

    assert violations == []
    assert "primary_quote = _require_token_quote_provider(primary)" in source
    assert "market=_require_token_profile_source(gmgn_dex_market)" in source
    assert "asset_market_token_quotes_required" in source
    assert "asset_market_token_profile_required" in source


@pytest.mark.architecture
def test_asset_market_wiring_cleanup_uses_formal_okx_bundle_fields_without_optional_probe() -> None:
    source = ASSET_MARKET_PROVIDER_WIRING.read_text(encoding="utf-8")
    wire_source = source.split("def wire_asset_market", 1)[1].split(
        "\n\n\ndef wire_asset_market_providers",
        1,
    )[0]
    cleanup_source = source.split("def _okx_bundle_cleanup_providers", 1)[1].split(
        "\n\n\ndef _quote_key",
        1,
    )[0]
    forbidden_tokens = (
        'getattr(okx_bundle, "dex_discovery_market", None)',
        'getattr(okx_bundle, "dex_quote_market", None)',
        'getattr(okx_bundle, "stream_dex_market", None)',
    )
    violations = [token for token in forbidden_tokens if token in wire_source or token in cleanup_source]

    assert violations == []
    assert "_okx_bundle_cleanup_providers(exc, okx_bundle)" in wire_source
    assert "dex_discovery_market = okx_bundle.dex_discovery_market" in cleanup_source
    assert "dex_quote_market = okx_bundle.dex_quote_market" in cleanup_source
    assert "stream_dex_market = okx_bundle.stream_dex_market" in cleanup_source
    assert '"okx_bundle.dex_quote_market"' in cleanup_source
    assert '"okx_bundle.stream_dex_market"' in cleanup_source


@pytest.mark.architecture
def test_api_worker_dependencies_use_formal_status_payload_contracts() -> None:
    source = API_DEPENDENCIES.read_text(encoding="utf-8")
    worker_object = source.split("def _worker_object", 1)[1].split("\ndef _now_ms", 1)[0]

    forbidden_tokens = (
        'getattr(runtime, "scheduler", None)',
        'getattr(runtime, "workers", {})',
        'getattr(worker, "status_payload", None)',
        "except Exception:",
        "status_payload is None",
    )
    violations = [token for token in forbidden_tokens if token in worker_object]

    assert violations == []
    assert "scheduler = runtime.scheduler" in worker_object
    assert "payload = worker.status_payload()" in worker_object
    assert "payload = worker.status_payload()" in source
    assert "api_worker_status_payload_must_be_dict" in source


@pytest.mark.architecture
def test_agent_execution_status_uses_runtime_gateway_contract_without_provider_alias() -> None:
    app_source = APP_RUNTIME_APP.read_text(encoding="utf-8")
    app_helper = app_source.split("def _agent_execution_status", 1)[1].split("\ndef _unhealthy_reasons", 1)[0]
    diagnostics_source = OPS_DIAGNOSTICS.read_text(encoding="utf-8")
    diagnostics_helper = diagnostics_source.split("def _agent_execution_payload", 1)[1].split(
        "\ndef _worker_lanes_payload",
        1,
    )[0]

    helper_sources = {
        "api_status": app_helper,
        "ops_diagnostics": diagnostics_helper,
    }
    forbidden_tokens = (
        'getattr(runtime, "agent_execution_gateway", None)',
        'getattr(providers, "agent_execution_gateway", None)',
        'getattr(gateway, "status_snapshot", None)',
        "if not callable(snapshot)",
    )
    violations = [
        f"{source_name} contains {token}"
        for source_name, source in helper_sources.items()
        for token in forbidden_tokens
        if token in source
    ]

    assert violations == []
    assert "gateway = runtime.agent_execution_gateway" in app_helper
    assert "gateway = runtime.agent_execution_gateway" in diagnostics_helper
    assert "payload = gateway.status_snapshot()" in app_helper
    assert "raw_snapshot = gateway.status_snapshot()" in diagnostics_helper


@pytest.mark.architecture
def test_worker_manifest_matches_workers_yaml_schema() -> None:
    from parallax.platform.config.settings import WorkersSettings

    expected_keys = set(MANIFEST_WORKER_CLASSES)
    settings_keys = set(WorkersSettings.model_fields) - {"defaults", "agent_runtime"}
    docs_keys = _worker_inventory_keys()

    assert settings_keys == expected_keys
    assert docs_keys == expected_keys


@pytest.mark.architecture
def test_worker_manifest_owns_all_single_writer_tables() -> None:
    owned_tables = {
        table
        for manifest in all_worker_manifests()
        for table in (
            *manifest.writes_facts,
            *manifest.writes_input_observations,
            *manifest.writes_cache_state,
            *manifest.writes_read_models,
            *manifest.writes_control_plane,
            *manifest.side_effect_ledgers,
        )
    }
    missing = sorted(set(SINGLE_WRITER_READ_MODELS) - owned_tables)

    assert missing == []


@pytest.mark.architecture
def test_worker_manifest_keeps_provider_raw_frames_out_of_business_facts() -> None:
    collector = {manifest.name: manifest for manifest in all_worker_manifests()}["collector"]

    assert "raw_frames" not in collector.writes_facts
    assert collector.writes_input_observations == ("raw_frames",)


@pytest.mark.architecture
def test_worker_manifest_forbids_semantic_read_model_aliases() -> None:
    forbidden_aliases = {
        "cex_oi_radar_board",
        "macro_view",
        "news_pages",
        "news_source_quality",
        "news_stories",
        "watchlist_signal_summaries",
    }
    aliases = {
        f"{manifest.name}:{table}"
        for manifest in all_worker_manifests()
        for table in manifest.writes_read_models
        if table in forbidden_aliases
    }

    assert aliases == set()


@pytest.mark.architecture
def test_news_page_projection_manifest_uses_row_id_identity() -> None:
    manifests = {manifest.name: manifest for manifest in all_worker_manifests()}
    manifest = manifests["news_page_projection"]
    forbidden_identity_terms = {"generation_id", "run_id", "attempt_id", "timestamp", "uuid"}

    assert manifest.ordering_keys == ("row_id", "news_item_id")
    assert manifest.current_read_model_identities == (("news_page_rows", ("row_id",)),)
    assert "page_id" not in manifest.ordering_keys
    assert all("page_id" not in identity for _, identity in manifest.current_read_model_identities)
    assert all(
        term not in identity
        for _table, identity_columns in manifest.current_read_model_identities
        for identity in identity_columns
        for term in forbidden_identity_terms
    )
    assert "semantic news page reprojection work" in manifest.input_contract


@pytest.mark.architecture
def test_cex_oi_radar_runtime_uses_current_board_lifecycle() -> None:
    forbidden_tokens = (
        "run_id",
        "cex_oi_radar_runs",
        "start_run",
        "finish_run",
        "oi_radar_run_id",
    )
    violations = []
    for path in (CEX_OI_RADAR_REPOSITORY, CEX_OI_RADAR_BOARD_WORKER):
        text = path.read_text(encoding="utf-8")
        violations.extend(f"{_rel(path)} contains {token}" for token in forbidden_tokens if token in text)

    assert violations == []


@pytest.mark.architecture
def test_cex_oi_radar_manifest_uses_current_board_lifecycle() -> None:
    manifest = next(item for item in all_worker_manifests() if item.name == "cex_oi_radar_board")

    assert "cex_oi_radar_publication_state" in manifest.writes_read_models
    assert "cex_oi_radar_rows" in manifest.writes_read_models
    assert "cex_oi_radar_runs" not in manifest.writes_read_models


@pytest.mark.architecture
def test_macro_sync_is_fact_ingest_and_projection_remains_read_model_writer() -> None:
    manifests = {manifest.name: manifest for manifest in all_worker_manifests()}

    assert manifests["macro_sync"].domain == "macro_intel"
    assert manifests["macro_sync"].kind is WorkerKind.FACT_INGEST
    assert "macro_observations" in manifests["macro_sync"].writes_facts
    assert "macro_import_runs" in manifests["macro_sync"].writes_control_plane
    assert "macro_sync_windows" in manifests["macro_sync"].writes_control_plane
    assert "macro_sync_runs" in manifests["macro_sync"].writes_control_plane
    assert "macro_view_snapshots" not in manifests["macro_sync"].writes_read_models
    assert manifests["macro_sync"].wakes_out == ("macro_observations_imported",)

    projection = manifests["macro_view_projection"]
    assert projection.input_contract == ("macro_projection_dirty_targets", "macro_observation_series_rows current")
    assert "macro data providers" not in projection.input_contract
    assert "macro_observation_series_rows" in projection.writes_read_models
    assert "macro_observation_series_active_generation" not in projection.writes_read_models
    assert "macro_observation_series_generations" not in projection.writes_read_models
    assert "macro_view_snapshots" in projection.writes_read_models
    assert "macro_projection_dirty_targets" in projection.writes_control_plane
    assert projection.dirty_target_tables == ("macro_projection_dirty_targets",)
    assert "macro_observations_imported" in projection.wakes_on
    assert projection.wakes_out == ("macro_view_snapshot_updated",)

    daily_brief = manifests["macro_daily_brief_projection"]
    assert daily_brief.wakes_on == ("macro_view_snapshot_updated",)


@pytest.mark.architecture
def test_worker_manifest_declares_dirty_target_consumers() -> None:
    expected_dirty_targets = {
        "asset_profile_refresh_targets",
        "market_tick_current_dirty_targets",
        "macro_projection_dirty_targets",
        "narrative_admission_dirty_targets",
        "news_projection_dirty_targets",
        "token_capture_tier_dirty_targets",
        "token_discovery_dirty_lookup_keys",
        "token_image_source_dirty_targets",
        "token_profile_current_dirty_targets",
        "token_radar_dirty_targets",
    }
    manifest_dirty_targets = {table for manifest in all_worker_manifests() for table in manifest.dirty_target_tables}

    assert expected_dirty_targets <= manifest_dirty_targets


@pytest.mark.architecture
def test_token_image_mirror_starts_between_profile_refresh_and_current_projection() -> None:
    priority = worker_start_priority()

    assert priority["asset_profile_refresh"] < priority["token_image_mirror"]
    assert priority["token_image_mirror"] < priority["token_profile_current"]


@pytest.mark.architecture
def test_token_profile_current_owns_image_source_admission() -> None:
    manifests = {manifest.name: manifest for manifest in all_worker_manifests()}
    token_profile_current = manifests["token_profile_current"]

    assert "token_image_source_dirty_targets" not in manifests["asset_profile_refresh"].writes_control_plane
    assert "token_image_source_dirty_targets" in token_profile_current.writes_control_plane
    assert set(token_profile_current.idempotency_evidence) >= {
        "token_profile_current target primary key",
        "token image source dirty target source_url_hash/target key",
        "dirty target payload hash",
    }
    assert token_profile_current.dirty_target_tables == ("token_profile_current_dirty_targets",)
    assert token_profile_current.advisory_lock_key == "2026051702"


@pytest.mark.architecture
def test_token_image_mirror_is_only_token_image_assets_writer() -> None:
    writers = [
        manifest.name
        for manifest in all_worker_manifests()
        if "token_image_assets"
        in (
            *manifest.writes_facts,
            *manifest.writes_input_observations,
            *manifest.writes_cache_state,
            *manifest.writes_read_models,
            *manifest.writes_control_plane,
            *manifest.side_effect_ledgers,
        )
    ]

    assert writers == ["token_image_mirror"]


@pytest.mark.architecture
def test_non_continuous_worker_defaults_have_finite_hard_timeout() -> None:
    from parallax.platform.config.settings import WorkersSettings, default_workers_yaml

    settings = WorkersSettings(**yaml.safe_load(default_workers_yaml()))

    for worker_key in MANIFEST_WORKER_CLASSES:
        worker_settings = getattr(settings, worker_key)
        hard_timeout = worker_settings.hard_timeout_seconds
        if worker_key in ZERO_HARD_TIMEOUT_ALLOWLIST:
            assert hard_timeout == 0
            continue
        assert hard_timeout > 0, f"{worker_key} must have a finite hard timeout"


@pytest.mark.architecture
def test_worker_construction_is_split_into_domain_factories() -> None:
    from parallax.app.runtime.worker_factories import worker_factory_specs

    bootstrap_path = SRC / "app/runtime/bootstrap.py"
    bootstrap_tree = _parse(bootstrap_path)
    bootstrap_text = bootstrap_path.read_text(encoding="utf-8")
    bootstrap_functions = {
        node.name for node in ast.walk(bootstrap_tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    expected_worker_modules = {
        qualified_name.rpartition(".")[0]
        for key, qualified_name in MANIFEST_WORKER_CLASSES.items()
        if key != "collector"
    }
    bootstrap_runtime_worker_imports = sorted(
        module
        for module in _imported_modules(bootstrap_tree)
        if module in expected_worker_modules and module not in BOOTSTRAP_RUNTIME_WORKER_IMPORT_ALLOWLIST
    )
    worker_factory_files = {path.name for path in WORKER_FACTORIES.glob("*.py")}
    factory_runtime_worker_imports = set()
    if WORKER_FACTORIES.exists():
        for path in WORKER_FACTORIES.glob("*.py"):
            factory_runtime_worker_imports.update(_imported_modules(_parse(path)))
    specs = worker_factory_specs()
    owned_keys = [key for spec in specs for key in spec.keys]

    assert worker_factory_files == EXPECTED_WORKER_FACTORY_FILES
    assert {spec.name for spec in specs} == EXPECTED_WORKER_FACTORY_FILES - {"__init__.py"}
    assert set(owned_keys) == set(MANIFEST_WORKER_CLASSES)
    assert len(owned_keys) == len(set(owned_keys))
    assert "_construct_workers" not in bootstrap_functions
    assert bootstrap_runtime_worker_imports == []
    for worker_key in set(MANIFEST_WORKER_CLASSES) - {"collector"}:
        assert f'constructed["{worker_key}"]' not in bootstrap_text
    assert sorted(expected_worker_modules - factory_runtime_worker_imports) == []


@pytest.mark.architecture
def test_provider_io_worker_factories_do_not_import_raw_third_party_clients() -> None:
    forbidden_module_roots = {
        "coinglass_cli",
    }
    violations: list[str] = []
    for path in WORKER_FACTORIES.glob("*.py"):
        for module in _imported_modules(_parse(path)):
            root = module.split(".", 1)[0]
            if root in forbidden_module_roots:
                violations.append(f"{_rel(path)} imports raw third-party client module {module}")

    assert violations == []


@pytest.mark.architecture
def test_missing_worker_sentinel_uses_formal_worker_settings_contract_without_default_config() -> None:
    source = (WORKER_FACTORIES / "__init__.py").read_text(encoding="utf-8")
    config_enabled_source = source.split("def _worker_config_enabled", 1)[1].split(
        "\n\ndef _redacted_reason",
        1,
    )[0]
    worker_settings_source = source.split("def _worker_settings", 1)[1].split(
        "\n\ndef worker_factory_specs",
        1,
    )[0]
    forbidden_tokens = (
        "getattr(settings.workers, name, None)",
        'getattr(config, "enabled", True)',
        'getattr(value, "enabled", True)',
        'getattr(value, "model_dump", None)',
        "if config is None:",
        "return SimpleNamespace(enabled=enabled)",
        "SimpleNamespace(**",
        "def _object_values",
        "model_dump",
        "__dict__",
        "vars(",
    )
    combined = f"{config_enabled_source}\n{worker_settings_source}"
    violations = [token for token in forbidden_tokens if token in combined]

    assert violations == []
    assert "config = getattr(settings.workers, name)" in config_enabled_source
    assert "config = getattr(settings.workers, name)" in worker_settings_source
    assert "model_copy = config.model_copy" in worker_settings_source
    assert 'model_copy(update={"enabled": enabled})' in worker_settings_source
    assert "worker_settings_model_copy_required" in worker_settings_source


@pytest.mark.architecture
def test_db_pool_bundle_wake_listener_sizing_uses_manifest_worker_settings_contract() -> None:
    source = APP_RUNTIME_DB_POOL_BUNDLE.read_text(encoding="utf-8")
    helper_source = source.split("def enabled_wake_listener_concurrency", 1)[1].split(
        "\n\ndef _set_config",
        1,
    )[0]
    forbidden_tokens = (
        'getattr(settings, "workers", None)',
        "if workers is None:",
        'getattr(worker_settings, "enabled"',
        'getattr(worker_settings, "wakes_on"',
        'getattr(worker_settings, "concurrency"',
        "worker_settings.concurrency or 1",
        "max(1, int(worker_settings.concurrency",
    )
    violations = [token for token in forbidden_tokens if token in helper_source]

    assert violations == []
    assert "workers = settings.workers" in helper_source
    assert "for manifest in all_worker_manifests()" in helper_source
    assert "if not manifest.wakes_on:" in helper_source
    assert "worker_settings = getattr(workers, manifest.name)" in helper_source
    assert "worker_settings.enabled" in helper_source
    assert "worker_settings.concurrency" in helper_source
    assert "_worker_wake_concurrency(" in helper_source
    assert "worker_wake_listener_concurrency_required" in helper_source
    assert "isinstance(value, bool) or not isinstance(value, int)" in helper_source


@pytest.mark.architecture
def test_db_pool_bundle_statement_timeout_uses_formal_nonnegative_contract_without_runtime_repair() -> None:
    source = APP_RUNTIME_DB_POOL_BUNDLE.read_text(encoding="utf-8")
    helper_source = source.split("def _statement_timeout_value", 1)[1].split(
        "\n\ndef wake_pool_max_size",
        1,
    )[0]
    forbidden_tokens = (
        "max(0, int(float(seconds) * 1000))",
        "int(float(seconds) * 1000)",
    )

    assert [token for token in forbidden_tokens if token in helper_source] == []
    assert "_nonnegative_timeout_seconds(seconds)" in helper_source
    assert "db_statement_timeout_seconds_required" in helper_source
    assert "isinstance(value, bool) or not isinstance(value, int | float)" in helper_source


@pytest.mark.architecture
def test_enabled_asset_market_provider_workers_missing_provider_surface_unavailable() -> None:
    source = (WORKER_FACTORIES / "asset_market.py").read_text(encoding="utf-8")
    asset_profile_block = source.split("if workers.asset_profile_refresh.enabled:", 1)[1].split(
        "if workers.resolution_refresh.enabled:",
        1,
    )[0]
    resolution_block = source.split("if workers.resolution_refresh.enabled:", 1)[1].split(
        "if workers.live_price_gateway.enabled:",
        1,
    )[0]

    assert 'disabled_worker(ctx, "asset_profile_refresh")' not in asset_profile_block
    assert 'disabled_worker(ctx, "resolution_refresh")' not in resolution_block
    assert "unavailable_worker(" in asset_profile_block
    assert '"asset_profile_refresh"' in asset_profile_block
    assert '"missing_asset_profile_provider"' in asset_profile_block
    assert "unavailable_worker(" in resolution_block
    assert '"resolution_refresh"' in resolution_block
    assert '"missing_asset_discovery_provider"' in resolution_block


@pytest.mark.architecture
def test_asset_market_worker_factory_uses_formal_provider_bundle_fields_without_optional_probe() -> None:
    source = (WORKER_FACTORIES / "asset_market.py").read_text(encoding="utf-8")
    provider_setup = source.split("asset_market = ctx.providers.asset_market", 1)[1].split(
        "\n    constructed:",
        1,
    )[0]
    forbidden_tokens = (
        'getattr(asset_market, "cex_market", None)',
        'getattr(asset_market, "dex_quote_market", None)',
        'getattr(asset_market, "dex_profile_sources", ())',
        'getattr(asset_market, "dex_discovery_market", None)',
        'getattr(asset_market, "stream_dex_market", None)',
    )
    violations = [token for token in forbidden_tokens if token in provider_setup]

    assert violations == []
    assert "cex_market = asset_market.cex_market" in provider_setup
    assert "dex_quote_market = asset_market.dex_quote_market" in provider_setup
    assert "dex_profile_sources = tuple(asset_market.dex_profile_sources or ())" in provider_setup
    assert "dex_discovery_market = asset_market.dex_discovery_market" in provider_setup
    assert "stream_dex_market = asset_market.stream_dex_market" in provider_setup


@pytest.mark.architecture
def test_cex_and_news_worker_factories_use_formal_provider_bundle_fields_without_optional_probe() -> None:
    cex_source = (WORKER_FACTORIES / "cex_market_intel.py").read_text(encoding="utf-8")
    news_source = (WORKER_FACTORIES / "news_intel.py").read_text(encoding="utf-8")
    cex_provider_source = cex_source.split("cex_providers = ctx.providers.cex_market_intel", 1)[1]
    news_provider_source = news_source.split("news_providers = ctx.providers.news_intel", 1)[1].split(
        "\n    if workers.news_page_projection.enabled:",
        1,
    )[0]

    forbidden_tokens = (
        'getattr(cex_providers, "oi_market", None)',
        'getattr(cex_providers, "coinglass_derivatives", None)',
        'getattr(news_providers, "feed_client", None)',
        'getattr(news_providers, "brief_provider", None)',
    )
    sources = {
        "cex_market_intel": cex_provider_source,
        "news_intel": news_provider_source,
    }
    violations = [
        f"{source_name} contains {token}"
        for source_name, source in sources.items()
        for token in forbidden_tokens
        if token in source
    ]

    assert violations == []
    assert "oi_market = cex_providers.oi_market" in cex_provider_source
    assert "coinglass_derivatives = cex_providers.coinglass_derivatives" in cex_provider_source
    assert "feed_client = news_providers.feed_client" in news_provider_source
    assert "brief_provider = news_providers.brief_provider" in news_provider_source


@pytest.mark.architecture
def test_cex_oi_radar_board_worker_uses_formal_settings_and_provider_contract_without_runtime_defaults() -> None:
    source = CEX_OI_RADAR_BOARD_WORKER.read_text(encoding="utf-8")
    builder_source = CEX_BINANCE_OI_RADAR_BUILDER.read_text(encoding="utf-8")
    enricher_source = CEX_COINGLASS_DETAIL_ENRICHER.read_text(encoding="utf-8")
    init_source = source.split("def __init__", 1)[1].split("\n    async def run_once", 1)[0]
    settings_source = (SRC / "platform/config/settings.py").read_text(encoding="utf-8")
    settings_class = settings_source.split("class CexOiRadarBoardWorkerSettings", 1)[1].split(
        "\n\nclass MacroViewProjectionWorkerSettings",
        1,
    )[0]
    factory_source = (WORKER_FACTORIES / "cex_market_intel.py").read_text(encoding="utf-8")
    factory_worker_source = factory_source.split(
        '"cex_oi_radar_board": CexOiRadarBoardWorker(',
        1,
    )[1].split(
        "        )\n    }",
        1,
    )[0]
    forbidden_worker_tokens = (
        "**kwargs",
        "super().__init__(**kwargs)",
        "oi_market: CexOiMarketProvider | None",
        "if self.oi_market is None",
        'getattr(self.settings, "period"',
        'getattr(self.settings, "universe_limit"',
        'getattr(self.settings, "coinglass_enrichment_limit"',
        'getattr(self.settings, "coinglass_level_limit"',
        'getattr(self.settings, "statement_timeout_seconds"',
        'getattr(self.settings, "batch_size"',
        '"period", "5m"',
        '"universe_limit", self._batch_size()',
        '"coinglass_enrichment_limit", 0',
        '"coinglass_level_limit", 6',
        '"batch_size", 100',
        "max(1, min(int(self.settings.universe_limit), batch_size))",
        "return max(1, int(self.settings.batch_size))",
    )
    forbidden_enricher_tokens = (
        "level_limit: int =",
        "level_limit: int = 6",
    )
    forbidden_builder_tokens = (
        'period: str = "5m"',
        "period: str =",
        "limit: int = 500",
        "limit: int =",
    )
    violations = [
        *(f"worker contains {token}" for token in forbidden_worker_tokens if token in source),
        *(f"builder contains {token}" for token in forbidden_builder_tokens if token in builder_source),
        *(f"enricher contains {token}" for token in forbidden_enricher_tokens if token in enricher_source),
    ]

    assert violations == []
    assert "cex_oi_radar_board_settings_required" in init_source
    assert "cex_oi_radar_board_db_required" in init_source
    assert "cex_oi_radar_board_oi_market_required" in init_source
    assert "self.period = _required_worker_text(" in source
    assert 'error_code="cex_oi_radar_board_period_required"' in source
    assert "self.batch_size = _positive_worker_setting_int(" in source
    assert 'error_code="cex_oi_radar_board_batch_size_required"' in source
    assert "self.universe_limit = _positive_worker_setting_int(" in source
    assert 'error_code="cex_oi_radar_board_universe_limit_required"' in source
    assert "self.coinglass_enrichment_limit = _nonnegative_worker_setting_int(" in source
    assert "self.coinglass_level_limit = _nonnegative_worker_setting_int(" in source
    assert "limit = min(self.universe_limit, batch_size)" in source
    assert "limit=self.coinglass_enrichment_limit" in source
    assert "level_limit=self.coinglass_level_limit" in source
    assert "statement_timeout_seconds=self.settings.statement_timeout_seconds" in source
    assert "return self.batch_size" in source
    assert "cex_oi_radar_board_batch_size_required" in source
    assert "cex_oi_radar_board_universe_limit_required" in source
    assert "oi_market=oi_market" in factory_worker_source
    assert "coinglass_derivatives=coinglass_derivatives" in factory_worker_source
    assert "batch_size: int = Field(default=500, ge=1)" in settings_class
    assert "statement_timeout_seconds: float = Field(default=120.0, ge=0)" in settings_class
    assert "universe_limit: int = Field(default=500, ge=1)" in settings_class
    assert "coinglass_enrichment_limit: int = Field(default=5, ge=0)" in settings_class
    assert "coinglass_level_limit: int = Field(default=6, ge=0)" in settings_class
    assert "period: str," in builder_source
    assert "limit: int," in builder_source
    assert "level_limit: int," in enricher_source


@pytest.mark.architecture
def test_cex_market_intel_provider_wiring_uses_formal_worker_settings_fields_without_defaults() -> None:
    source = CEX_MARKET_INTEL_PROVIDER_WIRING.read_text(encoding="utf-8")
    coinglass_source = source.split("def _coinglass_derivatives", 1)[1].split("\n\n\n__all__", 1)[0]
    forbidden_tokens = (
        'getattr(worker_settings, "enabled", True)',
        'getattr(worker_settings, "coinglass_enrichment_limit", 0)',
    )
    violations = [token for token in forbidden_tokens if token in coinglass_source]

    assert violations == []
    assert "worker_settings = settings.workers.cex_oi_radar_board" in coinglass_source
    assert "if not worker_settings.enabled:" in coinglass_source
    assert "worker_settings.coinglass_enrichment_limit" in coinglass_source


@pytest.mark.architecture
def test_worker_factories_use_formal_wired_provider_domain_roots_without_optional_probe() -> None:
    factory_sources = {
        "cex_market_intel": (WORKER_FACTORIES / "cex_market_intel.py").read_text(encoding="utf-8"),
        "news_intel": (WORKER_FACTORIES / "news_intel.py").read_text(encoding="utf-8"),
    }
    forbidden_tokens = (
        'getattr(ctx.providers, "cex_market_intel", None)',
        'getattr(ctx.providers, "news_intel", None)',
    )

    violations = [
        f"{factory_name} contains {token}"
        for factory_name, source in factory_sources.items()
        for token in forbidden_tokens
        if token in source
    ]

    assert violations == []
    assert "ctx.providers.cex_market_intel" in factory_sources["cex_market_intel"]
    assert "ctx.providers.news_intel" in factory_sources["news_intel"]


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
    from parallax.app.runtime import app as app_module
    from parallax.app.runtime.queue_health import empty_queue_health
    from parallax.app.runtime.worker_manifest import worker_queue_health_tables
    from parallax.app.surfaces.api.schemas import StatusData

    now_ms = 1_700_000_000_000
    queue_tables = worker_queue_health_tables()
    top_level_schema_keys = set(StatusData.model_fields)
    runtime = SimpleNamespace(
        _queue_health_cache={
            "cached_at_ms": now_ms,
            "worker_tables": queue_tables,
            "workers": {worker_name: empty_queue_health() for worker_name in queue_tables},
        },
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
        agent_execution_gateway=None,
        providers=SimpleNamespace(asset_market=SimpleNamespace(stream_dex_market=None)),
        scheduler=SimpleNamespace(
            status_payload=lambda: {"collector": {"enabled": False, "running": False}},
            unhealthy_reasons=lambda: [],
        ),
        settings=SimpleNamespace(handles=("toly",), news_intel=SimpleNamespace(sources=())),
    )
    monkeypatch.setattr(app_module, "_db_status", lambda _runtime: {"ok": True})
    monkeypatch.setattr(
        app_module,
        "workers_status_payload",
        lambda _runtime: {
            "workers": {
                "collector": {
                    "enabled": False,
                    "running": False,
                    "details": runtime.collector.status.to_dict(),
                    "queue_health": {"tables": {}},
                }
            },
            "worker_lanes": {
                "ingest": {},
                "projection": {},
                "agent": {},
                "notification": {},
            },
        },
    )
    payload, status_code = app_module._readiness_payload(runtime)

    assert top_level_schema_keys.isdisjoint(MANIFEST_WORKER_CLASSES)
    assert "workers" in top_level_schema_keys
    assert "worker_lanes" in top_level_schema_keys
    assert status_code == 200
    assert set(payload).isdisjoint(MANIFEST_WORKER_CLASSES)
    assert set(payload["worker_lanes"]) >= {"ingest", "projection", "agent", "notification"}
    collector = payload["workers"]["collector"]
    assert collector["enabled"] is False
    assert collector["running"] is False
    assert collector["details"]["frames_received"] == 0
    assert collector["details"]["matched_twitter_events"] == 0
    assert collector["details"]["snapshot_gate_outcomes"] == {"debounced_complete": 1}
    assert payload["snapshot_gate"] == {"debounced_complete": 1}


@pytest.mark.architecture
def test_no_old_worker_runtime_settings() -> None:
    from parallax.platform.config.settings import (
        LlmConfig,
        NotificationsConfig,
        OkxProviderConfig,
        Settings,
        WorkersSettings,
    )

    forbidden_runtime_settings = {
        "enrichment_poll_interval_seconds",
        "enrichment_batch_size",
        "watchlist_handle_summary_poll_interval_seconds",
        "notification_worker_interval_seconds",
        "notification_delivery_interval_seconds",
        "_".join(("anchor", "price", "interval", "seconds")),
        "resolution_refresh_interval_seconds",
        "asset_profile_refresh_interval_seconds",
        "cex_sync_interval_seconds",
        "dex_sync_interval_seconds",
        "dex_price_hot_stale_seconds",
        "dex_price_warm_stale_seconds",
        "dex_price_refresh_limit",
    }
    checked_models = (LlmConfig, NotificationsConfig, OkxProviderConfig, Settings)
    violations = {
        f"{model.__name__}.{field_name}"
        for model in checked_models
        for field_name in model.model_fields
        if field_name in forbidden_runtime_settings
    }
    worker_fields = set(WorkersSettings.model_fields) - {"defaults", "agent_runtime"}

    assert violations == set()
    assert worker_fields == set(MANIFEST_WORKER_CLASSES)


@pytest.mark.architecture
def test_runtime_contracts_forbid_old_watchlist_queue_tokens() -> None:
    old_summary_constant = "_".join(("WATCHLIST", "SUMMARY", "JOBS"))
    old_summary_jobs = '"' + "_".join(("watchlist", "summary", "jobs")) + '"'
    old_summary_dirty_targets = '"' + "_".join(("watchlist", "summary", "dirty", "targets")) + '"'
    forbidden_tokens = (old_summary_constant, old_summary_jobs, old_summary_dirty_targets)
    scanned_paths = [
        SRC / "app/runtime/job_queue.py",
        SRC / "app/runtime/ops_diagnostics.py",
        ROOT / "tests/unit/test_ops_diagnostics.py",
        ROOT / "tests/architecture/test_runtime_worker_constraint_hard_cut.py",
    ]

    violations = [
        f"{_rel(path)} contains {token}"
        for path in scanned_paths
        for token in forbidden_tokens
        if token in path.read_text(encoding="utf-8")
    ]

    assert violations == []


@pytest.mark.architecture
def test_runtime_job_queue_is_ops_descriptor_only_without_generic_executor() -> None:
    job_queue_path = SRC / "app/runtime/job_queue.py"
    job_queue_source = job_queue_path.read_text(encoding="utf-8")
    job_queue_tree = ast.parse(job_queue_source)
    ops_diagnostics_source = (SRC / "app/runtime/ops_diagnostics.py").read_text(encoding="utf-8")
    forbidden_classes = {"BackoffPolicy", "JobQueue"}
    forbidden_functions = {"claim_batch", "finalize_success", "finalize_failure", "reclaim_stale"}
    forbidden_tokens = (
        "uuid.uuid4",
        "time.time",
        "RETURNING job.*",
        "RETURNING *",
    )

    class_names = {node.name for node in ast.walk(job_queue_tree) if isinstance(node, ast.ClassDef)}
    function_names = {
        node.name for node in ast.walk(job_queue_tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert class_names.isdisjoint(forbidden_classes)
    assert function_names.isdisjoint(forbidden_functions)
    assert [token for token in forbidden_tokens if token in job_queue_source] == []
    assert "JOB_QUEUE_DESCRIPTORS.get(" in ops_diagnostics_source
    assert "for descriptor in JOB_QUEUE_DESCRIPTORS.values()" in ops_diagnostics_source


@pytest.mark.architecture
def test_narrative_hard_cut_contracts_are_documented() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in (DOCS_WORKERS, DOCS_CONTRACTS, NARRATIVE_ARCHITECTURE)
    )

    for phrase in (
        "source_event_ids_json",
        "source-set truth",
        "no runtime compatibility",
        "NarrativeAdmissionWorker",
        "semantic/digest tables are not read",
        "narrative_admission",
        "Target-post responses remain raw evidence pages",
        "ops rebuild-narrative-intel",
    ):
        assert phrase in combined


@pytest.mark.architecture
def test_global_architecture_does_not_describe_retired_narrative_llm_lanes_as_current() -> None:
    architecture = DOCS_ARCHITECTURE.read_text(encoding="utf-8")
    forbidden_active_phrases = (
        "domains/narrative_intel     (per-mention semantics and token discussion digests)",
        "| `domains/narrative_intel/` | Per-mention trade stance / attention valence labels",
        "Mention semantics, token discussion digest generation, evidence refs",
    )
    required_phrases = (
        "Public surfaces expose only admission-derived `narrative_admission` state.",
        "Per-mention semantics and discussion-digest lanes and storage are removed.",
        "Current `narrative_admissions` ownership, API admission coverage",
    )

    assert [phrase for phrase in forbidden_active_phrases if phrase in architecture] == []
    assert [phrase for phrase in required_phrases if phrase not in architecture] == []


@pytest.mark.architecture
def test_public_narrative_reads_do_not_expose_retired_semantic_backlog() -> None:
    repository = NARRATIVE_REPOSITORY.read_text(encoding="utf-8")
    current_admission_method = repository.split("def current_narrative_admissions_for_targets", 1)[1].split(
        "def _current_admissions_for_targets",
        1,
    )[0]
    read_model = NARRATIVE_READ_MODEL.read_text(encoding="utf-8")
    api_schemas = API_SCHEMAS.read_text(encoding="utf-8")

    forbidden_repository_tokens = (
        "semantic_backlog_",
        "_semantic_coverage_for_admissions",
        "semantic_labeling_pending",
    )
    forbidden_read_model_tokens = (
        "semantic_backlog_",
        '"processing"',
    )
    forbidden_schema_tokens = (
        "NarrativeBacklogHealthData",
        "NarrativeSemanticBacklog",
    )

    assert [token for token in forbidden_repository_tokens if token in current_admission_method] == []
    assert [token for token in forbidden_repository_tokens if token in repository] == []
    assert [token for token in forbidden_read_model_tokens if token in read_model] == []
    assert [token for token in forbidden_schema_tokens if token in api_schemas] == []


@pytest.mark.architecture
def test_wake_bus_is_emit_only() -> None:
    from parallax.app.runtime import wake_bus

    text = (SRC / "app/runtime/wake_bus.py").read_text(encoding="utf-8")
    waiter_text = (SRC / "app/runtime/wake_waiter.py").read_text(encoding="utf-8")
    legacy_channel = "_".join(("market", "observation", "written"))

    assert not hasattr(wake_bus, "WakeListener")
    assert not hasattr(wake_bus.WakeBus, f"notify_{legacy_channel}")
    assert not hasattr(wake_bus.WakeBus, "notify_news_item_brief_updated")
    assert legacy_channel not in text
    assert "news_item_brief_updated" not in text
    assert "notify_market_tick_written" in text
    assert "LISTEN" not in text
    assert 'getattr(conn, "commit", None)' not in text
    assert 'getattr(conn, "commit", None)' not in waiter_text
    assert "if not notifies:" not in waiter_text


@pytest.mark.architecture
def test_wake_waiter_timeout_is_formal_nonnegative_contract_without_runtime_repair() -> None:
    text = (SRC / "app/runtime/wake_waiter.py").read_text(encoding="utf-8")
    notification_factory = (WORKER_FACTORIES / "notifications.py").read_text(encoding="utf-8")
    wait_source = text.split("def wait", 1)[1].split("\n    def _wait_once", 1)[0]
    local_wait_source = notification_factory.split("class _LocalWakeWaiter", 1)[1]
    forbidden_tokens = (
        "max(0.0, float(timeout))",
        "max(0.0, timeout)",
    )

    assert [token for token in forbidden_tokens if token in wait_source] == []
    assert [token for token in forbidden_tokens if token in local_wait_source] == []
    assert "_nonnegative_timeout_seconds(timeout)" in wait_source
    assert "_nonnegative_timeout_seconds(timeout)" in local_wait_source
    assert "wake_waiter_timeout_seconds_required" in text
    assert "wake_waiter_timeout_seconds_required" in notification_factory


@pytest.mark.architecture
def test_wake_bus_requires_connection_context_without_raw_connection_fallback() -> None:
    text = (SRC / "app/runtime/wake_bus.py").read_text(encoding="utf-8")
    forbidden_tokens = (
        'hasattr(conn_or_context, "__enter__")',
        "conn_or_context = self._conn_factory()",
        "_execute_notify(conn_or_context",
        "_commit(conn_or_context)",
    )

    assert [token for token in forbidden_tokens if token in text] == []
    assert "with context as conn:" in text
    assert "wake_bus_connection_context_required" in text


@pytest.mark.architecture
def test_runtime_wake_emitters_do_not_swallow_missing_notify_contracts() -> None:
    paths = (
        SRC / "domains/notifications/runtime/notification_worker.py",
        SRC / "domains/news_intel/runtime/news_fetch_worker.py",
        SRC / "domains/news_intel/runtime/news_source_quality_projection_worker.py",
        SRC / "domains/asset_market/runtime/market_tick_current_projection_worker.py",
        SRC / "domains/asset_market/runtime/event_anchor_backfill_worker.py",
    )
    forbidden = (
        'getattr(self.delivery_wake, "wake", None)',
        'getattr(wake_bus, "notify_news_page_dirty", None)',
        'getattr(self.wake_emitter, "notify_market_tick_current_updated", None)',
        'getattr(wake_emitter, "notify_market_tick_written", None)',
        "if notify is None:",
        "if wake is not None:",
    )
    violations = [
        f"{_rel(path)} keeps optional wake-emitter compatibility token `{token}`"
        for path in paths
        for token in forbidden
        if token in path.read_text(encoding="utf-8")
    ]

    assert violations == []


@pytest.mark.architecture
def test_worker_base_wake_waiter_contract_is_direct_when_injected() -> None:
    text = (SRC / "app/runtime/worker_base.py").read_text(encoding="utf-8")
    close_source = text.split("async def _close_wake_waiter", 1)[1].split(
        "\n\ndef _worker_result_payload",
        1,
    )[0]
    forbidden = (
        "import inspect",
        'getattr(self.wake_waiter, "wake", None)',
        'getattr(self.wake_waiter, "close", None)',
        'hasattr(self.wake_waiter, "async_wait")',
        "inspect.isawaitable",
        "await result",
    )
    violations = [
        f"worker_base keeps optional wake-waiter compatibility token `{token}`" for token in forbidden if token in text
    ]

    assert violations == []
    assert "result = self.wake_waiter.close()" in close_source
    assert "worker_wake_waiter_close_must_be_sync" in close_source


@pytest.mark.architecture
def test_worker_base_core_settings_use_formal_worker_settings_without_runtime_defaults() -> None:
    text = (SRC / "app/runtime/worker_base.py").read_text(encoding="utf-8")
    enabled_source = text.split("def enabled", 1)[1].split("\n    @property\n    def effective_status", 1)[0]
    interval_source = text.split("def interval_seconds", 1)[1].split(
        "\n    @property\n    def soft_timeout_seconds",
        1,
    )[0]
    timeout_source = text.split("def soft_timeout_seconds", 1)[1].split(
        "\n    async def _run_once_with_timeout",
        1,
    )[0]
    backoff_source = text.split("def _backoff_seconds", 1)[1].split("\n    def _queue_depth", 1)[0]
    forbidden = (
        "_DEFAULT_INTERVAL_SECONDS",
        "_DEFAULT_BACKOFF_BASE_MS",
        "_DEFAULT_BACKOFF_MAX_MS",
        'getattr(self.settings, "enabled", True)',
        'getattr(self.settings, "interval_seconds",',
        'getattr(self.settings, "backoff"',
        'getattr(backoff, "base_ms"',
        'getattr(backoff, "max_ms"',
        "max(0.0, float(self.settings.interval_seconds))",
        "max(0.0, float(self.settings.soft_timeout_seconds))",
        "max(0.0, float(self.settings.hard_timeout_seconds))",
        "min(max(0, max_ms), max(0, base_ms)",
    )
    violations = [f"worker_base keeps core settings fallback token `{token}`" for token in forbidden if token in text]

    assert violations == []
    assert "return bool(self.settings.enabled)" in enabled_source
    assert "worker_interval_seconds_required" in text
    assert "worker_soft_timeout_seconds_required" in text
    assert "worker_hard_timeout_seconds_required" in text
    assert "_nonnegative_setting_seconds(" in interval_source
    assert "_nonnegative_setting_seconds(" in timeout_source
    assert "backoff = self.settings.backoff" in backoff_source
    assert "worker_backoff_base_ms_required" in text
    assert "worker_backoff_max_ms_required" in text
    assert "_nonnegative_setting_int(backoff.base_ms" in backoff_source
    assert "_nonnegative_setting_int(backoff.max_ms" in backoff_source


@pytest.mark.architecture
def test_worker_base_advisory_lock_key_uses_formal_settings_without_class_attr_fallback() -> None:
    text = (SRC / "app/runtime/worker_base.py").read_text(encoding="utf-8")
    lock_key_source = text.split("def _advisory_lock_key", 1)[1].split(
        "\n    async def _wait_for_next_iteration",
        1,
    )[0]
    forbidden = (
        'getattr(self.settings, "advisory_lock_key", None)',
        "return int(self.SINGLE_WRITER_KEY)",
        "settings_key = getattr",
    )
    violations = [
        f"worker_base keeps advisory-lock key fallback token `{token}`"
        for token in forbidden
        if token in lock_key_source
    ]

    assert violations == []
    assert "settings_key = self.settings.advisory_lock_key" in lock_key_source
    assert 'raise RuntimeError("worker_advisory_lock_key_required") from exc' in lock_key_source
    assert 'raise RuntimeError("worker_advisory_lock_key_required")' in lock_key_source
    assert "if self.SINGLE_WRITER_KEY is None:" in lock_key_source


@pytest.mark.architecture
def test_worker_base_advisory_lock_release_contract_is_direct() -> None:
    text = (SRC / "app/runtime/worker_base.py").read_text(encoding="utf-8")
    release_source = text.split("def _release_advisory_lock", 1)[1].split(
        "\n    async def _close_wake_waiter",
        1,
    )[0]
    forbidden = (
        'getattr(self._advisory_lock_connection, "release", None)',
        'getattr(self._advisory_lock_connection, "close", None)',
        "release or close",
        "releaser is not None",
    )
    violations = [
        f"worker_base keeps optional advisory-lock release compatibility token `{token}`"
        for token in forbidden
        if token in release_source
    ]

    assert violations == []
    assert "worker_advisory_lock_release_required" in release_source
    assert "release = lock_connection.release" in release_source
    assert "release()" in release_source


@pytest.mark.architecture
@pytest.mark.parametrize("table_name", sorted(SINGLE_WRITER_READ_MODELS))
def test_read_model_single_writers(table_name: str) -> None:
    allowlist = SINGLE_WRITER_READ_MODELS[table_name]
    write_pattern = re.compile(
        rf"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+{re.escape(table_name)}\b",
        re.IGNORECASE,
    )
    violations = [
        f"{_rel(path)} writes {table_name}"
        for path in SRC.rglob("*.py")
        if path not in allowlist
        and "alembic/versions" not in path.as_posix()
        and write_pattern.search(path.read_text())
    ]

    assert violations == []


@pytest.mark.architecture
def test_dirty_target_control_plane_tables_are_not_read_models() -> None:
    assert set(CONTROL_PLANE_TABLES).isdisjoint(SINGLE_WRITER_READ_MODELS)


@pytest.mark.architecture
def test_resolution_refresh_dirty_lookup_queue_is_control_plane() -> None:
    assert CONTROL_PLANE_TABLES["token_discovery_dirty_lookup_keys"] == {
        SRC / "domains/asset_market/repositories/discovery_repository.py",
        SRC / "platform/db/alembic/versions/20260525_0096_token_discovery_dirty_lookup_keys.py",
    }


@pytest.mark.architecture
def test_resolution_refresh_once_helper_is_not_retained() -> None:
    source = (SRC / "domains/asset_market/runtime/resolution_refresh_worker.py").read_text(encoding="utf-8")

    forbidden = (
        "def run_resolution_refresh_once",
        "def _process_lookup",
        "def _process_dex_symbol_lookup",
        "def _process_address_lookup",
    )
    assert [token for token in forbidden if token in source] == []


@pytest.mark.architecture
@pytest.mark.parametrize("table_name", sorted(CONTROL_PLANE_TABLES))
def test_dirty_target_control_plane_sql_is_repository_owned(table_name: str) -> None:
    allowlist = CONTROL_PLANE_TABLES[table_name]
    migration_allowlist = {path for path in allowlist if "alembic/versions" in path.as_posix()}
    runtime_allowlist = allowlist - migration_allowlist
    write_pattern = re.compile(
        rf"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+{re.escape(table_name)}\b",
        re.IGNORECASE,
    )
    violations = [
        f"{_rel(path)} writes control-plane table {table_name}"
        for path in SRC.rglob("*.py")
        if path not in runtime_allowlist
        and "alembic/versions" not in path.as_posix()
        and write_pattern.search(path.read_text())
    ]
    migration_violations = [
        f"{_rel(path)} writes control-plane table {table_name}"
        for path in (SRC / "platform/db/alembic/versions").glob("*.py")
        if path not in migration_allowlist and write_pattern.search(path.read_text())
    ]

    assert all(table_name in path.read_text() for path in migration_allowlist)
    assert violations == []
    assert migration_violations == []


@pytest.mark.architecture
def test_token_radar_runtime_has_no_full_window_source_query() -> None:
    old_query_path = SRC / "domains/token_intel/queries/token_radar_source_query.py"
    old_module = "parallax.domains.token_intel.queries.token_radar_source_query"
    violations = [_rel(path) for path in SRC.rglob("*.py") if path != old_query_path and old_module in path.read_text()]

    assert not old_query_path.exists()
    assert violations == []


@pytest.mark.architecture
def test_runtime_dirty_workers_do_not_run_broad_fact_catchups() -> None:
    banned_by_path = {
        SRC / "domains/token_intel/runtime/token_radar_projection_worker.py": (
            "_enqueue_recent_dirty_targets",
            "enqueue_recent_resolved_targets",
        ),
        SRC / "domains/asset_market/runtime/resolution_refresh_worker.py": (
            ".due_lookup_keys(",
            "recent_refresh_candidates",
        ),
    }
    violations = [
        f"{_rel(path)} contains runtime catch-up token `{token}`"
        for path, banned_tokens in banned_by_path.items()
        for token in banned_tokens
        if token in path.read_text(encoding="utf-8")
    ]

    assert violations == []


@pytest.mark.architecture
def test_discovery_repository_does_not_keep_due_lookup_peek_helper() -> None:
    source = (SRC / "domains/asset_market/repositories/discovery_repository.py").read_text(encoding="utf-8")
    forbidden_tokens = (
        "def due_lookup_keys(",
        "since_ms: int,",
    )
    violations = [token for token in forbidden_tokens if token in source]

    assert violations == []


@pytest.mark.architecture
@pytest.mark.parametrize("table_name", LEGACY_ASSET_TABLES)
def test_legacy_asset_tables_have_no_runtime_writers(table_name: str) -> None:
    write_pattern = re.compile(
        rf"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+{re.escape(table_name)}\b",
        re.IGNORECASE,
    )
    violations = [
        f"{_rel(path)} writes legacy table {table_name}"
        for path in SRC.rglob("*.py")
        if "alembic/versions" not in path.as_posix() and write_pattern.search(path.read_text())
    ]

    assert violations == []


@pytest.mark.architecture
def test_deleted_narrative_llm_workers_are_not_runtime_contracts() -> None:
    assert not (SRC / "domains/narrative_intel/runtime/mention_semantics_worker.py").exists()
    assert not (SRC / "domains/narrative_intel/runtime/token_discussion_digest_worker.py").exists()
    assert not (SRC / "integrations/model_execution/narrative_intel_agent_client.py").exists()


@pytest.mark.architecture
def test_public_narrative_hydration_is_admission_only() -> None:
    text = NARRATIVE_REPOSITORY.read_text()
    method = text.split("def current_narrative_admissions_for_targets", 1)[1].split(
        "def _current_admissions_for_targets",
        1,
    )[0]

    assert "token_discussion_digests" not in method
    assert "token_mention_semantics" not in method
    assert "_current_admissions_for_targets" in method
    assert "_admission_state" in method


@pytest.mark.architecture
def test_removed_narrative_llm_writer_methods_are_not_repository_contracts() -> None:
    text = NARRATIVE_REPOSITORY.read_text()
    removed_methods = (
        "cleanup_narrative_current_hard_cut",
        "replace_current_digest",
        "record_narrative_model_run",
        "complete_mention_semantics_batch",
        "enqueue_missing_mention_semantics",
        "claim_due_mention_semantics",
        "due_digest_targets",
        "digest_context",
    )

    assert all(f"def {name}" not in text for name in removed_methods)


@pytest.mark.architecture
def test_token_radar_narrative_read_model_does_not_reuse_1h_digest_for_other_windows() -> None:
    text = NARRATIVE_READ_MODEL.read_text()

    assert "TOKEN_RADAR_NARRATIVE_SURFACE_WINDOWS" not in text
    assert "_token_radar_overlay_digest" not in text
    assert "reuse_reason" not in text


@pytest.mark.architecture
def test_token_radar_narrative_read_model_requires_formal_target_identity_without_type_id_aliases() -> None:
    text = NARRATIVE_READ_MODEL.read_text()
    forbidden = (
        'row.get("target_type") or row.get("type")',
        'row.get("target_id") or row.get("id")',
        'row.get("type")',
        'row.get("id")',
    )

    assert [token for token in forbidden if token in text] == []
    assert 'target.get("target_type")' in text
    assert 'target.get("target_id")' in text


@pytest.mark.architecture
def test_narrative_runtime_does_not_keep_removed_digest_not_ready_reason() -> None:
    narrative_files = [
        path for path in (SRC / "domains" / "narrative_intel").rglob("*.py") if "/migrations/" not in path.as_posix()
    ]

    offenders = [path for path in narrative_files if "digest_not_ready" in path.read_text()]

    assert offenders == []


@pytest.mark.architecture
def test_deleted_narrative_llm_service_modules_are_not_runtime_contracts() -> None:
    assert not (SRC / "domains/narrative_intel/services/mention_semantics_service.py").exists()
    assert not (SRC / "domains/narrative_intel/services/discussion_digest_service.py").exists()
    assert not (SRC / "domains/narrative_intel/services/narrative_epoch_policy.py").exists()
    assert not (SRC / "domains/narrative_intel/providers.py").exists()


@pytest.mark.architecture
def test_api_routes_do_not_import_narrative_providers_or_write_narrative_tables() -> None:
    violations: list[str] = []
    write_tokens = ("replace_current_digest", "record_narrative_model_run", "complete_mention_semantics_batch")
    for path in sorted(API_ROUTES.glob("routes_*.py")):
        text = path.read_text()
        if "narrative_intel.providers" in text:
            violations.append(f"{_rel(path)} imports narrative providers")
        violations.extend(
            f"{_rel(path)} calls narrative write method {token}" for token in write_tokens if token in text
        )

    assert violations == []


@pytest.mark.architecture
def test_legacy_asset_repository_is_not_imported() -> None:
    forbidden_imports = re.compile(
        r"\b(?:AssetRepository|MarketRepository|asset_repository|market_repository)\b",
    )
    violations = [
        f"{_rel(path)} references legacy AssetRepository/MarketRepository"
        for path in SRC.rglob("*.py")
        if forbidden_imports.search(path.read_text())
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
    return sorted(Path(_module_file(qualified_name)) for qualified_name in MANIFEST_WORKER_CLASSES.values())


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


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


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
