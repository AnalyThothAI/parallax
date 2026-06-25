from __future__ import annotations

from parallax.app.surfaces.api.exceptions import ApiBadRequest
from parallax.domains.pulse_lab.services.pulse_horizon_policy import SIGNAL_PULSE_WINDOW_SET

WINDOWS = {"5m", "1h", "4h", "24h"}
SIGNAL_PULSE_WINDOWS = set(SIGNAL_PULSE_WINDOW_SET)
SCOPES = {"all", "matched"}
TOKEN_RADAR_VENUES = {"all", "sol", "eth", "base", "bsc", "cex"}
ALERT_TYPES = {"account_token", "token"}
JOB_STATUSES = {"pending", "running", "failed", "dead", "done"}
DELIVERY_STATUSES = {"pending", "running", "failed", "dead", "delivered"}
HORIZONS = {"6h", "24h"}
PUBLIC_SIGNAL_PULSE_STATUSES = {"trade_candidate", "token_watch", "risk_rejected_high_info"}
SIGNAL_PULSE_VISIBILITIES = {"public", "hidden"}
WATCHLIST_TIMELINE_SCOPES = {"signal", "all"}


def _limit(value: int, *, maximum: int = 1000, field: str = "limit") -> int:
    parsed = _api_limit_int(value, field=field)
    if parsed < 0:
        raise ApiBadRequest("invalid_limit", field=field)
    return min(parsed, maximum)


def _positive_limit(value: int, *, maximum: int = 1000, field: str = "limit") -> int:
    parsed = _api_limit_int(value, field=field)
    if parsed <= 0:
        raise ApiBadRequest("invalid_limit", field=field)
    return min(parsed, maximum)


def _api_limit_int(value: int, *, field: str) -> int:
    if isinstance(value, bool):
        raise ApiBadRequest("invalid_limit", field=field)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ApiBadRequest("invalid_limit", field=field) from exc


def _handle_set(raw: str) -> set[str]:
    return {item.strip().lstrip("@").lower() for item in raw.split(",") if item.strip()}


def _csv_set(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


def _scope(value: str) -> str:
    if value in SCOPES:
        return value
    raise ApiBadRequest("invalid_scope", field="scope")


def _token_radar_venue(value: str) -> str:
    if value in TOKEN_RADAR_VENUES:
        return value
    raise ApiBadRequest("invalid_venue", field="venue")


def _watchlist_timeline_scope(value: str) -> str:
    if value in WATCHLIST_TIMELINE_SCOPES:
        return value
    raise ApiBadRequest("invalid_scope", field="scope")


def _window(value: str) -> str:
    if value in WINDOWS:
        return value
    raise ApiBadRequest("invalid_window", field="window")


def _signal_pulse_window(value: str) -> str:
    if value in SIGNAL_PULSE_WINDOWS:
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


def _signal_pulse_visibility(value: str) -> str:
    if not value:
        return "public"
    if value in SIGNAL_PULSE_VISIBILITIES:
        return value
    raise ApiBadRequest("invalid_visibility", field="visibility")


def _job_status(value: str | None) -> str | None:
    return value if value in JOB_STATUSES else None


def _delivery_status(value: str | None) -> str | None:
    return value if value in DELIVERY_STATUSES else None
