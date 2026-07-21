from __future__ import annotations

from parallax.app.surfaces.api.exceptions import ApiBadRequest

WINDOWS = {"5m", "1h", "4h", "24h"}
SCOPES = {"all", "matched"}
TOKEN_RADAR_VENUES = {"all", "sol", "eth", "base", "bsc", "cex"}
ALERT_TYPES = {"account_token", "token"}
DELIVERY_STATUSES = {"pending", "running", "failed", "dead", "delivered"}


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


def _scope(value: str) -> str:
    if value in SCOPES:
        return value
    raise ApiBadRequest("invalid_scope", field="scope")


def _token_radar_venue(value: str) -> str:
    if value in TOKEN_RADAR_VENUES:
        return value
    raise ApiBadRequest("invalid_venue", field="venue")


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


def _alert_type(value: str | None) -> str | None:
    return value if value in ALERT_TYPES else None


def _delivery_status(value: str | None) -> str | None:
    return value if value in DELIVERY_STATUSES else None
