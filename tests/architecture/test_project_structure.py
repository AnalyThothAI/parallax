import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_project_metadata_uses_parallax_name():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert metadata["project"]["name"] == "parallax"
    assert metadata["project"]["scripts"] == {
        "parallax": "parallax.cli:main",
    }


def test_macrodata_cli_is_packaged_from_versioned_git_source():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
    dependencies = set(metadata["project"]["dependencies"])
    sources = metadata["tool"]["uv"]["sources"]

    assert "macrodata-cli" in dependencies
    assert sources["macrodata-cli"] == {
        "git": "https://github.com/AnalyThothAI/macrodata-cli.git",
        "tag": "v0.1.5",
    }
    assert "path" not in sources["macrodata-cli"]
    assert "editable" not in sources["macrodata-cli"]
    assert "url" not in sources["macrodata-cli"]


def test_project_uses_domain_package_src_layout():
    base = ROOT / "src" / "parallax"
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
        "routes_cex.py",
        "routes_events.py",
        "routes_macro.py",
        "routes_news.py",
        "routes_notifications.py",
        "routes_ops.py",
        "routes_pulse.py",
        "routes_radar.py",
        "routes_search.py",
        "routes_status.py",
        "routes_token_images.py",
        "routes_watchlist.py",
    }
    assert {path.name for path in (cli / "commands").glob("*.py")} == {
        "__init__.py",
        "config.py",
        "db.py",
        "macro.py",
        "ops.py",
        "pulse_replay.py",
        "queue_ops.py",
        "read_models.py",
        "serve.py",
    }
    for domain in (
        "ingestion",
        "evidence",
        "asset_market",
        "token_intel",
        "notifications",
        "pulse_lab",
        "account_quality",
    ):
        assert (base / "domains" / domain / "__init__.py").is_file()
    assert (base / "integrations" / "gmgn" / "__init__.py").is_file()
    assert (base / "integrations" / "okx" / "__init__.py").is_file()
    assert (base / "integrations" / "model_execution" / "__init__.py").is_file()
    assert (base / "platform" / "db" / "postgres_client.py").is_file()
    assert (ROOT / "Makefile").is_file()
    assert (ROOT / "Dockerfile").is_file()
    assert (ROOT / "compose.yaml").is_file()


def test_api_and_cli_surface_roots_stay_thin_dispatchers():
    api = ROOT / "src" / "parallax" / "app" / "surfaces" / "api"
    cli = ROOT / "src" / "parallax" / "app" / "surfaces" / "cli"
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
    assert not (ROOT / "src" / "parallax" / "pipeline" / "llm_client.py").exists()
    assert not (ROOT / "src" / "parallax" / "pipeline" / "llm_enrichment.py").exists()
    assert not (ROOT / "src" / "parallax" / "pipeline" / "narrative_seed_builder.py").exists()
    assert not (ROOT / "src" / "parallax" / "pipeline" / "narrative_token_linker.py").exists()
    assert not (ROOT / "src" / "parallax" / "retrieval" / "narrative_service.py").exists()
    assert not (ROOT / "src" / "parallax" / "retrieval" / "narrative_link_service.py").exists()
    assert not (ROOT / "src" / "parallax" / "retrieval" / "narrative_link_scoring.py").exists()


def test_social_enrichment_runtime_modules_stay_removed():
    assert not (ROOT / "src" / "parallax" / "domains" / "social_enrichment").exists()
    assert not (ROOT / "src" / "parallax" / "app" / "surfaces" / "api" / "routes_social_enrichment.py").exists()


