import pytest
import yaml
from pydantic import ValidationError

from gmgn_twitter_intel.domains.social_enrichment.repositories.enrichment_repository import RUNNING_TIMEOUT_MS
from gmgn_twitter_intel.platform.config.settings import load_settings, write_default_config
from gmgn_twitter_intel.platform.paths.runtime_paths import app_home, config_path


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
    assert settings.llm_timeout_seconds == 120
    assert settings.llm_timeout_seconds * 1000 < RUNNING_TIMEOUT_MS
    assert settings.pulse_agent_enabled is True
    assert settings.pulse_agent_interval_seconds == 60
    assert settings.pulse_agent_batch_size == 10
    assert settings.pulse_agent_max_attempts == 3
    assert settings.pulse_agent_model is None
    assert settings.pulse_agent_configured is False
    assert settings.pulse_agent_asset_heat_min == 80
    assert settings.pulse_agent_asset_propagation_min == 70
    assert settings.pulse_agent_trade_heat_min == 75
    assert settings.pulse_agent_trade_quality_min == 62
    assert settings.pulse_agent_trade_propagation_min == 62
    assert settings.pulse_agent_tradeability_min == 70
    assert settings.pulse_agent_timing_min == 50
    assert settings.pulse_agent_confidence_min == 0.65
    assert settings.pulse_agent_token_watch_signal_min == 45
    assert settings.pulse_agent_high_conviction_min == 78
    assert settings.gmgn_configured is False
    assert settings.upstream_chains == ("sol", "eth", "base", "bsc")
    assert settings.upstream_channels == ("twitter_monitor_basic", "twitter_monitor_token")
    assert settings.okx_dex_sync_interval_seconds == 30.0
    assert settings.okx_dex_price_hot_stale_seconds == 90.0
    assert settings.okx_dex_price_warm_stale_seconds == 300.0
    assert settings.okx_dex_price_refresh_limit == 160


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
                "enrichment_concurrency": 3,
                "trace_enabled": True,
                "trace_api_key": "sk-trace",
                "trace_include_sensitive_data": False,
                "pulse_agent_enabled": True,
                "pulse_agent_interval_seconds": 0,
                "pulse_agent_batch_size": 999,
                "pulse_agent_max_attempts": 0,
                "pulse_agent_model": " ",
                "pulse_agent_asset_heat_min": 70,
                "pulse_agent_asset_propagation_min": 60,
                "pulse_agent_trade_heat_min": 70,
                "pulse_agent_trade_quality_min": 58,
                "pulse_agent_trade_propagation_min": 58,
                "pulse_agent_tradeability_min": 65,
                "pulse_agent_timing_min": 45,
                "pulse_agent_confidence_min": 0.6,
                "pulse_agent_token_watch_signal_min": 40,
                "pulse_agent_high_conviction_min": 74,
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
    assert settings.enrichment_concurrency == 3
    assert settings.llm_trace_enabled is True
    assert settings.llm_trace_api_key == "sk-trace"
    assert settings.llm_trace_export_configured is True
    assert settings.llm_trace_include_sensitive_data is False
    assert settings.pulse_agent_enabled is True
    assert settings.pulse_agent_interval_seconds == 1
    assert settings.pulse_agent_batch_size == 100
    assert settings.pulse_agent_max_attempts == 1
    assert settings.pulse_agent_model == "gpt-test"
    assert settings.pulse_agent_configured is True
    assert settings.pulse_agent_asset_heat_min == 70
    assert settings.pulse_agent_asset_propagation_min == 60
    assert settings.pulse_agent_trade_heat_min == 70
    assert settings.pulse_agent_trade_quality_min == 58
    assert settings.pulse_agent_trade_propagation_min == 58
    assert settings.pulse_agent_tradeability_min == 65
    assert settings.pulse_agent_timing_min == 45
    assert settings.pulse_agent_confidence_min == 0.6
    assert settings.pulse_agent_token_watch_signal_min == 40
    assert settings.pulse_agent_high_conviction_min == 74


def test_pulse_agent_model_can_override_llm_model(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "llm": {
                "provider": "openai",
                "api_key": "sk-test",
                "model": "gpt-base",
                "pulse_agent_model": "gpt-pulse",
            },
        },
    )

    settings = load_settings()

    assert settings.llm_model == "gpt-base"
    assert settings.pulse_agent_model == "gpt-pulse"
    assert settings.pulse_agent_configured is True


