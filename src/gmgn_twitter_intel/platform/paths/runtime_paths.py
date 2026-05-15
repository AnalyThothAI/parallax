from __future__ import annotations

from pathlib import Path

APP_NAME = "gmgn-twitter-intel"
CONFIG_FILE_NAME = "config.yaml"
WORKERS_CONFIG_FILE_NAME = "workers.yaml"


def app_home(path_override: str | Path | None = None) -> Path:
    if path_override:
        return Path(path_override).expanduser()
    return Path.home() / ".gmgn-twitter-intel"


def app_log_path(app_home_override: str | Path | None = None) -> Path:
    return app_home(app_home_override) / "logs" / "gmgn-twitter-intel.log"


def config_path(app_home_override: str | Path | None = None) -> Path:
    return app_home(app_home_override) / CONFIG_FILE_NAME


def workers_config_path(app_home_override: str | Path | None = None) -> Path:
    return app_home(app_home_override) / WORKERS_CONFIG_FILE_NAME