def test_legacy_token_resolution_runtime_modules_stay_removed():
    assert not (ROOT / "src" / "parallax" / "pipeline" / "asset_attribution.py").exists()
    assert not (ROOT / "src" / "parallax" / "pipeline" / "asset_mention_builder.py").exists()
    assert not (ROOT / "src" / "parallax" / "pipeline" / "asset_resolution_worker.py").exists()
    assert not (ROOT / "src" / "parallax" / "pipeline" / "asset_resolver.py").exists()
    assert not (ROOT / "src" / "parallax" / "pipeline" / "token_identity_resolver.py").exists()
    assert not (ROOT / "src" / "parallax" / "pipeline" / "signal_builder.py").exists()
    assert not (ROOT / "src" / "parallax" / "pipeline" / "token_attribution.py").exists()
    assert not (ROOT / "src" / "parallax" / "retrieval" / "search_service.py").exists()
    assert not (ROOT / "src" / "parallax" / "retrieval" / "rolling_token_flow.py").exists()
    assert not (ROOT / "src" / "parallax" / "retrieval" / "token_flow_service.py").exists()
    assert not (ROOT / "src" / "parallax" / "retrieval" / "token_posts_service.py").exists()
    assert not (ROOT / "src" / "parallax" / "retrieval" / "token_social_timeline_service.py").exists()
    assert not (ROOT / "src" / "parallax" / "storage" / "market_observation_repository.py").exists()
    assert not (ROOT / "src" / "parallax" / "storage" / "token_repository.py").exists()
    assert not (ROOT / "src" / "parallax" / "storage" / "token_signal_repository.py").exists()


def test_trading_attention_service_has_been_hard_deleted():
    assert not (ROOT / "src" / "parallax" / "retrieval" / "trading_attention_service.py").exists()
    assert not (ROOT / "tests" / "test_trading_attention_service.py").exists()


def test_pulse_agent_repository_has_no_dual_name_compatibility_arguments():
    pulse_repo_path = ROOT / "src" / "parallax" / "domains" / "pulse_lab" / "repositories" / "pulse_runs_repository.py"
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

    assert not (ROOT / "src" / "parallax" / "domains" / "pulse_lab" / "repositories" / "pulse_repository.py").exists()
    class_name = "Pulse" + "Repository"
    import_text = f"from parallax.domains.pulse_lab.repositories.pulse_repository import {class_name}"
    for path, text in text_by_path.items():
        assert f"class {class_name}" not in text, path
        assert f"{class_name}(" not in text, path
        assert re.search(r"repos\\.pulse\\b", text) is None, path
        assert import_text not in text, path


def test_pulse_repository_split_keeps_read_sql_and_jobs_out_of_shared_admission():
    repo_dir = ROOT / "src" / "parallax" / "domains" / "pulse_lab" / "repositories"
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
        ROOT / "src/parallax/app/runtime/app.py",
        ROOT / "src/parallax/app/surfaces/api/http.py",
        ROOT / "src/parallax/domains/evidence/services/ingest_service.py",
        ROOT / "src/parallax/domains/token_intel/services/token_radar_projection.py",
        ROOT / "src/parallax/app/runtime/repository_session.py",
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
        for path in (ROOT / "src" / "parallax").rglob("*.py")
        if "platform/db/alembic/versions" not in path.as_posix()
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in runtime_files)
    for item in forbidden:
        assert item not in text


def test_token_image_hard_cut_contracts_stay_removed():
    old_proxy_pattern = re.compile(r"/api/token-image(?!s)")
    production_paths = [
        path
        for base in (
            ROOT / "src" / "parallax",
            ROOT / "web" / "src",
        )
        for path in base.rglob("*")
        if path.suffix in {".py", ".ts", ".tsx"} and "platform/db/alembic/versions" not in path.as_posix()
    ]
    public_contract_docs = [
        ROOT / "docs" / "ARCHITECTURE.md",
        ROOT / "docs" / "CONTRACTS.md",
        ROOT / "docs" / "FRONTEND.md",
        ROOT / "docs" / "SETUP.md",
        ROOT / "docs" / "WORKERS.md",
        ROOT / "docs" / "WORKER_FLOW.md",
    ]

    assert not (ROOT / "src" / "parallax" / "app" / "surfaces" / "api" / "routes_token_image.py").exists()
    assert not (ROOT / "web" / "src" / "shared" / "model" / "tokenImageUrl.ts").exists()

    offenders: list[str] = []
    for path in production_paths:
        text = path.read_text(encoding="utf-8")
        if "tokenImageUrl" in text:
            offenders.append(f"{path.relative_to(ROOT)}: tokenImageUrl")
        if "localLogoUrl" in text:
            offenders.append(f"{path.relative_to(ROOT)}: localLogoUrl")
        if "_local_logo_url" in text:
            offenders.append(f"{path.relative_to(ROOT)}: _local_logo_url")
        if "LOCAL_LOGO_PREFIX" in text:
            offenders.append(f"{path.relative_to(ROOT)}: LOCAL_LOGO_PREFIX")
        if old_proxy_pattern.search(text):
            offenders.append(f"{path.relative_to(ROOT)}: /api/token-image")

    profile_example_pattern = re.compile(r"logo_url[^\n]{0,80}https?://|https?://[^\n]{0,80}logo_url")
    for path in public_contract_docs:
        text = path.read_text(encoding="utf-8")
        if profile_example_pattern.search(text):
            offenders.append(f"{path.relative_to(ROOT)}: remote logo_url public example")

    assert offenders == []


