from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from gmgn_twitter_intel.domains.social_enrichment.repositories.enrichment_repository import RUNNING_TIMEOUT_MS
from gmgn_twitter_intel.platform.config.settings import (
    Settings,
    WorkersSettings,
    default_config_yaml,
    default_workers_yaml,
    load_settings,
    write_default_config,
)
from gmgn_twitter_intel.platform.paths.runtime_paths import app_home, config_path, workers_config_path


def _legacy_anchor_worker_key() -> str:
    return "_".join(("anchor", "price"))


def write_config(home, payload, *, write_workers=True):
    app_dir = home / ".gmgn-twitter-intel"
    app_dir.mkdir(parents=True, exist_ok=True)
    path = app_dir / "config.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    if write_workers:
        (app_dir / "workers.yaml").write_text(default_workers_yaml(), encoding="utf-8")
    return path


def write_workers_config(home, payload):
    app_dir = home / ".gmgn-twitter-intel"
    app_dir.mkdir(parents=True, exist_ok=True)
    path = app_dir / "workers.yaml"
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
    assert settings.api_host == "0.0.0.0"  # noqa: S104 -- testing default bind-all-interfaces config value
    assert settings.api_port == 8765
    assert settings.ws_token == "secret"
    assert settings.postgres_dsn == "postgresql://gmgn_app@postgres:5432/gmgn_twitter_intel"
    assert settings.postgres_password_file == tmp_path / ".gmgn-twitter-intel" / "postgres_password"
    assert settings.postgres_pool_max_size == 16
    assert settings.log_file == tmp_path / ".gmgn-twitter-intel" / "logs" / "gmgn-twitter-intel.log"
    assert settings.llm_configured is False
    assert settings.llm_timeout_seconds == 120
    assert settings.llm_timeout_seconds * 1000 < RUNNING_TIMEOUT_MS
    assert settings.pulse_agent_model is None
    assert settings.pulse_agent_configured is False
    assert settings.watchlist_handle_summary_model is None
    assert settings.watchlist_handle_summary_configured is False
    assert settings.workers.enrichment.interval_seconds == 2
    assert settings.workers.enrichment.concurrency == 4
    assert settings.workers.pulse_candidate.interval_seconds == 60
    assert settings.workers.pulse_candidate.batch_size == 10
    assert settings.workers.pulse_candidate.max_attempts == 3
    assert settings.workers.pulse_candidate.trigger_thresholds.min_rank_score == 45
    assert settings.workers.pulse_candidate.gate_thresholds.trade_candidate_min == 72
    assert settings.workers.handle_summary.enabled is True
    assert settings.workers.handle_summary.signal_threshold == 10
    assert settings.workers.handle_summary.time_threshold_ms == 1_800_000
    assert settings.workers.handle_summary.min_interval_ms == 300_000
    assert settings.workers.handle_summary.input_limit == 80
    assert settings.workers.handle_summary.window_days == 7
    assert settings.workers.handle_summary.lease_ms == 120_000
    assert settings.workers.handle_summary.max_attempts == 3
    assert settings.gmgn_configured is False
    assert settings.upstream_chains == ("sol", "eth", "base", "bsc")
    assert settings.upstream_channels == ("twitter_monitor_basic", "twitter_monitor_token")
    assert settings.okx_dex_ws_url == "wss://wsdex.okx.com/ws/v6/dex"
    assert settings.binance_enabled is True
    assert settings.binance_web3_base_url == "https://web3.binance.com"
    assert settings.binance_cex_base_url == "https://www.binance.com"
    assert settings.binance_timeout_seconds == 15
    assert not hasattr(settings.workers, _legacy_anchor_worker_key())
    assert settings.workers.market_tick_stream.subscription_limit == 100
    assert settings.workers.market_tick_poll.interval_seconds == 15
    assert settings.workers.token_capture_tier.batch_size == 500
    assert settings.workers.token_capture_tier.ws_limit == 100
    assert settings.workers.token_capture_tier.poll_limit == 500
    assert settings.workers.live_price_gateway.interval_seconds == 2
    assert not hasattr(settings.workers.live_price_gateway, "subscription_limit")
    assert settings.okx_dex_ws_configured is False


