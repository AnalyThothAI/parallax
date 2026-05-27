from pathlib import Path
from typing import get_args

import pytest
import yaml
from pydantic import ValidationError

from gmgn_twitter_intel.domains.news_intel.types.source_classification import PROVIDER_TYPES, SOURCE_ROLES
from gmgn_twitter_intel.domains.social_enrichment.repositories.enrichment_repository import RUNNING_TIMEOUT_MS
from gmgn_twitter_intel.platform.config.settings import (
    NEWS_PROVIDER_TYPES,
    NEWS_SOURCE_ROLES,
    NewsSourceSettings,
    Settings,
    SettingsNewsProviderType,
    SettingsNewsSourceRole,
    WorkersSettings,
    default_config_yaml,
    default_workers_yaml,
    load_settings,
    write_default_config,
)
from gmgn_twitter_intel.platform.paths.runtime_paths import app_home, config_path, workers_config_path


def _manifest_worker_names() -> set[str]:
    from gmgn_twitter_intel.app.runtime.worker_manifest import all_worker_manifests

    return {manifest.name for manifest in all_worker_manifests()}


def _old_anchor_worker_key() -> str:
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
    assert settings.agent_runtime_default_model == "qwen3.6"
    assert settings.agent_runtime_model_for_lane("pulse.pipeline") == "qwen3.6"
    assert settings.agent_runtime_model_for_lane("pulse.signal_analyst") == "qwen3.6"
    assert settings.agent_runtime_model_for_lane("pulse.bear_case") == "qwen3.6"
    assert settings.agent_runtime_model_for_lane("pulse.risk_portfolio_judge") == "deepseek-v4-flash"
    assert settings.pulse_agent_configured is False
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
    assert settings.workers.handle_summary.interval_seconds == 30
    assert settings.workers.handle_summary.statement_timeout_seconds == 10
    assert settings.workers.handle_summary.reconcile_limit == 20
    assert settings.workers.handle_summary.window_days == 3
    assert settings.workers.handle_summary.lease_ms == 120_000
    assert settings.workers.handle_summary.max_attempts == 3
    assert settings.gmgn_configured is False
    assert settings.upstream_chains == ("sol", "eth", "base", "bsc")
    assert settings.upstream_channels == ("twitter_monitor_basic", "twitter_monitor_token")
    assert settings.okx_dex_ws_url == "wss://wsdex.okx.com/ws/v6/dex"
    assert settings.binance_enabled is True
    assert settings.binance_web3_base_url == "https://web3.binance.com"
    assert settings.binance_cex_profile_base_url == "https://www.binance.com"
    assert settings.binance_usdm_futures_base_url == "https://fapi.binance.com"
    assert settings.binance_cex_universe_quote_symbol == "USDT"
    assert settings.binance_cex_universe_contract_type == "PERPETUAL"
    assert settings.binance_timeout_seconds == 15
    assert not hasattr(settings, "okx_cex_base_url")
    assert not hasattr(settings, "okx_cex_sync_enabled")
    assert not hasattr(settings, "okx_cex_inst_types")
    assert not hasattr(settings.workers, _old_anchor_worker_key())
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
        "cryptopanic-en",
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
        "cryptopanic-en",
    }.issubset(enabled_source_ids)

    cryptopanic = next(source for source in settings.news_intel.sources if source.source_id == "cryptopanic-en")
    assert cryptopanic.provider_type == "cryptopanic"
    assert cryptopanic.feed_url.startswith("cryptopanic://posts?")
    assert cryptopanic.source_role == "aggregator"
    opennews = next(source for source in settings.news_intel.sources if source.source_id == "opennews-realtime")
    assert opennews.provider_type == "opennews"
    assert opennews.feed_url == "opennews://subscribe"
    assert opennews.enabled is False
    assert opennews.fetch_policy["max_messages"] == 20
    assert settings.news_intel.opennews.api_token is None
    assert settings.news_intel.opennews.api_base_url == "https://ai.6551.io"
    assert settings.news_intel.opennews.wss_url == "wss://ai.6551.io/open/news_wss"


