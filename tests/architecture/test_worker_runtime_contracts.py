from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"
DOCS_WORKERS = ROOT / "docs" / "WORKERS.md"
DOCS_CONTRACTS = ROOT / "docs" / "CONTRACTS.md"
NARRATIVE_ARCHITECTURE = SRC / "domains" / "narrative_intel" / "ARCHITECTURE.md"
NARRATIVE_REPOSITORY = SRC / "domains" / "narrative_intel" / "repositories" / "narrative_repository.py"
NARRATIVE_DIGEST_WORKER = SRC / "domains" / "narrative_intel" / "runtime" / "token_discussion_digest_worker.py"
NARRATIVE_EPOCH_POLICY = SRC / "domains" / "narrative_intel" / "services" / "narrative_epoch_policy.py"
API_ROUTES = SRC / "app" / "surfaces" / "api"
WORKER_FACTORIES = SRC / "app" / "runtime" / "worker_factories"

ZERO_HARD_TIMEOUT_ALLOWLIST = {"collector"}


def _legacy_anchor_worker_key() -> str:
    return "_".join(("anchor", "price"))


EXPECTED_WORKERS = {
    "collector": "gmgn_twitter_intel.domains.ingestion.runtime.collector_service.CollectorService",
    "market_tick_stream": (
        "gmgn_twitter_intel.domains.asset_market.runtime.market_tick_stream_worker.MarketTickStreamWorker"
    ),
    "market_tick_poll": "gmgn_twitter_intel.domains.asset_market.runtime.market_tick_poll_worker.MarketTickPollWorker",
    "event_anchor_backfill": (
        "gmgn_twitter_intel.domains.asset_market.runtime.event_anchor_backfill_worker.EventAnchorBackfillWorker"
    ),
    "token_capture_tier": (
        "gmgn_twitter_intel.domains.asset_market.runtime.token_capture_tier_worker.TokenCaptureTierWorker"
    ),
    "live_price_gateway": "gmgn_twitter_intel.domains.asset_market.runtime.live_price_gateway.LivePriceGateway",
    "resolution_refresh": (
        "gmgn_twitter_intel.domains.asset_market.runtime.resolution_refresh_worker.ResolutionRefreshWorker"
    ),
    "asset_profile_refresh": (
        "gmgn_twitter_intel.domains.asset_market.runtime.asset_profile_refresh_worker.AssetProfileRefreshWorker"
    ),
    "token_image_mirror": (
        "gmgn_twitter_intel.domains.asset_market.runtime.token_image_mirror_worker.TokenImageMirrorWorker"
    ),
    "token_profile_current": (
        "gmgn_twitter_intel.domains.asset_market.runtime.token_profile_current_worker.TokenProfileCurrentWorker"
    ),
    "token_radar_projection": (
        "gmgn_twitter_intel.domains.token_intel.runtime.token_radar_projection_worker.TokenRadarProjectionWorker"
    ),
    "narrative_admission": (
        "gmgn_twitter_intel.domains.narrative_intel.runtime.narrative_admission_worker.NarrativeAdmissionWorker"
    ),
    "mention_semantics": (
        "gmgn_twitter_intel.domains.narrative_intel.runtime.mention_semantics_worker.MentionSemanticsWorker"
    ),
    "token_discussion_digest": (
        "gmgn_twitter_intel.domains.narrative_intel.runtime.token_discussion_digest_worker.TokenDiscussionDigestWorker"
    ),
    "news_fetch": "gmgn_twitter_intel.domains.news_intel.runtime.news_fetch_worker.NewsFetchWorker",
    "news_item_process": (
        "gmgn_twitter_intel.domains.news_intel.runtime.news_item_process_worker.NewsItemProcessWorker"
    ),
    "news_story_projection": (
        "gmgn_twitter_intel.domains.news_intel.runtime.news_story_projection_worker.NewsStoryProjectionWorker"
    ),
    "news_item_brief": ("gmgn_twitter_intel.domains.news_intel.runtime.news_item_brief_worker.NewsItemBriefWorker"),
    "news_page_projection": (
        "gmgn_twitter_intel.domains.news_intel.runtime.news_page_projection_worker.NewsPageProjectionWorker"
    ),
    "news_source_quality_projection": (
        "gmgn_twitter_intel.domains.news_intel.runtime.news_source_quality_projection_worker."
        "NewsSourceQualityProjectionWorker"
    ),
    "cex_oi_radar_board": (
        "gmgn_twitter_intel.domains.cex_market_intel.runtime.cex_oi_radar_board_worker.CexOiRadarBoardWorker"
    ),
    "macro_view_projection": (
        "gmgn_twitter_intel.domains.macro_intel.runtime.macro_view_projection_worker.MacroViewProjectionWorker"
    ),
    "pulse_candidate": "gmgn_twitter_intel.domains.pulse_lab.runtime.pulse_candidate_worker.PulseCandidateWorker",
    "enrichment": "gmgn_twitter_intel.domains.social_enrichment.runtime.enrichment_worker.EnrichmentWorker",
    "handle_summary": "gmgn_twitter_intel.domains.watchlist_intel.runtime.handle_summary_worker.HandleSummaryWorker",
    "notification_rule": "gmgn_twitter_intel.domains.notifications.runtime.notification_worker.NotificationWorker",
    "notification_delivery": (
        "gmgn_twitter_intel.domains.notifications.runtime.notification_delivery.NotificationDeliveryWorker"
    ),
}