def test_news_intel_defaults_enable_core_crypto_and_us_market_sources() -> None:
    settings = Settings()
    source_ids = {source.source_id for source in settings.news_intel.sources}

    assert settings.news_intel.enabled is True
    assert {
        "coindesk",
        "cointelegraph",
        "theblock",
        "decrypt",
        "marketwatch-top-stories",
        "wsj-markets",
        "cnbc-economy",
        "cnbc-markets",
        "yahoo-finance",
    }.issubset(source_ids)

    enabled_source_ids = {source.source_id for source in settings.news_intel.sources if source.enabled}
    assert {
        "coindesk",
        "cointelegraph",
        "theblock",
        "decrypt",
        "marketwatch-top-stories",
        "wsj-markets",
        "cnbc-economy",
        "cnbc-markets",
        "yahoo-finance",
    }.issubset(enabled_source_ids)


def test_default_config_yaml_contains_explicit_news_intel_block() -> None:
    payload = yaml.safe_load(default_config_yaml())
    news_intel = payload["news_intel"]

    assert news_intel["enabled"] is True
    assert len(news_intel["sources"]) >= 9
    assert {source["source_id"] for source in news_intel["sources"] if source["enabled"]} >= {
        "coindesk",
        "cointelegraph",
        "theblock",
        "decrypt",
        "marketwatch-top-stories",
        "wsj-markets",
        "cnbc-economy",
        "cnbc-markets",
        "yahoo-finance",
    }


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
                "trace_enabled": True,
                "trace_api_key": "sk-trace",
                "trace_include_sensitive_data": False,
                "pulse_agent_model": " ",
                "watchlist_handle_summary_model": " ",
            },
        },
    )
    write_workers_config(
        tmp_path,
        yaml.safe_load(default_workers_yaml())
        | {
            "enrichment": {"interval_seconds": 0.5, "concurrency": 3},
            "pulse_candidate": {
                "interval_seconds": 1,
                "batch_size": 100,
                "max_attempts": 1,
                "trigger_thresholds": {"min_rank_score": 60},
                "gate_thresholds": {
                    "trade_candidate_min": 70,
                    "token_watch_min": 40,
                    "high_info_rejection_min": 25,
                    "high_conviction_min": 74,
                },
            },
            "handle_summary": {
                "interval_seconds": 1,
                "concurrency": 8,
                "lease_ms": 10_000,
                "max_attempts": 1,
                "signal_threshold": 1,
                "time_threshold_ms": 60_000,
                "min_interval_ms": 60_000,
                "input_limit": 500,
                "window_days": 30,
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
    assert settings.llm_trace_enabled is True
    assert settings.llm_trace_api_key == "sk-trace"
    assert settings.llm_trace_export_configured is True
    assert settings.llm_trace_include_sensitive_data is False
    assert settings.workers.enrichment.interval_seconds == 0.5
    assert settings.workers.enrichment.concurrency == 3
    assert settings.workers.pulse_candidate.interval_seconds == 1
    assert settings.workers.pulse_candidate.batch_size == 100
    assert settings.workers.pulse_candidate.max_attempts == 1
    assert settings.pulse_agent_model == "gpt-test"
    assert settings.pulse_agent_configured is True
    assert settings.workers.pulse_candidate.trigger_thresholds.min_rank_score == 60
    assert settings.workers.pulse_candidate.gate_thresholds.trade_candidate_min == 70
    assert settings.workers.pulse_candidate.gate_thresholds.token_watch_min == 40
    assert settings.workers.pulse_candidate.gate_thresholds.high_info_rejection_min == 25
    assert settings.workers.pulse_candidate.gate_thresholds.high_conviction_min == 74
    assert settings.watchlist_handle_summary_model == "gpt-test"
    assert settings.watchlist_handle_summary_configured is True
    assert settings.workers.handle_summary.signal_threshold == 1
    assert settings.workers.handle_summary.time_threshold_ms == 60_000
    assert settings.workers.handle_summary.min_interval_ms == 60_000
    assert settings.workers.handle_summary.interval_seconds == 1
    assert settings.workers.handle_summary.concurrency == 8
    assert settings.workers.handle_summary.input_limit == 500
    assert settings.workers.handle_summary.window_days == 30
    assert settings.workers.handle_summary.lease_ms == 10_000
    assert settings.workers.handle_summary.max_attempts == 1


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


def test_watchlist_summary_model_can_override_llm_model(tmp_path, monkeypatch):
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
                "watchlist_handle_summary_model": "gpt-watchlist",
            },
        },
    )

    settings = load_settings()

    assert settings.llm_model == "gpt-base"
    assert settings.watchlist_handle_summary_model == "gpt-watchlist"
    assert settings.watchlist_handle_summary_configured is True


