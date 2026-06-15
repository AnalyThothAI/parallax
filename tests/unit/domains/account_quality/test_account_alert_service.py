from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.account_quality.read_models.account_alert_service import AccountAlertService


def test_account_alert_service_requires_explicit_window_and_limit_before_repository_call() -> None:
    signals = FakeAccountAlertSignals()
    service = AccountAlertService(signals)

    with pytest.raises(TypeError, match="window"):
        service.account_alerts(limit=50, now_ms=1_700_000_000_000)
    with pytest.raises(TypeError, match="limit"):
        service.account_alerts(window="1h", now_ms=1_700_000_000_000)
    with pytest.raises(TypeError, match="now_ms"):
        service.account_alerts(window="1h", limit=50)

    assert signals.calls == []


def test_account_alert_service_passes_explicit_clock_to_repository() -> None:
    signals = FakeAccountAlertSignals()

    AccountAlertService(signals).account_alerts(window="1h", limit=50, now_ms=1_700_000_123_000)

    assert signals.calls == [
        {
            "window_ms": 3_600_000,
            "now_ms": 1_700_000_123_000,
            "limit": 50,
            "handles": None,
            "alert_type": None,
        }
    ]


class FakeAccountAlertSignals:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def account_alerts(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(dict(kwargs))
        return []
