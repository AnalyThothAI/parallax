from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UPSTREAM_CHAINS = ("sol", "eth", "base", "bsc")
DEFAULT_UPSTREAM_CHANNELS = ("twitter_monitor_basic", "twitter_monitor_token")
DEFAULT_GMGN_APP_VERSION = "20260429-12894-ccec416"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        enable_decoding=False,
        extra="ignore",
        populate_by_name=True,
    )

    handles: tuple[str, ...] = Field(default_factory=tuple, validation_alias="MONITOR_HANDLES")
    ws_token: str = Field(validation_alias="WS_TOKEN")
    api_host: str = Field(default="0.0.0.0", validation_alias="API_HOST")
    api_port: int = Field(default=8765, validation_alias="API_PORT")
    ws_heartbeat_interval: int = Field(default=30, validation_alias="WS_HEARTBEAT_INTERVAL")
    event_db_path: Path = Field(default=PROJECT_ROOT / "data" / "events.sqlite3", validation_alias="EVENT_DB_PATH")
    replay_limit: int = Field(default=100, validation_alias="REPLAY_LIMIT")
    observed_retention_days: int = Field(default=7, validation_alias="OBSERVED_RETENTION_DAYS")
    matched_retention_days: int = Field(default=180, validation_alias="MATCHED_RETENTION_DAYS")
    log_file: Path = Field(default=PROJECT_ROOT / "logs" / "gmgn-twitter-cli.log", validation_alias="LOG_FILE")

    upstream_chains: tuple[str, ...] = Field(default=DEFAULT_UPSTREAM_CHAINS, validation_alias="UPSTREAM_CHAINS")
    upstream_channels: tuple[str, ...] = Field(default=DEFAULT_UPSTREAM_CHANNELS, validation_alias="UPSTREAM_CHANNELS")
    upstream_app_version: str = Field(default=DEFAULT_GMGN_APP_VERSION, validation_alias="GMGN_WS_APP_VERSION")
    upstream_proxy: str | None = Field(default=None, validation_alias="GMGN_WS_PROXY")
    upstream_reconnect_delay: float = Field(default=3.0, validation_alias="UPSTREAM_RECONNECT_DELAY")
    upstream_heartbeat_interval: float = Field(default=25.0, validation_alias="UPSTREAM_HEARTBEAT_INTERVAL")

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

    @field_validator("upstream_chains", "upstream_channels", mode="before")
    @classmethod
    def parse_tuple(cls, value: Any) -> tuple[str, ...]:
        values = tuple(_split_values(value))
        return values

    @field_validator("ws_token")
    @classmethod
    def require_ws_token(cls, value: str) -> str:
        token = value.strip()
        if not token:
            raise ValueError("WS_TOKEN is required")
        return token

    @field_validator("upstream_proxy", mode="before")
    @classmethod
    def parse_optional_proxy(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if normalized.lower() in {"", "none", "false", "off", "direct"}:
            return None
        return normalized


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    if env is None:
        return Settings()
    return Settings(_env_file=None, **dict(env))


def _split_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]
