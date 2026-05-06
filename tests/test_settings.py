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
    assert settings.ws_token == "secret"
    assert settings.postgres_dsn == "postgresql://gmgn_app@postgres:5432/gmgn_twitter_intel"
    assert settings.postgres_password_file == tmp_path / ".gmgn-twitter-intel" / "postgres_password"
    assert settings.log_file == tmp_path / ".gmgn-twitter-intel" / "logs" / "gmgn-twitter-intel.log"
    assert settings.llm_configured is False
    assert settings.gmgn_configured is False
    assert settings.upstream_chains == ("sol", "eth", "base", "bsc")
    assert settings.upstream_channels == ("twitter_monitor_basic", "twitter_monitor_token")


def test_load_settings_rejects_missing_ws_token_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(tmp_path, {"handles": ["toly"]})

    with pytest.raises(ValueError, match="ws_token is required"):
        load_settings()


def test_load_settings_rejects_unknown_top_level_keys(tmp_path, monkeypatch):
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


def test_postgres_storage_and_llm_enrichment_can_be_explicitly_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "storage": {
                "postgres": {
                    "dsn": "postgresql://gmgn_app:secret@postgres:5432/gmgn_twitter_intel",
                    "password_file": "pg_password",
                    "pool_min_size": 2,
                    "pool_max_size": 12,
                    "connect_timeout_seconds": 4,
                }
            },
            "llm": {
                "provider": "openai",
                "api_key": "sk-test",
                "model": "gpt-test",
                "base_url": "https://example.test/v1/",
                "timeout_seconds": 7,
                "enrichment_poll_interval": 0.5,
            },
        },
    )

    settings = load_settings()

    assert settings.postgres_dsn == "postgresql://gmgn_app:secret@postgres:5432/gmgn_twitter_intel"
    assert settings.postgres_password_file == tmp_path / ".gmgn-twitter-intel" / "pg_password"
    assert settings.postgres_pool_min_size == 2
    assert settings.postgres_pool_max_size == 12
    assert settings.postgres_connect_timeout_seconds == 4
    assert not hasattr(settings, "sqlite_path")
    assert settings.llm_configured is True
    assert settings.llm_model == "gpt-test"
    assert settings.llm_base_url == "https://example.test/v1"
    assert settings.llm_timeout_seconds == 7
    assert settings.enrichment_poll_interval == 0.5


def test_load_settings_accepts_gmgn_openapi_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "gmgn": {
                "api_key": "gmgn-test",
                "openapi_base_url": "https://openapi.example.test/",
                "timeout_seconds": 3,
                "token_info_cache_ttl_seconds": 60,
                "evm_candidate_chains": ["base", "bsc", "eth"],
            },
        },
    )

    settings = load_settings()

    assert settings.gmgn_configured is True
    assert settings.gmgn_api_key == "gmgn-test"
    assert settings.gmgn_openapi_base_url == "https://openapi.example.test"
    assert settings.gmgn_timeout_seconds == 3
    assert settings.gmgn_token_info_cache_ttl_seconds == 60
    assert settings.gmgn_evm_candidate_chains == ("base", "bsc", "eth")


def test_load_settings_accepts_notification_defaults_and_rule_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "notifications": {
                "enabled": True,
                "poll_interval_seconds": 3,
                "token_flow_limit": 40,
                "rules": {
                    "hot_quality_token_5m": {
                        "enabled": True,
                        "channels": ["in_app"],
                        "social_heat_min": 82,
                        "discussion_quality_min": 72,
                        "suppress_chase_risk": True,
                        "cooldown_seconds": 600,
                    },
                },
                "channels": {
                    "pushdeer": {
                        "enabled": True,
                        "provider": "pushdeer",
                        "url": "pushdeer://pushKey",
                        "min_severity": "high",
                    },
                },
            },
        },
    )

    settings = load_settings()

    assert settings.notifications.enabled is True
    assert settings.notifications.poll_interval_seconds == 3
    assert settings.notifications.token_flow_limit == 40
    assert settings.notifications.rules["watched_account_activity"].channels == ("in_app",)
    assert settings.notifications.rules["hot_quality_token_5m"].social_heat_min == 82
    assert settings.notifications.rules["hot_quality_token_5m"].discussion_quality_min == 72
    assert settings.notifications.rules["hot_quality_token_5m"].suppress_chase_risk is True
    assert settings.notifications.rules["hot_quality_token_5m"].cooldown_seconds == 600
    assert settings.notifications.channels["pushdeer"].provider == "pushdeer"
    assert settings.notifications.channels["pushdeer"].url == "pushdeer://pushKey"


def test_load_settings_accepts_config_without_ws_token(tmp_path, monkeypatch):
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
    assert settings.postgres_dsn == "postgresql://gmgn_app@postgres:5432/gmgn_twitter_intel"
