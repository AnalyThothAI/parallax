import pytest
import yaml
from pydantic import ValidationError

from gmgn_twitter_intel.runtime_paths import app_home, config_path
from gmgn_twitter_intel.settings import load_settings, write_default_config


def write_config(home, payload):
    app_dir = home / ".gmgn-twitter-intel"
    app_dir.mkdir(parents=True, exist_ok=True)
    path = app_dir / "config.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_load_settings_accepts_yaml_handle_list_as_public_subscription(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": [" @toly ", "CryptoDevinL", "heyibinance", "toly"],
        },
    )

    settings = load_settings()

    assert settings.handles == ("toly", "cryptodevinl", "heyibinance")
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 8765
    assert settings.sqlite_path == tmp_path / ".gmgn-twitter-intel" / "twitter_intel.sqlite3"
    assert settings.log_file == tmp_path / ".gmgn-twitter-intel" / "logs" / "gmgn-twitter-intel.log"
    assert settings.llm_configured is False
    assert settings.upstream_chains == ("sol", "eth", "base", "bsc")
    assert settings.upstream_channels == ("twitter_monitor_basic", "twitter_monitor_token")


def test_load_settings_rejects_missing_ws_token(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(tmp_path, {"handles": ["toly"]})

    with pytest.raises(ValueError, match="ws_token"):
        load_settings()


def test_load_settings_rejects_unknown_legacy_environment_style_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "SQLITE_PATH": str(tmp_path / "ignored.sqlite3"),
        },
    )

    with pytest.raises(ValidationError):
        load_settings()


def test_sqlite_path_and_llm_enrichment_can_be_explicitly_configured(tmp_path, monkeypatch):
    configured_path = tmp_path / "custom.sqlite3"
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "storage": {"sqlite_path": str(configured_path)},
            "llm": {
                "openai_api_key": "sk-test",
                "openai_model": "gpt-test",
                "openai_base_url": "https://example.test/v1/",
                "timeout_seconds": 7,
                "enrichment_poll_interval": 0.5,
            },
        },
    )

    settings = load_settings()

    assert settings.sqlite_path == configured_path
    assert settings.llm_configured is True
    assert settings.openai_model == "gpt-test"
    assert settings.openai_base_url == "https://example.test/v1"
    assert settings.llm_timeout_seconds == 7
    assert settings.enrichment_poll_interval == 0.5


def test_load_settings_can_skip_ws_token_for_read_only_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(tmp_path, {"handles": ["toly"]})

    settings = load_settings(require_ws_token=False)

    assert settings.handles == ("toly",)
    assert settings.ws_token is None


def test_init_creates_single_config_file_and_runtime_directories(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    path = write_default_config()

    assert path == tmp_path / ".gmgn-twitter-intel" / "config.yaml"
    assert app_home() == tmp_path / ".gmgn-twitter-intel"
    assert config_path() == path
    assert (tmp_path / ".gmgn-twitter-intel" / "logs").is_dir()
    settings = load_settings()
    assert settings.ws_token
    assert settings.sqlite_path == tmp_path / ".gmgn-twitter-intel" / "twitter_intel.sqlite3"