def test_news_source_settings_accepts_classification_fields_and_normalizes_tuples() -> None:
    source = NewsSourceSettings(
        source_id="github-eth",
        provider_type="github",
        feed_url="https://api.github.com/repos/ethereum/go-ethereum/releases",
        source_domain="github.com",
        source_name="go-ethereum releases",
        source_role="developer_signal",
        coverage_tags="ethereum, protocol , releases",
        asset_universe=[" eth ", "ethereum", ""],
        authority_scope={"project": "ethereum"},
        fetch_policy={"interval": "release"},
        context_policy={"include_threads": True},
        cost_policy={"tier": "free"},
    )

    assert source.coverage_tags == ("ethereum", "protocol", "releases")
    assert source.asset_universe == ("eth", "ethereum")
    assert source.authority_scope == {"project": "ethereum"}
    assert source.fetch_policy == {"interval": "release"}
    assert source.context_policy == {"include_threads": True}
    assert source.cost_policy == {"tier": "free"}


def test_news_intel_accepts_opennews_credentials_without_using_environment_shadow_config() -> None:
    settings = Settings(
        ws_token="secret",
        news_intel={
            "opennews": {
                "api_token": "opennews-test-token",
                "api_base_url": "https://example.com",
                "wss_url": "wss://example.com/news_wss",
                "connect_timeout_seconds": 2,
            },
            "sources": [
                {
                    "source_id": "opennews-realtime",
                    "provider_type": "opennews",
                    "feed_url": "opennews://subscribe",
                    "source_domain": "6551.io",
                    "source_name": "OpenNews Realtime",
                    "source_role": "aggregator",
                    "trust_tier": "standard",
                    "enabled": True,
                    "refresh_interval_seconds": 10,
                    "fetch_policy": {
                        "engineTypes": {"news": ["Bloomberg"]},
                        "coins": ["BTC"],
                        "hasCoin": True,
                    },
                }
            ],
        },
    )

    assert settings.news_intel.opennews.api_token == "opennews-test-token"
    assert settings.news_intel.opennews.api_base_url == "https://example.com"
    assert settings.news_intel.opennews.wss_url == "wss://example.com/news_wss"
    assert settings.news_intel.opennews.connect_timeout_seconds == 2
    assert settings.news_intel.sources[0].provider_type == "opennews"
    assert settings.news_intel.sources[0].fetch_policy["coins"] == ["BTC"]


def test_news_source_settings_rejects_unknown_provider_type_and_source_role() -> None:
    base = {
        "source_id": "bad-source",
        "feed_url": "https://example.com/feed",
        "source_domain": "example.com",
        "source_name": "Bad Source",
    }

    with pytest.raises(ValidationError):
        NewsSourceSettings(**base, provider_type="newsletter")

    with pytest.raises(ValidationError):
        NewsSourceSettings(**base, source_role="rumor_mill")


def test_news_source_settings_taxonomy_matches_domain_taxonomy() -> None:
    assert NEWS_PROVIDER_TYPES == PROVIDER_TYPES
    assert NEWS_SOURCE_ROLES == SOURCE_ROLES
    assert get_args(SettingsNewsProviderType) == NEWS_PROVIDER_TYPES
    assert get_args(SettingsNewsSourceRole) == NEWS_SOURCE_ROLES


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
        "cryptopanic-en",
    }
    opennews = next(source for source in news_intel["sources"] if source["source_id"] == "opennews-realtime")
    assert opennews["provider_type"] == "opennews"
    assert opennews["enabled"] is False
    assert news_intel["opennews"] == {
        "api_token": None,
        "api_base_url": "https://ai.6551.io",
        "wss_url": "wss://ai.6551.io/open/news_wss",
        "connect_timeout_seconds": 3.0,
    }


