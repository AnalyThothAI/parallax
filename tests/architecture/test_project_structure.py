import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_project_metadata_uses_gmgn_twitter_intel_name():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert metadata["project"]["name"] == "gmgn-twitter-intel"
    assert metadata["project"]["scripts"] == {
        "gmgn-twitter-intel": "gmgn_twitter_intel.cli:main",
    }


def test_project_uses_domain_package_src_layout():
    base = ROOT / "src" / "gmgn_twitter_intel"
    api = base / "app" / "surfaces" / "api"
    cli = base / "app" / "surfaces" / "cli"
    assert (ROOT / "pyproject.toml").is_file()
    assert (base / "__init__.py").is_file()
    assert (base / "__main__.py").is_file()
    assert (base / "cli.py").is_file()
    assert (base / "app" / "runtime" / "app.py").is_file()
    assert (api / "http.py").is_file()
    assert (api / "ws.py").is_file()
    assert (cli / "main.py").is_file()
    assert {path.name for path in api.glob("routes_*.py")} == {
        "routes_events.py",
        "routes_notifications.py",
        "routes_pulse.py",
        "routes_radar.py",
        "routes_search.py",
        "routes_social_enrichment.py",
        "routes_status.py",
        "routes_token_image.py",
        "routes_watchlist.py",
    }
    assert {path.name for path in (cli / "commands").glob("*.py")} == {
        "__init__.py",
        "config.py",
        "db.py",
        "ops.py",
        "read_models.py",
        "serve.py",
    }
    for domain in (
        "ingestion",
        "evidence",
        "asset_market",
        "token_intel",
        "social_enrichment",
        "notifications",
        "pulse_lab",
        "account_quality",
    ):
        assert (base / "domains" / domain / "__init__.py").is_file()
    assert (base / "integrations" / "gmgn" / "__init__.py").is_file()
    assert (base / "integrations" / "okx" / "__init__.py").is_file()
    assert (base / "integrations" / "openai_agents" / "__init__.py").is_file()
    assert (base / "platform" / "db" / "postgres_client.py").is_file()
    assert (ROOT / "Makefile").is_file()
    assert (ROOT / "Dockerfile").is_file()
    assert (ROOT / "compose.yaml").is_file()


def test_api_and_cli_surface_roots_stay_thin_dispatchers():
    api = ROOT / "src" / "gmgn_twitter_intel" / "app" / "surfaces" / "api"
    cli = ROOT / "src" / "gmgn_twitter_intel" / "app" / "surfaces" / "cli"
    http_source = (api / "http.py").read_text(encoding="utf-8")
    cli_main_source = (cli / "main.py").read_text(encoding="utf-8")

    assert "@router." not in http_source
    assert "@app." not in http_source
    assert http_source.count("include_router(") == len(list(api.glob("routes_*.py")))
    assert "routes_search" in http_source
    assert "routes_pulse" in http_source

    assert "ArgumentParser" not in cli_main_source
    assert "def handle_" not in cli_main_source
    assert "from .commands import" in cli_main_source
    assert "read_models.READ_MODEL_COMMANDS" in cli_main_source


def test_current_projection_docs_are_postgres_only():
    paths = [
        ROOT / "docs" / "superpowers" / "specs" / "completed" / "2026-05-06-materialized-read-models-production-cn.md",
        ROOT / "docs" / "superpowers" / "plans" / "completed" / "2026-05-06-postgresql-projection-closure.md",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        assert "sqlite" not in text
        assert "test_sqlite" not in text
        assert "wal/fts5" not in text


def test_legacy_narrative_modules_stay_removed():
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "llm_client.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "llm_enrichment.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "narrative_seed_builder.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "narrative_token_linker.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "narrative_service.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "narrative_link_service.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "narrative_link_scoring.py").exists()


def test_enrichment_worker_does_not_claim_legacy_job_types():
    text = (
        ROOT
        / "src"
        / "gmgn_twitter_intel"
        / "domains"
        / "social_enrichment"
        / "repositories"
        / "enrichment_repository.py"
    ).read_text()

    assert "legacy_job_type_retired" in text
    assert "job_type = %s" in text


def test_legacy_token_resolution_runtime_modules_stay_removed():
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "asset_attribution.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "asset_mention_builder.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "asset_resolution_worker.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "asset_resolver.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "token_identity_resolver.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "signal_builder.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "token_attribution.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "search_service.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "rolling_token_flow.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "token_flow_service.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "token_posts_service.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "token_social_timeline_service.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "market_observation_repository.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "token_repository.py").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "token_signal_repository.py").exists()


def test_trading_attention_service_has_been_hard_deleted():
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "trading_attention_service.py").exists()
    assert not (ROOT / "tests" / "test_trading_attention_service.py").exists()


