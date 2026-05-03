import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_project_metadata_uses_gmgn_twitter_intel_name():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert metadata["project"]["name"] == "gmgn-twitter-intel"
    assert metadata["project"]["scripts"] == {
        "gmgn-twitter-intel": "gmgn_twitter_intel.cli:main",
    }


def test_project_uses_standard_uv_src_layout():
    assert (ROOT / "pyproject.toml").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "__init__.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "api" / "app.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "collector" / "service.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "tweet_text.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "entity_extractor.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "ingest_service.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "signal_builder.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "llm_enrichment.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "enrichment_worker.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "search_service.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "token_flow_service.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "account_alert_service.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "narrative_service.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "sqlite_client.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "sqlite_schema.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "evidence_repository.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "entity_repository.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "signal_repository.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "enrichment_repository.py").is_file()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "storage" / ("lance" + "db_client.py")).exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / ("embed" + "ding.py")).exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "store" / "sqlite.py").exists()
    assert (ROOT / "Makefile").is_file()
    assert (ROOT / "Dockerfile").is_file()
    assert (ROOT / "compose.yaml").is_file()


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

    assert "env_file:" not in compose
    assert "environment:" not in compose
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