def test_news_item_brief_model_can_override_llm_model(tmp_path, monkeypatch):
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
                "news_item_brief_model": "gpt-news",
            },
        },
    )

    settings = load_settings()

    assert settings.llm_model == "gpt-base"
    assert settings.news_item_brief_model == "gpt-news"
    assert settings.news_item_brief_configured is True


def test_news_item_brief_model_falls_back_to_llm_model(tmp_path, monkeypatch):
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
            },
        },
    )

    settings = load_settings()

    assert settings.news_item_brief_model == "gpt-base"
    assert settings.news_item_brief_configured is True


def test_news_item_brief_model_empty_string_normalizes_to_fallback(tmp_path, monkeypatch):
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
                "news_item_brief_model": " ",
            },
        },
    )

    settings = load_settings()

    assert settings.llm.news_item_brief_model is None
    assert settings.news_item_brief_model == "gpt-base"
    assert settings.news_item_brief_configured is True


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


def test_news_item_brief_can_be_configured_without_default_llm_model(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "llm": {
                "provider": "openai",
                "api_key": "sk-test",
                "news_item_brief_model": "gpt-news",
            },
        },
    )

    settings = load_settings()

    assert settings.llm_model is None
    assert settings.llm_configured is False
    assert settings.news_item_brief_model == "gpt-news"
    assert settings.news_item_brief_configured is True


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
                    "cex_inst_types": ["SPOT"],
                    "dex_base_url": "https://web3-okx.example.test/",
                    "dex_chain_indexes": ["501", "1"],
                    "dex_ws_url": "wss://okx-ws.example.test/ws/v6/dex",
                    "dex_api_key": "okx-key",
                    "dex_secret_key": "okx-secret",
                    "dex_passphrase": "okx-pass",
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
    assert settings.okx_cex_inst_types == ("SPOT",)
    assert settings.okx_dex_base_url == "https://web3-okx.example.test"
    assert settings.okx_dex_chain_indexes == ("501", "1")
    assert settings.okx_dex_ws_url == "wss://okx-ws.example.test/ws/v6/dex"
    assert settings.okx_dex_ws_configured is True
    assert settings.okx_timeout_seconds == 9


def test_okx_dex_ws_configured_requires_url_and_all_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "providers": {
                "okx": {
                    "dex_api_key": "okx-key",
                    "dex_secret_key": "okx-secret",
                }
            },
        },
    )

    settings = load_settings()

    assert settings.okx_dex_ws_configured is False


def test_okx_provider_rejects_removed_dex_ws_enabled_key(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "providers": {"okx": {"dex_ws_enabled": True}},
        },
    )

    with pytest.raises(ValidationError):
        load_settings()


def test_okx_provider_rejects_unknown_dex_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "providers": {
                "okx": {
                    "dex_surprise_budget": 10,
                }
            },
        },
    )

    with pytest.raises(ValidationError):
        load_settings()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("cex_sync_interval_seconds", 300),
        ("dex_sync_interval_seconds", 0),
        ("dex_price_hot_stale_seconds", -1),
        ("dex_price_warm_stale_seconds", 0),
        ("dex_price_refresh_limit", -10),
    ],
)
def test_okx_provider_rejects_removed_dex_refresh_knobs(tmp_path, monkeypatch, key, value):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "providers": {"okx": {key: value}},
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


def test_signal_pulse_rule_rejects_theme_watch_status(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "notifications": {
                "rules": {
                    "signal_pulse_candidate": {
                        "statuses": ["trade_candidate", "theme_watch"],
                    }
                }
            },
        },
    )

    with pytest.raises(ValidationError, match="unsupported Signal Pulse statuses"):
        load_settings()


