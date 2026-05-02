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
    assert (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "search_service.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "token_flow_service.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "account_alert_service.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "sqlite_client.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "sqlite_schema.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "evidence_repository.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "entity_repository.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "signal_repository.py").is_file()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "storage" / ("lance" + "db_client.py")).exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / ("embed" + "ding.py")).exists()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / ("llm" + "_enrichment.py")).exists()
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


def test_compose_uses_sqlite_runtime_without_lance_thread_pools():
    compose = (ROOT / "compose.yaml").read_text()

    assert "OMP_NUM_THREADS: 1" in compose
    assert "OPENBLAS_NUM_THREADS: 1" in compose
    assert "MKL_NUM_THREADS: 1" in compose
    assert "NUMEXPR_NUM_THREADS: 1" in compose
    assert "SQLITE_PATH: /data/twitter_intel.sqlite3" in compose
    assert ("LANCE" + "_") not in compose
    assert ("RAYON" + "_") not in compose


def test_legacy_root_runtime_files_are_removed():
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
