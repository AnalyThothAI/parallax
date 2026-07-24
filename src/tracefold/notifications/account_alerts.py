"""Read persisted watched-account alert facts for notification/public consumers."""

from __future__ import annotations

from typing import Any

WINDOW_MS = {
    "5m": 300_000,
    "1h": 3_600_000,
    "4h": 4 * 3_600_000,
    "24h": 86_400_000,
}


class AccountAlertService:
    def __init__(self, signals: Any) -> None:
        self.signals = signals

    def account_alerts(
        self,
        *,
        window: str,
        limit: int,
        now_ms: int,
        handles: set[str] | None = None,
        alert_type: str | None = None,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = self.signals.account_alerts(
            window_ms=WINDOW_MS[window],
            now_ms=int(now_ms),
            limit=limit,
            handles=handles,
            alert_type=alert_type,
        )
        return result