def test_default_config_yaml_contains_macrodata_fred_env_pointer() -> None:
    payload = yaml.safe_load(default_config_yaml())

    assert payload["providers"]["macrodata"] == {
        "enabled": True,
        "quote_timeout_seconds": 5,
        "quote_cache_ttl_seconds": 30,
        "fred_api_key_env": "FINANCE_FRED_API_KEY",
        "cli_project_dir": None,
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
                "base_url": "https://example.test/v1/",
                "timeout_seconds": 7,
                "trace_enabled": True,
                "trace_api_key": "sk-trace",
                "trace_include_sensitive_data": False,
            },
        },
    )
    write_workers_config(
        tmp_path,
        yaml.safe_load(default_workers_yaml())
        | {
            "agent_runtime": {
                "defaults": {
                    "model": "gpt-test",
                    "disable_thinking": True,
                    "include_usage": True,
                },
                "lanes": {
                    "watchlist.handle_summary": {
                        "model": "gpt-summary",
                    },
                },
            },
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
    assert settings.agent_runtime_default_model == "gpt-test"
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
    assert settings.agent_runtime_model_for_lane("pulse.signal_analyst") == "qwen3.6"
    assert settings.agent_runtime_model_for_lane("pulse.bear_case") == "qwen3.6"
    assert settings.agent_runtime_model_for_lane("pulse.risk_portfolio_judge") == "deepseek-v4-flash"
    assert settings.pulse_agent_configured is True
    assert settings.workers.pulse_candidate.trigger_thresholds.min_rank_score == 60
    assert settings.workers.pulse_candidate.gate_thresholds.trade_candidate_min == 70
    assert settings.workers.pulse_candidate.gate_thresholds.token_watch_min == 40
    assert settings.workers.pulse_candidate.gate_thresholds.high_info_rejection_min == 25
    assert settings.workers.pulse_candidate.gate_thresholds.high_conviction_min == 74
    assert settings.agent_runtime_model_for_lane("watchlist.handle_summary") == "gpt-summary"
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


def test_agent_runtime_lane_model_can_override_default_model(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "llm": {
                "provider": "openai",
                "api_key": "sk-test",
            },
        },
    )
    workers = yaml.safe_load(default_workers_yaml())
    workers["agent_runtime"]["defaults"]["model"] = "gpt-base"
    workers["agent_runtime"]["lanes"]["pulse.signal_analyst"]["model"] = "gpt-pulse"
    workers["agent_runtime"]["lanes"]["news.item_brief"]["model"] = "gpt-news"
    write_workers_config(tmp_path, workers)

    settings = load_settings()

    assert settings.agent_runtime_default_model == "gpt-base"
    assert settings.agent_runtime_model_for_lane("pulse.signal_analyst") == "gpt-pulse"
    assert settings.agent_runtime_model_for_lane("pulse.bear_case") == "qwen3.6"
    assert settings.agent_runtime_model_for_lane("pulse.risk_portfolio_judge") == "deepseek-v4-flash"
    assert settings.agent_runtime_model_for_lane("news.item_brief") == "gpt-news"
    assert settings.pulse_agent_configured is True
    assert settings.news_item_brief_configured is True


def test_load_settings_rejects_legacy_llm_model_fields(tmp_path, monkeypatch):
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
                "watchlist_handle_summary_model": "gpt-watchlist",
                "narrative_intel_model": "gpt-narrative",
                "news_item_brief_model": "gpt-news",
            },
        },
    )

    with pytest.raises(ValidationError):
        load_settings()


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
                    "dex_base_url": "https://web3-okx.example.test/",
                    "dex_chain_indexes": ["501", "1"],
                    "dex_ws_url": "wss://okx-ws.example.test/ws/v6/dex",
                    "dex_api_key": "okx-key",
                    "dex_secret_key": "okx-secret",
                    "dex_passphrase": "okx-pass",
                    "timeout_seconds": 9,
                },
                "binance": {
                    "enabled": True,
                    "web3_base_url": "https://web3-binance.example.test/",
                    "cex_profile_base_url": "https://binance-profile.example.test/",
                    "usdm_futures_base_url": "https://fapi-binance.example.test/",
                    "cex_universe_quote_symbol": "usdt",
                    "cex_universe_contract_type": "perpetual",
                    "timeout_seconds": 7,
                },
            },
        },
    )

    settings = load_settings()

    assert settings.gmgn_configured is True
    assert settings.gmgn_api_key == "gmgn-test"
    assert settings.gmgn_openapi_base_url == "https://openapi.example.test"
    assert settings.gmgn_timeout_seconds == 3
    assert settings.gmgn_token_info_cache_ttl_seconds == 60
    assert settings.okx_dex_base_url == "https://web3-okx.example.test"
    assert settings.okx_dex_chain_indexes == ("501", "1")
    assert settings.okx_dex_ws_url == "wss://okx-ws.example.test/ws/v6/dex"
    assert settings.okx_dex_ws_configured is True
    assert settings.okx_timeout_seconds == 9
    assert settings.binance_web3_base_url == "https://web3-binance.example.test"
    assert settings.binance_cex_profile_base_url == "https://binance-profile.example.test"
    assert settings.binance_usdm_futures_base_url == "https://fapi-binance.example.test"
    assert settings.binance_cex_universe_quote_symbol == "USDT"
    assert settings.binance_cex_universe_contract_type == "PERPETUAL"
    assert settings.binance_timeout_seconds == 7


