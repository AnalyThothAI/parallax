from __future__ import annotations

import secrets
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

from gmgn_twitter_intel.platform.paths.runtime_paths import app_home, app_log_path, config_path, workers_config_path

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
    "signal_pulse_candidate",
)


class ApiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "0.0.0.0"  # noqa: S104 -- configurable API bind address; defaults to all interfaces intentionally
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
    timeout_seconds: float = 120.0
    trace_enabled: bool = True
    trace_api_key: str | None = None
    trace_include_sensitive_data: bool = False
    pulse_agent_model: str | None = None
    watchlist_handle_summary_model: str | None = None

    @field_validator("provider", mode="before")
    @classmethod
    def parse_provider(cls, value: Any) -> str:
        normalized = str(value or "openai").strip().lower()
        if normalized != "openai":
            raise ValueError("llm.provider must be 'openai'")
        return normalized

    @field_validator(
        "api_key",
        "model",
        "trace_api_key",
        "pulse_agent_model",
        "watchlist_handle_summary_model",
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
    cooldown_seconds: int = 0
    window: str | None = None
    scopes: tuple[str, ...] | None = None
    statuses: tuple[str, ...] | None = None

    @field_validator("channels", mode="before")
    @classmethod
    def parse_channels(cls, value: Any) -> tuple[str, ...]:
        parsed = tuple(_split_values(value))
        return parsed or ("in_app",)

    @field_validator("scopes", "statuses", mode="before")
    @classmethod
    def parse_optional_tuple(cls, value: Any) -> tuple[str, ...] | None:
        parsed = tuple(_split_values(value))
        return parsed or None

    @field_validator("window", mode="before")
    @classmethod
    def parse_optional_window(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


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
            if key == "signal_pulse_candidate":
                forbidden = {"social_heat_min", "discussion_quality_min", "opportunity_min", "combined_score_min"}
                present = sorted(forbidden.intersection(payload))
                if present:
                    joined = ", ".join(present)
                    raise ValueError(f"notifications.rules.{key} does not accept token-flow thresholds: {joined}")
            merged[key] = {**merged[key], **dict(payload)}
        return merged


class OkxProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cex_base_url: str = "https://www.okx.com"
    cex_sync_enabled: bool = True
    cex_inst_types: tuple[str, ...] = ("SPOT", "SWAP")
    dex_base_url: str = "https://web3.okx.com"
    dex_chain_indexes: tuple[str, ...] = ("501", "1", "56", "8453", "607")
    dex_ws_url: str = "wss://wsdex.okx.com/ws/v6/dex"
    dex_api_key: str | None = None
    dex_secret_key: str | None = None
    dex_passphrase: str | None = None
    timeout_seconds: float = 15.0

    @field_validator("cex_base_url", "dex_base_url", mode="before")
    @classmethod
    def parse_base_url(cls, value: Any) -> str:
        normalized = str(value or "").strip().rstrip("/")
        return normalized

    @field_validator("cex_inst_types", "dex_chain_indexes", mode="before")
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


class MarketlaneProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    quote_timeout_seconds: float = Field(default=5.0, gt=0)
    quote_cache_ttl_seconds: float = Field(default=30.0, ge=0)


class ProvidersConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    okx: OkxProviderConfig = Field(default_factory=OkxProviderConfig)
    marketlane: MarketlaneProviderConfig = Field(default_factory=MarketlaneProviderConfig)


class BackoffPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["exponential"] = "exponential"
    base_ms: int = Field(default=1000, ge=0)
    max_ms: int = Field(default=60_000, ge=0)


class PerWorkerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    interval_seconds: float = Field(default=5.0, ge=0)
    timeout_seconds: float = Field(default=120.0, ge=0)
    concurrency: int = Field(default=1, ge=1)
    batch_size: int = Field(default=100, ge=1)
    max_attempts: int = Field(default=3, ge=1)
    lease_ms: int = Field(default=120_000, ge=1)
    restart_locally: bool = False
    statement_timeout_seconds: float = Field(default=30.0, ge=0)
    backoff: BackoffPolicy = Field(default_factory=BackoffPolicy)


class WorkerDefaults(PerWorkerSettings):
    pass


class CollectorWorkerSettings(PerWorkerSettings):
    mode: Literal["continuous"] = "continuous"
    interval_seconds: float = Field(default=3.0, ge=0)
    timeout_seconds: float = Field(default=0.0, ge=0)
    snapshot_timeout_seconds: float = Field(default=0.5, ge=0)
    watchdog_interval_seconds: float = Field(default=30.0, ge=0)
    stale_timeout_seconds: float = Field(default=180.0, ge=0)


class AnchorPriceWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=5.0, ge=0)
    batch_size: int = Field(default=100, ge=1)
    statement_timeout_seconds: float = Field(default=120.0, ge=0)


class LivePriceGatewayWorkerSettings(PerWorkerSettings):
    mode: Literal["continuous"] = "continuous"
    interval_seconds: float = Field(default=30.0, ge=0)
    batch_size: int = Field(default=100, ge=1)
    subscription_limit: int = Field(default=100, ge=1)
    hot_target_ttl_seconds: float = Field(default=300.0, ge=0)
    reconnect_delay_seconds: float = Field(default=3.0, ge=0)
    cex_poll_interval_seconds: float = Field(default=30.0, ge=0)
    live_observation_heartbeat_seconds: float = Field(default=60.0, gt=0)
    live_observation_min_price_change_pct: float = Field(default=0.005, ge=0)
    live_observation_min_write_interval_seconds: float = Field(default=5.0, ge=0)


class ResolutionRefreshWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=30.0, ge=0)
    batch_size: int = Field(default=50, ge=1)
    reprocess_limit: int = Field(default=500, ge=1)
    chain_ids: tuple[str, ...] = ("solana", "eip155:1", "eip155:56", "eip155:8453", "ton")

    @field_validator("chain_ids", mode="before")
    @classmethod
    def parse_chain_ids(cls, value: Any) -> tuple[str, ...]:
        return tuple(_split_values(value))


class AssetProfileRefreshWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=60.0, ge=0)
    batch_size: int = Field(default=50, ge=1)
    statement_timeout_seconds: float = Field(default=120.0, ge=0)


class TokenCaptureTierWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=10.0, ge=0)
    batch_size: int = Field(default=100, ge=1)
    ws_limit: int = Field(default=50, ge=0)
    poll_limit: int = Field(default=200, ge=0)
    statement_timeout_seconds: float = Field(default=120.0, ge=0)
    advisory_lock_key: int = 2026051503


class TokenRadarProjectionWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=10.0, ge=0)
    batch_size: int = Field(default=100, ge=1)
    statement_timeout_seconds: float = Field(default=120.0, ge=0)
    advisory_lock_key: int = 2026051501
    wakes_on: tuple[str, ...] = ("market_observation_written", "resolution_updated")
    windows: tuple[str, ...] = ("5m", "1h", "4h", "24h")
    scopes: tuple[str, ...] = ("all", "matched")
    hot_windows: tuple[str, ...] = ("5m",)

    @field_validator("wakes_on", "windows", "scopes", "hot_windows", mode="before")
    @classmethod
    def parse_tuple(cls, value: Any) -> tuple[str, ...]:
        return tuple(_split_values(value))


class PulseCandidateTriggerThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_rank_score: int = 45


class PulseCandidateGateThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trade_candidate_min: int = 72
    token_watch_min: int = 45
    high_info_rejection_min: int = 30
    high_conviction_min: int = 78


class PulseCandidateWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=60.0, ge=0)
    timeout_seconds: float = Field(default=0.0, ge=0)
    batch_size: int = Field(default=10, ge=1)
    max_attempts: int = Field(default=3, ge=1)
    advisory_lock_key: int = 2026051502
    wakes_on: tuple[str, ...] = ("token_radar_updated",)
    windows: tuple[str, ...] = ("5m", "1h", "4h", "24h")
    scopes: tuple[str, ...] = ("all", "matched")
    trigger_thresholds: PulseCandidateTriggerThresholds = Field(default_factory=PulseCandidateTriggerThresholds)
    gate_thresholds: PulseCandidateGateThresholds = Field(default_factory=PulseCandidateGateThresholds)

    @field_validator("wakes_on", "windows", "scopes", mode="before")
    @classmethod
    def parse_tuple(cls, value: Any) -> tuple[str, ...]:
        return tuple(_split_values(value))


class EnrichmentWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=2.0, ge=0)
    concurrency: int = Field(default=4, ge=1)
    batch_size: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=3, ge=1)


class HandleSummaryWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=2.0, ge=0)
    concurrency: int = Field(default=1, ge=1)
    batch_size: int = Field(default=1, ge=1)
    lease_ms: int = Field(default=120_000, ge=1)
    max_attempts: int = Field(default=3, ge=1)
    reconcile_limit: int = Field(default=100, ge=1)
    signal_threshold: int = Field(default=10, ge=1)
    time_threshold_ms: int = Field(default=1_800_000, ge=1)
    min_interval_ms: int = Field(default=300_000, ge=1)
    input_limit: int = Field(default=80, ge=1)
    window_days: int = Field(default=7, ge=1)


class HarnessOpsWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=60.0, ge=0)
    batch_size: int = Field(default=200, ge=1)
    horizons: tuple[str, ...] = ("6h", "24h")

    @field_validator("horizons", mode="before")
    @classmethod
    def parse_horizons(cls, value: Any) -> tuple[str, ...]:
        return tuple(_split_values(value))


class NotificationRuleWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=5.0, ge=0)
    batch_size: int = Field(default=50, ge=1)


class NotificationDeliveryWorkerSettings(PerWorkerSettings):
    interval_seconds: float = Field(default=5.0, ge=0)
    batch_size: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=5, ge=1)


class WorkersSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defaults: WorkerDefaults = Field(default_factory=WorkerDefaults)
    collector: CollectorWorkerSettings = Field(default_factory=CollectorWorkerSettings)
    anchor_price: AnchorPriceWorkerSettings = Field(default_factory=AnchorPriceWorkerSettings)
    live_price_gateway: LivePriceGatewayWorkerSettings = Field(default_factory=LivePriceGatewayWorkerSettings)
    resolution_refresh: ResolutionRefreshWorkerSettings = Field(default_factory=ResolutionRefreshWorkerSettings)
    asset_profile_refresh: AssetProfileRefreshWorkerSettings = Field(default_factory=AssetProfileRefreshWorkerSettings)
    token_capture_tier: TokenCaptureTierWorkerSettings = Field(default_factory=TokenCaptureTierWorkerSettings)
    token_radar_projection: TokenRadarProjectionWorkerSettings = Field(
        default_factory=TokenRadarProjectionWorkerSettings
    )
    pulse_candidate: PulseCandidateWorkerSettings = Field(default_factory=PulseCandidateWorkerSettings)
    enrichment: EnrichmentWorkerSettings = Field(default_factory=EnrichmentWorkerSettings)
    handle_summary: HandleSummaryWorkerSettings = Field(default_factory=HandleSummaryWorkerSettings)
    harness_ops: HarnessOpsWorkerSettings = Field(default_factory=HarnessOpsWorkerSettings)
    notification_rule: NotificationRuleWorkerSettings = Field(default_factory=NotificationRuleWorkerSettings)
    notification_delivery: NotificationDeliveryWorkerSettings = Field(
        default_factory=NotificationDeliveryWorkerSettings
    )


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
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    workers: WorkersSettings = Field(default_factory=WorkersSettings)

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
    def pulse_agent_model(self) -> str | None:
        return self.llm.pulse_agent_model or self.llm_model

    @property
    def pulse_agent_configured(self) -> bool:
        return bool(self.llm_api_key and self.pulse_agent_model)

    @property
    def watchlist_handle_summary_model(self) -> str | None:
        return self.llm.watchlist_handle_summary_model or self.llm_model

    @property
    def watchlist_handle_summary_configured(self) -> bool:
        return bool(self.llm_api_key and self.watchlist_handle_summary_model)

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
        if self.llm_trace_api_key:
            return True
        normalized_base_url = self.llm_base_url.rstrip("/")
        is_openai_base_url = normalized_base_url == "https://api.openai.com" or normalized_base_url.startswith(
            "https://api.openai.com/"
        )
        return is_openai_base_url and bool(self.llm_api_key)

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
    def okx_cex_sync_enabled(self) -> bool:
        return self.providers.okx.cex_sync_enabled

    @property
    def okx_cex_inst_types(self) -> tuple[str, ...]:
        return self.providers.okx.cex_inst_types or ("SPOT", "SWAP")

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
    def marketlane_enabled(self) -> bool:
        return bool(self.providers.marketlane.enabled)

    @property
    def marketlane_quote_timeout_seconds(self) -> float:
        return self.providers.marketlane.quote_timeout_seconds

    @property
    def marketlane_quote_cache_ttl_seconds(self) -> float:
        return self.providers.marketlane.quote_cache_ttl_seconds

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
        raise FileNotFoundError(f"config.yaml not found at {path}; run `gmgn-twitter-intel init` first")
    workers_path = workers_config_path(path.parent)
    if not workers_path.exists():
        raise FileNotFoundError(f"workers.yaml not found at {workers_path}; run `gmgn-twitter-intel init` first")
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
  timeout_seconds: 120
  trace_enabled: true
  trace_api_key:
  trace_include_sensitive_data: false
  pulse_agent_model:
  watchlist_handle_summary_model:

