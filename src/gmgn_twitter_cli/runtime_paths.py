from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "gmgn-twitter-cli"


def runtime_state_dir() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home).expanduser() / APP_NAME
    return Path.home() / ".local" / "state" / APP_NAME


def event_db_path() -> Path:
    return runtime_state_dir() / "events.sqlite3"


def app_log_path() -> Path:
    return runtime_state_dir() / "gmgn-twitter-cli.log"


def launchd_log_dir() -> Path:
    return runtime_state_dir() / "launchd"
