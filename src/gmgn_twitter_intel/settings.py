from __future__ import annotations

import secrets
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

from .runtime_paths import app_home, app_log_path, config_path

DEFAULT_UPSTREAM_CHAINS = ("sol", "eth", "base", "bsc")
DEFAULT_UPSTREAM_CHANNELS = ("twitter_monitor_basic", "twitter_monitor_token")
DEFAULT_GMGN_APP_VERSION = "20260429-12894-ccec416"
NOTIFICATION_SEVERITIES = ("info", "warning", "high", "critical")
NOTIFICATION_RULE_IDS = (
    "watched_account_activity",
    "watched_account_token_alert",
    "hot_quality_token_5m",
    "quality_token_5m",
    "harness_snapshot_high_score",
)


class ApiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "0.0.0.0"
    port: int = 8765
    heartbeat_interval: int = 30
    replay_limit: int = 100


class PostgresConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dsn: str = "postgresql://gmgn_app@postgres:5432/gmgn_twitter_intel"
    password_file: str | None = "postgres_password"
    pool_min_size: int = 1
    pool_max_size: int = 10
    connect_timeout_seconds: float = 5.0

    @field_validator("dsn", mode="before")
    @classmethod
    def parse_dsn(cls, value: Any) -> str:
        normalized = str(value or "").strip()
        return normalized or "postgresql://gmgn_app@postgres:5432/gmgn_twitter_intel"

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

    provider: str = "openai"
    api_key: str | None = None
    model: str | None = None
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: float = 20.0
    enrichment_poll_interval: float = 2.0

    @field_validator("provider", mode="before")
    @classmethod
    def parse_provider(cls, value: Any) -> str:
        normalized = str(value or "openai").strip().lower()
        if normalized != "openai":
            raise ValueError("llm.provider must be 'openai'")
        return normalized

    @field_validator("api_key", "model", mode="before")
    @classmethod
    def parse_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("base_url", mode="before")
    @classmethod
    def parse_base_url(cls, value: Any) -> str:
        normalized = str(value or "https://api.openai.com/v1").strip().rstrip("/")
        return normalized or "https://api.openai.com/v1"


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


class CollectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watchdog_interval: float = 30.0
    stale_timeout: float = 180.0


class NotificationRuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    channels: tuple[str, ...] = ("in_app",)
    social_heat_min: int | None = None
    discussion_quality_min: int | None = None
    opportunity_min: int | None = None
    combined_score_min: float | None = None
    suppress_chase_risk: bool = False
    cooldown_seconds: int = 0

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
    max_attempts: int = 5

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
    poll_interval_seconds: float = 5.0
    token_flow_limit: int = 50
    retention_days: int = 30
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
        for rule_id, payload in value.items():
            key = str(rule_id).strip()
            if key not in NOTIFICATION_RULE_IDS:
                raise ValueError(f"unknown notification rule: {key}")
            if isinstance(payload, NotificationRuleConfig):
                payload = payload.model_dump()
            if payload is None:
                payload = {}
            if not isinstance(payload, Mapping):
                raise ValueError(f"notifications.rules.{key} must be a mapping")
            merged[key] = {**merged[key], **dict(payload)}
        return merged


class OkxProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cex_base_url: str = "https://www.okx.com"
    dex_base_url: str = "https://web3.okx.com"
    dex_chain_indexes: tuple[str, ...] = ("501", "1", "56", "8453")
    timeout_seconds: float = 15.0

    @field_validator("cex_base_url", "dex_base_url", mode="before")
    @classmethod
    def parse_base_url(cls, value: Any) -> str:
        normalized = str(value or "").strip().rstrip("/")
        return normalized

    @field_validator("dex_chain_indexes", mode="before")
    @classmethod
    def parse_chain_indexes(cls, value: Any) -> tuple[str, ...]:
        return tuple(_split_values(value)) or ("501", "1", "56", "8453")


class ProvidersConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    okx: OkxProviderConfig = Field(default_factory=OkxProviderConfig)


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
    upstream: UpstreamConfig = Field(default_factory=UpstreamConfig)
    collector: CollectorConfig = Field(default_factory=CollectorConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)

    @property
    def config_dir(self) -> Path:
        return self._config_dir

    def set_config_dir(self, value: Path) -> None:
        self._config_dir = value

    @property
    def app_home(self) -> Path:
        return self.config_dir

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
        return self.config_dir / configured

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
        return app_log_path(self.config_dir)

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
    def llm_model(self) -> str | None:
        return self.llm.model

    @property
    def llm_base_url(self) -> str:
        return self.llm.base_url

    @property
    def llm_provider(self) -> str:
        return self.llm.provider

    @property
    def llm_timeout_seconds(self) -> float:
        return self.llm.timeout_seconds

    @property
    def enrichment_poll_interval(self) -> float:
        return self.llm.enrichment_poll_interval

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key and self.llm_model)

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
    def okx_cex_base_url(self) -> str:
        return self.providers.okx.cex_base_url

    @property
    def okx_dex_base_url(self) -> str:
        return self.providers.okx.dex_base_url

    @property
    def okx_dex_chain_indexes(self) -> tuple[str, ...]:
        return self.providers.okx.dex_chain_indexes

    @property
    def okx_timeout_seconds(self) -> float:
        return self.providers.okx.timeout_seconds

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

    @property
    def collector_watchdog_interval(self) -> float:
        return self.collector.watchdog_interval

    @property
    def collector_stale_timeout(self) -> float:
        return self.collector.stale_timeout

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
        raise FileNotFoundError(f"config.yaml not found at {path}; run `gmgn-twitter-intel init` first")
    data = _load_yaml_mapping(path)
    settings = Settings(**data)
    settings.set_config_dir(path.parent)
    if require_ws_token and not settings.ws_token:
        raise ValueError("ws_token is required in config.yaml")
    return settings


def write_default_config(*, force: bool = False) -> Path:
    home = app_home()
    path = config_path(home)
    home.mkdir(parents=True, exist_ok=True)
    (home / "logs").mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return path
    path.write_text(default_config_yaml(), encoding="utf-8")
    return path


def default_config_yaml() -> str:
    token = secrets.token_urlsafe(32)
    return f"""# GMGN Twitter Intel
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
    dsn: "postgresql://gmgn_app@postgres:5432/gmgn_twitter_intel"
    password_file: "postgres_password"
    pool_min_size: 1
    pool_max_size: 10
    connect_timeout_seconds: 5

llm:
  provider: "openai"
  api_key:
  model:
  base_url: "https://api.openai.com/v1"
  timeout_seconds: 20
  enrichment_poll_interval: 2

gmgn:
  api_key:
  openapi_base_url: "https://openapi.gmgn.ai"
  timeout_seconds: 5
  token_info_cache_ttl_seconds: 60

providers:
  okx:
    cex_base_url: "https://www.okx.com"
    dex_base_url: "https://web3.okx.com"
    dex_chain_indexes: ["501", "1", "56", "8453"]
    timeout_seconds: 15

upstream:
  chains: ["sol", "eth", "base", "bsc"]
  channels: ["twitter_monitor_basic", "twitter_monitor_token"]
  app_version: "{DEFAULT_GMGN_APP_VERSION}"
  proxy:
  reconnect_delay: 3
  heartbeat_interval: 25
  idle_timeout: 90

collector:
  watchdog_interval: 30
  stale_timeout: 180

notifications:
  enabled: true
  poll_interval_seconds: 5
  token_flow_limit: 50
  retention_days: 30
  rules:
    watched_account_activity:
      enabled: true
      channels: ["in_app"]
    watched_account_token_alert:
      enabled: true
      channels: ["in_app"]
    hot_quality_token_5m:
      enabled: true
      channels: ["in_app"]
      social_heat_min: 80
      discussion_quality_min: 70
      suppress_chase_risk: true
      cooldown_seconds: 900
    quality_token_5m:
      enabled: true
      channels: ["in_app"]
      social_heat_min: 65
      discussion_quality_min: 80
      suppress_chase_risk: true
      cooldown_seconds: 900
    harness_snapshot_high_score:
      enabled: true
      channels: ["in_app"]
      combined_score_min: 0.8
      cooldown_seconds: 900
  channels: {{}}
"""


def _load_yaml_mapping(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"config.yaml must contain a mapping at {path}")
    return data


def _split_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _default_notification_rule_payloads() -> dict[str, dict[str, Any]]:
    return {
        "watched_account_activity": {
            "enabled": True,
            "channels": ("in_app",),
        },
        "watched_account_token_alert": {
            "enabled": True,
            "channels": ("in_app",),
        },
        "hot_quality_token_5m": {
            "enabled": True,
            "channels": ("in_app",),
            "social_heat_min": 80,
            "discussion_quality_min": 70,
            "suppress_chase_risk": True,
            "cooldown_seconds": 900,
        },
        "quality_token_5m": {
            "enabled": True,
            "channels": ("in_app",),
            "social_heat_min": 65,
            "discussion_quality_min": 80,
            "suppress_chase_risk": True,
            "cooldown_seconds": 900,
        },
        "harness_snapshot_high_score": {
            "enabled": True,
            "channels": ("in_app",),
            "combined_score_min": 0.8,
            "cooldown_seconds": 900,
        },
    }