gmgn:
  api_key:
  openapi_base_url: "https://openapi.gmgn.ai"
  timeout_seconds: 5
  token_info_cache_ttl_seconds: 60

providers:
  okx:
    cex_base_url: "https://www.okx.com"
    cex_sync_enabled: true
    cex_inst_types: ["SPOT", "SWAP"]
    dex_base_url: "https://web3.okx.com"
    dex_chain_indexes: ["501", "1", "56", "8453", "607"]
    dex_ws_url: "wss://wsdex.okx.com/ws/v6/dex"
    dex_api_key:
    dex_secret_key:
    dex_passphrase:
    timeout_seconds: 15

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
      cooldown_seconds: 900
    quality_token_5m:
      enabled: true
      channels: ["in_app"]
      social_heat_min: 65
      discussion_quality_min: 80
      cooldown_seconds: 900
    harness_snapshot_high_score:
      enabled: true
      channels: ["in_app"]
      combined_score_min: 0.8
      cooldown_seconds: 900
    signal_pulse_candidate:
      enabled: true
      channels: ["in_app"]
      window: "1h"
      scopes: ["all", "matched"]
      statuses: ["trade_candidate", "token_watch", "risk_rejected_high_info"]
      cooldown_seconds: 0
  channels: {{}}
"""


def default_workers_yaml() -> str:
    return """# GMGN Twitter Intel worker runtime
defaults:
  enabled: true
  interval_seconds: 5.0
  timeout_seconds: 120.0
  concurrency: 1
  batch_size: 100
  max_attempts: 3
  lease_ms: 120000
  restart_locally: false
  statement_timeout_seconds: 30.0
  backoff:
    kind: "exponential"
    base_ms: 1000
    max_ms: 60000
collector:
  enabled: true
  mode: "continuous"
  interval_seconds: 3.0
  timeout_seconds: 0.0
  snapshot_timeout_seconds: 0.5
  watchdog_interval_seconds: 30.0
  stale_timeout_seconds: 180.0
anchor_price:
  enabled: true
  interval_seconds: 5.0
  batch_size: 100
  statement_timeout_seconds: 120.0