OLD_READYZ_WORKER_KEYS = {
    "collector",
    "market_tick_stream",
    "market_tick_poll",
    "event_anchor_backfill",
    "token_capture_tier",
    "live_price_gateway",
    "resolution_refresh",
    "asset_profile_refresh",
    "token_image_mirror",
    "token_profile_current",
    "token_radar_projection",
    "narrative_admission",
    "mention_semantics",
    "token_discussion_digest",
    "news_fetch",
    "news_item_process",
    "news_story_projection",
    "news_item_brief",
    "news_page_projection",
    "news_source_quality_projection",
    "pulse_candidate",
    "enrichment",
    "handle_summary",
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
    f"{_legacy_anchor_worker_key()}_interval_seconds",
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

SINGLE_WRITER_READ_MODELS: dict[str, set[Path]] = {
    "token_radar_rows": TOKEN_RADAR_WRITE_OWNER_ALLOWLIST,
    "token_profile_current": {
        SRC / "domains/asset_market/repositories/token_profile_current_repository.py",
        SRC / "domains/asset_market/runtime/token_profile_current_worker.py",
        SRC / "platform/db/alembic/versions/20260517_0052_token_profile_current.py",
        SRC / "platform/db/alembic/versions/20260521_0079_token_profile_local_logo_hard_cut.py",
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
    "token_mention_semantics": {
        SRC / "domains/narrative_intel/repositories/narrative_repository.py",
        SRC / "domains/narrative_intel/runtime/mention_semantics_worker.py",
        SRC / "platform/db/alembic/versions/20260518_0063_narrative_intel_read_models.py",
    },
    "narrative_admissions": {
        SRC / "domains/narrative_intel/repositories/narrative_repository.py",
        SRC / "domains/narrative_intel/runtime/narrative_admission_worker.py",
        SRC / "platform/db/alembic/versions/20260518_0063_narrative_intel_read_models.py",
        SRC / "platform/db/alembic/versions/20260519_0064_narrative_admission_source_sets.py",
    },
    "token_discussion_digests": {
        SRC / "domains/narrative_intel/repositories/narrative_repository.py",
        SRC / "domains/narrative_intel/runtime/token_discussion_digest_worker.py",
        SRC / "platform/db/alembic/versions/20260518_0063_narrative_intel_read_models.py",
    },
    "news_story_groups": {
        SRC / "domains/news_intel/repositories/news_repository.py",
        SRC / "domains/news_intel/runtime/news_story_projection_worker.py",
        SRC / "platform/db/alembic/versions/20260519_0064_news_intel_kappa_cqrs.py",
    },
    "news_story_members": {
        SRC / "domains/news_intel/repositories/news_repository.py",
        SRC / "domains/news_intel/runtime/news_story_projection_worker.py",
        SRC / "platform/db/alembic/versions/20260519_0064_news_intel_kappa_cqrs.py",
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
    "cex_oi_radar_runs": {
        SRC / "domains/cex_market_intel/repositories/cex_oi_radar_repository.py",
        SRC / "domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py",
        SRC / "platform/db/alembic/versions/20260521_0073_cex_oi_radar_board.py",
    },
    "cex_oi_radar_rows": {
        SRC / "domains/cex_market_intel/repositories/cex_oi_radar_repository.py",
        SRC / "domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py",
        SRC / "platform/db/alembic/versions/20260521_0073_cex_oi_radar_board.py",
    },
    "macro_view_snapshots": {
        SRC / "domains/macro_intel/repositories/macro_intel_repository.py",
        SRC / "domains/macro_intel/runtime/macro_view_projection_worker.py",
        SRC / "platform/db/alembic/versions/20260521_0076_macro_views.py",
    },
}

LEGACY_ASSET_TABLES = ("assets", "asset_aliases", "asset_venues", "asset_market_snapshots")
EXPECTED_WORKER_FACTORY_FILES = {
    "__init__.py",
    "asset_market.py",
    "cex_market_intel.py",
    "enrichment.py",
    "ingestion.py",
    "macro_intel.py",
    "narrative_intel.py",
    "news_intel.py",
    "notifications.py",
    "pulse.py",
    "token_intel.py",
    "watchlist.py",
}
BOOTSTRAP_RUNTIME_WORKER_IMPORT_ALLOWLIST = {
    "gmgn_twitter_intel.domains.ingestion.runtime.collector_service",
}


@pytest.mark.architecture
@pytest.mark.parametrize(("worker_key", "qualified_name"), EXPECTED_WORKERS.items())
def test_all_long_running_workers_inherit_worker_base(worker_key: str, qualified_name: str) -> None:
    try:
        worker_class = _import_qualified_name(qualified_name)
    except ModuleNotFoundError as exc:
        if ".narrative_intel." in qualified_name:
            pytest.skip(f"{worker_key} runtime is owned by agent A: {exc.name}")
        raise

    assert issubclass(worker_class, WorkerBase), f"{worker_key} must inherit WorkerBase"


@pytest.mark.architecture
def test_long_running_workers_do_not_override_worker_base_run_without_allowlist() -> None:
    allowlist = {
        "live_price_gateway",
    }
    violations: list[str] = []
    for worker_key, qualified_name in EXPECTED_WORKERS.items():
        try:
            worker_class = _import_qualified_name(qualified_name)
        except ModuleNotFoundError as exc:
            if ".narrative_intel." in qualified_name:
                pytest.skip(f"{worker_key} runtime is owned by agent A: {exc.name}")
            raise
        if worker_key in allowlist:
            continue
        if "run" in worker_class.__dict__:
            violations.append(f"{worker_key} overrides run()")

    assert violations == []


@pytest.mark.architecture
def test_worker_registry_matches_workers_yaml_schema() -> None:
    from gmgn_twitter_intel.app.runtime.worker_registry import CANONICAL_WORKER_CLASSES, CANONICAL_WORKER_NAMES
    from gmgn_twitter_intel.app.runtime.worker_scheduler import _START_PRIORITY
    from gmgn_twitter_intel.platform.config.settings import WorkersSettings

    expected_keys = set(EXPECTED_WORKERS)
    settings_keys = set(WorkersSettings.model_fields) - {"defaults", "agent_runtime"}
    docs_keys = _worker_inventory_keys()

    assert CANONICAL_WORKER_CLASSES == EXPECTED_WORKERS
    assert set(CANONICAL_WORKER_NAMES) == expected_keys
    assert set(_START_PRIORITY) == expected_keys
    assert settings_keys == expected_keys
    assert docs_keys == expected_keys


@pytest.mark.architecture
def test_token_image_mirror_starts_between_profile_refresh_and_current_projection() -> None:
    from gmgn_twitter_intel.app.runtime.worker_registry import WORKER_START_PRIORITY

    assert WORKER_START_PRIORITY["asset_profile_refresh"] < WORKER_START_PRIORITY["token_image_mirror"]
    assert WORKER_START_PRIORITY["token_image_mirror"] < WORKER_START_PRIORITY["token_profile_current"]


@pytest.mark.architecture
def test_non_continuous_worker_defaults_have_finite_hard_timeout() -> None:
    from gmgn_twitter_intel.app.runtime.worker_registry import CANONICAL_WORKER_NAMES
    from gmgn_twitter_intel.platform.config.settings import WorkersSettings, default_workers_yaml

    settings = WorkersSettings(**yaml.safe_load(default_workers_yaml()))

    for worker_key in CANONICAL_WORKER_NAMES:
        worker_settings = getattr(settings, worker_key)
        hard_timeout = worker_settings.hard_timeout_seconds
        if worker_key in ZERO_HARD_TIMEOUT_ALLOWLIST:
            assert hard_timeout == 0
            continue
        assert hard_timeout > 0, f"{worker_key} must have a finite hard timeout"


@pytest.mark.architecture
def test_worker_construction_is_split_into_domain_factories() -> None:
    from gmgn_twitter_intel.app.runtime.worker_factories import worker_factory_specs
    from gmgn_twitter_intel.app.runtime.worker_registry import CANONICAL_WORKER_NAMES

    bootstrap_path = SRC / "app/runtime/bootstrap.py"
    bootstrap_tree = _parse(bootstrap_path)
    bootstrap_text = bootstrap_path.read_text(encoding="utf-8")
    bootstrap_functions = {
        node.name for node in ast.walk(bootstrap_tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    expected_worker_modules = {
        qualified_name.rpartition(".")[0] for key, qualified_name in EXPECTED_WORKERS.items() if key != "collector"
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
    assert set(owned_keys) == set(CANONICAL_WORKER_NAMES)
    assert len(owned_keys) == len(set(owned_keys))
    assert "_construct_workers" not in bootstrap_functions
    assert bootstrap_runtime_worker_imports == []
    for worker_key in set(EXPECTED_WORKERS) - {"collector"}:
        assert f'constructed["{worker_key}"]' not in bootstrap_text
    assert sorted(expected_worker_modules - factory_runtime_worker_imports) == []


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
    worker_fields = set(WorkersSettings.model_fields) - {"defaults", "agent_runtime"}

    assert violations == set()
    assert worker_fields == set(EXPECTED_WORKERS)


@pytest.mark.architecture
def test_narrative_hard_cut_contracts_are_documented() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in (DOCS_WORKERS, DOCS_CONTRACTS, NARRATIVE_ARCHITECTURE)
    )

    for phrase in (
        "source_event_ids_json",
        "source-set truth",
        "maintenance writer exception",
        "no runtime compatibility",
        "discussion_digest.currentness",
        "unsupported_window",
        "no_material_delta",
        "llm_cycle_budget_exhausted",
        "llm_failure_budget_exhausted",
    ):
        assert phrase in combined


@pytest.mark.architecture
def test_wake_bus_is_emit_only() -> None:
    from gmgn_twitter_intel.app.runtime import wake_bus

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
def test_token_discussion_digest_worker_uses_epoch_policy_for_refresh_decisions() -> None:
    text = NARRATIVE_DIGEST_WORKER.read_text()
    policy_text = NARRATIVE_EPOCH_POLICY.read_text()

    assert "NarrativeEpochPolicy" in text
    assert "self.epoch_policy.evaluate" in text
    assert 'reason="unsupported_window"' in policy_text
    assert "should_write_status_digest=False" in policy_text


@pytest.mark.architecture
def test_no_exact_fingerprint_only_public_narrative_hydration() -> None:
    text = NARRATIVE_REPOSITORY.read_text()
    method = text.split("def current_narrative_snapshots_for_targets", 1)[1].split(
        "def current_digests_for_targets",
        1,
    )[0]

    assert "COALESCE(admissions.source_fingerprint, '') = COALESCE(digest.source_fingerprint, '')" not in method
    assert "latest_ready_digest_for_target" in method
    assert "public_currentness" in method


@pytest.mark.architecture
def test_narrative_cleanup_deletes_non_current_digest_state() -> None:
    text = NARRATIVE_REPOSITORY.read_text()
    method = text.split("def cleanup_narrative_current_hard_cut", 1)[1].split(
        "def record_narrative_model_run",
        1,
    )[0]

    assert "DELETE FROM token_discussion_digests" in method
    assert "deleted_old_digests" in method
    assert "fingerprint_mismatch_digests_preserved" not in method
    assert "UPDATE token_discussion_digests" not in method
    assert "SET status = 'stale'" not in method


@pytest.mark.architecture
def test_token_discussion_digest_worker_does_not_write_unsupported_5m_digests() -> None:
    text = NARRATIVE_EPOCH_POLICY.read_text()
    unsupported_index = text.find('reason="unsupported_window"')
    next_decision_index = text.find("if last_ready_digest is None", unsupported_index)

    assert unsupported_index >= 0
    assert "should_refresh=False" in text[unsupported_index:next_decision_index]
    assert "should_write_status_digest=False" in text[unsupported_index:next_decision_index]


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
    paths: list[Path] = []
    for qualified_name in EXPECTED_WORKERS.values():
        try:
            paths.append(Path(_module_file(qualified_name)))
        except ModuleNotFoundError:
            if ".narrative_intel." not in qualified_name:
                raise
    return sorted(paths)


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
