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
    worker_class_by_name,
    worker_dirty_target_tables,
    worker_start_priority,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"
DOCS_WORKERS = ROOT / "docs" / "WORKERS.md"
DOCS_CONTRACTS = ROOT / "docs" / "CONTRACTS.md"
NARRATIVE_ARCHITECTURE = SRC / "domains" / "narrative_intel" / "ARCHITECTURE.md"
NARRATIVE_REPOSITORY = SRC / "domains" / "narrative_intel" / "repositories" / "narrative_repository.py"
NARRATIVE_READ_MODEL = SRC / "domains" / "narrative_intel" / "read_models" / "narrative_read_model.py"
API_ROUTES = SRC / "app" / "surfaces" / "api"
WORKER_FACTORIES = SRC / "app" / "runtime" / "worker_factories"
CEX_OI_RADAR_REPOSITORY = SRC / "domains" / "cex_market_intel" / "repositories" / "cex_oi_radar_repository.py"
CEX_OI_RADAR_BOARD_WORKER = SRC / "domains" / "cex_market_intel" / "runtime" / "cex_oi_radar_board_worker.py"
NEWS_INTEL_CANONICAL_DEDUP_MIGRATION = (
    SRC / "platform/db/alembic/versions/20260528_0117_news_intel_canonical_dedup_hard_cut.py"
)
NEWS_REALTIME_POSTGRES_HOTPATH_MIGRATION = (
    SRC / "platform/db/alembic/versions/20260528_0118_news_realtime_postgres_hotpath_hard_cut.py"
)
ZERO_HARD_TIMEOUT_ALLOWLIST = {"collector"}


MANIFEST_WORKER_CLASSES = worker_class_by_name()

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
        SRC / "domains/asset_market/services/market_tick_current_rebuild.py",
        SRC / "platform/db/alembic/versions/20260523_0090_token_radar_postgres_hard_cut.py",
    },
    "token_image_assets": {
        SRC / "domains/asset_market/repositories/token_image_asset_repository.py",
        SRC / "platform/db/alembic/versions/20260521_0078_token_image_assets.py",
    },
    "token_capture_tier": {
        SRC / "domains/asset_market/repositories/token_capture_tier_repository.py",
    },
    "pulse_candidates": {
        SRC / "domains/pulse_lab/repositories/pulse_candidates_repository.py",
    },
    "pulse_agent_runs": {
        SRC / "domains/pulse_lab/repositories/pulse_evidence_repository.py",
        SRC / "domains/pulse_lab/repositories/pulse_jobs_repository.py",
        SRC / "domains/pulse_lab/repositories/pulse_runs_repository.py",
    },
    "pulse_agent_run_steps": {
        SRC / "domains/pulse_lab/repositories/pulse_runs_repository.py",
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
    "pulse_trigger_dirty_targets": {
        SRC / "domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py",
        SRC / "platform/db/alembic/versions/20260525_0098_runtime_worker_dirty_targets.py",
    },
    "narrative_admission_dirty_targets": {
        SRC / "domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py",
        SRC / "platform/db/alembic/versions/20260525_0098_runtime_worker_dirty_targets.py",
    },
    "token_profile_current_dirty_targets": {
        SRC / "domains/asset_market/repositories/token_profile_current_dirty_target_repository.py",
        SRC / "platform/db/alembic/versions/20260525_0098_runtime_worker_dirty_targets.py",
        SRC / "platform/db/alembic/versions/20260531_0136_okx_symbol_candidate_profile_icons.py",
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
    "pulse.py",
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
            *getattr(manifest, "writes_input_observations", ()),
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
        "pulse_trigger_dirty_targets",
        "token_capture_tier_dirty_targets",
        "token_discovery_dirty_lookup_keys",
        "token_image_source_dirty_targets",
        "token_profile_current_dirty_targets",
        "token_radar_dirty_targets",
    }
    manifest_dirty_targets = {table for dirty_tables in worker_dirty_target_tables().values() for table in dirty_tables}

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
            *getattr(manifest, "writes_input_observations", ()),
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
        providers=SimpleNamespace(asset_market=SimpleNamespace(stream_dex_market=None)),
        scheduler=SimpleNamespace(
            status_payload=lambda: {"collector": {"enabled": False, "running": False}},
            unhealthy_reasons=lambda: [],
        ),
        settings=SimpleNamespace(handles=("toly",)),
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
    payload, status_code = app_module._readiness_payload(runtime, now_ms=now_ms)

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
        CollectorConfig,
        LlmConfig,
        NotificationsConfig,
        OkxProviderConfig,
        Settings,
        WorkersSettings,
    )

    forbidden_runtime_settings = {
        "enrichment_poll_interval_seconds",
        "enrichment_batch_size",
        "pulse_agent_batch_size",
        "pulse_agent_interval_seconds",
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
    checked_models = (CollectorConfig, LlmConfig, NotificationsConfig, OkxProviderConfig, Settings)
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
        ROOT / "tests/unit/test_job_queue.py",
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
def test_narrative_hard_cut_contracts_are_documented() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in (DOCS_WORKERS, DOCS_CONTRACTS, NARRATIVE_ARCHITECTURE)
    )

    for phrase in (
        "source_event_ids_json",
        "source-set truth",
        "no runtime compatibility",
        "NarrativeAdmissionWorker",
        "were hard-cut",
        "no active worker refreshes",
        "discussion_digest.currentness",
        "ops rebuild-narrative-intel",
    ):
        assert phrase in combined


@pytest.mark.architecture
def test_wake_bus_is_emit_only() -> None:
    from parallax.app.runtime import wake_bus

    text = (SRC / "app/runtime/wake_bus.py").read_text(encoding="utf-8")
    legacy_channel = "_".join(("market", "observation", "written"))

    assert not hasattr(wake_bus, "WakeListener")
    assert not hasattr(wake_bus.WakeBus, f"notify_{legacy_channel}")
    assert legacy_channel not in text
    assert "notify_market_tick_written" in text
    assert "LISTEN" not in text


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
def test_no_exact_fingerprint_only_public_narrative_hydration() -> None:
    text = NARRATIVE_REPOSITORY.read_text()
    method = text.split("def current_narrative_snapshots_for_targets", 1)[1].split(
        "def current_digests_for_targets",
        1,
    )[0]

    assert "COALESCE(admissions.source_fingerprint, '') = COALESCE(digest.source_fingerprint, '')" not in method
    assert "_current_ready_digests_for_targets" in method
    assert "public_currentness" in method


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