live_price_gateway:
  enabled: true
  mode: "continuous"
  interval_seconds: 30.0
  batch_size: 100
  subscription_limit: 100
  hot_target_ttl_seconds: 300.0
  reconnect_delay_seconds: 3.0
  cex_poll_interval_seconds: 30.0
  live_observation_heartbeat_seconds: 60.0
  live_observation_min_price_change_pct: 0.005
  live_observation_min_write_interval_seconds: 5.0
resolution_refresh:
  enabled: true
  interval_seconds: 30.0
  batch_size: 50
  reprocess_limit: 500
  chain_ids: ["solana", "eip155:1", "eip155:56", "eip155:8453", "ton"]
asset_profile_refresh:
  enabled: true
  interval_seconds: 60.0
  batch_size: 50
  statement_timeout_seconds: 120.0
token_capture_tier:
  enabled: true
  interval_seconds: 10.0
  batch_size: 100
  ws_limit: 50
  poll_limit: 200
  statement_timeout_seconds: 120.0
  advisory_lock_key: 2026051503
token_radar_projection:
  enabled: true
  interval_seconds: 10.0
  batch_size: 100
  statement_timeout_seconds: 120.0
  advisory_lock_key: 2026051501
  wakes_on: ["market_observation_written", "resolution_updated"]
  windows: ["5m", "1h", "4h", "24h"]
  scopes: ["all", "matched"]
  hot_windows: ["5m"]
pulse_candidate:
  enabled: true
  interval_seconds: 60.0
  timeout_seconds: 0.0
  batch_size: 10
  max_attempts: 3
  advisory_lock_key: 2026051502
  wakes_on: ["token_radar_updated"]
  windows: ["5m", "1h", "4h", "24h"]
  scopes: ["all", "matched"]
  trigger_thresholds:
    min_rank_score: 45
  gate_thresholds:
    trade_candidate_min: 72
    token_watch_min: 45
    high_info_rejection_min: 30
    high_conviction_min: 78
enrichment:
  enabled: true
  interval_seconds: 2.0
  concurrency: 4
  batch_size: 1
  max_attempts: 3
handle_summary:
  enabled: true
  interval_seconds: 2.0
  concurrency: 1
  batch_size: 1
  lease_ms: 120000
  max_attempts: 3
  reconcile_limit: 100
  signal_threshold: 10
  time_threshold_ms: 1800000
  min_interval_ms: 300000
  input_limit: 80
  window_days: 7
harness_ops:
  enabled: true
  interval_seconds: 60.0
  batch_size: 200
  horizons: ["6h", "24h"]
notification_rule:
  enabled: true
  interval_seconds: 5.0
  batch_size: 50
notification_delivery:
  enabled: true
  interval_seconds: 5.0
  batch_size: 1
  max_attempts: 5
"""


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


def _clamp_int(value: Any, *, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = low
    return max(low, min(high, parsed))


def _clamp_float(value: Any, *, low: float, high: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = low
    return max(low, min(high, parsed))


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
        "hot_quality_token_5m": {
            "enabled": True,
            "channels": ("in_app",),
            "social_heat_min": 80,
            "discussion_quality_min": 70,
            "cooldown_seconds": 900,
        },
        "quality_token_5m": {
            "enabled": True,
            "channels": ("in_app",),
            "social_heat_min": 65,
            "discussion_quality_min": 80,
            "cooldown_seconds": 900,
        },
        "harness_snapshot_high_score": {
            "enabled": True,
            "channels": ("in_app",),
            "combined_score_min": 0.8,
            "cooldown_seconds": 900,
        },
        "signal_pulse_candidate": {
            "enabled": True,
            "channels": ("in_app",),
            "window": "1h",
            "scopes": ("all", "matched"),
            "statuses": ("trade_candidate", "token_watch", "risk_rejected_high_info"),
            "cooldown_seconds": 0,
        },
    }
