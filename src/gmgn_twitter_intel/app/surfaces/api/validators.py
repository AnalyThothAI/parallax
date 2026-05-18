from __future__ import annotations

from gmgn_twitter_intel.app.surfaces.api.exceptions import ApiBadRequest

WINDOWS = {"5m", "1h", "4h", "24h"}
SCOPES = {"all", "matched"}
ALERT_TYPES = {"account_token", "token"}
JOB_STATUSES = {"pending", "running", "failed", "dead", "done"}
DELIVERY_STATUSES = {"pending", "running", "failed", "dead", "delivered"}
HORIZONS = {"6h", "24h"}
PUBLIC_SIGNAL_PULSE_STATUSES = {"trade_candidate", "token_watch", "risk_rejected_high_info"}
WATCHLIST_TIMELINE_SCOPES = {"signal", "all"}


def _limit(value: int, *, maximum: int = 1000) -> int:
    return max(0, min(int(value), maximum))


def _handle_set(raw: str) -> set[str]:
    return {item.strip().lstrip("@").lower() for item in raw.split(",") if item.strip()}


def _csv_set(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


def _scope(value: str) -> str:
    return value if value in SCOPES else "matched"


def _watchlist_timeline_scope(value: str) -> str:
    if value in WATCHLIST_TIMELINE_SCOPES:
        return value
    raise ApiBadRequest("invalid_scope", field="scope")


def _window(value: str) -> str:
    if value in WINDOWS:
        return value
    raise ApiBadRequest("invalid_window", field="window")


def _post_range(value: str) -> str:
    if value in {"current_window", "since_ignition", "all_history"}:
        return value
    raise ApiBadRequest("invalid_range", field="range")


def _target_type(value: str) -> str | None:
    return value if value in {"Asset", "CexToken"} else None


def _horizon(value: str) -> str:
    return value if value in HORIZONS else "6h"


def _alert_type(value: str | None) -> str | None:
    return value if value in ALERT_TYPES else None


def _signal_pulse_public_status(value: str) -> str | None:
    if not value:
        return None
    if value in PUBLIC_SIGNAL_PULSE_STATUSES:
        return value
    raise ApiBadRequest("invalid_status", field="status")


def _job_status(value: str | None) -> str | None:
    return value if value in JOB_STATUSES else None


def _delivery_status(value: str | None) -> str | None:
    return value if value in DELIVERY_STATUSES else None
