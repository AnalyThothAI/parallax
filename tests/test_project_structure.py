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
    assert (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "token_extractor.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "token_registry.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "processing_policy.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "embedding.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "pipeline" / "llm_enrichment.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "search_service.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "retrieval" / "mindshare_service.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "lancedb_client.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "index_maintenance.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "runtime_bootstrap.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "tweet_repository.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "social_repository.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "token_registry_repository.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "storage" / "llm_repository.py").is_file()
    assert (ROOT / "src" / "gmgn_twitter_intel" / "runtime" / "background_loops.py").is_file()
    assert not (ROOT / "src" / "gmgn_twitter_intel" / "store" / "sqlite.py").exists()
    assert (ROOT / "Makefile").is_file()
    assert (ROOT / "Dockerfile").is_file()
    assert (ROOT / "compose.yaml").is_file()


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
