import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_project_metadata_uses_gmgn_twitter_cli_name():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert metadata["project"]["name"] == "gmgn-twitter-cli"
    assert metadata["project"]["scripts"] == {
        "gmgn-twitter-cli": "gmgn_twitter_cli.cli:main",
    }


def test_project_uses_standard_uv_src_layout():
    assert (ROOT / "pyproject.toml").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "__init__.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "api" / "app.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "service_control.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "collector" / "service.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "pipeline" / "tweet_text.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "pipeline" / "token_extractor.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "pipeline" / "token_registry.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "pipeline" / "processing_policy.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "pipeline" / "embedding.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "pipeline" / "llm_enrichment.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "retrieval" / "search_service.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "retrieval" / "mindshare_service.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "storage" / "lancedb_client.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "storage" / "index_maintenance.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "storage" / "runtime_bootstrap.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "storage" / "tweet_repository.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "storage" / "social_repository.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "storage" / "token_registry_repository.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "storage" / "llm_repository.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_cli" / "runtime" / "background_loops.py").is_file()
    assert not (ROOT / "src" / "gmgn_twitter_cli" / "store" / "sqlite.py").exists()
    assert (ROOT / "deploy" / "systemd" / "gmgn-twitter-cli.service").is_file()
    assert (ROOT / "deploy" / "macos" / "install_launchd.sh").is_file()


def test_legacy_root_runtime_files_are_removed():
    assert not (ROOT / "gmgn_twitter_monitor.py").exists()
    assert not (ROOT / "gmgn-twitter-monitor.service").exists()
    assert not (ROOT / "requirements.txt").exists()
    assert not (ROOT / "gmgn_twitter_monitor").exists()
    assert not (ROOT / "src" / "gmgn_twitter_gateway").exists()
    assert not (ROOT / "deploy" / "systemd" / "gmgn-twitter-gateway.service").exists()


def test_macos_launchd_installer_bootstraps_cli_service():
    script = (ROOT / "deploy" / "macos" / "install_launchd.sh").read_text()

    assert "uv run gmgn-twitter-cli service install --start" in script
    assert "launchctl bootstrap" not in script
    assert "rsync" not in script
