from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .runtime_paths import app_home, app_log_path, lancedb_path

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
    replay_limit: int = Field(default=100, validation_alias="REPLAY_LIMIT")
    app_home_override: Path | None = Field(default=None, validation_alias="GMGN_TWITTER_HOME")
    lancedb_path_override: Path | None = Field(default=None, validation_alias="LANCEDB_PATH")
    embedding_dim: int = Field(default=1024, validation_alias="EMBEDDING_DIM")
    sentiment_backend: str = Field(default="none", validation_alias="SENTIMENT_BACKEND")
    llm_model: str | None = Field(default=None, validation_alias="LLM_MODEL")

    upstream_chains: tuple[str, ...] = Field(default=DEFAULT_UPSTREAM_CHAINS, validation_alias="UPSTREAM_CHAINS")
    upstream_channels: tuple[str, ...] = Field(default=DEFAULT_UPSTREAM_CHANNELS, validation_alias="UPSTREAM_CHANNELS")
    upstream_app_version: str = Field(default=DEFAULT_GMGN_APP_VERSION, validation_alias="GMGN_WS_APP_VERSION")
    upstream_proxy: str | None = Field(default=None, validation_alias="GMGN_WS_PROXY")
    upstream_reconnect_delay: float = Field(default=3.0, validation_alias="UPSTREAM_RECONNECT_DELAY")
    upstream_heartbeat_interval: float = Field(default=25.0, validation_alias="UPSTREAM_HEARTBEAT_INTERVAL")

    @property
    def app_home(self) -> Path:
        return app_home(self.app_home_override)

    @property
    def lancedb_path(self) -> Path:
        return self.lancedb_path_override or lancedb_path(self.app_home_override)

    @property
    def log_file(self) -> Path:
        return app_log_path(self.app_home_override)

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

    @field_validator("app_home_override", "lancedb_path_override", mode="before")
    @classmethod
    def parse_optional_path(cls, value: Any) -> Any:
        if value is None:
            return None
        if str(value).strip() == "":
            return None
        return value

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

    @field_validator("sentiment_backend")
    @classmethod
    def validate_sentiment_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"none", "tweetnlp", "cardiff"}:
            raise ValueError("SENTIMENT_BACKEND must be one of: none, tweetnlp, cardiff")
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
