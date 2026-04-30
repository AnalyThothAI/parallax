from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "gmgn-twitter-intel"
APP_HOME_ENV = "GMGN_TWITTER_HOME"


def app_home(path_override: str | Path | None = None) -> Path:
    if path_override:
        return Path(path_override).expanduser()
    configured = os.environ.get(APP_HOME_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".gmgn-twitter-intel"


def lancedb_path(app_home_override: str | Path | None = None) -> Path:
    return app_home(app_home_override) / "twitter_intel.lancedb"


def app_log_path(app_home_override: str | Path | None = None) -> Path:
    return app_home(app_home_override) / "logs" / "gmgn-twitter-intel.log"
