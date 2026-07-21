from __future__ import annotations

import os
import secrets
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, SecretStr, field_validator, model_validator

from parallax.platform.config.news_provider_types import OPENNEWS_FETCH_POLICY_KEYS
from parallax.platform.paths.runtime_paths import app_home, app_log_path, config_path, workers_config_path

DEFAULT_UPSTREAM_CHAINS = ("sol", "eth", "base", "bsc")
DEFAULT_UPSTREAM_CHANNELS = ("twitter_monitor_basic", "twitter_monitor_token")
DEFAULT_GMGN_APP_VERSION = "20260429-12894-ccec416"
NOTIFICATION_SEVERITIES = ("info", "warning", "high", "critical")
NOTIFICATION_RULE_IDS = (
    "watched_account_activity",
    "watched_account_token_alert",
    "news_high_signal",
)
SettingsNewsProviderType = Literal[
    "rss",
    "atom",
    "json_feed",
    "cryptopanic",
    "opennews",
    "openbb",
    "telegram_public",
    "twitter_profile",
    "twitter_thread_context",
    "reddit",
    "hackernews",
    "github",
    "ossinsight",
    "manual_api",
]
SettingsNewsSourceRole = Literal[
    "official_exchange",
    "official_regulator",
    "official_protocol",
    "official_issuer",
    "specialist_media",
    "aggregator",
    "social",
    "community",
    "developer_signal",
    "observed_source",
]
DEFAULT_NEWS_SOURCE_CONFIGS: tuple[dict[str, object], ...] = (
    {
        "source_id": "coindesk",
        "provider_type": "rss",
        "feed_url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "source_domain": "coindesk.com",
        "source_name": "CoinDesk",
        "source_role": "specialist_media",
        "trust_tier": "high",
        "enabled": True,
        "refresh_interval_seconds": 300,
    },
    {
        "source_id": "cointelegraph",
        "provider_type": "rss",
        "feed_url": "https://cointelegraph.com/rss",
        "source_domain": "cointelegraph.com",
        "source_name": "CoinTelegraph",
        "source_role": "specialist_media",
        "trust_tier": "standard",
        "enabled": True,
        "refresh_interval_seconds": 300,
    },
    {
        "source_id": "theblock",
        "provider_type": "rss",
        "feed_url": "https://www.theblock.co/rss.xml",
        "source_domain": "theblock.co",
        "source_name": "The Block",
        "source_role": "specialist_media",
        "trust_tier": "high",
        "enabled": True,
        "refresh_interval_seconds": 300,
    },
    {
        "source_id": "bitcoinmagazine",
        "provider_type": "rss",
        "feed_url": "https://bitcoinmagazine.com/feed",
        "source_domain": "bitcoinmagazine.com",
        "source_name": "Bitcoin Magazine",
        "source_role": "specialist_media",
        "trust_tier": "standard",
        "enabled": True,
        "refresh_interval_seconds": 600,
    },
    {
        "source_id": "decrypt",
        "provider_type": "rss",
        "feed_url": "https://decrypt.co/feed",
        "source_domain": "decrypt.co",
        "source_name": "Decrypt",
        "source_role": "specialist_media",
        "trust_tier": "standard",
        "enabled": True,
        "refresh_interval_seconds": 300,
    },
    {
        "source_id": "marketwatch-top-stories",
        "provider_type": "rss",
        "feed_url": "http://feeds.marketwatch.com/marketwatch/topstories/",
        "source_domain": "marketwatch.com",
        "source_name": "MarketWatch Top Stories",
        "source_role": "specialist_media",
        "trust_tier": "standard",
        "enabled": True,
        "refresh_interval_seconds": 600,
    },
    {
        "source_id": "wsj-markets",
        "provider_type": "rss",
        "feed_url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "source_domain": "wsj.com",
        "source_name": "WSJ Markets",
        "source_role": "specialist_media",
        "trust_tier": "high",
        "enabled": True,
        "refresh_interval_seconds": 600,
    },
    {
        "source_id": "cnbc-economy",
        "provider_type": "rss",
        "feed_url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
        "source_domain": "cnbc.com",
        "source_name": "CNBC Economy",
        "source_role": "specialist_media",
        "trust_tier": "standard",
        "enabled": True,
        "refresh_interval_seconds": 600,
    },
    {
        "source_id": "cnbc-markets",
        "provider_type": "rss",
        "feed_url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069",
        "source_domain": "cnbc.com",
        "source_name": "CNBC Markets",
        "source_role": "specialist_media",
        "trust_tier": "standard",
        "enabled": True,
        "refresh_interval_seconds": 600,
    },
    {
        "source_id": "yahoo-finance",
        "provider_type": "rss",
        "feed_url": "https://finance.yahoo.com/news/rssindex",
        "source_domain": "finance.yahoo.com",
        "source_name": "Yahoo Finance",
        "source_role": "aggregator",
        "trust_tier": "standard",
        "enabled": True,
        "refresh_interval_seconds": 600,
    },
    {
        "source_id": "cryptopanic-en",
        "provider_type": "cryptopanic",
        "feed_url": (
            "cryptopanic://posts?regions=en&kind=all&max_items=50"
            "&profile_dir=~/.parallax/cryptopanic-profile&timeout=60"
        ),
        "source_domain": "cryptopanic.com",
        "source_name": "CryptoPanic",
        "source_role": "aggregator",
        "trust_tier": "standard",
        "enabled": True,
        "refresh_interval_seconds": 300,
    },
    {
        "source_id": "opennews-news",
        "provider_type": "opennews",
        "feed_url": "opennews://subscribe",
        "source_domain": "6551.io",
        "source_name": "OpenNews News",
        "source_role": "aggregator",
        "trust_tier": "standard",
        "enabled": False,
        "refresh_interval_seconds": 10,
        "coverage_tags": ("crypto", "realtime", "opennews", "news"),
        "fetch_policy": {
            "engineTypes": {"news": []},
            "hasCoin": True,
            "rest_limit": 100,
            "max_rest_pages": 5,
            "rest_overlap_ms": 900_000,
        },
    },
    {
        "source_id": "opennews-listing",
        "provider_type": "opennews",
        "feed_url": "opennews://subscribe",
        "source_domain": "6551.io",
        "source_name": "OpenNews Listing",
        "source_role": "aggregator",
        "trust_tier": "standard",
        "enabled": False,
        "refresh_interval_seconds": 10,
        "coverage_tags": ("crypto", "realtime", "opennews", "listing"),
        "fetch_policy": {
            "engineTypes": {"listing": []},
            "hasCoin": True,
            "rest_limit": 100,
            "max_rest_pages": 5,
            "rest_overlap_ms": 900_000,
        },
    },
    {
        "source_id": "opennews-onchain",
        "provider_type": "opennews",
        "feed_url": "opennews://subscribe",
        "source_domain": "6551.io",
        "source_name": "OpenNews OnChain",
        "source_role": "aggregator",
        "trust_tier": "standard",
        "enabled": False,
        "refresh_interval_seconds": 10,
        "coverage_tags": ("crypto", "realtime", "opennews", "onchain"),
        "fetch_policy": {
            "engineTypes": {"onchain": []},
            "hasCoin": True,
            "rest_limit": 100,
            "max_rest_pages": 5,
            "rest_overlap_ms": 900_000,
        },
    },
)


class ApiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "0.0.0.0"  # noqa: S104 -- configurable API bind address; defaults to all interfaces intentionally
    port: int = 8765
    heartbeat_interval: int = 30
    replay_limit: int = 100


class PostgresConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dsn: str = "postgresql://parallax_app@postgres:5432/parallax"
    password_file: str | None = "postgres_password"
    pool_min_size: int = 1
    pool_max_size: int = 16
    connect_timeout_seconds: float = 5.0

    @field_validator("dsn", mode="before")
    @classmethod
    def parse_dsn(cls, value: Any) -> str:
        normalized = str(value or "").strip()
        return normalized or "postgresql://parallax_app@postgres:5432/parallax"

    @field_validator("password_file", mode="before")
    @classmethod
    def parse_optional_path(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    postgres: PostgresConfig = Field(default_factory=PostgresConfig)


class LlmConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "litellm"
    api_key: str | None = None
    base_url: str = ""
    timeout_seconds: float = 120.0
    trace_enabled: bool = True
    trace_api_key: str | None = None
    trace_include_sensitive_data: bool = False

    @field_validator("provider", mode="before")
    @classmethod
    def parse_provider(cls, value: Any) -> str:
        normalized = str(value or "litellm").strip().lower()
        if normalized != "litellm":
            raise ValueError("llm.provider must be 'litellm'")
        return normalized

    @field_validator(
        "api_key",
        "trace_api_key",
        mode="before",
    )
    @classmethod
    def parse_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("base_url", mode="before")
    @classmethod
    def parse_base_url(cls, value: Any) -> str:
        return str(value or "").strip().rstrip("/")


class GmgnConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str | None = None
    openapi_base_url: str = "https://openapi.gmgn.ai"
    timeout_seconds: float = 5.0
    token_info_cache_ttl_seconds: int = 60

    @field_validator("api_key", mode="before")
    @classmethod
    def parse_optional_api_key(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("openapi_base_url", mode="before")
    @classmethod
    def parse_openapi_base_url(cls, value: Any) -> str:
        normalized = str(value or "https://openapi.gmgn.ai").strip().rstrip("/")
        return normalized or "https://openapi.gmgn.ai"


class UpstreamConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chains: tuple[str, ...] = DEFAULT_UPSTREAM_CHAINS
    channels: tuple[str, ...] = DEFAULT_UPSTREAM_CHANNELS
    app_version: str = DEFAULT_GMGN_APP_VERSION
    proxy: str | None = None
    reconnect_delay: float = 3.0
    heartbeat_interval: float = 25.0
    idle_timeout: float = 90.0

    @field_validator("chains", "channels", mode="before")
    @classmethod
    def parse_tuple(cls, value: Any) -> tuple[str, ...]:
        return tuple(_split_values(value))

    @field_validator("proxy", mode="before")
    @classmethod
    def parse_optional_proxy(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if normalized.lower() in {"", "none", "false", "off", "direct"}:
            return None
        return normalized


class NotificationRuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    channels: tuple[str, ...] = ("in_app",)
    cooldown_seconds: int = Field(default=0, ge=0)

    @field_validator("channels", mode="before")
    @classmethod
    def parse_channels(cls, value: Any) -> tuple[str, ...]:
        parsed = tuple(_split_values(value))
        return parsed or ("in_app",)


class NotificationChannelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    provider: str = "apprise"
    url: str | None = None
    min_severity: str = "warning"

    @field_validator("provider", mode="before")
    @classmethod
    def parse_provider(cls, value: Any) -> str:
        normalized = str(value or "apprise").strip().lower()
        if normalized not in {"apprise", "log", "pushdeer"}:
            raise ValueError("notifications channel provider must be 'apprise', 'log', or 'pushdeer'")
        return normalized

    @field_validator("url", mode="before")
    @classmethod
    def parse_url(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("min_severity", mode="before")
    @classmethod
    def parse_min_severity(cls, value: Any) -> str:
        normalized = str(value or "warning").strip().lower()
        if normalized not in NOTIFICATION_SEVERITIES:
            raise ValueError("notifications channel min_severity must be info, warning, high, or critical")
        return normalized


class NotificationsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    candidate_limit: int = Field(default=50, ge=1)
    watched_activity_window_ms: int = Field(default=3_600_000, ge=1)
    news_high_signal_recency_window_ms: int = Field(default=7_200_000, ge=1)
    news_high_signal_query_min_limit: int = Field(default=500, ge=1)
    news_high_signal_query_multiplier: int = Field(default=20, ge=1)
    retention_days: int = Field(default=30, ge=1)
    rules: dict[str, NotificationRuleConfig] = Field(
        default_factory=lambda: {
            rule_id: NotificationRuleConfig(**payload)
            for rule_id, payload in _default_notification_rule_payloads().items()
        }
    )
    channels: dict[str, NotificationChannelConfig] = Field(default_factory=dict)

    @field_validator("rules", mode="before")
    @classmethod
    def parse_rules(cls, value: Any) -> dict[str, Any]:
        merged = _default_notification_rule_payloads()
        if value is None:
            return merged
        if not isinstance(value, Mapping):
            raise ValueError("notifications.rules must be a mapping")
        for rule_id, raw_payload in value.items():
            key = str(rule_id).strip()
            if key not in NOTIFICATION_RULE_IDS:
                raise ValueError(f"unknown notification rule: {key}")
            if isinstance(raw_payload, NotificationRuleConfig):
                payload: Mapping[str, Any] = raw_payload.model_dump(exclude_unset=True)
            elif raw_payload is None:
                payload = {}
            else:
                payload = raw_payload
            if not isinstance(payload, Mapping):
                raise ValueError(f"notifications.rules.{key} must be a mapping")
            merged[key] = {**merged[key], **dict(payload)}
        return merged


class OkxProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dex_base_url: str = "https://web3.okx.com"
    dex_chain_indexes: tuple[str, ...] = ("501", "1", "56", "8453", "607")
    dex_ws_url: str = "wss://wsdex.okx.com/ws/v6/dex"
    dex_api_key: str | None = None
    dex_secret_key: str | None = None
    dex_passphrase: str | None = None
    timeout_seconds: float = 15.0

    @field_validator("dex_base_url", mode="before")
    @classmethod
    def parse_base_url(cls, value: Any) -> str:
        normalized = str(value or "").strip().rstrip("/")
        return normalized

    @field_validator("dex_chain_indexes", mode="before")
    @classmethod
    def parse_tuple(cls, value: Any) -> tuple[str, ...]:
        return tuple(_split_values(value))

    @field_validator("dex_api_key", "dex_secret_key", "dex_passphrase", mode="before")
    @classmethod
    def parse_optional_secret(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("dex_ws_url", mode="before")
    @classmethod
    def parse_ws_url(cls, value: Any) -> str:
        return str(value or "wss://wsdex.okx.com/ws/v6/dex").strip()


class BinanceProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    web3_base_url: str = "https://web3.binance.com"
    cex_profile_base_url: str = "https://www.binance.com"
    usdm_futures_base_url: str = "https://fapi.binance.com"
    cex_universe_quote_symbol: str = "USDT"
    cex_universe_contract_type: str = "PERPETUAL"
    timeout_seconds: float = 15.0

    @field_validator("web3_base_url", "cex_profile_base_url", "usdm_futures_base_url", mode="before")
    @classmethod
    def parse_base_url(cls, value: Any) -> str:
        return str(value or "").strip().rstrip("/")

    @field_validator("cex_universe_quote_symbol", "cex_universe_contract_type", mode="before")
    @classmethod
    def parse_uppercase_string(cls, value: Any) -> str:
        return str(value or "").strip().upper()


class MacrodataProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    fred_api_key_env: str | None = "FINANCE_FRED_API_KEY"
    fred_api_key: SecretStr | None = None

    @field_validator("fred_api_key_env", mode="before")
    @classmethod
    def parse_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("fred_api_key", mode="before")
    @classmethod
    def parse_optional_secret(cls, value: Any) -> Any:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class ProvidersConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    okx: OkxProviderConfig = Field(default_factory=OkxProviderConfig)
    binance: BinanceProviderConfig = Field(default_factory=BinanceProviderConfig)
    macrodata: MacrodataProviderConfig = Field(default_factory=MacrodataProviderConfig)


class NewsSourceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    provider_type: SettingsNewsProviderType = "rss"
    feed_url: str
    source_domain: str
    source_name: str
    source_role: SettingsNewsSourceRole = "observed_source"
    trust_tier: Literal["official", "high", "standard", "low"] = "standard"
    managed_by_config: bool = True
    enabled: bool = True
    refresh_interval_seconds: int = Field(default=300, ge=1)
    coverage_tags: tuple[str, ...] = ()
    asset_universe: tuple[str, ...] = ()
    authority_scope: dict[str, Any] = Field(default_factory=dict)
    fetch_policy: dict[str, Any] = Field(default_factory=dict)
    cost_policy: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_id", "feed_url", "source_domain", "source_name", mode="before")
    @classmethod
    def parse_required_string(cls, value: Any) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("news source field must not be empty")
        return normalized

    @field_validator("source_domain", mode="before")
    @classmethod
    def parse_source_domain(cls, value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized:
            raise ValueError("news source field must not be empty")
        return normalized

    @field_validator("coverage_tags", "asset_universe", mode="before")
    @classmethod
    def parse_string_tuple(cls, value: Any) -> tuple[str, ...]:
        return _normalize_news_string_tuple(value)


class OpenNewsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_token: str | None = None
    api_base_url: str = "https://ai.6551.io"

    @field_validator("api_token", mode="before")
    @classmethod
    def parse_optional_token(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("api_base_url", mode="before")
    @classmethod
    def parse_api_base_url(cls, value: Any) -> str:
        normalized = str(value or "https://ai.6551.io").strip().rstrip("/")
        return normalized or "https://ai.6551.io"


def _default_news_source_settings() -> tuple[NewsSourceSettings, ...]:
    return tuple(NewsSourceSettings(**source) for source in DEFAULT_NEWS_SOURCE_CONFIGS)


def _normalize_news_string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return _normalize_news_string_parts(value.split(","))
    if isinstance(value, bytes | bytearray):
        try:
            return _normalize_news_string_tuple(bytes(value).decode("utf-8"))
        except UnicodeDecodeError:
            return _normalize_news_string_parts((str(value).strip(),))
    if isinstance(value, Mapping):
        raise TypeError("mappings are not valid string tuples")
    if isinstance(value, Iterable):
        return _normalize_news_string_parts(value)
    return _normalize_news_string_parts((value,))


def _normalize_news_string_parts(parts: Iterable[object]) -> tuple[str, ...]:
    normalized: list[str] = []
    for part in parts:
        item = str(part or "").strip()
        if item:
            normalized.append(item)
    return tuple(normalized)


class NewsIntelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    opennews: OpenNewsSettings = Field(default_factory=OpenNewsSettings)
    sources: tuple[NewsSourceSettings, ...] = Field(default_factory=_default_news_source_settings)

    @field_validator("sources", mode="before")
    @classmethod
    def parse_sources(cls, value: Any) -> tuple[Any, ...]:
        if value is None:
            return ()
        if isinstance(value, tuple):
            return value
        if isinstance(value, list):
            return tuple(value)
        raise ValueError("news_intel.sources must be a list")

    @field_validator("sources", mode="after")
    @classmethod
    def validate_opennews_fetch_policy(cls, sources: tuple[NewsSourceSettings, ...]) -> tuple[NewsSourceSettings, ...]:
        for source in sources:
            if source.provider_type != "opennews":
                continue
            unknown = sorted(set(source.fetch_policy) - OPENNEWS_FETCH_POLICY_KEYS)
            if unknown:
                raise ValueError(f"{source.source_id} has unknown OpenNews fetch policy keys: {', '.join(unknown)}")
        return sources


class BackoffPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["exponential"] = "exponential"
    base_ms: int = Field(default=1000, ge=0)
    max_ms: int = Field(default=60_000, ge=0)


class AgentCircuitBreakerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_threshold: int = Field(default=5, ge=1)
    window_seconds: int = Field(default=300, ge=1)
    open_seconds: int = Field(default=120, ge=1)


class AgentLaneSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = None
    provider_family: Literal["litellm", "deepseek"] | None = None
    client_validation_retries: int | None = Field(default=None, ge=0)
    max_tokens: int | None = Field(default=None, ge=1)
    priority: Literal["high", "normal", "bulk", "low"] = "normal"
    max_concurrency: int = Field(default=1, ge=1)
    timeout_seconds: float = Field(default=180.0, ge=1)
    rpm_limit: int | None = Field(default=None, ge=1)
    circuit_breaker: AgentCircuitBreakerSettings = Field(default_factory=AgentCircuitBreakerSettings)

    @field_validator("model", mode="before")
    @classmethod
    def parse_optional_model(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("provider_family", mode="before")
    @classmethod
    def parse_optional_capability_label(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        return normalized or None


def _default_agent_lanes() -> dict[str, AgentLaneSettings]:
    return {
        "news.story_brief": AgentLaneSettings(
            priority="low",
            max_concurrency=1,
            timeout_seconds=180.0,
            max_tokens=2200,
        ),
    }


class AgentRuntimeDefaultsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = "deepseek-v4-flash"
    provider_family: Literal["litellm", "deepseek"] | None = None
    client_validation_retries: int | None = Field(default=None, ge=0)
    max_tokens: int | None = Field(default=None, ge=1)
    disable_thinking: bool = True
    include_usage: bool = True

    @field_validator("model", mode="before")
    @classmethod
    def parse_model(cls, value: Any) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("agent_runtime.defaults.model is required")
        return normalized

    @field_validator("provider_family", mode="before")
    @classmethod
    def parse_capability_label(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value or "").strip().lower()
        return normalized or None


class AgentRuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defaults: AgentRuntimeDefaultsSettings = Field(default_factory=AgentRuntimeDefaultsSettings)
    global_max_concurrency: int = Field(default=4, ge=1)
    global_rpm_limit: int = Field(default=60, ge=1)
    lanes: dict[str, AgentLaneSettings] = Field(default_factory=_default_agent_lanes)

    @field_validator("lanes", mode="before")
    @classmethod
    def merge_default_lanes(cls, value: Any) -> dict[str, Any]:
        default_lanes = _default_agent_lanes()
        if value is None:
            return default_lanes
        if not isinstance(value, Mapping):
            raise ValueError("agent_runtime.lanes must be a mapping")

        unknown_keys = set(value) - set(default_lanes)
        if unknown_keys:
            unknown = ", ".join(sorted(str(key) for key in unknown_keys))
            raise ValueError(f"agent_runtime.lanes contains unknown lane keys: {unknown}")

        merged: dict[str, Any] = {key: lane.model_dump() for key, lane in default_lanes.items()}
        for key, lane_value in value.items():
            if isinstance(lane_value, AgentLaneSettings):
                merged[key] = lane_value.model_dump()
            elif isinstance(lane_value, Mapping):
                merged[key].update(dict(lane_value))
            else:
                raise ValueError(f"agent_runtime.lanes.{key} must be a mapping")
        return merged


class PerWorkerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    interval_seconds: float = Field(default=5.0, ge=0)
    hard_timeout_seconds: float = Field(default=180.0, ge=0)
    concurrency: int = Field(default=1, ge=1)
    batch_size: int = Field(default=100, ge=1)
    max_attempts: int = Field(default=3, ge=1)
    lease_ms: int = Field(default=120_000, ge=1)
    statement_timeout_seconds: float = Field(default=30.0, ge=0)
    backoff: BackoffPolicy = Field(default_factory=BackoffPolicy)


class CollectorWorkerSettings(PerWorkerSettings):
    mode: Literal["continuous"] = "continuous"
    interval_seconds: float = Field(default=3.0, ge=0)
    hard_timeout_seconds: float = Field(default=0.0, ge=0)
    snapshot_timeout_seconds: float = Field(default=0.5, ge=0)
    watchdog_interval_seconds: float = Field(default=30.0, ge=0)
    stale_timeout_seconds: float = Field(default=180.0, ge=0)


class MarketTickStreamWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=5.0, ge=0)
    subscription_limit: int = Field(default=100, ge=1)
    stream_cycle_seconds: float = Field(default=30.0, ge=0.001)


class MarketTickPollWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=15.0, ge=0)
    batch_size: int = Field(default=100, ge=1)
    concurrency: int = Field(default=4, ge=1)


class MarketTickCurrentProjectionWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=5.0, ge=0)
    batch_size: int = Field(default=100, ge=1)
    retry_ms: int = Field(default=30_000, ge=1)
    advisory_lock_key: int = 2026052401


class EventAnchorBackfillWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=1.0, ge=0)
    batch_size: int = Field(default=50, ge=1)
    concurrency: int = Field(default=8, ge=1)
    min_age_ms: int = Field(default=250, ge=0)
    active_window_ms: int = Field(default=300_000, ge=1)
    max_anchor_lag_ms: int = Field(default=60_000, ge=1)


class LivePriceGatewayWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=2.0, ge=0)
    target_limit: int = Field(default=100, ge=0)
    target_ttl_seconds: float = Field(default=300.0, ge=0)


class ResolutionRefreshWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=30.0, ge=0)
    batch_size: int = Field(default=50, ge=1)
    lease_ms: int = Field(default=300_000, ge=1)
    hot_not_found_retry_ms: int = Field(default=60_000, ge=1)
    reprocess_limit: int = Field(default=500, ge=1)
    chain_ids: tuple[str, ...] = ("solana", "eip155:1", "eip155:56", "eip155:8453", "ton")

    @field_validator("chain_ids", mode="before")
    @classmethod
    def parse_chain_ids(cls, value: Any) -> tuple[str, ...]:
        return tuple(_split_values(value))


class AssetProfileRefreshWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=60.0, ge=0)
    batch_size: int = Field(default=50, ge=1)
    provider_retry_ms: int = Field(default=300_000, ge=1)
    ready_refresh_ms: int = Field(default=21_600_000, ge=1)
    missing_refresh_ms: int = Field(default=900_000, ge=1)
    error_refresh_ms: int = Field(default=900_000, ge=1)
    statement_timeout_seconds: float = Field(default=120.0, ge=0)


class TokenImageMirrorWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=60.0, ge=0)
    batch_size: int = Field(default=100, ge=1)
    source_limit: int = Field(default=5000, ge=0)
    retry_ms: int = Field(default=300_000, ge=1)
    max_attempts: int = Field(default=3, ge=1)
    statement_timeout_seconds: float = Field(default=120.0, ge=0)
    advisory_lock_key: int = 2026052111


class TokenProfileCurrentWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=60.0, ge=0)
    batch_size: int = Field(default=500, ge=1)
    retry_ms: int = Field(default=30_000, ge=1)
    advisory_lock_key: int = 2026051702


class TokenCaptureTierWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=30.0, ge=0)
    batch_size: int = Field(default=500, ge=1)
    ws_limit: int = Field(default=100, ge=0)
    poll_limit: int = Field(default=500, ge=0)
    retry_ms: int = Field(default=30_000, ge=1)
    statement_timeout_seconds: float = Field(default=120.0, ge=0)
    advisory_lock_key: int = 2026051503


class TokenRadarProjectionWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=10.0, ge=0)
    batch_size: int = Field(default=100, ge=1)
    retry_ms: int = Field(default=30_000, ge=1)
    private_cache_retention_enabled: bool = True
    private_cache_retention_ms: int = Field(default=172_800_000, ge=1)
    statement_timeout_seconds: float = Field(default=120.0, ge=0)
    advisory_lock_key: int = 2026051501
    windows: tuple[str, ...] = ("5m", "1h", "4h", "24h")
    scopes: tuple[str, ...] = ("all", "matched")
    venues: tuple[str, ...] = ("all", "sol", "eth", "base", "bsc", "cex")
    hot_windows: tuple[str, ...] = ("5m",)
    cold_interval_seconds: float = Field(default=60.0, ge=0)

    @field_validator("windows", "scopes", "venues", "hot_windows", mode="before")
    @classmethod
    def parse_tuple(cls, value: Any) -> tuple[str, ...]:
        return tuple(_split_values(value))


class MacroViewProjectionWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=300.0, ge=0)
    batch_size: int = Field(default=250, ge=1)
    statement_timeout_seconds: float = Field(default=30.0, ge=0)
    lease_ms: int = Field(default=300_000, ge=1)
    retry_ms: int = Field(default=300_000, ge=1)
    max_attempts: int = Field(default=3, ge=1)
    advisory_lock_key: int = 2026052109
    lookback_days: int = Field(default=1095, ge=1095)
    limit_per_series: int = Field(default=800, ge=800)


class MacroSyncWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=900.0, ge=0)
    hard_timeout_seconds: float = Field(default=300.0, ge=0)
    batch_size: int = Field(default=3, ge=1)
    statement_timeout_seconds: float = Field(default=30.0, ge=0)
    advisory_lock_key: int = 2026052711
    bundle_names: tuple[str, ...] = (
        "macro-core",
        "macro-calendar-core",
        "treasury-auction-core",
        "fed-text-core",
        "crypto-derivatives-core",
    )
    source_name: str = "macrodata-cli"
    bootstrap_lookback_days: int = Field(default=1095, ge=1)
    max_window_days: int = Field(default=31, ge=1)
    steady_overlap_days: int = Field(default=7, ge=1)
    max_bootstrap_windows_per_cycle: int = Field(default=1, ge=1)
    lease_ms: int = Field(default=300_000, ge=1)
    retry_delay_ms: int = Field(default=900_000, ge=1)
    max_attempts: int = Field(default=8, ge=1)
    macrodata_timeout_seconds: float = Field(default=240.0, ge=1)

    @field_validator("bundle_names", mode="before")
    @classmethod
    def parse_bundle_names(cls, value: Any) -> tuple[str, ...]:
        parsed = tuple(_split_values(value))
        if not parsed:
            raise ValueError("macro_sync.bundle_names must not be empty")
        if len(set(parsed)) != len(parsed):
            raise ValueError("macro_sync.bundle_names must be unique")
        return parsed


class NotificationRuleWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=5.0, ge=0)
    batch_size: int = Field(default=50, ge=1)
    statement_timeout_seconds: float = Field(default=30.0, ge=0)


class NotificationDeliveryWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=5.0, ge=0)
    batch_size: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=5, ge=1)
    running_timeout_ms: int = Field(default=300_000, ge=1)
    stale_running_terminalization_batch_size: int = Field(default=100, ge=1)
    statement_timeout_seconds: float = Field(default=30.0, ge=0)


class NewsFetchWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=60.0, ge=0)
    batch_size: int = Field(default=5, ge=1)
    lease_ms: int = Field(default=60_000, ge=1)
    statement_timeout_seconds: float = Field(default=30.0, ge=0)
    advisory_lock_key: int = 2026051905


class NewsItemProcessWorkerSettings(PerWorkerSettings):
    batch_size: int = Field(default=10, ge=1)
    lease_ms: int = Field(default=120_000, ge=1)
    max_attempts: int = Field(default=3, ge=1)
    statement_timeout_seconds: float = Field(default=30.0, ge=0)
    advisory_lock_key: int = 2026051902
    retry_delay_ms: int = Field(default=60_000, ge=1)


class NewsStoryBriefWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=10.0, ge=0)
    hard_timeout_seconds: float = Field(default=240.0, ge=0)
    batch_size: int = Field(default=5, ge=1)
    lease_ms: int = Field(default=120_000, ge=1)
    retry_ms: int = Field(default=60_000, ge=1)
    statement_timeout_seconds: float = Field(default=30.0, ge=0)
    advisory_lock_key: int = 2026061801
    backpressure_cooldown_ms: int = Field(default=60_000, ge=1)