def test_pulse_agent_repository_has_no_dual_name_compatibility_arguments():
    pulse_repo_path = (
        ROOT / "src" / "gmgn_twitter_intel" / "domains" / "pulse_lab" / "repositories" / "pulse_runs_repository.py"
    )
    text = pulse_repo_path.read_text(encoding="utf-8")
    forbidden = {
        "context: dict[str, Any]",
        "request: dict[str, Any]",
        "response: dict[str, Any]",
        "trace_metadata: dict[str, Any]",
        "usage: dict[str, Any]",
        "thesis: dict[str, Any]",
        "radar_score: dict[str, Any]",
        "market_context: dict[str, Any]",
        "gate_reasons: list[Any]",
        "risk_reasons: list[Any]",
        "evidence_event_ids: list[Any]",
        "source_event_ids: list[Any]",
    }
    for item in forbidden:
        assert item not in text


def test_pulse_repository_monolith_and_session_facade_stay_removed():
    this_file = Path(__file__).resolve()
    active_paths = [
        path
        for base in (ROOT / "src", ROOT / "tests")
        for path in base.rglob("*.py")
        if "platform/db/alembic/versions" not in path.as_posix() and path.resolve() != this_file
    ]
    text_by_path = {path: path.read_text(encoding="utf-8") for path in active_paths}

    assert not (
        ROOT / "src" / "gmgn_twitter_intel" / "domains" / "pulse_lab" / "repositories" / "pulse_repository.py"
    ).exists()
    class_name = "Pulse" + "Repository"
    import_text = f"from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_repository import {class_name}"
    for path, text in text_by_path.items():
        assert f"class {class_name}" not in text, path
        assert f"{class_name}(" not in text, path
        assert re.search(r"repos\\.pulse\\b", text) is None, path
        assert import_text not in text, path


def test_pulse_repository_split_keeps_read_sql_and_jobs_out_of_shared_admission():
    repo_dir = ROOT / "src" / "gmgn_twitter_intel" / "domains" / "pulse_lab" / "repositories"
    shared_text = (repo_dir / "_pulse_repository_shared.py").read_text(encoding="utf-8")
    admission_text = (repo_dir / "pulse_admission_repository.py").read_text(encoding="utf-8")

    assert "social_event_extractions" not in shared_text
    assert "LEFT JOIN events" not in shared_text
    assert "PulseJobsRepository" not in admission_text


def test_current_token_radar_runtime_does_not_import_old_token_market_paths():
    forbidden = {
        "TokenRepository",
        "TokenSignalRepository",
        "token_market_snapshots",
        "token_signal_snapshots",
    }
    runtime_files = [
        ROOT / "src/gmgn_twitter_intel/app/runtime/app.py",
        ROOT / "src/gmgn_twitter_intel/app/surfaces/api/http.py",
        ROOT / "src/gmgn_twitter_intel/domains/evidence/services/ingest_service.py",
        ROOT / "src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py",
        ROOT / "src/gmgn_twitter_intel/app/runtime/repository_session.py",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in runtime_files)
    for item in forbidden:
        assert item not in text


def test_runtime_source_does_not_reference_removed_token_radar_versions():
    removed_version = "v" + "4"
    forbidden = {
        f"token_radar_{removed_version}",
        f"token-radar-{removed_version}",
        f"{removed_version}_deterministic_resolver",
    }
    runtime_files = [
        path
        for path in (ROOT / "src" / "gmgn_twitter_intel").rglob("*.py")
        if "platform/db/alembic/versions" not in path.as_posix()
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in runtime_files)
    for item in forbidden:
        assert item not in text


def test_makefile_exposes_global_cli_install_targets():
    makefile = (ROOT / "Makefile").read_text()

    assert "install: ## install or update the global CLI with uv tool" in makefile
    assert "\t@uv tool install --force --reinstall ." in makefile
    assert "uninstall: ## uninstall the global CLI installed by uv tool" in makefile
    assert "\t@uv tool uninstall gmgn-twitter-intel" in makefile
    assert "tool-path: ## ensure uv tool executables are on PATH" in makefile
    assert "\t@uv tool update-shell" in makefile
    assert "init: ## create ~/.gmgn-twitter-intel/config.yaml" in makefile


def test_compose_bind_mounts_local_runtime_home_without_env_config_sources():
    compose = (ROOT / "compose.yaml").read_text()
    data = yaml.safe_load(compose)
    services = data["services"]

    assert "env_file:" not in compose
    assert "environment" not in services["app"]
    assert "environment" not in services["migrate"]
    assert "${HOME}/.gmgn-twitter-intel:/root/.gmgn-twitter-intel" in compose
    assert "gmgn-twitter-intel_data" not in compose
    assert ("LANCE" + "_") not in compose
    assert ("RAYON" + "_") not in compose


def test_removed_root_runtime_files_stay_absent():
    assert not (ROOT / "gmgn_twitter_monitor.py").exists()
    assert not (ROOT / "gmgn-twitter-monitor.service").exists()
    assert not (ROOT / "requirements.txt").exists()
    assert not (ROOT / "gmgn_twitter_monitor").exists()
    assert not (ROOT / "src" / "gmgn_twitter_gateway").exists()
    assert not (ROOT / "deploy" / "systemd" / "gmgn-twitter-gateway.service").exists()
    assert not (ROOT / "deploy" / "systemd" / "gmgn-twitter-intel.service").exists()
    assert not (ROOT / "deploy" / "macos" / "install_launchd.sh").exists()
    assert not (ROOT / "deploy" / "nginx" / "gmgn-twitter-intel.conf").exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "service_control.py").exists()