def test_load_settings_accepts_config_without_ws_token(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(tmp_path, {"handles": ["toly"]})

    settings = load_settings(require_ws_token=False)

    assert settings.handles == ("toly",)
    assert settings.ws_token is None


def test_load_settings_requires_workers_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(tmp_path, {"ws_token": "secret", "handles": ["toly"]}, write_workers=False)

    with pytest.raises(FileNotFoundError, match=r"workers\.yaml not found"):
        load_settings()


@pytest.mark.parametrize(
    "removed_payload",
    [
        {"llm": {"enrichment_poll_interval": 2}},
        {"llm": {"enrichment_concurrency": 4}},
        {"llm": {"pulse_agent_batch_size": 10}},
        {"llm": {"watchlist_handle_summary_poll_interval_seconds": 2}},
        {"notifications": {"poll_interval_seconds": 5}},
        {"live_observation_heartbeat_seconds": 60},
        {"providers": {"okx": {"dex_ws_subscription_limit": 100}}},
    ],
)
def test_load_settings_rejects_old_config_worker_fields(tmp_path, monkeypatch, removed_payload):
    monkeypatch.setenv("HOME", str(tmp_path))
    payload = {"ws_token": "secret", "handles": ["toly"]}
    for key, value in removed_payload.items():
        if isinstance(value, dict):
            payload[key] = value
        else:
            payload[key] = value
    write_config(tmp_path, payload)

    with pytest.raises(ValidationError):
        load_settings()


def test_config_example_excludes_worker_runtime_knobs() -> None:
    payload = yaml.safe_load(Path("config.example.yaml").read_text(encoding="utf-8"))
    llm = payload["llm"]
    forbidden_llm_keys = {
        "enrichment_poll_interval",
        "enrichment_concurrency",
        "pulse_agent_enabled",
        "pulse_agent_interval_seconds",
        "pulse_agent_batch_size",
        "pulse_agent_max_attempts",
        "pulse_agent_trigger_min_rank_score",
        "pulse_agent_gate_trade_candidate_min",
        "pulse_agent_gate_token_watch_min",
        "pulse_agent_gate_high_info_rejection_min",
        "pulse_agent_gate_high_conviction_min",
        "watchlist_handle_summary_enabled",
        "watchlist_handle_summary_signal_threshold",
        "watchlist_handle_summary_time_threshold_ms",
        "watchlist_handle_summary_min_interval_ms",
        "watchlist_handle_summary_poll_interval_seconds",
        "watchlist_handle_summary_concurrency",
        "watchlist_handle_summary_input_limit",
        "watchlist_handle_summary_window_days",
        "watchlist_handle_summary_lease_ms",
        "watchlist_handle_summary_max_attempts",
    }

    assert forbidden_llm_keys.isdisjoint(llm)
    assert list(llm) == [
        "provider",
        "api_key",
        "model",
        "base_url",
        "timeout_seconds",
        "trace_enabled",
        "trace_api_key",
        "trace_include_sensitive_data",
        "pulse_agent_model",
        "watchlist_handle_summary_model",
        "narrative_intel_model",
        "news_item_brief_model",
    ]
    assert "workers" not in payload
    workers = WorkersSettings(**yaml.safe_load(default_workers_yaml()))
    assert workers.enrichment.concurrency == 4
    assert workers.pulse_candidate.trigger_thresholds.min_rank_score == 45
    assert workers.handle_summary.time_threshold_ms == 1_800_000
    Settings(**{**payload, "workers": workers})


def test_init_creates_config_workers_file_and_runtime_directories(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    path = write_default_config()

    assert path == tmp_path / ".gmgn-twitter-intel" / "config.yaml"
    assert app_home() == tmp_path / ".gmgn-twitter-intel"
    assert config_path() == path
    assert workers_config_path() == tmp_path / ".gmgn-twitter-intel" / "workers.yaml"
    assert workers_config_path().exists()
    assert (tmp_path / ".gmgn-twitter-intel" / "logs").is_dir()
    settings = load_settings()
    assert settings.ws_token
    assert settings.postgres_dsn == "postgresql://gmgn_app@postgres:5432/gmgn_twitter_intel"
    assert settings.workers.collector.mode == "continuous"
    assert settings.workers.notification_delivery.max_attempts == 5