def test_makefile_exposes_global_cli_install_targets():
    makefile = (ROOT / "Makefile").read_text()

    assert "install: ## install or update the global CLI with uv tool" in makefile
    assert "\t@uv tool install --force --reinstall ." in makefile
    assert "uninstall: ## uninstall the global CLI installed by uv tool" in makefile
    assert "\t@uv tool uninstall parallax" in makefile
    assert "tool-path: ## ensure uv tool executables are on PATH" in makefile
    assert "\t@uv tool update-shell" in makefile
    assert "init: ## create ~/.parallax/config.yaml" in makefile


def test_makefile_exposes_single_token_radar_cex_recovery_target():
    makefile = (ROOT / "Makefile").read_text()

    assert "token-radar-cex-recover: ## recover Token Radar CEX recognition" in makefile
    assert "\t@$(PARALLAX) ops sync-binance-usdt-perp-universe --execute" in makefile
    assert "\t@$(PARALLAX) ops sync-binance-cex-profiles" in makefile
    assert "\t@$(PARALLAX) ops cex-binance-hard-cut-cleanup --dry-run --min-binance-feeds 400" in makefile
    assert "\t@$(PARALLAX) ops cex-binance-hard-cut-cleanup --execute --min-binance-feeds 400" in makefile
    assert "\t@$(PARALLAX) ops rebuild-token-intents --window 24h --limit 5000 --projection-limit 5000" in makefile
    assert "\t@$(PARALLAX) ops audit-token-radar --window 1h --scope all --limit 20" in makefile


def test_compose_bind_mounts_local_runtime_home_without_env_config_sources():
    compose = (ROOT / "compose.yaml").read_text()
    data = yaml.safe_load(compose)
    services = data["services"]

    assert "env_file:" not in compose
    assert services["app"].get("environment") == {"FINANCE_FRED_API_KEY": "${FINANCE_FRED_API_KEY:-}"}
    assert "environment" not in services["migrate"]
    assert "${HOME}/.parallax:/root/.parallax" in compose
    assert "parallax_data" not in compose
    assert ("LANCE" + "_") not in compose
    assert ("RAYON" + "_") not in compose


def test_removed_root_runtime_files_stay_absent():
    assert not (ROOT / "gmgn_twitter_monitor.py").exists()
    assert not (ROOT / "gmgn-twitter-monitor.service").exists()
    assert not (ROOT / "requirements.txt").exists()
    assert not (ROOT / "gmgn_twitter_monitor").exists()
    assert not (ROOT / "src" / "gmgn_twitter_gateway").exists()
    assert not (ROOT / "deploy" / "systemd" / "gmgn-twitter-gateway.service").exists()
    assert not (ROOT / "deploy" / "systemd" / "parallax.service").exists()
    assert not (ROOT / "deploy" / "macos" / "install_launchd.sh").exists()
    assert not (ROOT / "deploy" / "nginx" / "parallax.conf").exists()
    assert not (ROOT / "src" / "parallax" / "service_control.py").exists()
