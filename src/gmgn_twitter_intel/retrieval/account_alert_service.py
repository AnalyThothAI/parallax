from __future__ import annotations

WINDOW_MS = {
    "5m": 300_000,
    "1h": 3_600_000,
    "4h": 4 * 3_600_000,
    "24h": 86_400_000,
}


class AccountAlertService:
    def __init__(self, signals):
        self.signals = signals

    def account_alerts(
        self,
        *,
        window: str = "24h",
        limit: int = 50,
        handles: set[str] | None = None,
        alert_type: str | None = None,
    ) -> list[dict]:
        return self.signals.account_alerts(
            window_ms=WINDOW_MS[window],
            limit=limit,
            handles=handles,
            alert_type=alert_type,
        )