def test_macrodata_fred_env_pointer_is_redacted_and_configurable(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("FINANCE_FRED_API_KEY", raising=False)
    monkeypatch.setenv("CUSTOM_FRED_ENV", "secret-fred-key")
    write_config(
        tmp_path,
        {
            "ws_token": "secret",
            "handles": ["toly"],
            "providers": {
                "macrodata": {
                    "enabled": True,
                    "quote_timeout_seconds": 6,
                    "quote_cache_ttl_seconds": 45,
                    "fred_api_key_env": " CUSTOM_FRED_ENV ",
                },
            },
        },
    )

    settings = load_settings()

    assert settings.macrodata_enabled is True
    assert settings.macrodata_quote_timeout_seconds == 6
    assert settings.macrodata_quote_cache_ttl_seconds == 45
    assert settings.macrodata_fred_api_key_env == "CUSTOM_FRED_ENV"
    assert settings.macrodata_cli_project_dir is None
    assert settings.macrodata_fred_api_key_configured is True


def test_macrodata_fred_configured_is_false_without_env_value(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("FINANCE_FRED_API_KEY", raising=False)
    write_config(tmp_path, {"ws_token": "secret", "handles": ["toly"]})

    settings = load_settings()

    assert settings.macrodata_fred_api_key_env == "FINANCE_FRED_API_KEY"
    assert settings.macrodata_fred_api_key_configured is False


def test_cli_config_reports_macrodata_without_secret(tmp_path, monkeypatch):
    from gmgn_twitter_intel.app.surfaces.cli.commands.config import handle_config

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("FINANCE_FRED_API_KEY", "secret-fred-key")
    write_config(tmp_path, {"ws_token": "secret", "handles": ["toly"]})

    code, payload = handle_config(object())

    assert code == 0
    macrodata = payload["data"]["providers"]["macrodata"]
    assert macrodata == {
        "enabled": True,
        "quote_timeout_seconds": 5.0,
        "quote_cache_ttl_seconds": 30.0,
        "fred_api_key_env": "FINANCE_FRED_API_KEY",
        "fred_api_key_configured": True,
        "cli_project_dir_configured": False,
    }
    assert "secret-fred-key" not in str(payload)


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
        "base_url",
        "timeout_seconds",
        "trace_enabled",
        "trace_api_key",
        "trace_include_sensitive_data",
    ]
    assert "workers" not in payload
    workers = WorkersSettings(**yaml.safe_load(default_workers_yaml()))
    assert workers.enrichment.concurrency == 4
    assert workers.pulse_candidate.trigger_thresholds.min_rank_score == 45
    assert workers.handle_summary.time_threshold_ms == 1_800_000
    assert workers.handle_summary.window_days == 3
    Settings(**{**payload, "workers": workers})


def test_default_workers_yaml_keys_match_manifest_worker_names() -> None:
    payload = yaml.safe_load(default_workers_yaml())

    assert set(payload) == _manifest_worker_names() | {"defaults", "agent_runtime"}
    assert set(WorkersSettings.model_fields) == set(payload)


def test_config_example_matches_settings_schema() -> None:
    payload = yaml.safe_load(Path("config.example.yaml").read_text(encoding="utf-8"))

    Settings(**payload, workers=WorkersSettings())


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
