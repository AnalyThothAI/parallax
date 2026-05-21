from __future__ import annotations

from pathlib import Path
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_registry import CANONICAL_WORKER_NAMES
from gmgn_twitter_intel.platform.config.settings import Settings
from tests.postgres_test_utils import postgres_settings_storage

WS_TOKEN = "hot-path-token"
FIXED_NOW_MS = 1_777_729_877_581
EVENT_ID = "gmgn:twitter_monitor_token:fixture-internal-001"
AUTHOR_HANDLE = "fixture_signal"
SYMBOL = "MIRROR"
CHAIN_ID = "eip155:56"
ADDRESS = "0x8f32420f2e3728c49399b00dd0a796602d984444"
MARKET_TARGET_TYPE = "chain_token"
MARKET_TARGET_ID = f"{CHAIN_ID}:{ADDRESS}"


def backend_hot_path_settings(tmp_path: Path) -> Settings:
    workers = _disabled_workers()
    settings = Settings(
        ws_token=WS_TOKEN,
        handles=(AUTHOR_HANDLE,),
        storage=postgres_settings_storage(),
        providers={
            "okx": {
                "dex_base_url": "",
                "dex_ws_url": "",
            },
            "binance": {"enabled": False},
            "marketlane": {"enabled": False},
        },
        notifications={
            "enabled": True,
            "token_flow_limit": 50,
            "rules": {
                "watched_account_activity": {"enabled": False},
                "watched_account_token_alert": {"enabled": False},
                "hot_quality_token_5m": {"enabled": False},
                "quality_token_5m": {"enabled": False},
                "signal_pulse_candidate": {
                    "enabled": True,
                    "channels": ("in_app", "log"),
                    "window": "1h",
                    "scopes": ("all",),
                    "statuses": ("trade_candidate",),
                    "cooldown_seconds": 0,
                },
            },
            "channels": {
                "log": {
                    "enabled": True,
                    "provider": "log",
                    "min_severity": "info",
                }
            },
        },
        workers=workers,
    )
    settings.set_config_dir(tmp_path / "gmgn-hot-path-home")
    return settings


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {WS_TOKEN}"}


def _disabled_workers() -> dict[str, dict[str, Any]]:
    workers = {name: {"enabled": False} for name in CANONICAL_WORKER_NAMES}
    workers.update(
        {
            "event_anchor_backfill": {
                "enabled": False,
                "batch_size": 10,
                "concurrency": 2,
                "min_age_ms": 0,
                "active_window_ms": 300_000,
                "max_anchor_lag_ms": 60_000,
            },
            "token_radar_projection": {
                "enabled": False,
                "batch_size": 20,
                "windows": ("1h",),
                "scopes": ("all",),
                "hot_windows": ("1h",),
                "cold_interval_seconds": 0,
            },
            "pulse_candidate": {
                "enabled": False,
                "batch_size": 10,
                "windows": ("1h",),
                "scopes": ("all",),
                "trigger_thresholds": {"min_rank_score": 0},
                "gate_thresholds": {
                    "trade_candidate_min": 0,
                    "token_watch_min": 0,
                    "high_info_rejection_min": 0,
                    "high_conviction_min": 0,
                },
            },
            "notification_rule": {
                "enabled": False,
                "batch_size": 10,
            },
            "notification_delivery": {
                "enabled": False,
                "batch_size": 10,
            },
        }
    )
    return workers