class NewsPageProjectionWorkerSettings(PerWorkerSettings):
    batch_size: int = Field(default=100, ge=1)
    lease_ms: int = Field(default=120_000, ge=1)
    retry_ms: int = Field(default=30_000, ge=1)
    statement_timeout_seconds: float = Field(default=30.0, ge=0)
    advisory_lock_key: int = 2026051904


class WorkersSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_runtime: AgentRuntimeSettings = Field(default_factory=AgentRuntimeSettings)
    collector: CollectorWorkerSettings = Field(default_factory=CollectorWorkerSettings)
    market_tick_stream: MarketTickStreamWorkerSettings = Field(default_factory=MarketTickStreamWorkerSettings)
    market_tick_poll: MarketTickPollWorkerSettings = Field(default_factory=MarketTickPollWorkerSettings)
    market_tick_current_projection: MarketTickCurrentProjectionWorkerSettings = Field(
        default_factory=MarketTickCurrentProjectionWorkerSettings
    )
    event_anchor_backfill: EventAnchorBackfillWorkerSettings = Field(default_factory=EventAnchorBackfillWorkerSettings)
    token_capture_tier: TokenCaptureTierWorkerSettings = Field(default_factory=TokenCaptureTierWorkerSettings)
    live_price_gateway: LivePriceGatewayWorkerSettings = Field(default_factory=LivePriceGatewayWorkerSettings)
    resolution_refresh: ResolutionRefreshWorkerSettings = Field(default_factory=ResolutionRefreshWorkerSettings)
    asset_profile_refresh: AssetProfileRefreshWorkerSettings = Field(default_factory=AssetProfileRefreshWorkerSettings)
    token_image_mirror: TokenImageMirrorWorkerSettings = Field(default_factory=TokenImageMirrorWorkerSettings)
    token_profile_current: TokenProfileCurrentWorkerSettings = Field(default_factory=TokenProfileCurrentWorkerSettings)
    token_radar_projection: TokenRadarProjectionWorkerSettings = Field(
        default_factory=TokenRadarProjectionWorkerSettings
    )
    macro_sync: MacroSyncWorkerSettings = Field(default_factory=MacroSyncWorkerSettings)
    macro_view_projection: MacroViewProjectionWorkerSettings = Field(default_factory=MacroViewProjectionWorkerSettings)
    notification_rule: NotificationRuleWorkerSettings = Field(default_factory=NotificationRuleWorkerSettings)
    notification_delivery: NotificationDeliveryWorkerSettings = Field(
        default_factory=NotificationDeliveryWorkerSettings
    )
    news_fetch: NewsFetchWorkerSettings = Field(default_factory=NewsFetchWorkerSettings)
    news_item_process: NewsItemProcessWorkerSettings = Field(default_factory=NewsItemProcessWorkerSettings)
    news_story_brief: NewsStoryBriefWorkerSettings = Field(default_factory=NewsStoryBriefWorkerSettings)
    news_page_projection: NewsPageProjectionWorkerSettings = Field(default_factory=NewsPageProjectionWorkerSettings)

    @model_validator(mode="after")
    def reject_zero_hard_timeout_for_non_continuous_workers(self) -> WorkersSettings:
        for worker_key in type(self).model_fields:
            if worker_key in {"agent_runtime", "collector"}:
                continue
            worker_settings = getattr(self, worker_key)
            if worker_settings.hard_timeout_seconds <= 0:
                raise ValueError(f"{worker_key}.hard_timeout_seconds must be > 0")
        return self


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    _config_dir: Path = PrivateAttr(default_factory=app_home)

    ws_token: str | None = None
    handles: tuple[str, ...] = Field(default_factory=tuple)
    api: ApiConfig = Field(default_factory=ApiConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    gmgn: GmgnConfig = Field(default_factory=GmgnConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    news_intel: NewsIntelSettings = Field(default_factory=NewsIntelSettings)
    upstream: UpstreamConfig = Field(default_factory=UpstreamConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    workers: WorkersSettings = Field(default_factory=WorkersSettings)

    def set_config_dir(self, value: Path) -> None:
        self._config_dir = value

    @property
    def app_home(self) -> Path:
        return self._config_dir

    @property
    def postgres_dsn(self) -> str:
        return self.storage.postgres.dsn

    @property
    def postgres_password_file(self) -> Path | None:
        value = self.storage.postgres.password_file
        if not value:
            return None
        configured = Path(value).expanduser()
        if configured.is_absolute():
            return configured
        return self._config_dir / configured

    @property
    def postgres_pool_min_size(self) -> int:
        return self.storage.postgres.pool_min_size

    @property
    def postgres_pool_max_size(self) -> int:
        return self.storage.postgres.pool_max_size

    @property
    def postgres_connect_timeout_seconds(self) -> float:
        return self.storage.postgres.connect_timeout_seconds

    @property
    def log_file(self) -> Path:
        return app_log_path(self._config_dir)

    @property
    def api_host(self) -> str:
        return self.api.host

    @property
    def api_port(self) -> int:
        return self.api.port

    @property
    def ws_heartbeat_interval(self) -> int:
        return self.api.heartbeat_interval

    @property
    def replay_limit(self) -> int:
        return self.api.replay_limit

    @property
    def llm_api_key(self) -> str | None:
        return self.llm.api_key

    @property
    def agent_runtime_default_model(self) -> str:
        return self.workers.agent_runtime.defaults.model

    @property
    def llm_base_url(self) -> str:
        return self.llm.base_url

    @property
    def llm_provider(self) -> str:
        return self.llm.provider

    @property
    def llm_trace_enabled(self) -> bool:
        return bool(self.llm.trace_enabled)

    @property
    def llm_trace_api_key(self) -> str | None:
        return self.llm.trace_api_key

    @property
    def llm_trace_include_sensitive_data(self) -> bool:
        return bool(self.llm.trace_include_sensitive_data)

    @property
    def llm_trace_export_configured(self) -> bool:
        return False

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key and self.agent_runtime_default_model)

    @property
    def news_agent_execution_enabled(self) -> bool:
        return bool(self.news_intel.enabled and self.llm_configured and self.workers.news_story_brief.enabled)

    @property
    def gmgn_api_key(self) -> str | None:
        return self.gmgn.api_key

    @property
    def gmgn_openapi_base_url(self) -> str:
        return self.gmgn.openapi_base_url

    @property
    def gmgn_timeout_seconds(self) -> float:
        return self.gmgn.timeout_seconds

    @property
    def gmgn_token_info_cache_ttl_seconds(self) -> int:
        return self.gmgn.token_info_cache_ttl_seconds

    @property
    def gmgn_configured(self) -> bool:
        return bool(self.gmgn_api_key)

    @property
    def okx_dex_base_url(self) -> str:
        return self.providers.okx.dex_base_url

    @property
    def okx_dex_chain_indexes(self) -> tuple[str, ...]:
        return self.providers.okx.dex_chain_indexes or ("501", "1", "56", "8453", "607")

    @property
    def okx_dex_ws_url(self) -> str:
        return self.providers.okx.dex_ws_url

    @property
    def okx_dex_api_key(self) -> str | None:
        return self.providers.okx.dex_api_key

    @property
    def okx_dex_secret_key(self) -> str | None:
        return self.providers.okx.dex_secret_key

    @property
    def okx_dex_passphrase(self) -> str | None:
        return self.providers.okx.dex_passphrase

    @property
    def okx_timeout_seconds(self) -> float:
        return self.providers.okx.timeout_seconds

    @property
    def okx_dex_configured(self) -> bool:
        return bool(self.okx_dex_base_url)

    @property
    def okx_dex_ws_configured(self) -> bool:
        return bool(
            self.okx_dex_ws_url and self.okx_dex_api_key and self.okx_dex_secret_key and self.okx_dex_passphrase
        )

    @property
    def binance_enabled(self) -> bool:
        return bool(self.providers.binance.enabled)

    @property
    def binance_web3_base_url(self) -> str:
        return self.providers.binance.web3_base_url

    @property
    def binance_cex_profile_base_url(self) -> str:
        return self.providers.binance.cex_profile_base_url

    @property
    def binance_usdm_futures_base_url(self) -> str:
        return self.providers.binance.usdm_futures_base_url

    @property
    def binance_cex_universe_quote_symbol(self) -> str:
        return self.providers.binance.cex_universe_quote_symbol

    @property
    def binance_cex_universe_contract_type(self) -> str:
        return self.providers.binance.cex_universe_contract_type

    @property
    def binance_timeout_seconds(self) -> float:
        return self.providers.binance.timeout_seconds

    @property
    def macrodata_enabled(self) -> bool:
        return bool(self.providers.macrodata.enabled)

    @property
    def macrodata_fred_api_key_env(self) -> str | None:
        return self.providers.macrodata.fred_api_key_env

    @property
    def macrodata_fred_api_key(self) -> str | None:
        secret = self.providers.macrodata.fred_api_key
        if secret is None:
            return None
        value = secret.get_secret_value().strip()
        return value or None

    @property
    def macrodata_fred_api_key_configured(self) -> bool:
        if self.macrodata_fred_api_key:
            return True
        env_name = self.macrodata_fred_api_key_env
        if not env_name:
            return False
        return bool(os.environ.get(env_name, "").strip())

    @property
    def upstream_chains(self) -> tuple[str, ...]:
        return self.upstream.chains

    @property
    def upstream_channels(self) -> tuple[str, ...]:
        return self.upstream.channels

    @property
    def upstream_app_version(self) -> str:
        return self.upstream.app_version

    @property
    def upstream_proxy(self) -> str | None:
        return self.upstream.proxy

    @property
    def upstream_reconnect_delay(self) -> float:
        return self.upstream.reconnect_delay

    @property
    def upstream_heartbeat_interval(self) -> float:
        return self.upstream.heartbeat_interval

    @property
    def upstream_idle_timeout(self) -> float:
        return self.upstream.idle_timeout

    @field_validator("handles", mode="before")
    @classmethod
    def parse_handles(cls, value: Any) -> tuple[str, ...]:
        handles = []
        seen = set()
        for item in _split_values(value):
            handle = item.lstrip("@").lower()
            if handle and handle not in seen:
                handles.append(handle)
                seen.add(handle)
        return tuple(handles)

    @field_validator("ws_token", mode="before")
    @classmethod
    def parse_optional_ws_token(cls, value: Any) -> str | None:
        if value is None:
            return None
        token = str(value).strip()
        return token or None


def load_settings(*, require_ws_token: bool = True) -> Settings:
    path = config_path()
    if not path.exists():
        raise FileNotFoundError(f"config.yaml not found at {path}; run `parallax init` first")
    workers_path = workers_config_path(path.parent)
    if not workers_path.exists():
        raise FileNotFoundError(f"workers.yaml not found at {workers_path}; run `parallax init` first")
    data = _load_yaml_mapping(path)
    if "workers" in data:
        raise ValueError("workers runtime settings must be configured in workers.yaml, not config.yaml")
    workers = WorkersSettings(**_load_yaml_mapping(workers_path))
    settings = Settings(**dict(data), workers=workers)
    settings.set_config_dir(path.parent)
    if require_ws_token and not settings.ws_token:
        raise ValueError("ws_token is required in config.yaml")
    return settings


def write_default_config(*, force: bool = False) -> Path:
    home = app_home()
    path = config_path(home)
    workers_path = workers_config_path(home)
    home.mkdir(parents=True, exist_ok=True)
    (home / "logs").mkdir(parents=True, exist_ok=True)
    if force or not path.exists():
        path.write_text(default_config_yaml(), encoding="utf-8")
    if force or not workers_path.exists():
        workers_path.write_text(default_workers_yaml(), encoding="utf-8")
    return path


def default_config_yaml() -> str:
    token = secrets.token_urlsafe(32)
    return f"""# Parallax
ws_token: "{token}"
handles:
  - toly
  - traderpow
  - theunipcs
  - dotyyds1234
  - brc20niubi
  - jessepollak
  - cz_binance
  - heyibinance
  - elonmusk
  - cookerflips
  - himgajria
  - cryptodevinl
  - spidercrypto0x

api:
  host: "0.0.0.0"
  port: 8765
  heartbeat_interval: 30
  replay_limit: 100

storage:
  postgres:
    dsn: "postgresql://parallax_app@postgres:5432/parallax"
    password_file: "postgres_password"
    pool_min_size: 1
    pool_max_size: 16
    connect_timeout_seconds: 5

llm:
  provider: "litellm"
  api_key:
  base_url: ""
  timeout_seconds: 120
  trace_enabled: true
  trace_api_key:
  trace_include_sensitive_data: false

gmgn:
  api_key:
  openapi_base_url: "https://openapi.gmgn.ai"
  timeout_seconds: 5
  token_info_cache_ttl_seconds: 60

providers:
  okx:
    dex_base_url: "https://web3.okx.com"
    dex_chain_indexes: ["501", "1", "56", "8453", "607"]
    dex_ws_url: "wss://wsdex.okx.com/ws/v6/dex"
    dex_api_key:
    dex_secret_key:
    dex_passphrase:
    timeout_seconds: 15
  binance:
    enabled: true
    web3_base_url: "https://web3.binance.com"
    cex_profile_base_url: "https://www.binance.com"
    usdm_futures_base_url: "https://fapi.binance.com"
    cex_universe_quote_symbol: "USDT"
    cex_universe_contract_type: "PERPETUAL"
    timeout_seconds: 15
  macrodata:
    enabled: true
    fred_api_key_env: "FINANCE_FRED_API_KEY"
    fred_api_key:

{_default_news_intel_yaml()}

upstream:
  chains: ["sol", "eth", "base", "bsc"]
  channels: ["twitter_monitor_basic", "twitter_monitor_token"]
  app_version: "{DEFAULT_GMGN_APP_VERSION}"
  proxy:
  reconnect_delay: 3
  heartbeat_interval: 25
  idle_timeout: 90

notifications:
  enabled: true
  candidate_limit: 50
  watched_activity_window_ms: 3600000
  news_high_signal_recency_window_ms: 7200000
  news_high_signal_query_min_limit: 500
  news_high_signal_query_multiplier: 20
  retention_days: 30
  rules:
    watched_account_activity:
      enabled: true
      channels: ["in_app"]
    watched_account_token_alert:
      enabled: true
      channels: ["in_app"]
    news_high_signal:
      enabled: true
      channels: ["in_app", "pushdeer"]
      cooldown_seconds: 3600
  channels: {{}}
"""


def _default_news_intel_yaml() -> str:
    rendered = yaml.safe_dump(
        {
            "news_intel": {
                "enabled": True,
                "opennews": OpenNewsSettings().model_dump(),
                "sources": [dict(source) for source in DEFAULT_NEWS_SOURCE_CONFIGS],
            }
        },
        sort_keys=False,
    )
    return str(rendered).rstrip()


def default_workers_yaml() -> str:
    payload = WorkersSettings().model_dump(mode="json")
    rendered = yaml.safe_dump(payload, sort_keys=False)
    return f"# Parallax worker runtime\n{rendered}"


def write_default_workers_config(*, force: bool = False) -> Path:
    home = app_home()
    path = workers_config_path(home)
    home.mkdir(parents=True, exist_ok=True)
    if force or not path.exists():
        path.write_text(default_workers_yaml(), encoding="utf-8")
    return path


def _load_yaml_mapping(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a mapping at {path}")
    return data


def _split_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _default_notification_rule_payloads() -> dict[str, dict[str, Any]]:
    return {
        "watched_account_activity": {
            "enabled": True,
            "channels": ("in_app",),
            "cooldown_seconds": 300,
        },
        "watched_account_token_alert": {
            "enabled": True,
            "channels": ("in_app",),
            "cooldown_seconds": 900,
        },
        "news_high_signal": {
            "enabled": True,
            "channels": ("in_app", "pushdeer"),
            "cooldown_seconds": 3600,
        },
    }