def test_pulse_agent_can_be_configured_without_enrichment_model(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "llm": {
                "provider": "openai",
                "api_key": "sk-test",
                "pulse_agent_model": "gpt-pulse",
            },
        },
    )

    settings = load_settings()

    assert settings.llm_model is None
    assert settings.llm_configured is False
    assert settings.pulse_agent_model == "gpt-pulse"
    assert settings.pulse_agent_configured is True


def test_openai_root_base_url_with_api_key_counts_as_trace_export_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "llm": {
                "provider": "openai",
                "api_key": "sk-test",
                "base_url": "https://api.openai.com",
            },
        },
    )

    settings = load_settings()

    assert settings.llm_base_url == "https://api.openai.com"
    assert settings.llm_trace_export_configured is True


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
            },
            "providers": {
                "okx": {
                    "cex_base_url": "https://okx.example.test/",
                    "cex_sync_enabled": True,
                    "cex_sync_interval_seconds": 120,
                    "cex_inst_types": ["SPOT"],
                    "dex_base_url": "https://web3-okx.example.test/",
                    "dex_chain_indexes": ["501", "1"],
                    "dex_sync_interval_seconds": 12,
                    "dex_price_hot_stale_seconds": 45,
                    "dex_price_warm_stale_seconds": 180,
                    "dex_price_refresh_limit": 25,
                    "timeout_seconds": 9,
                }
            },
        },
    )

    settings = load_settings()

    assert settings.gmgn_configured is True
    assert settings.gmgn_api_key == "gmgn-test"
    assert settings.gmgn_openapi_base_url == "https://openapi.example.test"
    assert settings.gmgn_timeout_seconds == 3
    assert settings.gmgn_token_info_cache_ttl_seconds == 60
    assert settings.okx_cex_base_url == "https://okx.example.test"
    assert settings.okx_cex_sync_enabled is True
    assert settings.okx_cex_sync_interval_seconds == 120
    assert settings.okx_cex_inst_types == ("SPOT",)
    assert settings.okx_dex_base_url == "https://web3-okx.example.test"
    assert settings.okx_dex_chain_indexes == ("501", "1")
    assert settings.okx_dex_sync_interval_seconds == 12
    assert settings.okx_dex_price_hot_stale_seconds == 45
    assert settings.okx_dex_price_warm_stale_seconds == 180
    assert settings.okx_dex_price_refresh_limit == 25
    assert settings.okx_timeout_seconds == 9


def test_okx_provider_rejects_unknown_dex_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "providers": {
                "okx": {
                    "dex_price_refresh_limit": 160,
                    "dex_surprise_budget": 10,
                }
            },
        },
    )

    with pytest.raises(ValidationError):
        load_settings()


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
                        "cooldown_seconds": 600,
                    },
                    "signal_pulse_candidate": {
                        "enabled": True,
                        "channels": ["in_app", "pushdeer"],
                        "window": "5m",
                        "scopes": ["all"],
                        "statuses": ["trade_candidate", "token_watch"],
                        "cooldown_seconds": 120,
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
    activity_rule = settings.notifications.rules["watched_account_activity"]
    assert activity_rule.channels == ("in_app",)
    assert activity_rule.cooldown_seconds == 300
    alert_rule = settings.notifications.rules["watched_account_token_alert"]
    assert alert_rule.channels == ("in_app",)
    assert alert_rule.cooldown_seconds == 900
    assert settings.notifications.rules["hot_quality_token_5m"].social_heat_min == 82
    assert settings.notifications.rules["hot_quality_token_5m"].discussion_quality_min == 72
    assert settings.notifications.rules["hot_quality_token_5m"].cooldown_seconds == 600
    pulse_rule = settings.notifications.rules["signal_pulse_candidate"]
    assert pulse_rule.channels == ("in_app", "pushdeer")
    assert pulse_rule.window == "5m"
    assert pulse_rule.scopes == ("all",)
    assert pulse_rule.statuses == ("trade_candidate", "token_watch")
    assert pulse_rule.cooldown_seconds == 120
    assert settings.notifications.channels["pushdeer"].provider == "pushdeer"
    assert settings.notifications.channels["pushdeer"].url == "pushdeer://pushKey"


def test_notification_settings_reject_removed_rule_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "notifications": {
                "rules": {
                    "signal_pulse_candidate": {
                        "candidate_score_min": 70,
                    }
                }
            },
        },
    )

    with pytest.raises(ValidationError):
        load_settings()


def test_signal_pulse_rule_rejects_token_flow_thresholds(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "notifications": {
                "rules": {
                    "signal_pulse_candidate": {
                        "social_heat_min": 70,
                    }
                }
            },
        },
    )

    with pytest.raises(ValidationError):
        load_settings()


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
